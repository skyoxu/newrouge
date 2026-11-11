"""Versioned multi-view delivery regression; no model or native workspace.

The short neutral Packet1 fixtures exercise the real material/compact modules.
They qualify transport semantics and resource gates, not original native proof.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _b_route_compact_literal as compact
import _b_route_compensation_review_materials as materials
import _planning_apply_journal as journal


def ordered(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def refresh(packet):
    rows = [row for frame in packet['materials']['frames'] for row in frame['files']]
    packet['roles']['files'] = sorted(rows, key=lambda row: (row['subject_digest'], row['path']))
    packet['presentation']['materials_digest'] = codec.canonical_digest(packet['materials'])
    packet['presentation']['roles_digest'] = codec.canonical_digest(packet['roles'])
    return packet


def packet_fixture(count=3):
    frames, documents = [], []
    previous = None
    for i in range(max(count, 1)):
        identity = codec.canonical_digest({'neutral-frame': i})
        fields = {'typed_order': {'r': 'literal-marker', '$mvg_ref': 'same bytes',
                                 '~r': 'original alias-like key', 'Z': [False, 0, True, 1, -0.0, 0.0],
                                 'text': 'quote\'"\\\r\n雪', 'empty': {}}}
        files = []
        if count:
            operation = {'schema_version': 'newrouge.b-route-compensation-operation.v2',
                         'operation_id': 'NEUTRAL-OP-' + str(i), 'state': 'synthetic', 'payload': fields}
            fields = {'request': {'compensates': {'operation_id': operation['operation_id']}},
                      'original_operation': operation}
            text = json.dumps(operation, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
            raw = text.encode('utf-8')
            digest = codec.raw_digest(raw)
            documents.append({'raw_digest': digest, 'raw_bytes': len(raw), 'text': text})
            path = journal._operation_ref(operation['operation_id'])
            files.append({'subject_digest': identity, 'path': path, 'raw_digest': digest,
                          'raw_bytes': len(raw), 'roles': ['semantic:original_operation'],
                          'document_ref': digest, 'semantic_frame_ref': None,
                          'owner_uses': [{'role': 'semantic:original_operation', 'owner': operation['schema_version'],
                                          'ref': path, 'source': path, 'subject_digest': identity}]})
        frames.append({'subject_digest': identity, 'operation_id': 'NEUTRAL-FRAME-' + str(i),
                       'subject_schema': materials.COMP_SUBJECT if count else materials.OLD_SUBJECT,
                       'semantic_fields': fields, 'previous_subject': previous, 'files': files})
        previous = identity
    material = {'schema_version': materials.MATERIALS, 'full_subject_digest': previous,
                'frames': frames, 'documents': documents}
    roles = {'schema_version': materials.ROLES, 'full_subject_digest': previous, 'files': []}
    presentation = {'schema_version': materials.PRESENTATION, 'claim': materials.CLAIM,
                    'full_subject_digest': previous, 'materials_digest': '', 'roles_digest': '',
                    'policy_identity': codec.canonical_digest({'neutral-policy': 1}), 'required_checks': ['complete']}
    return refresh({'schema_version': materials.PACKET, 'presentation': presentation, 'roles': roles, 'materials': material})


def envelope(packet):
    work = compact._EncodingWork()
    text = ordered(packet)
    measured = compact._json_preflight(packet, work)
    return materials._mv_transport_envelope(packet, codec.raw_digest(text.encode('utf-8')), work, (measured,), (len(text),))


class CompensationMultiViewTransportV2Tests(unittest.TestCase):
    def reject(self, bad):
        with self.assertRaises(codec.CodecError):
            materials._mv_read_transport(bad, compact._EncodingWork())

    def test_zero_one_multiple_restore_every_typed_ordered_byte_and_owner(self):
        for count in (0, 1, 3):
            with self.subTest(views=count):
                original = packet_fixture(count)
                before = ordered(original)
                prompt = materials.render_multi_view('Review every complete material.', original)
                restored = materials.read_prompt_multi_view(prompt)
                self.assertEqual(ordered(restored), before)
                self.assertEqual(ordered(original), before)
                self.assertEqual(len(envelope(original)['views']), count)
                self.assertEqual(ordered(restored['roles']), ordered(original['roles']))
                self.assertEqual(ordered(restored['materials']), ordered(original['materials']))

    def test_legacy_default_and_new_optin_remain_distinct_with_all_compact_schemas(self):
        original = packet_fixture(3)
        self.assertEqual(materials.DELIVERY, 'newrouge.b-route-compensation-review-delivery.v3')
        self.assertEqual(materials.TRANSPORT, 'newrouge.b-route-compensation-review-transport.v1')
        self.assertEqual(materials.MULTIVIEW_DELIVERY, 'newrouge.b-route-compensation-review-delivery.v4')
        self.assertEqual(materials.MULTIVIEW_TRANSPORT, 'newrouge.b-route-compensation-review-transport.v2')
        old = materials.render('Review all.', original)
        self.assertTrue(old.startswith(materials.DELIVERY + ' '))
        # Fixed old decoder/header bytes, independent of the fixture body.
        # Its short digest avoids embedding a second implementation/baseline.
        header = old.split('\n', 1)[0].encode('utf-8')
        self.assertEqual(len(header), 4009)
        self.assertEqual(hashlib.sha256(header).hexdigest(),
                         '256535c480652ccb4a0328ec527e7b13dae4c1165d5436e456428cd1a130dd1d')
        self.assertEqual(ordered(materials.read_prompt(old)), ordered(original))
        with self.assertRaises(codec.CodecError):
            materials.read_prompt_multi_view(old)
        new = materials.render_multi_view('Review all.', original)
        self.assertTrue(new.startswith(materials.MULTIVIEW_DELIVERY + ' '))
        with self.assertRaises(codec.CodecError):
            materials.read_prompt(new)
        value = {'r': {'$mvg_ref': 'x'}, '~r': [True, 1, -0.0, 'P0', 'D0', '雪\r\n']}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA, compact.RESIDUAL_SCHEMA):
            with self.subTest(compact_schema=schema):
                self.assertEqual(ordered(compact.loads(compact.dumps(value, schema=schema))), ordered(value))

    def test_complete_canonical_plan_rejects_omission_and_reordered_ordinals(self):
        original = packet_fixture(3)
        bad = envelope(original)
        removed = bad['views'].pop()
        j = removed['destination'][2]
        bad['packet_core']['materials']['documents'][j]['text'] = original['materials']['documents'][j]['text']
        self.reject(bad)
        bad = envelope(packet_fixture(3))
        bad['views'].reverse()
        for ordinal, view in enumerate(bad['views']):
            bad['packet_core']['materials']['documents'][view['destination'][2]]['text']['view'] = ordinal
        self.reject(bad)

    def test_indices_ownership_and_distinct_destinations_are_closed(self):
        original = envelope(packet_fixture(3))
        for index in (999, True, 1):
            with self.subTest(wrong_source=index, exact_type=type(index).__name__):
                bad = deepcopy(original)
                bad['views'][0]['source'][2] = index
                self.reject(bad)
        bad = deepcopy(original)
        bad['views'][1]['destination'] = list(bad['views'][0]['destination'])
        self.reject(bad)
        bad = envelope(packet_fixture(1))
        bad['packet_core']['materials']['frames'][0]['files'][0]['owner_uses'][0]['owner'] = 'foreign-owner'
        self.reject(bad)

    def test_placeholder_version_ordinal_and_original_raw_metadata_are_exact(self):
        original = envelope(packet_fixture(1))
        changes = [
            ('missing placeholder', lambda b: b['packet_core']['materials']['documents'][0].update(text='')),
            ('bool ordinal', lambda b: b['packet_core']['materials']['documents'][0]['text'].update(view=True)),
            ('old transport', lambda b: b.update(schema_version=materials.TRANSPORT)),
            ('old placeholder', lambda b: b['packet_core']['materials']['documents'][0]['text'].update(schema_version=materials.PLACEHOLDER)),
            ('raw byte count', lambda b: b['packet_core']['materials']['documents'][0].update(raw_bytes=1)),
            ('raw digest', lambda b: b['packet_core']['materials']['documents'][0].update(raw_digest='sha256:' + '0' * 64)),
        ]
        for label, change in changes:
            with self.subTest(change=label):
                bad = deepcopy(original)
                change(bad)
                self.reject(bad)

    def test_non_json2_document_is_preserved_complete_without_a_view(self):
        original = packet_fixture(1)
        document = original['materials']['documents'][0]
        document['text'] = document['text'].replace('\n', '\r\n')
        raw = document['text'].encode('utf-8')
        document['raw_bytes'], document['raw_digest'] = len(raw), codec.raw_digest(raw)
        row = original['materials']['frames'][0]['files'][0]
        row['raw_bytes'], row['raw_digest'], row['document_ref'] = len(raw), document['raw_digest'], document['raw_digest']
        refresh(original)
        self.assertEqual(envelope(original)['views'], [])
        prompt = materials.render_multi_view('Review all.', original)
        self.assertEqual(ordered(materials.read_prompt_multi_view(prompt)), ordered(original))

    def test_work_and_relation_capacity_fail_before_unfunded_index_allocation(self):
        work = compact._EncodingWork()
        work.remaining = 1
        with self.assertRaises(codec.CodecError):
            materials.render_multi_view('Review all.', packet_fixture(1), work=work)
        self.assertEqual(work.limit, compact.MAX_ENCODING_WORK)
        self.assertEqual(work.remaining, 1)
        original = packet_fixture(12)
        for frame in original['materials']['frames']:
            for row in frame['files']:
                row['roles'] = ['semantic:declared_source']
                for use in row['owner_uses']:
                    use['role'] = 'semantic:declared_source'
        refresh(original)
        materials.validate(original)
        count = (len(original['materials']['documents']) + len(original['materials']['frames'])
                 + sum(len(f['files']) for f in original['materials']['frames']) + 1)
        chars = sum(len(f['semantic_fields']['original_operation']['operation_id'])
                    for f in original['materials']['frames'])
        expected = (1024 * count + 8 * chars, 64 * count)
        events, entered = [], []
        real_metric, real_relations = compact._metric, materials._source_relations
        def observe_metric(size, nodes=1, depth=1, *args, **kwargs):
            result = real_metric(size, nodes, depth, *args, **kwargs)
            if kwargs.get('phase') == 'multiview.plan.relations':
                events.append((size, nodes))
            return result
        def observe_relations(*args, **kwargs):
            self.assertIn(expected, events)
            entered.append(None)
            return real_relations(*args, **kwargs)
        check_work = compact._EncodingWork()
        measured = compact._json_preflight(original, check_work)
        with patch.object(compact, '_metric', observe_metric), patch.object(materials, '_source_relations', observe_relations):
            self.assertEqual(materials._mv_select_views(original, check_work, (measured,)), [])
        self.assertEqual(len(entered), 1)
        entered.clear()
        def refuse_relation_space(*args, **kwargs):
            if kwargs.get('phase') in {'multiview.plan.relations', 'multiview.shape.relations'}:
                raise ValueError('neutral prospective relation capacity refusal')
            return real_metric(*args, **kwargs)
        capacity_work = compact._EncodingWork()
        capacity_metric = compact._json_preflight(original, capacity_work)
        with patch.object(compact, '_metric', refuse_relation_space), patch.object(materials, '_source_relations', observe_relations):
            with self.assertRaisesRegex(ValueError, 'prospective relation'):
                materials._mv_select_views(original, capacity_work, (capacity_metric,))
        self.assertEqual(entered, [])
        encoded = envelope(packet_fixture(1))
        with patch.object(compact, '_metric', refuse_relation_space), patch.object(materials, '_source_relations', observe_relations):
            with self.assertRaisesRegex(ValueError, 'prospective relation'):
                materials._mv_restore_transport_data(encoded, compact._EncodingWork())
        self.assertEqual(entered, [])

    def test_memoryerror_and_real_encoder_caller_mutation_do_not_retry_or_escape_checks(self):
        work = compact._EncodingWork()
        previous = object()
        work._residual_retained = previous
        calls = []
        original = packet_fixture(1)
        before = ordered(original)
        def allocation_failure(*args, **kwargs):
            calls.append(None)
            raise MemoryError('neutral injected atomic allocation failure')
        with patch.object(compact, '_ATOMIC_PRODUCER', allocation_failure):
            with self.assertRaises(MemoryError):
                materials.render_multi_view('Review all.', original, work=work)
        self.assertIs(work._residual_retained, previous)
        self.assertEqual(len(calls), 1)
        self.assertLess(work.remaining, work.limit)
        self.assertEqual(ordered(original), before)
        calls.clear()
        actual_encoder = compact._ATOMIC_PRODUCER
        caller_packet = packet_fixture(1)
        def mutate_after_genuine_encode(*args, **kwargs):
            calls.append(None)
            body = actual_encoder(*args, **kwargs)
            caller_packet['presentation']['policy_identity'] = 'sha256:' + '1' * 64
            return body
        with patch.object(compact, '_ATOMIC_PRODUCER', mutate_after_genuine_encode):
            with self.assertRaises(codec.CodecError):
                materials.render_multi_view('Review all.', caller_packet)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
