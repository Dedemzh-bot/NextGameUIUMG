"""Deterministic image evidence for NextGame art refinement.

These helpers make no model calls and do not authorize visual acceptance. Resource
IDs identify bytes, not filenames. Candidate scores are appearance heuristics,
not probabilities. Matching searches local regions at a finite set of scales;
it cannot resolve occlusion, materials, nine-slicing, or semantic intent.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageOps


VERSION = 1
ALGORITHM = "art-images/1"
SUPPORTED = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp", ".tif", ".tiff"}
SCALES = (0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0, 1.125, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write(path: Path, data: bytes) -> None:
    """Atomic replacement; no write when the existing bytes already agree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _binding(path: Path, data: bytes | None = None) -> dict:
    path = Path(path).resolve()
    return {"path": str(path), "sha256": _hash(path.read_bytes() if data is None else data)}


def _load(path: Path) -> tuple[Image.Image, bytes]:
    data = Path(path).read_bytes()
    with Image.open(io.BytesIO(data)) as original:
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError(f"Only single-frame images are supported: {path}")
        # Respect orientation metadata without modifying the source bytes.
        result = ImageOps.exif_transpose(original).convert("RGBA")
        result.load()
    return result, data


def _bounds(image: Image.Image) -> list[int]:
    bounds = image.getchannel("A").getbbox()
    return [0, 0, 0, 0] if bounds is None else [bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1]]


def _rect(value: Any, size: tuple[int, int], name: str = "region") -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{name} must contain x, y, width, height")
    if any(isinstance(x, bool) or not isinstance(x, (int, np.integer)) for x in value):
        raise ValueError(f"{name} must contain finite integers")
    x, y, width, height = map(int, value)
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > size[0] or y + height > size[1]:
        raise ValueError(f"{name} is outside image dimensions {size}")
    return [x, y, width, height]


def _crop(image: Image.Image, bounds: list[int]) -> Image.Image:
    x, y, width, height = bounds
    return image.crop((x, y, x + width, y + height))


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def index_resources(resource_dir: Path, output_dir: Path, cache_dir: Path | None = None) -> dict:
    """Index single-frame raster resources, deduplicating identical source bytes.

    Every run hashes source content. Cached metadata binds the source hash and
    thumbnail hash; missing/corrupt thumbnail outputs are regenerated. Duplicate
    paths remain explicit in ``duplicates`` and are not repeated in resources.
    """
    resource_dir, output_dir = Path(resource_dir).resolve(), Path(output_dir).resolve()
    cache_dir = Path(cache_dir).resolve() if cache_dir is not None else output_dir / ".cache"
    if not resource_dir.is_dir():
        raise ValueError("resource_dir must be an existing directory")
    if _inside(resource_dir, output_dir) or _inside(resource_dir, cache_dir):
        raise ValueError("The source directory must not be inside an output or cache directory")
    resources, duplicates, unsupported = [], [], []
    known: dict[str, dict] = {}
    cache_hits = 0
    for raw_path in sorted(resource_dir.rglob("*"), key=lambda p: p.as_posix().casefold()):
        path = raw_path.resolve()
        if _inside(path, output_dir) or _inside(path, cache_dir) or not raw_path.is_file():
            continue
        if not _inside(path, resource_dir):
            unsupported.append({"path": str(raw_path.absolute()), "reason": "symlink-outside-source"})
            continue
        if path.suffix.lower() not in SUPPORTED:
            unsupported.append({"path": str(path), "reason": "unsupported-extension"})
            continue
        data = path.read_bytes()
        sha = _hash(data)
        if sha in known:
            duplicates.append({"resourceId": known[sha]["id"], "path": str(path), "duplicateOf": known[sha]["path"], "sha256": sha})
            continue
        cached_meta, cached_png = cache_dir / (sha + ".json"), cache_dir / (sha + ".png")
        metadata = None
        thumbnail_data = None
        try:
            possible = json.loads(cached_meta.read_text(encoding="utf-8"))
            thumbnail_data = cached_png.read_bytes()
            if (isinstance(possible, dict) and possible.get("algorithm") == ALGORITHM and possible.get("sha256") == sha
                    and possible.get("thumbnailSha256") == _hash(thumbnail_data)
                    and possible.get("metadataSha256") == _hash(_json_bytes({k: v for k, v in possible.items() if k != "metadataSha256"}))):
                width, height = possible["width"], possible["height"]
                if isinstance(width, int) and not isinstance(width, bool) and isinstance(height, int) and not isinstance(height, bool) and width > 0 and height > 0:
                    alpha = possible["alphaBounds"]
                    if alpha != [0, 0, 0, 0]:
                        _rect(alpha, (width, height), "cached alphaBounds")
                    with Image.open(io.BytesIO(thumbnail_data)) as thumb:
                        thumb.verify()
                        if thumb.format == "PNG" and list(thumb.size) == possible["thumbnailSize"] and max(thumb.size) <= 192:
                            metadata = possible
            if metadata is not None:
                cache_hits += 1
        except (OSError, ValueError, TypeError, KeyError, SyntaxError):
            pass
        if metadata is None:
            try:
                image, loaded_data = _load(path)
                if loaded_data != data:
                    raise ValueError("Source changed during resource indexing; retry with a stable source")
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                unsupported.append({"path": str(path), "reason": "invalid-or-unsupported-image", "detail": str(exc)})
                continue
            thumbnail = image.copy()
            thumbnail.thumbnail((192, 192), Image.Resampling.LANCZOS)
            thumbnail_data = _png(thumbnail)
            metadata = {"algorithm": ALGORITHM, "sha256": sha, "width": image.width, "height": image.height,
                        "alphaBounds": _bounds(image), "thumbnailSize": list(thumbnail.size), "thumbnailSha256": _hash(thumbnail_data)}
            metadata["metadataSha256"] = _hash(_json_bytes(metadata))
            _write(cached_png, thumbnail_data)
            _write(cached_meta, _json_bytes(metadata))
        thumbnail_path = output_dir / "thumbnails" / (sha + ".png")
        _write(thumbnail_path, thumbnail_data)
        item = {"id": "res_" + sha, "path": str(path), "sha256": sha, "width": metadata["width"], "height": metadata["height"],
                "alphaBounds": metadata["alphaBounds"], "thumbnail": str(thumbnail_path), "thumbnailSha256": metadata["thumbnailSha256"]}
        resources.append(item)
        known[sha] = item
    result = {"version": VERSION, "algorithm": ALGORITHM, "sourceDirectory": str(resource_dir), "resources": resources,
              "duplicates": duplicates, "unsupported": unsupported, "cacheHits": cache_hits}
    _write(output_dir / "resource-index.json", _json_bytes(result))
    return result


def _resource_images(inventory: dict) -> dict[str, tuple[dict, Image.Image]]:
    if inventory.get("version") != VERSION or not isinstance(inventory.get("resources"), list):
        raise ValueError("Unsupported resource inventory")
    result = {}
    for item in inventory["resources"]:
        if item["id"] in result:
            raise ValueError("Inventory contains repeated resource IDs")
        path = Path(item["path"])
        if not path.is_absolute():
            raise ValueError("Resource paths must be absolute")
        image, data = _load(path)
        sha = _hash(data)
        if sha != item["sha256"] or item["id"] != "res_" + sha or list(image.size) != [item["width"], item["height"]] or _bounds(image) != item["alphaBounds"]:
            raise ValueError(f"Stale or invalid inventory entry: {path}; rebuild the resource index")
        result[item["id"]] = (item, image)
    return result


def _rgba(image: Image.Image) -> np.ndarray:
    return np.asarray(image, dtype=np.float32) / 255.0


def _score_map(reference: Image.Image, template: Image.Image, background_rgb: np.ndarray | None = None) -> np.ndarray:
    """Weighted RGB/alpha RMSE using FFT correlation; transparent padding ignored."""
    ref, query = _rgba(reference).astype(np.float64), _rgba(template).astype(np.float64)
    rh, rw, _ = ref.shape
    th, tw, _ = query.shape
    if th > rh or tw > rw:
        raise ValueError("Template exceeds search region")
    fft_shape = tuple(1 << (n - 1).bit_length() for n in (rh + th - 1, rw + tw - 1))
    slices = (slice(th - 1, rh), slice(tw - 1, rw))
    weight = query[:, :, 3]
    weight_sum = float(weight.sum())
    if weight_sum <= 0:
        return np.ones((rh - th + 1, rw - tw + 1), dtype=np.float32)
    fft_weight = np.fft.rfft2(weight[::-1, ::-1], s=fft_shape)
    # Alpha-weighted straight RGB is robust to invisible padding; an additional
    # alpha channel comparison is meaningful only for references with alpha.
    channels = 4 if np.min(ref[:, :, 3]) < 1.0 else 3
    targets = [query]
    if channels == 3 and np.any((weight > 0) & (weight < 1)):
        # Screenshots usually contain alpha-composited slices. Test an inferred
        # flat background as a second hypothesis; complex backgrounds still
        # require review and are never assigned confidence probabilities.
        background = np.median(ref[:, :, :3].reshape(-1, 3), axis=0) if background_rgb is None else background_rgb
        composite = query.copy()
        composite[:, :, :3] = np.round((query[:, :, :3] * weight[:, :, None] + background * (1 - weight[:, :, None])) * 255) / 255
        targets.append(composite)
    errors = [np.zeros((rh - th + 1, rw - tw + 1), dtype=np.float64) for _ in targets]
    for channel in range(channels):
        src = ref[:, :, channel]
        fft_src = np.fft.rfft2(src, s=fft_shape)
        square = np.fft.irfft2(np.fft.rfft2(src * src, s=fft_shape) * fft_weight, s=fft_shape)[slices]
        for index, target_image in enumerate(targets):
            target = target_image[:, :, channel]
            cross = np.fft.irfft2(fft_src * np.fft.rfft2((target * weight)[::-1, ::-1], s=fft_shape), s=fft_shape)[slices]
            errors[index] += square - 2 * cross + float(np.sum(target * target * weight))
    return np.sqrt(np.clip(np.minimum.reduce(errors) / (weight_sum * channels), 0.0, 1.0))


def _peaks(errors: np.ndarray, template_size: tuple[int, int], count: int = 3) -> list[tuple[float, int, int]]:
    working = errors.copy()
    found = []
    for _ in range(count):
        flat = int(np.argmin(working))
        y, x = np.unravel_index(flat, working.shape)
        score = float(working[y, x])
        if not math.isfinite(score):
            break
        found.append((score, int(x), int(y)))
        radius_x, radius_y = max(1, template_size[0] // 2), max(1, template_size[1] // 2)
        working[max(0, y - radius_y):y + radius_y + 1, max(0, x - radius_x):x + radius_x + 1] = np.inf
    return found


def _same_occurrence(left: dict, right: dict) -> bool:
    if left["resourceId"] != right["resourceId"]:
        return False
    a, b = left["visibleBounds"], right["visibleBounds"]
    intersection = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    union = a[2] * a[3] + b[2] * b[3] - intersection
    return intersection / max(1, union) > 0.45


def match_candidates(reference_path: Path, region_xywh: list[int], inventory: dict, limit: int = 3) -> list[dict]:
    """Return finite-scale local matches, including repeated occurrences.

    ``bounds`` includes the original image's transparent padding; ``visibleBounds``
    bounds the scaled alpha content. Both use global reference coordinates.
    ``ambiguous`` marks low appearance similarity or a competing near-tie. Even a
    high-scoring unambiguous result remains a candidate, never an approval.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20")
    reference, _ = _load(Path(reference_path))
    bounds = _rect(region_xywh, reference.size)
    crop = _crop(reference, bounds)
    reduction = min(1.0, 192.0 / max(crop.size))
    coarse = crop.resize((max(1, round(crop.width * reduction)), max(1, round(crop.height * reduction))), Image.Resampling.LANCZOS)
    ratio_x, ratio_y = coarse.width / crop.width, coarse.height / crop.height
    background_rgb = np.median(_rgba(coarse)[:, :, :3].reshape(-1, 3), axis=0)
    candidates = []
    for resource_id, (_, source) in _resource_images(inventory).items():
        if _bounds(source)[2] == 0:
            continue
        proposals, sizes = [], set()
        for scale in SCALES:
            size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
            if size in sizes:
                continue
            sizes.add(size)
            scaled = source.resize(size, Image.Resampling.LANCZOS)
            alpha = _bounds(scaled)
            if alpha[2] == 0 or alpha[2] > crop.width or alpha[3] > crop.height:
                continue
            template = _crop(scaled, alpha)
            small_size = (max(1, round(template.width * ratio_x)), max(1, round(template.height * ratio_y)))
            if small_size[0] > coarse.width or small_size[1] > coarse.height:
                continue
            small = template.resize(small_size, Image.Resampling.LANCZOS)
            for error, x, y in _peaks(_score_map(coarse, small, background_rgb), small.size, max(3, limit)):
                proposals.append((error, abs(math.log2(scale)), scale, x, y, scaled, alpha, template))
        # Refine the best coarse proposals at original resolution. Bounded work
        # keeps screenshots outside model context and avoids exhaustive pixel
        # searches over every resource at full-screen resolution.
        proposals.sort(key=lambda p: (round(p[0], 5), p[1], p[4], p[3]))
        for _, _, scale, x, y, scaled, alpha, template in proposals[:max(12, limit * 4)]:
            origin_x, origin_y = round(x / ratio_x), round(y / ratio_y)
            radius_x, radius_y = math.ceil(2 / ratio_x), math.ceil(2 / ratio_y)
            start_x, start_y = max(0, origin_x - radius_x), max(0, origin_y - radius_y)
            end_x = min(crop.width, origin_x + radius_x + template.width)
            end_y = min(crop.height, origin_y + radius_y + template.height)
            local = crop.crop((start_x, start_y, end_x, end_y))
            if local.width < template.width or local.height < template.height:
                continue
            error, dx, dy = _peaks(_score_map(local, template, background_rgb), template.size, 1)[0]
            visible_x, visible_y = bounds[0] + start_x + dx, bounds[1] + start_y + dy
            full = [visible_x - alpha[0], visible_y - alpha[1], scaled.width, scaled.height]
            if full[0] < 0 or full[1] < 0 or full[0] + full[2] > reference.width or full[1] + full[3] > reference.height:
                continue
            candidates.append({"resourceId": resource_id, "score": round(max(0.0, 1.0 - error), 6), "bounds": full,
                               "visibleBounds": [visible_x, visible_y, template.width, template.height], "scale": scale})
    candidates.sort(key=lambda c: (-c["score"], abs(math.log2(c["scale"])), c["resourceId"], c["bounds"][1], c["bounds"][0]))
    unique = []
    for candidate in candidates:
        if not any(_same_occurrence(candidate, other) for other in unique):
            unique.append(candidate)
    for index, candidate in enumerate(unique):
        near_tie = any(abs(candidate["score"] - other["score"]) <= 0.025 for j, other in enumerate(unique) if j != index)
        candidate["ambiguous"] = bool(candidate["score"] < 0.92 or near_tie)
        candidate["scoreMeaning"] = "appearance-similarity-not-confidence"
    return unique[:limit]


def _premultiplied(image: Image.Image) -> np.ndarray:
    values = np.asarray(image, dtype=np.float32).copy()
    values[:, :, :3] *= values[:, :, 3:4] / 255.0
    return values


def _metrics(delta: np.ndarray) -> dict:
    return {"mae": round(float(np.mean(delta)), 6), "changedPixels": int(np.count_nonzero(np.any(delta > 0.001, axis=2))),
            "totalPixels": int(delta.shape[0] * delta.shape[1])}


def compare_images(reference: Path, actual: Path, output_dir: Path, regions: list[dict] | None = None) -> dict:
    """Measure premultiplied RGBA differences without resizing or accepting them."""
    reference, actual, output_dir = Path(reference).resolve(), Path(actual).resolve(), Path(output_dir).resolve()
    expected, expected_bytes = _load(reference)
    rendered, rendered_bytes = _load(actual)
    region_specs = []
    used_ids = set()
    for index, region in enumerate(regions or []):
        identity = region.get("id", f"region-{index + 1}")
        if not isinstance(identity, str) or not identity or identity in used_ids:
            raise ValueError("Region IDs must be unique nonempty strings")
        used_ids.add(identity)
        region_specs.append({"id": identity, "bounds": _rect(region.get("bounds", region.get("region")), expected.size, "comparison region")})
    result = {"version": VERSION, "dimensionAgreement": expected.size == rendered.size,
              "reference": dict(_binding(reference, expected_bytes), width=expected.width, height=expected.height),
              "actual": dict(_binding(actual, rendered_bytes), width=rendered.width, height=rendered.height),
              "metric": "premultiplied-rgba-mae-0-255", "mae": None, "changedPixels": None, "regions": [],
              "overlay": None, "diff": None, "acceptance": "requires-human-review"}
    if expected.size != rendered.size:
        result["diagnostic"] = "Image dimensions disagree; no rescaling or pixel comparison was performed"
        _write(output_dir / "comparison.json", _json_bytes(result))
        return result
    delta = np.abs(_premultiplied(expected) - _premultiplied(rendered))
    result.update(_metrics(delta))
    for region in region_specs:
        x, y, width, height = region["bounds"]
        result["regions"].append(dict(region, **_metrics(delta[y:y + height, x:x + width])))
    artifact_id = _hash(expected_bytes + rendered_bytes)[:20]
    overlay = Image.blend(expected, rendered, 0.5)
    heat = np.zeros((expected.height, expected.width, 4), dtype=np.uint8)
    heat[:, :, 0] = np.clip(np.max(delta, axis=2) * 4, 0, 255).astype(np.uint8)
    heat[:, :, 3] = 255
    for name, image in (("overlay", overlay), ("diff", Image.fromarray(heat))):
        path = output_dir / f"{artifact_id}-{name}.png"
        data = _png(image)
        _write(path, data)
        result[name] = _binding(path, data)
    _write(output_dir / "comparison.json", _json_bytes(result))
    return result


def validate_comparison(evidence: dict, regions: list[dict], owner: Path) -> None:
    """Recheck bound pixels and measured results without writing new evidence."""
    def bound_image(field):
        record=evidence[field]
        path=Path(record['path'])
        if not path.is_absolute(): path=Path(owner).resolve().parent/path
        image,data=_load(path)
        if _hash(data)!=record['sha256']: raise ValueError('Comparison image changed: '+field)
        return image
    expected,rendered=bound_image('reference'),bound_image('actual')
    if expected.size!=rendered.size or evidence.get('dimensionAgreement') is not True:
        raise ValueError('Comparison dimensions disagree')
    for field,image in (('reference',expected),('actual',rendered)):
        if (evidence[field].get('width'),evidence[field].get('height'))!=image.size:
            raise ValueError('Comparison image dimensions were altered')
    if evidence.get('metric')!='premultiplied-rgba-mae-0-255' or evidence.get('version')!=VERSION:
        raise ValueError('Unsupported comparison algorithm')
    delta=np.abs(_premultiplied(expected)-_premultiplied(rendered))
    if any(evidence.get(k)!=v for k,v in _metrics(delta).items()):
        raise ValueError('Comparison metrics differ from actual pixels')
    measured=[]
    for region in regions:
        x,y,w,h=_rect(region['bounds'],expected.size,'comparison region')
        measured.append({'id':region['id'],'bounds':[x,y,w,h],**_metrics(delta[y:y+h,x:x+w])})
    if evidence.get('regions')!=measured: raise ValueError('Comparison regions or local metrics changed')
    overlay=Image.blend(expected,rendered,0.5)
    heat=np.zeros((expected.height,expected.width,4),dtype=np.uint8)
    heat[:,:,0]=np.clip(np.max(delta,axis=2)*4,0,255).astype(np.uint8)
    heat[:,:,3]=255
    for field,target in (('overlay',np.asarray(overlay)),('diff',heat)):
        actual=np.asarray(bound_image(field))
        if actual.shape!=target.shape or not np.array_equal(actual,target):
            raise ValueError('Comparison '+field+' does not show the measured images')


def create_review_sheet(reference_path: Path, regions: list[dict], inventory: dict, output_path: Path,
                        candidates_by_region: dict[str, list[dict]] | None = None) -> dict:
    """Produce a numbered local comparison sheet and machine-readable cell map.

    Callers supply already computed candidates to avoid repeated matching. Region
    IDs are labels; arbitrary text is not treated as an instruction or approval.
    """
    if not regions or len(regions) > 24:
        raise ValueError("Review sheets must contain between 1 and 24 regions")
    output_path = Path(output_path).resolve()
    protected_paths = {Path(reference_path).resolve()} | {Path(item["path"]).resolve() for item in inventory.get("resources", [])}
    if output_path in protected_paths or output_path.with_suffix(".json") in protected_paths:
        raise ValueError("Review outputs must not overwrite source evidence")
    reference, reference_data = _load(Path(reference_path))
    resources = _resource_images(inventory)
    candidates_by_region = candidates_by_region or {}
    sheet = Image.new("RGB", (960, 210 * len(regions)), "#20242c")
    draw = ImageDraw.Draw(sheet)
    cells, used_ids = [], set()
    for index, region in enumerate(regions):
        identity = region.get("id", f"region-{index + 1}")
        if not isinstance(identity, str) or not identity or identity in used_ids:
            raise ValueError("Review region IDs must be unique nonempty strings")
        used_ids.add(identity)
        bounds = _rect(region.get("bounds", region.get("region")), reference.size, "review region")
        candidates = candidates_by_region.get(identity, [])
        if len(candidates) > 3:
            raise ValueError("A review row supports at most three candidates")
        images = [("Reference", _crop(reference, bounds), None)]
        for n, candidate in enumerate(candidates):
            resource_id = candidate["resourceId"]
            if resource_id not in resources:
                raise ValueError("Review candidate references an unknown resource")
            score = candidate.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Candidate scores must be finite and between zero and one")
            images.append((f"Candidate {n + 1}: {score:.3f}", resources[resource_id][1], resource_id))
        for col, (label, image, resource_id) in enumerate(images):
            x, y = col * 240, index * 210
            thumb = image.copy()
            thumb.thumbnail((224, 166), Image.Resampling.LANCZOS)
            sheet.paste(thumb, (x + (240 - thumb.width) // 2, y + 30 + (170 - thumb.height) // 2), thumb)
            draw.text((x + 8, y + 8), f"{index + 1}. {label}", fill="white")
            cells.append({"regionId": identity, "resourceId": resource_id, "cellBounds": [x, y, 240, 210], "referenceBounds": bounds})
    data = _png(sheet)
    _write(output_path, data)
    result = {"version": VERSION, "reference": _binding(Path(reference_path), reference_data), "sheet": _binding(output_path, data),
              "cells": cells, "acceptance": "requires-human-review"}
    _write(output_path.with_suffix(".json"), _json_bytes(result))
    return result


def export_sample(reference_path: Path, readback_path: Path, inventory: dict, mappings: list[dict], output_dir: Path, scope: str) -> dict:
    """Export a bounded reference sample, preserving exact source evidence.

    This does not certify a readback or confirm a mapping. The coordinator must
    validate UE provenance and collect user review separately before reuse.
    """
    if not isinstance(scope, str) or not scope.strip() or not mappings:
        raise ValueError("Samples require explicit applicability scope and at least one mapping")
    output_dir = Path(output_dir).resolve()
    resources = _resource_images(inventory)
    reference, reference_data = _load(Path(reference_path))
    readback_data = Path(readback_path).read_bytes()
    readback = json.loads(readback_data)
    if not isinstance(readback, dict):
        raise ValueError("Readback must be a JSON object")
    copied_resources = []
    seen = set()
    for mapping in mappings:
        resource_id = mapping.get("resourceId")
        if resource_id not in resources or not isinstance(mapping.get("widgetName"), str) or not mapping["widgetName"] or not isinstance(mapping.get("assetPath"), str) or not mapping["assetPath"].startswith("/Game/"):
            raise ValueError("Each sample mapping needs a known resourceId, widgetName, and /Game/ assetPath")
        if "bounds" in mapping:
            _rect(mapping["bounds"], reference.size, "sample mapping")
        if resource_id in seen:
            continue
        seen.add(resource_id)
        item = resources[resource_id][0]
        data = Path(item["path"]).read_bytes()
        if _hash(data) != item["sha256"]:
            raise ValueError("Resource changed during sample export")
        path = output_dir / "resources" / (item["sha256"] + Path(item["path"]).suffix.lower())
        _write(path, data)
        copied_resources.append(dict(_binding(path, data), resourceId=resource_id, sourcePath=item["path"]))
    reference_copy = output_dir / ("reference" + Path(reference_path).suffix.lower())
    readback_copy = output_dir / "readback.json"
    _write(reference_copy, reference_data)
    _write(readback_copy, readback_data)
    result = {"version": VERSION, "status": "reference-only", "scope": scope.strip(), "reference": _binding(reference_copy, reference_data),
              "readback": _binding(readback_copy, readback_data), "resources": copied_resources, "mappings": mappings,
              "approval": "not-established-by-export", "globalStandard": False}
    result["id"] = "sample_" + _hash(_json_bytes({"reference": _hash(reference_data), "readback": _hash(readback_data), "mappings": mappings, "scope": scope.strip()}))
    _write(output_dir / "sample.json", _json_bytes(result))
    return result
