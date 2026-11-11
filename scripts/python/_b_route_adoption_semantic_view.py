"""Positive, versioned semantic evidence; no qualification, reads or authority grant."""
import base64
from copy import deepcopy
import re
import _b_route_codec as codec

PROFILE = 'expanded-semantics.v3'
SUBJECT = 'newrouge.b-route-adoption-review-subject.v3'
PUBLIC = 'newrouge.b-route-adoption-model-subject.v3'
VERDICT = 'newrouge.b-route-adoption-review-verdict.v3'
PROOF = 'newrouge.b-route-adoption-review-proof.v3'

def extract_design_history(raw, capsule):
    """Exact positive semantic nodes from the authenticated original proposal."""
    from _b_route_qualified_origin import ORIGIN, RUN, PROFILE as ORIGIN_PROFILE
    path = str(ORIGIN / RUN / 'accepted-chain/proposal.json')
    require(capsule['profile'] == ORIGIN_PROFILE
            and codec.raw_digest(raw) == capsule['native_capture']['files'].get(path),
            'original selected proposal exact captured raw')
    proposal = codec.strict_json_loads(raw);provenance = proposal['provenance']
    require(provenance['kind'] == 'model_draft' and proposal['content'] == capsule['proposal']['content']
            and proposal['input_identity'] == capsule['prepared_identity']['input_identity'],
            'actual model-draft selection and same complete final candidate')
    chain = provenance['draft_chain'];identities = [];rows = []
    require(type(chain) is list and len(chain) >= 2, 'ordered original drafts with final synthesis')
    for index, draft in enumerate(chain):
        require(draft['schema_version'] == 'newrouge.b-route-planning-draft.v1'
                and draft['input_identity'] == proposal['input_identity'] and draft['ordinal'] == index + 1
                and draft['parent_draft_identities'] == identities, 'actual original ordered parent correspondence')
        identity = codec.canonical_digest(draft)
        rows.append({'source_pointer': '/provenance/draft_chain/' + str(index), 'draft_identity': identity,
            **{k: deepcopy(draft[k]) for k in ('schema_version', 'input_identity', 'stage', 'ordinal', 'parent_draft_identities')}})
        identities.append(identity)
    require(chain[-1]['stage'] == 'synthesis' and provenance['final_draft_identity'] == identities[-1]
            and chain[-1]['content'] == proposal['content'], 'same complete final synthesis')
    first = chain[0]['content'];profile = first['launch_message_profile']
    require(set(profile) == {'name', 'version', 'owner', 'launch', 'launch_bindings', 'framing',
                'messages', 'ordering', 'independent_observations'} and profile['name'] == 'exclusive-reward-jsonl'
            and profile['version'] == 1, 'closed selected synthetic launch/message profile')
    choices = first['design_choices']['selected_choices']
    require(type(choices) is list and len(choices) >= 3 and type(choices[0]) is str and type(choices[2]) is str,
            'complete exact profile and independent observer choice text')
    commands = proposal['content']['definitions']['commands']
    profile_commands = [(i, r) for i, r in enumerate(commands) if r['id'] == 'profile-and-hooks']
    observers = [(i, r) for i, r in enumerate(commands) if r['id'] == 'render-and-probe-adapter']
    require(len(profile_commands) == len(observers) == 1 and profile['launch'] in profile_commands[0][1]['responsibility'],
            'current complete selected launch and distinct observer command')
    return {'schema_version': 'newrouge.b-route-selected-design-history.v1',
        'document': {'origin_relative_path': RUN + '/accepted-chain/proposal.json',
            'raw_digest': codec.raw_digest(raw), 'raw_bytes': len(raw), 'input_identity': proposal['input_identity']},
        'drafts': rows, 'final_draft_identity': identities[-1],
        'fragments': [
            {'source_pointer': '/provenance/draft_chain/0/content/design_choices/selected_choices/0', 'value': choices[0]},
            {'source_pointer': '/provenance/draft_chain/0/content/design_choices/selected_choices/2', 'value': choices[2]},
            {'source_pointer': '/provenance/draft_chain/0/content/launch_message_profile', 'value': deepcopy(profile)}],
        'current_correspondence': {'profile_command_pointer': '/definitions/commands/' + str(profile_commands[0][0]),
            'observer_command_pointer': '/definitions/commands/' + str(observers[0][0]),
            'final_content_equals_current_native': True},
        'scope': 'selected semantic fragments and ordered identities; not complete draft bodies or host approval'}

def collect_design_history(capsule):
    """Owner-time read, never public-render-time IO; original capture pins it."""
    from _b_route_qualified_origin import ORIGIN, RUN
    from _b_route_frozen_native_reader import _safe
    return extract_design_history(_safe(ORIGIN / RUN / 'accepted-chain/proposal.json').read_bytes(), capsule)

def positive_history(value):
    require(set(value) == {'schema_version', 'document', 'drafts', 'final_draft_identity', 'fragments',
                'current_correspondence', 'scope'}
            and value['schema_version'] == 'newrouge.b-route-selected-design-history.v1', 'closed selected history view')
    require(set(value['document']) == {'origin_relative_path', 'raw_digest', 'raw_bytes', 'input_identity'},
            'only original proposal technical observation')
    from _b_route_qualified_origin import RUN
    require(value['document']['origin_relative_path'] == RUN + '/accepted-chain/proposal.json'
            and type(value['document']['raw_bytes']) is int and value['document']['raw_bytes'] > 0,
            'one positive original proposal locator')
    _path(value['document']['origin_relative_path']);_digest(value['document']['raw_digest'])
    _digest(value['document']['input_identity'])
    identities = []
    for index, row in enumerate(value['drafts']):
        require(set(row) == {'source_pointer', 'draft_identity', 'schema_version', 'input_identity', 'stage',
                    'ordinal', 'parent_draft_identities'}
                and row['source_pointer'] == '/provenance/draft_chain/' + str(index)
                and row['schema_version'] == 'newrouge.b-route-planning-draft.v1'
                and row['input_identity'] == value['document']['input_identity']
                and row['stage'] in {'batch', 'synthesis'}
                and row['ordinal'] == index + 1 and row['parent_draft_identities'] == identities,
                'complete ordered selected history identities')
        identities.append(_digest(row['draft_identity']))
    require(identities and identities[-1] == value['final_draft_identity'], 'exact final selected history identity')
    expected = ['/provenance/draft_chain/0/content/design_choices/selected_choices/0',
                '/provenance/draft_chain/0/content/design_choices/selected_choices/2',
                '/provenance/draft_chain/0/content/launch_message_profile']
    require(len(value['fragments']) == 3 and all(set(row) == {'source_pointer', 'value'}
            and row['source_pointer'] == pointer for row, pointer in zip(value['fragments'], expected)),
            'complete exact semantic profile/observer fragments')
    profile = value['fragments'][2]['value']
    require(set(profile) == {'name', 'version', 'owner', 'launch', 'launch_bindings', 'framing', 'messages',
                'ordering', 'independent_observations'}, 'no private profile carrier')
    require(set(profile['independent_observations']) == {'readUI', 'readJ', 'startup_identity'},
            'complete independent observation subtree')
    for message in profile['messages']:
        require({'channel', 'type', 'fields'} <= set(message) <= {'channel', 'type', 'fields', 'binding',
                    'op_values', 'phase_values', 'ui_values'} and message['channel'] in {'Q', 'C'},
                'positive selected wire-profile message, no protocol/capture carrier')
    require(set(value['current_correspondence']) == {'profile_command_pointer', 'observer_command_pointer',
                'final_content_equals_current_native'} and value['current_correspondence']['final_content_equals_current_native'] is True,
            'separate exact current correspondence, not historical approval')
    return deepcopy(value)

def require(ok, label):
    if not ok:
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE,
                                               codec.Stage.BUNDLE, expected=label, actual='blocked'))

def _digest(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'typed technical digest')
    return value

def _path(value):
    codec.validate_reference_path(value)
    require(not any(part.casefold() in {'.codex', '.aws', '.ssh', 'sessions', 'archived_sessions',
                'auth.json', 'credentials', 'credentials.json', 'credentials.toml'}
                or part.casefold().startswith('.env') for part in value.split('/')), 'no private disclosure locator')
    return value

def source_set(subject):
    from _b_route_qualified_origin import SOURCE, SOURCE_SET
    row = subject['registered_source_set']
    require(type(row) is dict and set(row) == {'path', 'raw_digest', 'raw_base64'}
            and row['path'] == SOURCE_SET, 'closed actual registered source observation')
    try:
        raw = base64.b64decode(row['raw_base64'], validate=True)
    except (ValueError, TypeError) as error:
        require(False, 'complete source-set raw encoding')
    require(len(raw) <= 32768 and codec.raw_digest(raw) == _digest(row['raw_digest'])
            == subject['origin_capsule']['source_set_digest']
            == subject['target_dependencies'][SOURCE_SET], 'same actual target source-set raw binding')
    value = codec.strict_json_loads(raw)
    require(value == {'schema_version': 'chapter3.source-set.v1', 'active_patterns': [SOURCE],
                     'active_sources': [SOURCE], 'retirements': []}, 'whole finite synthetic source set')
    return {'path': SOURCE_SET, 'raw_digest': row['raw_digest'], 'value': value}

def protection_scope(subject):
    """Metadata/literal inventories only; never protected raw bodies or protocol blobs."""
    p = subject['protection']
    require(p['stable'] is True and p['capture_complete'] is True and p['diagnostics'] == [],
            'complete original protection observation')
    authorization = p['authorization']
    inventory = p['inventory']
    require(set(inventory) == {'artifact', 'raw_digest', 'content_identity', 'adoptable', 'diagnostics'}
            and inventory['adoptable'] is True and inventory['diagnostics'] == [], 'closed actual protection inventory identity')
    _path(inventory['artifact']);_digest(inventory['raw_digest']);_digest(inventory['content_identity'])
    require(p['verification_limits'] == [
        'Read-only candidate, not a formal protection baseline or frozen-A policy.',
        'Missing historical debug attachments remain unresolved observations, not operation prerequisites; old done never satisfies new obligations.',
        'No committed reverse-governance proof is implemented; every Task candidate is blocked.',
        'Double-read observations do not isolate against external concurrent writers.',
        'Receipt target projections, policy bootstrap, journal and publication are not implemented.'],
        'unchanged technical collector limits, no unknown body disclosure')
    require(authorization == {'formal_protection_baseline': False, 'frozen_a': False, 'write': False,
                'policy_bootstrap': False, 'target_projection_verified': False}, 'original collector is not a grant')
    require(p['tasks'] == [] and p['cumulative'] == [] and p['historical_inventory'] is None
            and p['triplet']['counts'] == {'master': 0, 'back': 0, 'gameplay': 0}, 'separate observed empty scope sets')
    require(p['triplet']['documents'] == {'master': {'master': {'tasks': []}}, 'back': [], 'gameplay': []},
            'actual complete empty Task triplet literals')
    require(p['frozen_a'] == {'task_set': 'verified-empty', 'candidate_count': 0, 'candidates': [],
                            'classification_authorized': False}, 'empty frozen-A observation, no inferred A qualification')
    rows = []
    for row in p['raw_files']:
        require(set(row) == {'path', 'exists', 'raw_digest', 'canonical_digest', 'size_bytes', 'artifact', 'roles'}
                and type(row['exists']) is bool and type(row['roles']) is list
                and all(type(role) is str and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,127}', role)
                        for role in row['roles']), 'closed protected-file metadata')
        _path(row['path'])
        if row['exists']:
            _digest(row['raw_digest'])
            require(type(row['size_bytes']) is int and row['size_bytes'] >= 0, 'observed file size')
        else:
            require(row['raw_digest'] is None and row['canonical_digest'] is None
                    and row['size_bytes'] is None and row['artifact'] is None, 'explicit absent protected file')
        if row['canonical_digest'] is not None:
            _digest(row['canonical_digest'])
        rows.append({key: deepcopy(row[key]) for key in
                     ('path', 'exists', 'raw_digest', 'canonical_digest', 'size_bytes', 'roles')})
    require(len({r['path'] for r in rows}) == len(rows), 'complete unique protected-file inventory')
    legacy = p['legacy_manifest_requirement']
    require(legacy['schema_version'] == 'newrouge.b-route-legacy-manifest-requirement.v3'
            and legacy['state'] == 'initially_absent' and legacy['reason'] == 'governed_originals',
            'actual initial legacy-manifest state')
    b = legacy['governed_boundary']
    from _b_route_qualified_origin import SOURCE
    require(b['root_real'] == subject['origin_capsule']['target_identity']['path']
            and b['source_members'] == [SOURCE] and b['manifest_directory_exists'] is False
            and b['manifest_members'] == [], 'same target source boundary and actual missing legacy namespace')
    for path, digest in b['original_raw_digests'].items():
        _path(path)
        if digest is not None:
            _digest(digest)
    for path in b['owner_records']:
        _path(path)
    boundary = {key: deepcopy(b[key]) for key in ('root_real', 'head', 'anchors', 'reachable_commit_ids',
                'controls_absent', 'source_members', 'manifest_directory_exists', 'manifest_members',
                'owner_records', 'original_raw_digests')}
    return {'schema_version': p['schema_version'], 'inventory': deepcopy(p['inventory']),
        'protected_files': rows, 'triplet_documents': deepcopy(p['triplet']['documents']),
        'triplet_counts': deepcopy(p['triplet']['counts']), 'tasks': [], 'cumulative': [],
        'frozen_a': deepcopy(p['frozen_a']), 'historical_inventory': None,
        'legacy_manifest_requirement': {'schema_version': legacy['schema_version'], 'state': legacy['state'],
            'reason': legacy['reason'], 'original_observation_digest': legacy['original_observation_digest'],
            'governed_boundary': boundary},
        'authorization': deepcopy(authorization), 'verification_limits': deepcopy(p['verification_limits'])}

def expand(subject, base):
    from _b_route_adoption_projection import FIELDS, RETAINED_IN_NATIVE_PROOF, project_content, project_retained_fields
    require(subject['schema_version'] == SUBJECT
            and subject['request'].get('review_profile') == PROFILE, 'explicit v3 semantic review selection')
    plan_rows = [r for r in subject['preview']['targets'] if r['schema_version'] == 'newrouge.b-route-plan.v1']
    require(len(plan_rows) == 1, 'one actual formal plan target')
    plan = plan_rows[0]['after_payload'];ref = subject['request']['material']['handoff_ref']
    expected = {'owner': 'planning_proof', 'ref': ref['path'] + '#/proposal/content',
                'files': [{'path': ref['path'], 'raw_digest': ref['raw_digest']}]}
    require(plan['native_candidate_ref'] == expected, 'exact original retained native candidate locator')
    projected = project_content(subject['native_content'], subject['preview']['allocations'])
    require(all(plan[name] == projected[name] for name in FIELDS), 'all ten actual projected inline fields')
    retained = {name: deepcopy(subject['native_content'][name]) for name in sorted(RETAINED_IN_NATIVE_PROOF)}
    value = deepcopy(base);value['schema_version'] = PUBLIC
    value['plan_storage'] = {'plan_path': plan_rows[0]['path'], 'plan_schema': plan['schema_version'],
        'inline_field_names': list(FIELDS), 'native_candidate_ref': deepcopy(expected),
        'retained_native_fields': retained,
        'retained_fields_with_host_identity_interpretation': project_retained_fields(subject['native_content'], subject['preview']['allocations']),
        'formal_bundle_read_automatically_expands_native_fields': False,
        'complete_semantics_requires_available_verified_native_reference': True}
    value['review_scope'] = {'source_set': source_set(subject), 'protection': protection_scope(subject),
        'supplied_authority_files': [], 'supplied_host_lineage_refs': [],
        'governance_effect_boundary': 'recorded_policy_proposal_not_runtime_activation_or_A_qualification',
        'empty_operation_list_has_no_implemented_deny_all_or_wildcard_interpretation': True}
    value['origin_evidence_role'] = {'opaque_proof_is_machine_verified_not_model_evidence': True,
        'model_must_review_complete_visible_source_candidate_and_target_semantics': True,
        'model_is_not_asked_to_authenticate_private_capture_hashes_or_authorize_writes': True}
    value['current_selection'] = {'previous_formal_plan_ref': deepcopy(plan['lineage']['previous_plan_ref']),
        'selected_design_history': positive_history(subject['selected_design_history']),
        'prior_draft_documents_supplied_in_full': False,
        'native_draft_wording_is_preserved_not_verified_historical_approval': True,
        'semantic_dependency_on_unprovided_text_remains_blocking': True}
    return value
