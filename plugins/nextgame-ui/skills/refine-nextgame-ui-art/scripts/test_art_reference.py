"""Synthetic source-coordinate regressions; no Unreal or production proof."""
import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from art_common import ArtError, binding, write_json, validate, validate_preview_contract
from art_reference import CAPABILITY, source_size, compare_mapped, validate_mapped
from test_art_pipeline import ArtPipelineTests
from test_art_stage_integration import LinkedArtFixture
from art_pipeline import create_plan
from art_common import sha256


class MappedReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.png'
        self.actual = self.root / 'actual.png'
        Image.new('RGBA', (24, 10), 'red').save(self.source)
        Image.new('RGBA', (32, 18), 'blue').save(self.actual)
        self.reference = {'id': 'native', 'sourceSize': [24, 10], 'context': {'size': [32, 18]},
                          'regions': [{'id': 'part', 'bounds': [2, 1, 10, 8], 'captureBounds': [3, 2, 20, 12], 'widgetNames': ['ImgIcon']}]}

    def compare(self):
        return compare_mapped(self.source, self.actual, self.root / 'comparison', self.reference)

    def test_native_mismatched_dimensions_remain_truthful(self):
        evidence = self.compare()
        self.assertFalse(evidence['dimensionAgreement'])
        self.assertIsNone(evidence['metric'])
        self.assertEqual('none', evidence['resampling'])
        validate_mapped(evidence, self.reference, self.root / 'result.json')

    def test_wrong_capture_size_rejected(self):
        self.reference['context']['size'] = [24, 10]
        with self.assertRaises(ValueError): self.compare()

    def test_source_and_capture_bounds_checked_separately(self):
        for field in ('bounds', 'captureBounds'):
            with self.subTest(field=field):
                original = self.reference['regions'][0][field]
                self.reference['regions'][0][field] = [0, 0, 100, 100]
                with self.assertRaises(ValueError): self.compare()
                self.reference['regions'][0][field] = original

    def test_changed_region_or_pixels_rejected(self):
        evidence = self.compare()
        altered = copy.deepcopy(evidence)
        altered['regions'][0]['captureBounds'][0] += 1
        with self.assertRaises(ValueError): validate_mapped(altered, self.reference, self.root/'result.json')
        path = Path(evidence['regions'][0]['comparison']['path'])
        Image.new('RGBA', (1, 1), 'green').save(path)
        evidence['regions'][0]['comparison'] = binding(path)
        with self.assertRaises(ValueError): validate_mapped(evidence, self.reference, self.root/'result.json')

    def test_capability_required_and_complete(self):
        with self.assertRaises(ArtError): source_size({}, self.reference)
        request = {'capabilities': [CAPABILITY]}
        self.assertEqual([24, 10], source_size(request, self.reference))
        del self.reference['regions'][0]['captureBounds']
        with self.assertRaises(ArtError): source_size(request, self.reference)

    def test_cannot_add_metric_or_claim_same_dimensions(self):
        evidence = self.compare()
        for key, value in (('metric', 'fake-mae'), ('dimensionAgreement', True), ('overlay', {})):
            altered = copy.deepcopy(evidence); altered[key] = value
            with self.assertRaises(ValueError): validate_mapped(altered, self.reference, self.root/'result.json')


class MappedContractTests(ArtPipelineTests):
    def mapped(self):
        self.request['capabilities'] = [CAPABILITY]
        ref = self.request['references'][0]
        ref['sourceSize'] = [32, 32]
        ref['context']['size'] = [48, 64]
        ref['regions'][0]['captureBounds'] = [0, 0, 48, 64]
        return ref

    def test_mapped_request_and_plan_admit_native_source(self):
        self.mapped()
        validate(self.request, 'request')
        self.write('request.json', self.request)
        validate_preview_contract(self.request, self.root/'request.json')
        self.assertEqual('ready', self.plan()['status'])

    def test_closed_schema_rejects_legacy_mapping_and_missing_map(self):
        ref = self.mapped()
        for mutation in ('capability', 'source', 'target'):
            invalid = copy.deepcopy(self.request)
            if mutation == 'capability': del invalid['capabilities']
            if mutation == 'source': del invalid['references'][0]['sourceSize']
            if mutation == 'target': del invalid['references'][0]['regions'][0]['captureBounds']
            with self.assertRaises(ArtError): validate(invalid, 'request')

    def test_legacy_dimensions_still_strict(self):
        self.request['references'][0]['context']['size'] = [48, 64]
        with self.assertRaises(ArtError): validate_preview_contract(self.request, self.root/'request.json')


class MappedFinalGateTests(unittest.TestCase):
    def test_final_gate_recomputes_mapping_and_retains_canonical_guard(self):
        fx = LinkedArtFixture()
        self.addCleanup(fx.close)
        fx.request['capabilities'] = [CAPABILITY]
        for index, reference in enumerate(fx.request['references']):
            reference['sourceSize'] = [24, 16]
            source = Path(reference['image']['path'])
            fx.image(source, (24, 16))
            reference['image'] = binding(source)
            for region in reference['regions']:
                region['captureBounds'] = region['bounds']
                region['bounds'] = [0, 0, 24, 16]
            actual = Path(fx.captures[index]['image']['path'])
            mapped_folder = fx.comparison_paths[index].parent / 'mapped'
            comparison = compare_mapped(source, actual, mapped_folder, reference)
            fx.comparison_paths[index] = mapped_folder / 'bound-comparison.json'
            comparison.update(referenceId=reference['id'], capture=binding(fx.capture_paths[index]))
            fx.comparisons[index] = comparison
        fx.save(fx.request_path, fx.request)
        fx.decisions['requestSha256'] = sha256(fx.request_path)
        fx.save(fx.decisions_path, fx.decisions)
        fx.plan = create_plan(fx.request_path, fx.decisions_path, validate_sources=False)
        fx.save(fx.plan_path, fx.plan)
        fx.execution['planSha256'] = sha256(fx.plan_path)
        fx.save(fx.execution_path, fx.execution)
        fx.flush()
        self.assertEqual([], fx.helper())
        fx.comparisons[0]['regions'][0]['captureBounds'][0] += 1
        fx.flush()
        self.assertTrue(fx.helper())
        fx.comparisons[0]['regions'][0]['captureBounds'][0] -= 1
        fx.captures[0]['canonical'] = False
        fx.flush()
        self.assertTrue(fx.helper())


if __name__ == '__main__': unittest.main()
