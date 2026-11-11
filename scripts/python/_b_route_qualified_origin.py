"""Finite original-proof bridge. Never relocates an original artifact or dispatches.

Only the complete retained R22 selection is supported. The separate target is an
empty-Task bootstrap of the same synthetic source, not arbitrary unit reuse.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat
import re
import os

import _b_route_codec as codec

REQUEST = 'newrouge.b-route-adoption-request.v2'
SUBJECT = 'newrouge.b-route-adoption-review-subject.v2'
CAPSULE = 'newrouge.b-route-qualified-origin-capsule.v1'
PROFILE = 'r22-m4-nx-original.v1'
TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
ORIGIN = TASK / 'nx'
SOURCE = 'docs/testing/story-2-5-controlled-acceptance/exclusive-resolution-v15.md'
SOURCE_DIGEST = 'sha256:7e5e1fe8aeb5937c70caa16aea2a9e1784a429c70c30a4f7f4d66601f1880061'
SOURCE_SET = 'docs/workflows/chapter3-source-set.json'
RATIONALE = 'Preserve the complete qualified synthetic semantics with fresh target identity.'
SOURCE_SUPPORT = {
    'logs/ci/2026-11-06/b-route-sources/s25-v15-exclusive-offline/prepare-02/prepare/source-manifest.json':
        'sha256:67f96a837974e89bdfdb97fdf4386b3d89d308375c4d161136677daeaefcc020',
    'logs/ci/2026-11-06/b-route-sources/s25-v15-exclusive-offline/prepare-02/prepare/source-blocks.json':
        'sha256:b0c661a2838a07a0b88fe32cd8a6cebc480cec06325f07fe89264f858799db97',
}
RUN = 'logs/ci/mvg-planning/m4'
RUN_DIGEST = 'sha256:8acee02c87466a40f70b4751dfb74d5fde51bbd7054c7a0072323cb46714cb85'
HANDOFF_DIGEST = 'sha256:caea69f6af1d0c7e34f1e098979e38065832e35d8de9219c664f6166d3707cbf'
QUALIFICATIONS = {
    'logs/ci/2026-11-07/story25-v18-qualification/verify-01/qualified.json':
        'sha256:af853ce0ea84812ae30c5cf94f04ef174c5da3046ad06da0b3289f0b0e7ba36a',
    'logs/ci/2026-11-07/story25-r40-formal-closeout/formal-acceptance.json':
        'sha256:06e2eec3f97a83678efee02bd696f91b02d95457dde6c9624b529631d47b052e',
    'logs/ci/2026-11-08/story26-r47-native-step5-close/result.json':
        'sha256:46c3570d116efcc4b16fcf837c2e1f3edf74c079e4fa9c262a4f8b80838ca782',
}


def need(value, label):
    if not value:
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE,
                                               codec.Stage.BUNDLE, expected=label, actual='blocked'))


def is_request(value):
    return type(value) is dict and value.get('schema_version') == REQUEST


def identity(path):
    from _b_route_frozen_native_reader import _safe
    path = _safe(Path(path).absolute(), directory=True)
    info = path.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_dev != 0 and info.st_ino != 0,
         'stable plain root identity')
    return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino}


def fixed_origin(profile=PROFILE):
    need(profile == PROFILE, 'finite original profile')
    # An installed CWT copy must not reinterpret its parent as the trusted Task.
    need(Path(__file__).absolute().parents[3] == TASK, 'retained Task-side bridge installation')
    from _b_route_frozen_native_reader import _safe
    values = {}
    for ref, expected in QUALIFICATIONS.items():
        path = _safe(TASK / ref)
        need(codec.raw_digest(path.read_bytes()) == expected, 'original qualification raw pin')
        values[str(path)] = expected
    return identity(ORIGIN), values


def target_source(snapshot):
    from _b_route_adoption import _task_context
    root = snapshot.root
    origin = identity(ORIGIN)
    target = identity(root)
    old = Path(origin['path'])
    need(root != old and not root.is_relative_to(old) and not old.is_relative_to(root),
         'separate target and original root')
    for name in ('r5', 'r10', 'r19', 'r22', 'r50', 'r52'):
        source_root = TASK / name
        need(not root.is_relative_to(source_root) and not source_root.is_relative_to(root),
             'target separate from retained producer/source checkouts')
    _task_context(snapshot)
    need(not snapshot.tasks and not snapshot.task_payloads, 'empty target Task context')
    registration = codec.strict_json_loads(snapshot.read(SOURCE_SET))
    need(registration == {'schema_version': 'chapter3.source-set.v1',
        'active_patterns': [SOURCE], 'active_sources': [SOURCE], 'retirements': []},
        'exact single synthetic registered target source')
    data = snapshot.read(SOURCE)
    need(codec.raw_digest(data) == SOURCE_DIGEST, 'same complete original synthetic bytes')
    return target, {'path': SOURCE, 'raw_digest': SOURCE_DIGEST, 'text': data.decode('utf-8')}


@contextmanager
def activity(profile=PROFILE):
    fixed_origin(profile)
    import _b_route_adoption as adoption
    from _mvg_capability_checkpoint import coordinator_lock
    from _mvg_capability_recovery import operation_lock
    run = adoption.safe_path(ORIGIN, RUN)
    raw = adoption.safe_path(ORIGIN, RUN + '/run.json').read_bytes()
    need(codec.raw_digest(raw) == RUN_DIGEST, 'unchanged actual original selected run')
    state = codec.strict_json_loads(raw)
    need(state.get('recovery', {}).get('store') == str(ORIGIN / 'logs/ci/mvg-recovery'),
         'original project-local recovery owner')
    with operation_lock(ORIGIN, state), coordinator_lock(run):
        yield raw


def capsule_path(operation_id):
    codec.validate_business_id(operation_id)
    key = hashlib.sha256(operation_id.encode('utf-8')).hexdigest()
    return 'logs/ci/b-route-origin-captures/' + key + '/capsule.json'


def capture_value(target, operation_id, profile=PROFILE, *, _retained_action=None):
    """Caller holds original activity; invoke the actual frozen native owner."""
    import _b_route_adoption as adoption
    codec.validate_business_id(operation_id)
    origin, qualified = fixed_origin(profile)
    snapshot = adoption.Snapshot(target)
    target_id, source = target_source(snapshot)
    state_raw = adoption.safe_path(ORIGIN, RUN + '/run.json').read_bytes()
    need(codec.raw_digest(state_raw) == RUN_DIGEST, 'original selected state raw')
    handoff_ref = {'path': RUN + '/handoff.json',
        'schema_version': 'newrouge.b-route-planning-handoff.v1', 'raw_digest': HANDOFF_DIGEST}
    with adoption._frozen_native_reader() as reader:
        if _retained_action is None:
            native = reader.capture_completed(ORIGIN, planner='mvg', run_id='m4',
                state_raw=state_raw, expected_handoff_ref=handoff_ref)
        else:
            from _b_route_retained_execution import native_from_action
            native = native_from_action(target, _retained_action, operation_id=operation_id)
        adoption._reader_capture_source(reader, native)
        reader.verify_capture(ORIGIN, native)
    content = native['handoff']['proposal']['content']
    prepared = native['prepared']
    constraints = prepared['inputs']['contract']['constraints']
    need(constraints == [{'path': SOURCE, 'format': 'text'}]
         and prepared['inputs']['contract']['contexts'] == [], 'original same-case semantic inputs')
    # No current nx Task join or current nx protection is read as target content.
    need(codec.raw_digest(adoption.safe_path(ORIGIN, SOURCE).read_bytes()) == SOURCE_DIGEST,
         'original source closure')
    value = {'schema_version': CAPSULE, 'operation_id': operation_id, 'profile': profile,
        'origin_identity': origin, 'target_identity': target_id,
        'qualification_files': qualified, 'source_set_digest': snapshot.files[SOURCE_SET],
        'source': source, 'source_support': deepcopy(SOURCE_SUPPORT), 'proposal': {'content': deepcopy(content)},
        'origin_admission': {'path': RUN + '/accepted-chain/admission-review.json',
            'raw_digest': 'sha256:65fa7d7a80754d6fee062a897dad508c09f9d43f129a83a34b182a5e8cc5ba10',
            'canonical_digest': codec.canonical_digest(native['handoff']['admission'])},
        'native_capture': {k: deepcopy(native[k]) for k in
            ('schema_version', 'run_identity', 'source_identity', 'files', 'directories', 'result_digest')},
        'prepared_identity': {'input_identity': prepared['input_identity'],
            'canonical_digest': codec.canonical_digest(prepared)}}
    snapshot.verify()
    return value, native


def verify_capsule(target, value):
    """Reconstruct the original capture locally; never reinterpret its root."""
    import _b_route_adoption as adoption
    need(set(value) == {'schema_version', 'operation_id', 'profile', 'origin_identity',
        'target_identity', 'qualification_files', 'source_set_digest', 'source', 'proposal',
        'origin_admission', 'native_capture', 'prepared_identity', 'source_support'}, 'closed origin capsule')
    need(value['schema_version'] == CAPSULE, 'known origin capsule schema')
    origin, qualifications = fixed_origin(value['profile'])
    need(value['origin_identity'] == origin and value['qualification_files'] == qualifications,
         'original pinned root and qualification')
    snap = adoption.Snapshot(target)
    target_id, source = target_source(snap)
    need(value['target_identity'] == target_id and value['source'] == source
         and value['source_set_digest'] == snap.files[SOURCE_SET], 'current target source/root binding')
    handoff_raw = adoption.safe_path(ORIGIN, RUN + '/handoff.json').read_bytes()
    need(codec.raw_digest(handoff_raw) == HANDOFF_DIGEST, 'original handoff raw')
    handoff = codec.strict_json_loads(handoff_raw)
    prepared = codec.strict_json_loads(adoption.safe_path(ORIGIN, handoff['original_prepared_ref']).read_bytes())
    native = {**deepcopy(value['native_capture']), 'handoff': handoff, 'prepared': prepared}
    with adoption._frozen_native_reader() as reader:
        adoption._reader_capture_source(reader, native)
        reader.verify_capture(ORIGIN, native)
    need(value['proposal'] == {'content': handoff['proposal']['content']}
         and value['origin_admission'] == {'path': RUN + '/accepted-chain/admission-review.json',
             'raw_digest': 'sha256:65fa7d7a80754d6fee062a897dad508c09f9d43f129a83a34b182a5e8cc5ba10',
             'canonical_digest': codec.canonical_digest(handoff['admission'])}
         and value['prepared_identity'] == {'input_identity': prepared['input_identity'],
             'canonical_digest': codec.canonical_digest(prepared)}, 'exact original selected semantics')
    need(value['source_support'] == SOURCE_SUPPORT, 'finite synthetic source provenance support')
    for name, expected in SOURCE_SUPPORT.items():
        need(codec.raw_digest(snap.read(name)) == expected, 'exact target synthetic source provenance')
    snap.verify()
    return native


def prepare_origin(root, *, operation_id, profile=PROFILE):
    """Zero-model metadata stage; creates only a new derived target capsule."""
    import _b_route_adoption as adoption
    import _b_route_sources as sources
    codec.validate_business_id(operation_id)
    root = Path(root).resolve()
    with activity(profile):
        value, _ = capture_value(root, operation_id, profile)
        # These two complete synthetic provenance documents are consumed by the
        # unchanged formal Bundle.source owner. They are not relocated native proof.
        from _b_route_adoption_review import write_once
        for name, expected in value['source_support'].items():
            source_raw = adoption.safe_path(ORIGIN, name).read_bytes()
            need(codec.raw_digest(source_raw) == expected, 'original synthetic provenance raw')
            write_once(root, name, source_raw)
        ref = capsule_path(operation_id)
        data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        path = adoption.safe_path(root, ref)
        if path.exists():
            need(path.read_bytes() == data, 'same original derived capsule; never replace')
        else:
            sources.write(path, value)
            with path.open('r+b') as stream:
                os.fsync(stream.fileno())
        need(path.read_bytes() == data, 'persisted complete derived capsule')
        verify_capsule(root, value)
    return {'status': 'origin_captured', 'capsule_ref': {'path': ref,
        'schema_version': CAPSULE, 'raw_digest': codec.raw_digest(data)},
        'formal_adoption': False, 'readiness': False, 'runtime_verified': False, 'default_b_enabled': False,
        'model_dispatches': 0, 'formal_story29_acceptance': False}


@contextmanager
def capture_target(root, material, review_ref):
    import _b_route_adoption as adoption
    import _b_route_protection as protection
    need(material['origin_profile'] == PROFILE and material['planner'] == 'mvg'
         and material['run_id'] == 'm4', 'whole fixed original selection only')
    need(not material['authority_refs'] and not material['lineage_refs'],
         'no arbitrary external semantic authorities in narrow bridge')
    alignment = material['identity_alignment']
    need(alignment['plan'] == {'mode': 'new'} and alignment['binding'] == {'mode': 'none'}
         and not alignment['tasks'] and all(r['mode'] == 'allocate' for family in
             ('requirements', 'flows') for r in alignment[family]), 'new whole plan with empty Task binding')
    class TargetSnapshot(adoption.Snapshot):
        def verify(self):
            super().verify()
            verify_capsule(self.root, self.origin_capsule)
            action = getattr(self, '_retained_native_action', None)
            if action is not None:
                from _b_route_retained_execution import verify_action
                verify_action(self.root, action, operation_id=self.origin_capsule['operation_id'])
    with activity(material['origin_profile']):
        snapshot = TargetSnapshot(root)
        cap = snapshot.ref(material['handoff_ref'])
        need(review_ref == material['handoff_ref'] and review_ref['schema_version'] == CAPSULE
             and review_ref['path'] == capsule_path(cap['operation_id']), 'one operation-owned derived capsule')
        from _b_route_retained_execution import capture_for_material, binding_path
        action = capture_for_material(snapshot.root, operation_id=cap['operation_id'],
                                      material=material, review_ref=review_ref)
        expected, native = capture_value(snapshot.root, cap['operation_id'], material['origin_profile'],
                                         _retained_action=action)
        need(cap == expected, 'verified real original producer result equals saved capsule')
        snapshot._retained_native_action = action
        if action is not None:
            # Private target authority pin; original public_subject still chooses
            # its unchanged positive semantic frame, never this support payload.
            snapshot.read(binding_path(cap['operation_id']))
        snapshot.origin_capsule = cap
        snapshot.handoff, snapshot.prepared = deepcopy(native['handoff']), deepcopy(native['prepared'])
        target_source(snapshot)
        for name, expected in cap['source_support'].items():
            need(codec.raw_digest(snapshot.read(name)) == expected, 'target synthetic provenance closure')
        snapshot.ref(material['protection_ref'])
        result = protection.verify_protection(snapshot.root, material['protection_ref']['path'])
        need(result['ok'] and result.get('capture_complete') is True, 'complete current target protection')
        snapshot.protection = codec.strict_json_loads(snapshot.read(material['protection_ref']['path']))
        snapshot.tree(str(Path(material['protection_ref']['path']).parent).replace('\\', '/'))
        snapshot.proof_paths = set(snapshot.files)
        adoption._committed(snapshot)
        need(snapshot.catalog is None and not snapshot.committed, 'fresh unpublished target plan namespace')
        snapshot.verify()
        yield snapshot


def public_subject(subject):
    """Positive typed rendering; no original prepared/protection/history blobs."""
    capsule = subject['origin_capsule']
    need(capsule['operation_id'] == subject['operation_id'], 'same capsule and model operation')
    need(subject['schema_version'] == SUBJECT and not subject['task_definitions']
         and not subject['related_records'] and subject['affected_catalog'] is None
         and not subject['authority_files'], 'isolated synthetic model disclosure scope')
    need(capsule['source']['path'] == SOURCE and capsule['source']['raw_digest'] == SOURCE_DIGEST
         and codec.raw_digest(capsule['source']['text'].encode('utf-8')) == SOURCE_DIGEST,
         'complete allowed synthetic source')
    need(subject['native_content'] == capsule['proposal']['content'], 'complete selected semantic content')
    from _b_route_adoption_projection import _validate_content
    _validate_content(subject['native_content'])
    need(subject['native_content']['evidence_source_refs'] == [{'owner': 'implementation_reference',
        'ref': SOURCE, 'files': [{'path': SOURCE, 'raw_digest': SOURCE_DIGEST}]}],
        'all selected source evidence belongs to allowed synthetic case')
    need(all(row['raw_base64'] is None and row['text'] is None
             for row in subject['target_before_files']), 'absent formal target before images')
    import _b_route_records as records
    for target in subject['preview']['targets']:
        need(records.validate_record(target['after_payload'], path=target['path']).ok,
             'closed formal target schema before model rendering')
    _check_host_values(subject)
    return {'schema_version': 'newrouge.b-route-adoption-model-subject.v2',
        'operation_id': subject['operation_id'], 'private_subject_digest': codec.canonical_digest(subject),
        'policy_identity': subject['policy_identity'], 'source': deepcopy(capsule['source']),
        'native_content': deepcopy(subject['native_content']),
        'identity_alignment': deepcopy(subject['request']['material']['identity_alignment']),
        'allocations': deepcopy(subject['preview']['allocations']),
        'target_before_files': deepcopy(subject['target_before_files']),
        'targets': deepcopy(subject['preview']['targets']),
        'origin_binding': {'profile': capsule['profile'],
            'capture_digest': capsule['native_capture']['result_digest'],
            'prepared_identity': deepcopy(capsule['prepared_identity'])},
        'target_binding': {'identity': deepcopy(capsule['target_identity']),
            'source_set_digest': capsule['source_set_digest'],
            'protection_digest': codec.canonical_digest(subject['protection']),
            'task_count': 0, 'catalog_before': None},
        'disclosure': {'complete_source': SOURCE_DIGEST,
            'complete_candidate': codec.canonical_digest(subject['native_content']),
            'complete_targets': codec.canonical_digest(subject['preview']['targets']),
            'opaque_proof_is_machine_verified_not_model_evidence': True}}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _strings(nested)


def bootstrap_records():
    """Exact first-publication governance; no Task joins or B activation."""
    return {
        'docs/planning/b-route/policy.v1.json': {
            'schema_version': 'newrouge.b-route-policy.v1', 'policy_id': 'policy',
            'policy_revision': 1, 'switch_boundary': {'default_route': 'A',
                'a_write_allowed': True, 'allowed_a_operations': [], 'authority_refs': []},
            'frozen_a_refs': []},
        'docs/planning/b-route/task-origins.v1.json': {
            'schema_version': 'newrouge.b-route-origins.v1', 'origins_id': 'task-origins',
            'revision': 1, 'tasks': [], 'frozen_legacy_refs': []}}


def check_bootstrap_targets(targets, allocations, *, complete=True):
    """Classify the plan plus two exact, absent-before governance targets."""
    records = bootstrap_records()
    plan = 'docs/planning/b-route/plans/' + allocations['plan_id'] + '/1.json'
    seen = set()
    for row in targets:
        path = row['path']
        need(path not in seen, 'distinct bootstrap targets')
        seen.add(path)
        need(row['before_raw_digest'] is None and row['verification_mode'] == 'immutable_bytes',
             'absent-before immutable bootstrap target')
        if path == plan:
            need(row['schema_version'] == 'newrouge.b-route-plan.v1',
                 'derived technical whole-plan target path')
        else:
            need(path in records and row['schema_version'] == records[path]['schema_version']
                 and codec.canonical_digest(row['after_payload']) == codec.canonical_digest(records[path]),
                 'exact empty-Task A-route bootstrap governance')
    if complete:
        need(seen == {plan, *records}, 'complete plan, policy and empty origins bootstrap batch')
    return {plan, plan + '#/proposal/content', *records,
            *[text for record in records.values() for text in _strings(record)]}


def _technical_allocations(subject):
    """Classify only the finite new-plan UUID4 grammar, never generation proof."""
    value = subject['preview']['allocations']
    need(type(value) is dict and set(value) == {'plan_id', 'plan_revision',
         'binding_revision', 'requirements', 'flows', 'task_definitions'}, 'closed new-plan allocations')
    need(type(value['plan_revision']) is int and value['plan_revision'] == 1
         and value['binding_revision'] is None and value['task_definitions'] == {},
         'fresh plan without Task or binding allocation')
    def generated(identity, prefix):
        need(type(identity) is str and re.fullmatch(prefix +
             r'[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}', identity) is not None,
             'classified UUID4 technical identity')
        return identity
    allowed = {generated(value['plan_id'], 'PLAN-')}
    content = subject['native_content']
    for family, prefix, rows, key in (
            ('requirements', 'RQ-', content['requirements'], 'requirement_id'),
            ('flows', 'FLOW-', content['definitions']['flows'], 'id')):
        domain = {row[key] for row in rows}
        mapping = value[family]
        need(len(domain) == len(rows) and type(mapping) is dict and set(mapping) == domain,
             'complete native allocation key denominator')
        identities = [generated(identity, prefix) for identity in mapping.values()]
        need(len(set(identities)) == len(identities), 'one-to-one technical identity map')
        allowed.update(identities)
    # build_frozen requires the complete batch. Here classify every rendered
    # row as well, including a saved subject before any semantic execution.
    allowed.update(check_bootstrap_targets(subject['preview']['targets'], value, complete=False))
    return allowed


def _check_host_values(subject):
    """Host-added strings must have explicit synthetic or technical provenance.

    Do not use a secret detector: an unknown extra rationale is not silently
    classified as safe. This narrow new-plan profile uses one fixed rationale.
    """
    import _b_route_schema_resources as schemas
    allowed = set(_strings(subject['native_content'])) | {RATIONALE, PROFILE,
        'new', 'none', 'allocate', 'reuse', 'immutable_bytes', 'raw', 'canonical'}
    for _, data in schemas.resources(auxiliary=True):
        allowed.update(_strings(codec.strict_json_loads(data)))
    allowed.update(_technical_allocations(subject))
    cap_path = subject['request']['material']['handoff_ref']['path']
    allowed.update({cap_path, cap_path + '#/proposal/content', cap_path + '#/origin_admission'})
    for value in _strings({'alignment': subject['request']['material']['identity_alignment'],
                          'targets': subject['preview']['targets']}):
        technical = (re.fullmatch(r'sha256:[0-9a-f]{64}', value)
                     or re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.+Z-]+', value))
        need(value in allowed or bool(technical), 'no unclassified host text in model subject')
