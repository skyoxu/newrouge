"""Task-only DRAFT. Historical authentication, never fresh admission.

MUST run in a held, pinned original-owner worker: _b_route_* imports below
must resolve to actual retained R52 files, without changing their __file__.
Do not import this module into the integrated owner process's module cache.
No network, model, native producer, mutation, fresh-empty or current-target
source admission occurs here. Original verify_saved/verify_capsule remain intact.
"""
from copy import deepcopy
from pathlib import Path
import ast
import base64
import hashlib
import sys

import _b_route_codec as codec
import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_qualified_origin as origin
import _b_route_records as records
import _planning_apply_journal as journal
from _planning_execution_binding import receipt_from, validate_execution
from _b_route_qualified_historical_archive import load_historical_snapshot

AUTH = 'newrouge.b-route-qualified-historical-auth.v1'
CLAIM = 'original_v2_bytes_and_archives_authenticated_for_history_only'
PROOF = 'newrouge.b-route-adoption-review-proof.v2'
OPERATION = 'newrouge.b-route-adoption-operation.v2'
REQUEST = 'newrouge.b-route-adoption-request.v2'
_MINT = object()


def need(ok, expected, actual='historical authentication mismatch'):
    review.require(ok, expected, actual)


class HistoricalAuthentication:
    """Opaque owned-worker result. No from_dict or caller-approved constructor.

    The parent transport must mint its own opaque token only from an actual
    completed held worker, bound to source pins, exact input and complete stdout;
    decoding an arbitrary saved JSON object is not a minting operation.
    """
    __slots__ = ('_value', '_files', '_roles', '_public', '_capsule', '_operation', '_root')

    def __init__(self, key, value, files, roles, public, capsule, operation, root):
        need(key is _MINT, 'actual historical verifier result only')
        self._value, self._files, self._roles = value, files, roles
        self._public, self._capsule, self._operation = public, capsule, operation
        self._root = root

    def public_subject(self):
        return deepcopy(self._public)

    def binding(self):
        return deepcopy(self._value)

    def checked_original(self, root, operation):
        need(origin.identity(Path(root).absolute()) == self._root,
             'same actual historical target root')
        need(type(operation) is dict and operation == self._operation,
             'same actual journal operation and frozen effects')
        return self


def _owner(authority):
    """Authority is an INSTALLED policy resource, never a caller argument.

    authenticate() loads it from this module's fixed adjacent resource. Final
    installation must pin it in new consumer policy_observations. The Task
    observed descriptor is a draft of that resource, not a completed old ticket.
    """
    directory = origin.TASK / 'r52' / 'scripts' / 'python'
    need(Path(review.__file__).absolute() == directory / '_b_route_adoption_review.py'
         and Path(origin.__file__).absolute() == directory / '_b_route_qualified_origin.py',
         'real retained original-owner paths; no relocated or mixed module family')
    need(set(authority) == {'schema_version', 'original_owner_root', 'source_schema_pins',
        'python_version', 'python_executable', 'python_executable_raw_digest', 'scope',
        'dependency_authority'}, 'closed installed historical owner authority')
    need(authority['schema_version'] == 'newrouge.b-route-qualified-historical-owner-authority.v1'
         and Path(authority['original_owner_root']) == directory.parents[1]
         and sys.version == authority['python_version']
         and Path(sys.executable) == Path(authority['python_executable']),
         'actual original owner/schema/interpreter authority')
    from _b_route_frozen_native_reader import _safe
    policy_tree=ast.parse((directory/'_b_route_adoption_review.py').read_text(encoding='utf-8-sig'))
    policy_fn=next(n for n in policy_tree.body if isinstance(n,ast.FunctionDef) and n.name=='policy_identity')
    source_names=next(ast.literal_eval(n.value) for n in policy_fn.body
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='names' for t in n.targets))
    import _b_route_schema_resources as original_schemas
    allowed={'scripts/python/'+name for name in source_names}
    allowed.update('docs/planning/b-route/schemas/'+name+'.schema.json'
        for name in original_schemas.FORMAL+original_schemas.AUXILIARY)
    allowed.add('docs/planning/b-route/schemas/commit-intent.schema.json')
    need(set(authority['source_schema_pins'])==allowed,
         'complete exact original policy source/schema paths only; no caller extra paths')
    pins = {}
    for rel, expected in authority['source_schema_pins'].items():
        codec.validate_reference_path(rel)
        name = _safe(directory.parents[1] / rel)
        need(codec.raw_digest(name.read_bytes()) == expected, 'retained original source/schema raw pin', rel)
        pins[str(name)] = expected
    executable = _safe(Path(sys.executable))
    need(codec.raw_digest(executable.read_bytes()) == authority['python_executable_raw_digest'],
         'actual interpreter raw identity')
    pins[str(executable)] = authority['python_executable_raw_digest']
    return pins


def _semantic_buffers(root, subject, buffers):
    """Original semantic verifier's exact prompt/schema/runtime on checked bytes.

    validate_execution is the real ORIGINAL owner function, not a caller receipt
    verifier. workspace is the real original path, and no runner is dispatched.
    """
    home = review.location(subject['operation_id'])
    need(buffers['w/prompt.txt'] == review.prompt(subject).encode('utf-8')
         and buffers['w/schema.json'] == review.raw(review.verdict_schema(subject))
         and buffers['request.txt'] == review.request_payload(subject).encode('utf-8'),
         'original complete public prompt, schema and full serialized request')
    execution = codec.strict_json_loads(buffers['execution.json'])
    need(execution.get('command') == review.runner_command(root, subject['operation_id']),
         'original exact runner command and actual original owner source path')
    output = buffers['w/output.json']
    receipt = receipt_from(execution)
    validate_execution(review.path(root, home + '/w'), execution, receipt, 'auto', output,
        prompt=review.request_payload(subject), schema=review.verdict_schema(subject),
        require_runtime=True, expected_reasoning_effort='high')
    evidence = receipt['model_identity_evidence'][0]
    need(evidence['model_provider'] == 'openai' and evidence['thread_id'] not in subject['native_threads'],
         'original official independent semantic review')
    review.check_verdict(subject, codec.strict_json_loads(output))
    return {'thread_id': evidence['thread_id'], 'turn_id': evidence['turn_id'],
        'protocol_digest': evidence['protocol_sha256'], 'runtime_configuration':
        {'model': evidence['model'], 'provider': evidence['model_provider'], 'reasoning_effort': 'high'},
        'provider_actual_model': 'unknown', 'physical_requests': 'unknown'}


def _capsule_history(root, subject, snapshot, archived, read):
    """Real original native archive plus authenticated historical target bytes.

    Deliberately does not call target_source or verify_capsule: those APIs make
    a fresh-empty/current-source assertion, which is not historical authority.
    No fake Snapshot, root, __file__, supplied native dictionary or fresh capture.
    """
    cap = subject['origin_capsule']
    need(set(cap) == {'schema_version', 'operation_id', 'profile', 'origin_identity',
        'target_identity', 'qualification_files', 'source_set_digest', 'source', 'proposal',
        'origin_admission', 'native_capture', 'prepared_identity', 'source_support'},
        'closed original capsule')
    need(cap['schema_version'] == origin.CAPSULE and cap['operation_id'] == subject['operation_id'],
         'same original v2 capsule and operation')
    original_root, qualifications = origin.fixed_origin(cap['profile'])
    target_id = origin.identity(root)
    need(cap['origin_identity'] == original_root and cap['qualification_files'] == qualifications
         and cap['target_identity'] == target_id, 'actual roots and original finite qualification pins')
    old = Path(original_root['path'])
    need(root != old and not root.is_relative_to(old) and not old.is_relative_to(root),
         'separate real target and original root')
    for name in ('r5', 'r10', 'r19', 'r22', 'r50', 'r52'):
        retained = origin.TASK / name
        need(not root.is_relative_to(retained) and not retained.is_relative_to(root),
             'historical target separate from retained source roots')
    # The archive loader authenticates report collection identity and old Git
    # boundary. Match that report to the actual target, never to a fake root.
    need(cap['source_set_digest'] == codec.raw_digest(archived[origin.SOURCE_SET]),
         'original archived SourceSet raw identity')
    need(codec.strict_json_loads(archived[origin.SOURCE_SET]) == {
        'schema_version': 'chapter3.source-set.v1', 'active_patterns': [origin.SOURCE],
        'active_sources': [origin.SOURCE], 'retirements': []}, 'original complete registered source')
    source = archived[origin.SOURCE]
    need(codec.raw_digest(source) == origin.SOURCE_DIGEST and cap['source'] == {
        'path': origin.SOURCE, 'raw_digest': origin.SOURCE_DIGEST, 'text': source.decode('utf-8')},
        'complete original semantic source bytes')
    triplet = {role: codec.strict_json_loads(archived[name]) for role, name in adoption.TRIPLET.items()}
    join = records.TaskJoinContext(**triplet)
    master, _ = join.indexes()
    need(not master and not triplet['back'] and not triplet['gameplay'],
         'authenticated original empty Task preimage, not current Task eligibility')
    handoff_raw = read(origin.ORIGIN / (origin.RUN + '/handoff.json'))
    need(codec.raw_digest(handoff_raw) == origin.HANDOFF_DIGEST, 'actual original handoff raw pin')
    handoff = codec.strict_json_loads(handoff_raw)
    prepared_raw = read(origin.ORIGIN / handoff['original_prepared_ref'])
    prepared = codec.strict_json_loads(prepared_raw)
    # Reconstruct only from actual original bytes and the saved original capsule.
    # The ORIGINAL reader revalidates all capture/source/run/file closure.
    native = {**deepcopy(cap['native_capture']), 'handoff': handoff, 'prepared': prepared}
    with adoption._frozen_native_reader() as reader:
        adoption._reader_capture_source(reader, native)
        reader.verify_capture(origin.ORIGIN, native)
    need(cap['proposal'] == {'content': handoff['proposal']['content']}
         and subject['native_content'] == handoff['proposal']['content']
         and subject['prepared'] == prepared
         and cap['origin_admission'] == {'path': origin.RUN + '/accepted-chain/admission-review.json',
            'raw_digest': 'sha256:65fa7d7a80754d6fee062a897dad508c09f9d43f129a83a34b182a5e8cc5ba10',
            'canonical_digest': codec.canonical_digest(handoff['admission'])}
         and cap['prepared_identity'] == {'input_identity': prepared['input_identity'],
            'canonical_digest': codec.canonical_digest(prepared)}, 'actual complete original selected semantics')
    need(cap['source_support'] == origin.SOURCE_SUPPORT, 'original finite synthetic source provenance')
    for name, expected in origin.SOURCE_SUPPORT.items():
        # Current retained originals are acceptable ONLY when exact original raw
        # pins match; changed/lost bytes need actual archived originals, not text
        # summaries. These exact two retained bytes exist in observed native02.
        data = archived.get(name)
        if data is None:
            try:data=read(review.path(root,name))
            except FileNotFoundError:
                need(False,{'required_original_path':name,'expected_original_raw_digest':expected},'missing')
        need(codec.raw_digest(data)==expected,
             {'required_original_path':name,'expected_original_raw_digest':expected},
             {'actual_raw_digest':codec.raw_digest(data)})
    need(subject['protection'] == snapshot, 'original subject bound to full authenticated protection archive')
    return native


def authenticate(root, operation_id):
    """Private worker entry, input is only actual root + operation ID.

    The current consumer MUST separately validate its full journal/index pair
    with its installed mixed-family journal and bind this raw operation under
    the existing business/current-before locks. Old journal.inventory is not run
    over new compensation families; original _operation_validate validates just
    its own exact v2 row without requiring mutable authority digest freshness.
    """
    root = Path(root).absolute()
    authority_path = Path(__file__).with_name('qualified-historical-owner-authority.v1.json')
    authority_raw = authority_path.read_bytes()
    authority = codec.strict_json_loads(authority_raw)
    pins = _owner(authority)
    observed = {}
    from _b_route_frozen_native_reader import _safe
    def read(name):
        name = _safe(Path(name).absolute())
        key = str(name)
        data = name.read_bytes()
        need(key not in observed or observed[key] == data, 'unchanged same-read historical buffer', key)
        observed[key] = data
        return data
    operation_path = journal._operation_ref(operation_id)
    operation_raw = read(review.path(root, operation_path))
    operation = codec.strict_json_loads(operation_raw)
    need(operation.get('schema_version') == OPERATION and operation.get('operation_id') == operation_id,
         'original adoption.v2 operation only')
    journal._operation_validate(root, operation)
    request = operation['frozen']['request']
    need(request['schema_version'] == REQUEST, 'exact original adoption.v2 request')
    home = review.location(operation_id)
    ref = request['host_review_ref']
    review.shape(ref, ('path', 'schema_version', 'raw_digest'), 'original host review ref')
    need(ref['path'] == home + '/review.json' and ref['schema_version'] == PROOF,
         'exact original operation-owned proof version/path')
    proof_raw = read(review.path(root, ref['path']))
    need(codec.raw_digest(proof_raw) == ref['raw_digest'], 'exact original proof raw bytes')
    proof = codec.strict_json_loads(proof_raw)
    review.shape(proof, ('schema_version', 'operation_id', 'subject_digest', 'policy_identity',
        'mode', 'evidence', 'files'), 'original host review proof')
    buffers = {name: read(review.path(root, home + '/' + name)) for name in review.support_names('semantic')}
    subject = codec.strict_json_loads(buffers['subject.json'])
    review.shape(subject, ('schema_version', 'operation_id', 'request', 'policy_identity', 'preview',
        'native_content', 'prepared', 'protection', 'related_records', 'task_definitions', 'authority_files',
        'target_before_files', 'affected_catalog', 'native_threads', 'native_turns', 'origin_capsule',
        'target_dependencies'), 'exact original qualified subject')
    need(subject['schema_version'] == origin.SUBJECT and subject['operation_id'] == operation_id
         and subject['policy_identity'] == review.policy_identity()
         and subject['request'] == review.request_body(request),
         'original policy, complete original request and private subject')
    need(type(subject['target_dependencies']) is dict, 'original immutable target dependency map')
    for name in subject['target_dependencies']:
        codec.validate_reference_path(name)
    material = request['material']
    cap_ref, protection_ref = material['handoff_ref'], material['protection_ref']
    need(material['origin_profile'] == origin.PROFILE and material['planner'] == 'mvg'
         and material['run_id'] == 'm4' and not material['authority_refs'] and not material['lineage_refs'],
         'original finite qualified request family')
    need(request['review_ref'] == cap_ref and cap_ref['path'] == origin.capsule_path(operation_id)
         and cap_ref['schema_version'] == origin.CAPSULE, 'actual original operation capsule reference')
    cap_raw = read(review.path(root, cap_ref['path']))
    need(codec.raw_digest(cap_raw) == cap_ref['raw_digest']
         and codec.strict_json_loads(cap_raw) == subject['origin_capsule'], 'original capsule raw/subject binding')
    protection_raw = read(review.path(root, protection_ref['path']))
    need(codec.raw_digest(protection_raw) == protection_ref['raw_digest'], 'original protection raw ref')
    snapshot, report, archived = load_historical_snapshot(root, protection_ref['path'])
    need(snapshot == codec.strict_json_loads(protection_raw)
         and protection_ref['schema_version'] == snapshot['schema_version']
         and report['collection']['root_real'] == str(root.resolve()), 'actual original historical target identity')
    # Pin exactly the authenticated original archive files, not later live Task.
    parent = protection_ref['path'].rsplit('/', 1)[0]
    read(review.path(root, parent + '/inventory.json'))
    for row in snapshot['raw_files']:
        if row['exists']:
            data = read(review.path(root, parent + '/' + row['artifact']))
            need(data == archived[row['path']], 'same authenticated archive bytes', row['path'])
    native = _capsule_history(root, subject, snapshot, archived, read)
    public = origin.public_subject(subject)  # actual ORIGINAL positive disclosure API
    need(proof['schema_version'] == PROOF and proof['operation_id'] == operation_id
         and proof['subject_digest'] == codec.canonical_digest(subject)
         and proof['policy_identity'] == subject['policy_identity'] and proof['mode'] == 'semantic'
         and review.machine_mode(subject) is None, 'original exact proof and mandatory semantic mode')
    evidence = _semantic_buffers(root, subject, buffers)
    need(codec.canonical_digest(evidence) == codec.canonical_digest(proof['evidence']),
         'original complete saved runtime replay, without new model')
    support = [{'path': home + '/' + name, 'schema_version': 'raw.bytes.v1',
        'raw_digest': codec.raw_digest(buffers[name])} for name in review.support_names('semantic')]
    need(support == proof['files'], 'exact original support order and raw identities')
    expected = deepcopy(subject['preview'])
    expected['request'] = request
    expected['authority_refs'] = sorted([*expected['authority_refs'], ref, *support], key=lambda row: row['path'])
    need(codec.canonical_digest(expected) == operation['frozen_digest'],
         'original complete frozen effects and review support binding')
    need(snapshot.get('capture_complete') is True and report.get('adoptable') is True,
         'original complete admissible protection capture')
    # Close original owner-observed body dependencies using historical bytes.
    # This map was part of the exact private subject bound by original runtime,
    # schema and frozen proof above; it is NOT a caller native proof dictionary.
    # Current Task/catalog/source changes cannot turn recorded old absences or
    # old bytes into a fresh admission predicate.
    target_dependencies = {}
    for name, expected_digest in subject['target_dependencies'].items():
        if expected_digest is None:
            target_dependencies[name] = {'original_raw_digest': None,
                'historical_observation': 'original_owner_private_subject_recorded_absence',
                'private_subject_raw_digest': codec.raw_digest(buffers['subject.json'])}
            continue
        if name in archived and codec.raw_digest(archived[name]) == expected_digest:
            target_dependencies[name] = {'original_raw_digest': expected_digest,
                'historical_observation': 'authenticated_protection_raw_archive',
                'protection_raw_digest': codec.raw_digest(protection_raw)}
            continue
        # Immutable support not in protection (e.g. the two SOURCE_SUPPORT files
        # and operation-owned retained execution support) may remain as their
        # exact original raw file. Pin actual original bytes, never invoke the
        # retained action's fresh-target admission verifier after Task changes.
        try:data=read(review.path(root,name))
        except FileNotFoundError:
            need(False,{'required_original_path':name,'expected_original_raw_digest':expected_digest},'missing')
        need(codec.raw_digest(data)==expected_digest,
             {'required_original_path':name,'expected_original_raw_digest':expected_digest},
             {'actual_retained_raw_digest':codec.raw_digest(data)})
        retained_path = 'logs/ci/b-route-retained-executions/' + hashlib.sha256(operation_id.encode('utf-8')).hexdigest() + '/binding.json'
        if name == retained_path:
            import _b_route_retained_execution as retained
            module_path = Path(retained.__file__).absolute()
            expected_source = authority['source_schema_pins'].get('scripts/python/_b_route_retained_execution.py')
            need(module_path == origin.TASK / 'r52/scripts/python/_b_route_retained_execution.py'
                 and expected_source is not None
                 and codec.raw_digest(module_path.read_bytes()) == expected_source,
                 'actual original retained-support archive decoder authority')
            support = retained.read_support(root, operation_id=operation_id, expected_raw_digest=expected_digest)
            need(support['raw_digest'] == expected_digest and support['reference'] == name,
                 'actual original operation-owned archive-only retained support')
            sv = support['value']
            need(sv['origin_capsule_digest'] == codec.canonical_digest(subject['origin_capsule'])
                 and sv['request_body_digest'] == codec.canonical_digest(review.request_body(request))
                 and sv['material'] == request['material'] and sv['review_ref'] == request['review_ref']
                 and sv['consumer_rule'] == expected_source
                 and sv['consumer_policy_identity'] == subject['policy_identity']
                 and sv['execution']['execution_epoch'] == native['source_identity'],
                 'retained support original capsule/request/producer/source-policy binding')
            ta = sv['target_authority']
            need(type(ta) is dict and set(ta) == {'identity','source','files','directories'}
                 and ta['identity'] == subject['origin_capsule']['target_identity']
                 and ta['source'] == subject['origin_capsule']['source']
                 and type(ta['files']) is dict and type(ta['directories']) is dict
                 and all(name in subject['target_dependencies']
                         and subject['target_dependencies'][name] == pin
                         for name, pin in ta['files'].items()),
                 'original recorded target authority is bound to historical private subject, not fresh state')
        target_dependencies[name] = {'original_raw_digest': expected_digest,
            'historical_observation': 'actual_retained_exact_original_raw_file'}
    # The old private byte identities remain mandatory host evidence. Public
    # history makes a different, explicit claim: complete positive public view.
    files = {home + '/' + name: data for name, data in buffers.items()}
    files[ref['path']] = proof_raw
    labels = {'subject.json': 'host:subject', 'w/prompt.txt': 'host:prompt', 'request.txt': 'host:request',
        'w/schema.json': 'host:schema', 'execution.json': 'host:execution', 'w/output.json': 'host:output',
        'review.json': 'host:proof'}
    roles = {home + '/' + name: label for name, label in labels.items()}
    public_raw = review.raw(public)
    binding = {'schema_version': AUTH, 'claim': CLAIM, 'operation_id': operation_id,
        'original_policy_identity': subject['policy_identity'], 'subject_schema': origin.SUBJECT,
        'operation_raw_digest': codec.raw_digest(operation_raw), 'request_raw_digest': operation['request_raw_digest'],
        'frozen_digest': operation['frozen_digest'], 'private_subject_raw_digest': codec.raw_digest(buffers['subject.json']),
        'private_subject_digest': codec.canonical_digest(subject), 'public_subject_raw_digest': codec.raw_digest(public_raw),
        'public_subject_digest': codec.canonical_digest(public), 'capsule_raw_digest': codec.raw_digest(cap_raw),
        'protection_raw_digest': codec.raw_digest(protection_raw), 'native_capture_digest': native['result_digest'],
        'original_proof_raw_digest': codec.raw_digest(proof_raw), 'original_runtime': evidence,
        'actual_target_identity': origin.identity(root), 'authority_raw_digest': codec.raw_digest(authority_raw),
        'historical_target_dependencies': target_dependencies,
        'private_raw_pins': {**pins, **{name: codec.raw_digest(data) for name, data in observed.items()}},
        'native_file_pins': deepcopy(native['files']), 'native_directory_pins': deepcopy(native['directories'])}
    need(authority_path.read_bytes() == authority_raw, 'same installed historical authority resource')
    need(_owner(authority) == pins, 'same original source/schema/interpreter at historical auth close')
    for name, data in observed.items():
        need(_safe(Path(name)).read_bytes() == data, 'unchanged exact historical checked buffer', name)
    return HistoricalAuthentication(_MINT, binding, files, roles, public, deepcopy(subject['origin_capsule']),
                                    deepcopy(operation), origin.identity(root))
