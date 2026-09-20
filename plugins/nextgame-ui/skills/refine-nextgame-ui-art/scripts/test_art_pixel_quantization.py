"""Static resource aspect rounding only; synthetic fixtures, no visual approval."""
import copy
import struct
import unittest
from unittest.mock import patch

from PIL import Image

import art_common as common
import art_presentation as presentation
import test_art_presentation as original


def float32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


class PixelQuantizationTests(unittest.TestCase):
    def setUp(self):
        self.fx = original.PresentationTests(methodName='runTest')
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        source = self.fx.root / 'source-frame.png'
        Image.new('RGBA', (24, 28), (48, 99, 191, 255)).save(source)
        record = self.fx.catalog['resources'][0]
        record.update(sourceSha256=common.sha256(source), dimensions=[24, 28])
        self.fx.image['source'].update(image=common.binding(source), frameSize=[24, 28],
                                       alphaBounds=[0, 0, 24, 28])
        self.set_size([26.2857, 30.6667])
        self.fx.sync()

    def set_size(self, size):
        self.fx.icon['properties']['brush']['imageSize'] = dict(zip(('x', 'y'), size))
        self.fx.icon['slot']['properties']['layoutData']['offsets'].update(right=size[0], bottom=size[1])

    def test_four_decimal_arrow_and_float32_readback_preserve_aspect(self):
        for size in ([26.2857, 30.6667], [float32(v) for v in [26.2857, 30.6667]]):
            with self.subTest(size=size):
                self.assertFalse(presentation._close(size[0] / 24, size[1] / 28))
                self.set_size(size)
                self.assertEqual([], self.fx.check()['issues'])
                actual = self.fx.check('actual')
                self.assertTrue(any(c['status'] == 'pending' and c['id'].endswith(':geometry')
                                    for c in actual['checks']))

    def test_one_pixel_and_subpixel_real_stretch_still_fail(self):
        for delta in (1, -1, .01, .001):
            for axis in (0, 1):
                with self.subTest(delta=delta, axis=axis):
                    size = [26.2857, 30.6667]
                    size[axis] += delta
                    self.set_size(size)
                    self.fx.assertCode('presentation.aspect')

    def test_brush_success_does_not_excuse_stretched_slot(self):
        self.fx.icon['slot']['properties']['layoutData']['offsets']['right'] += 1
        self.fx.assertCode('presentation.aspect')

    def test_arbitrary_decimal_values_do_not_gain_rounding_budget(self):
        size = [26.28574, 30.66674]
        self.assertFalse(presentation._close(size[0] / 24, size[1] / 28))
        self.assertFalse(presentation._static_resource_aspect_close(size, [24, 28]))

    def test_additional_pixel_budget_is_bounded_at_large_dimensions(self):
        self.assertFalse(presentation._static_resource_aspect_close([8192, 8193], [1, 1]))
        self.assertFalse(presentation._static_resource_aspect_close([65536, 65536.1], [1, 1]))

    def test_transform_tolerance_is_not_widened(self):
        self.fx.snapshot['assets'][0]['widgets'][0]['properties']['renderTransform'] = original.transform(2, 2)
        self.assertEqual([], self.fx.check()['issues'])
        self.fx.snapshot['assets'][0]['widgets'][0]['properties']['renderTransform'] = original.transform(1, 1.000004)
        self.fx.assertCode('presentation.aspect')

    def test_global_native_comparison_remains_strict(self):
        with self.assertRaises(common.ArtError) as caught:
            presentation._values([26.2857], [30.6667 * 24 / 28], 'Native exact decision')
        self.assertEqual('presentation.native_mismatch', caught.exception.code)

    def test_material_domain_does_not_use_resource_rounding(self):
        from art_materials import CAPABILITY
        item = copy.deepcopy(self.fx.image)
        item['source'] = {'kind': 'material'}
        self.fx.icon['properties']['brush'].update(mirroring='NoMirror', uVRegion={'bIsValid': False})
        nodes = common.index_snapshot(self.fx.snapshot)[1]
        with patch('art_materials.validate_material_source', return_value={'evaluationSize': [24, 28]}), \
                patch.object(presentation, '_static_resource_aspect_close', side_effect=AssertionError('material bypass')):
            with self.assertRaises(common.ArtError) as caught:
                presentation._image(item, self.fx.icon, nodes, self.fx.catalog,
                                    self.fx.root / 'request.json', [], 'planned', [CAPABILITY])
        self.assertEqual('presentation.aspect', caught.exception.code)

    def test_nine_slice_native_basis_is_not_widened(self):
        self.fx.image['aspectMode'] = 'nine-slice'
        self.fx.image['nineSlice'] = {'cutPixels': [2, 0, 2, 0], 'stretchAxes': ['x'],
                                    'basisScale': 30.6667 / 28, 'protectedRegions': []}
        self.fx.icon['properties']['brush']['drawAs'] = 'Box'
        self.fx.icon['properties']['brush']['margin'].update(left=2 / 24, right=2 / 24)
        with patch.object(presentation, '_static_resource_aspect_close', side_effect=AssertionError('slice bypass')):
            nodes = common.index_snapshot(self.fx.snapshot)[1]
            with self.assertRaises(common.ArtError) as caught:
                presentation._image(self.fx.image, self.fx.icon, nodes, self.fx.catalog,
                                    self.fx.root / 'request.json', [], 'planned')
        self.assertEqual('presentation.native_mismatch', caught.exception.code)

    def test_source_identity_and_evidence_validation_remain_required(self):
        self.fx.image['source']['image']['sha256'] = '0' * 64
        self.fx.assertCode('binding.stale')


if __name__ == '__main__':
    unittest.main()
