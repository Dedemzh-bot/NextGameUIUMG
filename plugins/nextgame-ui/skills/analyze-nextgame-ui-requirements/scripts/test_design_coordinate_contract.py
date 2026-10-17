"""Synthetic offline checks for exact coordinate adoption; never UI approval."""
import copy
import shutil
import struct
import unittest
import uuid
import zlib
from pathlib import Path

from _contract_common import (ASSETS_ROOT, canonical_sha256, compute_approved_content_sha256,
                              compute_request_input_digest, load_json, sha256_file)
from accepted_build_view import build_accepted_build_view, validate_accepted_build_view
from design_contract import (DesignContractError, accept_requirement, compile_contract,
                             validate_design_contract)
from test_design_contract import fixture, refresh_compatibility, write
from validate_requirement_spec import validate_requirement_spec


class DesignCoordinateContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[3] / 'Saved' / 'CodexUITestTemp' / ('design-coordinate-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        self.contract = fixture(self.root)
        image = self.root / 'synthetic.png'
        def chunk(name, data):
            return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
        image.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2560, 1440, 8, 0, 0, 0, 0))
                          + chunk(b'IDAT', zlib.compress(bytes(2561 * 1440))) + chunk(b'IEND', b''))
        packet_path = self.root / 'request-packet.json'
        packet = load_json(packet_path)
        source = {'sourceKey': 'source-image', 'kind': 'image', 'locatorKind': 'local-file',
                  'description': 'Synthetic offline coordinate test image.', 'path': str(image),
                  'contentSha256': sha256_file(image), 'imageSize': [2560, 1440]}
        packet['sources'].append(source)
        packet['inputDigest'] = compute_request_input_digest(packet)
        write(packet_path, packet)
        content = self.contract['content']
        content['inputDigest'] = packet['inputDigest']
        content['sources'].append({'id': 'source-image', **{k: v for k, v in source.items() if k != 'imageSize'},
                                   'dimensions': source['imageSize']})
        content['evidence'][0].update(sourceId='source-image', kind='direct-observation', measurementMethod='image-measurement')
        self.contract['sourceBindings'][0]['sha256'] = sha256_file(packet_path)
        self.path = self.root / 'design.json'
        self.message = self.root / 'review-message.txt'
        self.message.write_text('Synthetic test review only; no production approval or Editor result.', encoding='utf-8')
        self.schema = load_json(ASSETS_ROOT / 'ui-requirement-spec.schema.json')
        self.save()
        observations = self.accept('observations')
        content['revision'] = 2
        content['coordinateContract'] = {
            'capability': 'source-target-coordinates/1', 'version': 1, 'status': 'trial',
            'sourceId': 'source-image', 'sourceSha256': sha256_file(image), 'sourceSize': [2560, 1440],
            'sourceObservations': {'path': str(observations), 'sha256': sha256_file(observations)},
            'contentFrame': [0, 0, 2560, 1440], 'targetSize': [2560, 1440], 'uniformScale': 1,
            'evidenceIds': ['evidence-design'], 'claimIds': ['claim-design'],
            'targets': [{'assetId': 'asset-screen', 'layoutNodeKey': 'root',
                         'subjectRefs': ['region-screen', 'element-root'], 'coordinateSpace': 'screen-design',
                         'rectPixels': [0, 0, 2560, 1440], 'slotContract': {'parent': None, 'anchor': 'left-top'},
                         'mode': 'source-transform', 'sourceRef': 'region-screen', 'geometryEvidenceId': 'evidence-design',
                         'evidenceIds': ['evidence-design'], 'claimIds': ['claim-design']}]}
        self.save()

    def save(self):
        self.contract['decisions'][0]['valueSha256'] = canonical_sha256(self.contract['content'])
        refresh_compatibility(self.root, self.contract)
        write(self.path, self.contract)

    def accept(self, name):
        pending = self.root / (name + '.pending.json')
        output = self.root / (name + '.accepted.json')
        compile_contract(self.path, pending)
        accept_requirement(pending, output, self.message, 'synthetic-test-agent', '2026-09-20T00:00:00Z',
                           review_kind='delegated-design-review')
        return output

    def test_schema_exactly_reuses_requirement_coordinate_definitions(self):
        schema = load_json(ASSETS_ROOT / 'design-contract.schema.json')
        self.assertEqual(schema['properties']['content']['properties']['coordinateContract'], self.schema['properties']['coordinateContract'])
        for key in ('coordinateContract', 'coordinateSlotContract'):
            self.assertEqual(schema['$defs'][key], self.schema['$defs'][key])
        self.assertFalse(schema['properties']['content']['additionalProperties'])

    def test_compile_accept_new_receipt_and_view_preserve_exact_coordinates(self):
        expected = copy.deepcopy(self.contract['content']['coordinateContract'])
        pending = self.root / 'inspected-coordinate.pending.json'
        compile_contract(self.path, pending)
        self.assertEqual(load_json(pending)['coordinateContract'], expected)
        self.assertEqual(load_json(pending)['reviewGate']['status'], 'pending')
        self.assertNotIn('designReview', load_json(pending)['reviewGate'])
        path = self.accept('coordinate')
        requirement = load_json(path)
        self.assertTrue(validate_requirement_spec(requirement, self.schema, spec_path=path)['valid'])
        receipt = load_json(Path(requirement['reviewGate']['designReview']['receiptPath']))
        self.assertEqual(receipt['reviewKind'], 'delegated-design-review')
        self.assertEqual(receipt['scope']['revision'], 2)
        view, mode, _ = build_accepted_build_view(path)
        self.assertEqual(mode, 'projected')
        self.assertEqual(view['requirement']['coordinateContract'], expected)
        self.assertTrue(validate_accepted_build_view(view, source_requirement=path)['valid'])

    def test_malformed_coordinate_and_unknown_fields_are_rejected(self):
        original = copy.deepcopy(self.contract)
        edits = [lambda c: c.update(skipSourceDrift=True), lambda c: c.update(version=2),
                 lambda c: c['targets'][0]['slotContract'].update(fakeGeometry=True),
                 lambda c: c.update(sourceSize=[0, 1440])]
        for edit in edits:
            self.contract = copy.deepcopy(original)
            edit(self.contract['content']['coordinateContract'])
            self.save()
            with self.subTest(edit=edit):
                self.assertFalse(validate_design_contract(self.contract, contract_path=self.path)['valid'])

    def test_shared_coordinate_semantics_reject_rehashed_wrong_uniform_scale(self):
        self.contract['content']['coordinateContract']['uniformScale'] = 2
        self.save()
        result = validate_design_contract(self.contract, contract_path=self.path)
        self.assertIn('coordinate.invalid', {e['code'] for e in result['errors']})

    def test_changed_source_observations_are_rejected(self):
        Path(self.contract['content']['coordinateContract']['sourceObservations']['path']).write_text('{}', encoding='utf-8')
        result = validate_design_contract(self.contract, contract_path=self.path)
        self.assertIn('coordinate.invalid', {e['code'] for e in result['errors']})

    def test_compiled_coordinate_edit_cannot_be_reapproved_locally(self):
        path = self.accept('coordinate')
        requirement = load_json(path)
        requirement['coordinateContract']['targets'][0]['slotContract']['anchor'] = 'center'
        requirement['reviewGate']['approvedContentSha256'] = compute_approved_content_sha256(requirement)
        result = validate_requirement_spec(requirement, self.schema, spec_path=path)
        self.assertIn('design.adoption_mismatch', {e['code'] for e in result['errors']})

    def test_prior_receipt_cannot_approve_new_coordinate_revision(self):
        old = load_json(self.accept('coordinate'))
        self.contract['content']['revision'] += 1
        self.save()
        pending = self.root / 'next.pending.json'
        compile_contract(self.path, pending)
        current = load_json(pending)
        current['reviewGate'] = copy.deepcopy(old['reviewGate'])
        current['reviewGate']['approvedContentSha256'] = compute_approved_content_sha256(current)
        self.assertFalse(validate_requirement_spec(current, self.schema, spec_path=pending)['valid'])

    def test_pending_compatibility_never_accepts_coordinates(self):
        self.contract['compatibility'] = {'status': 'pending', 'evidenceKeys': [], 'notes': ['No real compatibility review.']}
        self.save()
        with self.assertRaises(DesignContractError):
            self.accept('pending-compatibility')


if __name__ == '__main__':
    unittest.main()
