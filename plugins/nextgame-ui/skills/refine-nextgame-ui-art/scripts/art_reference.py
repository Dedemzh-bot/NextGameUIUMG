"""Explicit native-artwork / rendered-viewport comparison, without invented pixels.

The legacy equal-pixel comparison remains unchanged.  This capability compares
separately declared source and capture regions side by side at native scale;
it cannot produce a pixel-error score or prove a canonical capture by itself.
"""
from pathlib import Path
import json
import hashlib
import io

from PIL import Image, ImageDraw

CAPABILITY = 'mapped-source-reference/1'


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(right, list):
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    if isinstance(right, dict):
        return left.keys() == right.keys() and all(_typed_equal(left[k], v) for k, v in right.items())
    return left == right


def source_size(request, reference):
    from art_common import ArtError
    enabled = CAPABILITY in request.get('capabilities', [])
    has_mapping = 'sourceSize' in reference or any('captureBounds' in r for r in reference['regions'])
    if enabled != has_mapping:
        raise ArtError('preview.mapping_capability', 'Source mapping requires an explicit capability and complete mapping on every reference.')
    if enabled and ('sourceSize' not in reference or any('captureBounds' not in r for r in reference['regions'])):
        raise ArtError('preview.mapping_complete', 'Every mapped reference needs native source dimensions and every region needs capture bounds.')
    return reference['sourceSize'] if enabled else reference['context']['size']


def _rect(bounds, size):
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(isinstance(n, bool) or not isinstance(n, int) for n in bounds)):
        raise ValueError('Mapped comparison bounds must contain four integers.')
    x, y, w, h = bounds
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > size[0] or y + h > size[1]:
        raise ValueError('Mapped comparison region exceeds its own image.')
    return x, y, x + w, y + h


def validate_regions(reference):
    for region in reference['regions']:
        _rect(region['bounds'], reference['sourceSize'])
        _rect(region['captureBounds'], reference['context']['size'])


def _png(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def _pair(left, right):
    # Native pixels, explicit labels, no resizing or artificial target artwork.
    result = Image.new('RGBA', (left.width + right.width + 24, max(left.height, right.height) + 32), '#242831')
    draw = ImageDraw.Draw(result)
    draw.text((0, 4), 'SOURCE / native pixels', fill='white')
    draw.text((left.width + 24, 4), 'ACTUAL / native pixels', fill='white')
    result.alpha_composite(left, (0, 32))
    result.alpha_composite(right, (left.width + 24, 32))
    return result


def _binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _images(source, actual, reference):
    with Image.open(source) as image:
        left = image.convert('RGBA')
    with Image.open(actual) as image:
        right = image.convert('RGBA')
    if list(left.size) != reference['sourceSize'] or list(right.size) != reference['context']['size']:
        raise ValueError('Native source and actual capture dimensions must match their separately declared coordinate systems.')
    validate_regions(reference)
    return left, right


def compare_mapped(source, actual, output_dir, reference):
    from art_common import ArtError, PLUGIN_ROOT
    left, right = _images(source, actual, reference)
    folder = Path(output_dir).resolve()
    if folder.is_relative_to(PLUGIN_ROOT.resolve()):
        raise ArtError('output.plugin', 'Runtime comparison evidence belongs outside the plugin.')
    protected = {Path(source).resolve(), Path(actual).resolve()}
    outputs = {}
    def pending_image(path, image):
        data = _png(image)
        outputs[path] = data
        return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}
    result = {'version': 1, 'comparisonMode': CAPABILITY,
              'dimensionAgreement': left.size == right.size, 'coordinateSystemsVerified': True,
              'sourceSize': list(left.size), 'captureSize': list(right.size),
              'reference': _binding(source), 'actual': _binding(actual),
              'metric': None, 'resampling': 'none', 'acceptance': 'requires-visual-review', 'regions': []}
    full = folder / 'native-full-view.png'
    result['fullView'] = pending_image(full, _pair(left, right))
    for index, region in enumerate(reference['regions']):
        crop_left = left.crop(_rect(region['bounds'], left.size))
        crop_right = right.crop(_rect(region['captureBounds'], right.size))
        pair = folder / f'region-{index:03d}.png'
        pair_binding = pending_image(pair, _pair(crop_left, crop_right))
        result['regions'].append({'id': region['id'], 'bounds': region['bounds'],
                                  'captureBounds': region['captureBounds'], 'comparison': pair_binding})
    outputs[folder / 'comparison.json'] = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    # Check the entire transaction before writing any file. Recovery can reuse
    # identical bytes, but cannot damage prior bound evidence or either input.
    for path, data in outputs.items():
        if path.resolve() in protected:
            raise ArtError('output.source', 'Comparison output must not replace source or capture input.')
        if path.exists() and path.read_bytes() != data:
            raise ArtError('output.immutable', 'Choose a new comparison revision; existing evidence differs.')
    folder.mkdir(parents=True, exist_ok=True)
    for path, data in outputs.items():
        if not path.exists():
            with path.open('xb') as handle:
                handle.write(data)
    return result


def validate_mapped(evidence, reference, owner):
    from art_common import bound_path
    for field in ('reference', 'actual'):
        if not isinstance(evidence.get(field), dict) or set(evidence[field]) != {'path', 'sha256'}:
            raise ValueError('Comparison source bindings must be closed.')
    source = bound_path(evidence['reference'], owner)
    actual = bound_path(evidence['actual'], owner)
    left, right = _images(source, actual, reference)
    required = {'version': 1, 'comparisonMode': CAPABILITY,
                'dimensionAgreement': left.size == right.size, 'coordinateSystemsVerified': True,
                'sourceSize': list(left.size), 'captureSize': list(right.size),
                'metric': None, 'resampling': 'none', 'acceptance': 'requires-visual-review'}
    if not set(required) <= set(evidence) or any(not _typed_equal(evidence.get(k), v) for k, v in required.items()):
        raise ValueError('Mapped comparison interpretation or coordinate evidence changed.')
    allowed = set(required) | {'reference', 'actual', 'fullView', 'regions', 'capture', 'referenceId'}
    if set(evidence) - allowed or len(evidence['regions']) != len(reference['regions']):
        raise ValueError('Mapped comparison shape/region coverage changed.')
    def check_pixels(record, expected):
        if not isinstance(record, dict) or set(record) != {'path', 'sha256'}:
            raise ValueError('Comparison image bindings must be closed.')
        if Path(bound_path(record, owner)).read_bytes() != _png(expected):
            raise ValueError('Comparison pixels no longer show the exact native source and captured regions.')
    check_pixels(evidence['fullView'], _pair(left, right))
    for observed, spec in zip(evidence['regions'], reference['regions']):
        if (set(observed) != {'id', 'bounds', 'captureBounds', 'comparison'}
                or any(not _typed_equal(observed[k], spec[k]) for k in ('id', 'bounds', 'captureBounds'))):
            raise ValueError('Mapped region identity or bounds changed.')
        check_pixels(observed['comparison'], _pair(left.crop(_rect(spec['bounds'], left.size)),
                                                 right.crop(_rect(spec['captureBounds'], right.size))))
