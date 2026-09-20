"""Synthetic evidence tests; fixtures live only in temporary directories."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from PIL import Image, ImageDraw

from art_images import compare_images, create_review_sheet, export_sample, index_resources, match_candidates


class ArtImageTests(unittest.TestCase):
    def setUp(self):
        # Windows Python 3.14 mkdtemp's mode=0700 creates a DACL that a
        # restricted-token runner cannot reopen. Inherit the allowed temp-root
        # ACL instead; use an unpredictable, exclusive directory name.
        self.temp_parent = Path(os.environ.get("NEXTGAME_ART_TEST_ROOT", tempfile.gettempdir())).resolve()
        self.root = self.temp_parent / ("nextgame-art-images-" + uuid.uuid4().hex)
        self.root.mkdir(mode=0o777)
        self.sources = self.root / "source"
        self.sources.mkdir()
        self.output = self.root / "out"
        self.cache = self.root / "cache"

    def tearDown(self):
        resolved = self.root.resolve()
        if resolved.parent != self.temp_parent or not resolved.name.startswith("nextgame-art-images-"):
            raise ValueError("Refusing cleanup outside the generated test directory")
        shutil.rmtree(resolved)

    def save(self, path, image):
        image.save(path)
        return path

    def icon(self, size=20, padding=0):
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((padding, padding, size - 1 - padding, size - 1 - padding), fill=(180, 30, 50, 255))
        draw.rectangle((padding + 2, padding + 2, size // 2, size // 2), fill=(20, 220, 50, 255))
        draw.line((padding + 1, size - 2 - padding, size - 2 - padding, padding + 1), fill=(30, 40, 250, 255), width=2)
        return image

    def inventory(self):
        return index_resources(self.sources, self.output, self.cache)

    def assert_binding(self, binding):
        self.assertTrue(Path(binding["path"]).is_absolute())
        self.assertEqual(binding["sha256"], hashlib.sha256(Path(binding["path"]).read_bytes()).hexdigest())

    def test_index_alpha_padding_duplicates_and_unsupported(self):
        path = self.save(self.sources / "a.png", self.icon(20, 4))
        (self.sources / "b.png").write_bytes(path.read_bytes())
        (self.sources / "readme.txt").write_text("not an image", encoding="utf-8")
        (self.sources / "bad.png").write_bytes(b"bad image bytes")
        result = self.inventory()
        self.assertEqual(result["version"], 1)
        self.assertEqual(len(result["resources"]), 1)
        item = result["resources"][0]
        self.assertEqual(item["alphaBounds"], [4, 4, 12, 12])
        self.assertEqual((item["width"], item["height"]), (20, 20))
        self.assertEqual(result["duplicates"][0]["resourceId"], item["id"])
        self.assertEqual(result["duplicates"][0]["duplicateOf"], str(path.resolve()))
        self.assertEqual(len(result["unsupported"]), 2)
        self.assertTrue(Path(item["thumbnail"]).is_absolute())

    def test_modified_source_changes_id_and_output_is_repaired(self):
        path = self.save(self.sources / "icon.png", self.icon())
        first = self.inventory()["resources"][0]
        correct_thumbnail = Path(first["thumbnail"]).read_bytes()
        Path(first["thumbnail"]).write_bytes(b"corrupt output")
        second = self.inventory()
        self.assertEqual(second["cacheHits"], 1)
        self.assertEqual(Path(first["thumbnail"]).read_bytes(), correct_thumbnail)
        self.save(path, Image.new("RGBA", (22, 18), "blue"))
        third = self.inventory()["resources"][0]
        self.assertNotEqual(third["id"], first["id"])
        self.assertEqual((third["width"], third["height"]), (22, 18))

    def test_corrupt_cache_thumbnail_and_manifest_are_rebuilt(self):
        self.save(self.sources / "icon.png", self.icon())
        first = self.inventory()["resources"][0]
        cache_png = self.cache / (first["sha256"] + ".png")
        cache_png.write_bytes(b"bad cached output")
        result = self.inventory()
        self.assertEqual(result["cacheHits"], 0)
        self.assertEqual(hashlib.sha256(cache_png.read_bytes()).hexdigest(), first["thumbnailSha256"])
        meta_path = self.cache / (first["sha256"] + ".json")
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        metadata["alphaBounds"] = [0, 0, float("inf"), 10]
        meta_path.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(self.inventory()["resources"][0]["alphaBounds"], [0, 0, 20, 20])
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        metadata["alphaBounds"] = [1, 1, 10, 10]
        meta_path.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(self.inventory()["resources"][0]["alphaBounds"], [0, 0, 20, 20])
        meta_path.write_text("[]", encoding="utf-8")
        self.assertEqual(self.inventory()["resources"][0]["alphaBounds"], [0, 0, 20, 20])

    def test_output_below_sources_does_not_index_own_artifacts(self):
        self.save(self.sources / "icon.png", self.icon())
        first = index_resources(self.sources, self.sources / "derived")
        second = index_resources(self.sources, self.sources / "derived")
        self.assertEqual(len(first["resources"]), 1)
        self.assertEqual(len(second["resources"]), 1)
        self.assertEqual(second["unsupported"], [])

    def test_match_transparent_padding_recovers_full_bounds(self):
        icon = self.icon(20, 4)
        self.save(self.sources / "icon.png", icon)
        reference = Image.new("RGBA", (80, 60), (12, 22, 32, 255))
        reference.alpha_composite(icon, (27, 18))
        path = self.save(self.root / "reference.png", reference)
        candidates = match_candidates(path, [0, 0, 80, 60], self.inventory())
        self.assertGreater(candidates[0]["score"], 0.999)
        self.assertEqual(candidates[0]["bounds"], [27, 18, 20, 20])
        self.assertEqual(candidates[0]["visibleBounds"], [31, 22, 12, 12])

    def test_scaled_candidate_is_found(self):
        icon = self.icon(24)
        self.save(self.sources / "icon.png", icon)
        scaled = icon.resize((36, 36), Image.Resampling.LANCZOS)
        reference = Image.new("RGBA", (90, 80), (10, 15, 20, 255))
        reference.alpha_composite(scaled, (23, 19))
        path = self.save(self.root / "reference.png", reference)
        candidates = match_candidates(path, [10, 10, 70, 60], self.inventory())
        self.assertGreater(candidates[0]["score"], 0.999)
        self.assertEqual(candidates[0]["bounds"], [23, 19, 36, 36])
        self.assertEqual(candidates[0]["scale"], 1.5)

    def test_alpha_composited_candidate_matches_flat_background(self):
        icon = self.icon()
        icon.putalpha(128)
        self.save(self.sources / "icon.png", icon)
        reference = Image.new("RGBA", (100, 80), (8, 16, 24, 255))
        reference.alpha_composite(icon, (31, 28))
        path = self.save(self.root / "reference.png", reference)
        candidate = match_candidates(path, [0, 0, 100, 80], self.inventory())[0]
        self.assertGreater(candidate["score"], 0.999)
        self.assertEqual(candidate["bounds"], [31, 28, 20, 20])

    def test_coarse_search_refines_back_to_original_coordinates(self):
        icon = self.icon(60)
        self.save(self.sources / "icon.png", icon)
        reference = Image.new("RGBA", (500, 400), (10, 15, 20, 255))
        reference.alpha_composite(icon, (271, 213))
        path = self.save(self.root / "reference.png", reference)
        candidate = match_candidates(path, [0, 0, 500, 400], self.inventory())[0]
        self.assertGreater(candidate["score"], 0.999)
        self.assertEqual(candidate["bounds"], [271, 213, 60, 60])

    def test_repeated_match_is_explicitly_ambiguous_even_with_limit_one(self):
        icon = self.icon()
        self.save(self.sources / "icon.png", icon)
        reference = Image.new("RGBA", (100, 50), (10, 15, 20, 255))
        reference.alpha_composite(icon, (10, 15))
        reference.alpha_composite(icon, (65, 15))
        path = self.save(self.root / "reference.png", reference)
        inventory = self.inventory()
        candidates = match_candidates(path, [0, 0, 100, 50], inventory, limit=2)
        self.assertEqual({tuple(c["bounds"]) for c in candidates}, {(10, 15, 20, 20), (65, 15, 20, 20)})
        self.assertTrue(all(c["ambiguous"] for c in candidates))
        self.assertTrue(match_candidates(path, [0, 0, 100, 50], inventory, limit=1)[0]["ambiguous"])

    def test_stale_inventory_and_invalid_match_inputs_are_rejected(self):
        path = self.save(self.sources / "icon.png", self.icon())
        inventory = self.inventory()
        reference = self.save(self.root / "reference.png", Image.new("RGBA", (80, 60), "black"))
        for bounds in ([0, 0, float("nan"), 5], [-1, 0, 10, 10], [75, 0, 10, 10], [0, 0, 0, 10], [True, 0, 10, 10]):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                match_candidates(reference, bounds, inventory)
        for limit in (0, 21, float("inf"), True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                match_candidates(reference, [0, 0, 80, 60], inventory, limit=limit)
        self.save(path, Image.new("RGBA", (20, 20), "white"))
        with self.assertRaisesRegex(ValueError, "Stale"):
            match_candidates(reference, [0, 0, 80, 60], inventory)

    def test_comparison_detects_omitted_layer_by_region(self):
        background = Image.new("RGBA", (20, 20), "black")
        expected = background.copy()
        ImageDraw.Draw(expected).rectangle((2, 4, 7, 7), fill="red")
        reference = self.save(self.root / "reference.png", expected)
        actual = self.save(self.root / "actual.png", background)
        result = compare_images(reference, actual, self.root / "comparison", [{"id": "icon", "bounds": [2, 4, 6, 4]}, {"id": "unaffected", "bounds": [10, 10, 5, 5]}])
        self.assertTrue(result["dimensionAgreement"])
        self.assertEqual(result["changedPixels"], 24)
        self.assertAlmostEqual(result["mae"], 3.825)
        self.assertEqual(result["regions"][0]["changedPixels"], 24)
        self.assertEqual(result["regions"][1]["changedPixels"], 0)
        self.assertEqual(result["acceptance"], "requires-human-review")
        self.assert_binding(result["overlay"])
        self.assert_binding(result["diff"])

    def test_invisible_rgb_is_ignored_and_identical_results_need_review(self):
        reference = self.save(self.root / "reference.png", Image.new("RGBA", (10, 10), (255, 0, 0, 0)))
        actual = self.save(self.root / "actual.png", Image.new("RGBA", (10, 10), (0, 255, 0, 0)))
        result = compare_images(reference, actual, self.root / "comparison")
        self.assertEqual(result["mae"], 0)
        self.assertEqual(result["changedPixels"], 0)
        self.assertEqual(result["acceptance"], "requires-human-review")

    def test_mismatched_dimensions_are_reported_without_resizing(self):
        reference = self.save(self.root / "reference.png", Image.new("RGBA", (20, 20), "red"))
        actual = self.save(self.root / "actual.png", Image.new("RGBA", (10, 10), "red"))
        result = compare_images(reference, actual, self.root / "comparison")
        self.assertFalse(result["dimensionAgreement"])
        self.assertIsNone(result["mae"])
        self.assertIsNone(result["diff"])
        self.assertEqual(list((self.root / "comparison").glob("*.png")), [])
        with self.assertRaises(ValueError):
            compare_images(reference, actual, self.root / "comparison", [{"bounds": [0, 0, 100, 10]}])

    def test_review_sheet_is_evidence_and_rejects_nonfinite_score(self):
        icon = self.icon()
        self.save(self.sources / "icon.png", icon)
        reference = self.save(self.root / "reference.png", icon)
        inventory = self.inventory()
        rid = inventory["resources"][0]["id"]
        regions = [{"id": "button", "bounds": [0, 0, 20, 20]}]
        result = create_review_sheet(reference, regions, inventory, self.root / "review.png", {"button": [{"resourceId": rid, "score": 1.0}]})
        self.assert_binding(result["sheet"])
        self.assertEqual(len(result["cells"]), 2)
        self.assertEqual(result["acceptance"], "requires-human-review")
        with self.assertRaises(ValueError):
            create_review_sheet(reference, regions, inventory, self.root / "bad-review.png", {"button": [{"resourceId": rid, "score": float("nan")}]})
        with self.assertRaisesRegex(ValueError, "overwrite"):
            create_review_sheet(reference, regions, inventory, reference)

    def test_exported_sample_preserves_sources_without_inventing_approval(self):
        icon = self.icon()
        self.save(self.sources / "icon.png", icon)
        reference = self.save(self.root / "reference.png", icon)
        readback = self.root / "actual-readback.json"
        readback.write_text('{"actual":"fixture-only"}', encoding="utf-8")
        inventory = self.inventory()
        mappings = [{"resourceId": inventory["resources"][0]["id"], "assetPath": "/Game/UI/UMG/Test/uw_test", "widgetName": "ImgIcon"}]
        sample = export_sample(reference, readback, inventory, mappings, self.root / "sample", "Test system / item icon")
        self.assertEqual(sample["status"], "reference-only")
        self.assertFalse(sample["globalStandard"])
        self.assertEqual(sample["approval"], "not-established-by-export")
        self.assert_binding(sample["reference"])
        self.assert_binding(sample["readback"])
        self.assert_binding(sample["resources"][0])
        repeated = export_sample(reference, readback, inventory, mappings, self.root / "sample-2", "Test system / item icon")
        self.assertEqual(repeated["id"], sample["id"])


if __name__ == "__main__":
    unittest.main()
