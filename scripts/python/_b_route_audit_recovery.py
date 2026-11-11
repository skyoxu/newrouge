"""Read-only extraction reuse checks and conservative successor resource planning.

No dispatch, native audit completion, permit, refund, authority migration or
terminal-state inference is performed. A versioned outer controller and complete
per-phase proof integration are required before a successor comparison can run.
"""
from copy import deepcopy
from pathlib import Path

import _b_route_codec as codec
import _b_route_source_audit as audit
import _b_route_sources as sources


# The exact reviewed host-only repair commit 1797e4d1 / isolated 5b3f1641.
# This does not authorize arbitrary tool changes or a different semantic policy.
HOST_REPAIR = {
    'scripts/python/_planning_skill_common.py': (
        'sha256:87033aad915e1ebd3fc40f4e1eeaf74edbb42680faff0a9be40be33745aba93a',
        'sha256:f44235ae7dc1bd8c7078abf260b6a4262a76a59c282997fb9db37114fc452e19'),
    'scripts/python/_codex_app_server.py': (
        'sha256:ba11f5bc6d62202a0701c728fe89f88ff9054090b62e1479c562a439a85c9e26',
        'sha256:81af09f9949f28338d21912a8906d85c6c1a00abf448c79ce61a77e3d6781dcd'),
}


def compatible_phase_identities(original, current):
    """Require exact semantics/environment and only the pinned host repair delta."""
    codec.validate_json_value(original)
    codec.validate_json_value(current)
    before, after = deepcopy(original), deepcopy(current)
    old_tools, new_tools = before.pop('tools', None), after.pop('tools', None)
    sources.require(type(old_tools) is dict and type(new_tools) is dict and
        set(old_tools) == set(new_tools), 'recovery.tools', 'identical complete tool path domain')
    sources.require(before == after and before.get('expected_reasoning_effort') == 'high',
        'recovery.phase-identity', 'exact high model/rules/prompt/schema/packages/Python/input policy')
    changes = {}
    for path in old_tools:
        pair = old_tools[path], new_tools[path]
        if pair[0] != pair[1]:
            sources.require(path in HOST_REPAIR and pair == HOST_REPAIR[path],
                'recovery.host-repair', 'only exact independently reviewed host IO repair hashes', path)
            changes[path] = {'before': pair[0], 'after': pair[1]}
    return {'original_identity_digest': codec.canonical_digest(original),
        'current_identity_digest': codec.canonical_digest(current),
        'host_changes': changes, 'semantic_identity_unchanged': True,
        'provider_actual_model': 'unknown', 'provider_actual_reasoning': 'unknown'}


def validate_completed_extraction(obs, *, prefix, expected_bundle, current_identity):
    """Verify original extraction directly without inventing a complete prior audit.

    The outer controller must pin the retained original manifest/authority and
    build expected_bundle from current native accounted inputs before calling.
    The observation root is the original execution root: original invocation,
    raw request/schema/prompt, protocol/input binding, output, budget and permit
    are verified there, without relocation or rewriting captured command paths.
    """
    codec.validate_reference_path(prefix + '/input.json')
    original = obs.json(prefix + '/input.json')
    identity = obs.json(prefix + '/identity.json')
    request = obs.json(prefix + '/request.json')
    description = obs.json(prefix + '/runner.json')
    sources.require(original == expected_bundle and len(original['files']) == 1,
        'recovery.input', 'exact currently accounted one-file source bundle')
    sources.require(request['stage'] == 'audit' and request['expected_model'] == identity['expected_model']
        and description.get('requested_reasoning_effort') == 'high',
        'recovery.original-request', 'original audit with captured high runner configuration')
    compatibility = compatible_phase_identities(identity, current_identity)
    guidance = identity.get('citation_guidance')
    sources.require(guidance == request.get('citation_guidance') and identity['rules'] == audit.RULES
        and identity['prompt_identity'] == audit.producer_prompt_identity(guidance, identity.get('producer_schema_policy'))
        and identity['schema_identity'] == audit.canonical_sha([audit.output_schema(p) for p in ('extract', 'compare')]),
        'recovery.semantic-contract', 'original guidance and current semantic rules/prompt/schema')
    audit.validate_runner_description(description)
    expected = audit.phase_input('extract', original, file=original['files'][0], citation_guidance=guidance)
    output = audit.verify_step(obs, prefix, {'name': 'extract-000001'}, expected, identity)
    obs.verify()
    return {'extraction': output, 'original_identity': identity,
        'compatibility': compatibility, 'original_prefix': prefix,
        'extraction_identity': codec.canonical_digest(output),
        'old_comparison_outcome': 'unknown', 'complete_audit': False,
        'new_dispatch_authority': False, 'model_calls': 0}


def successor_budget(*, new_requests=1, capability_actual=None):
    """Plan from verified v15 liabilities; do not allocate or mutate any budget.

    Original 54 logical paid/unknown slots and all old permits remain charged.
    One comparison is preferred. Two requests describe the fallback only when
    extraction cannot safely be reused. Native Cap96 and MVG192 are unchanged.
    """
    sources.require(type(new_requests) is int and new_requests in (1, 2),
        'recovery.new-requests', 'one comparison or explicitly justified two-phase fallback')
    charged = 54 + new_requests
    max_cap = 290 - charged - 192
    result = {'campaign_limit': 290, 'old_paid_or_unknown': 54,
        'old_guard_occupancy': 240, 'outside_headroom': 50,
        'new_requests_ceiling': new_requests, 'paid_or_unknown_after_ceiling': charged,
        'comparison_timeout_seconds': 300, 'per_request_seconds_reserved': 330,
        'new_active_seconds_ceiling': 330 * new_requests,
        'native_capability_ceiling': 96, 'native_mvg_ceiling': 192,
        'max_qualified_capability_actual_for_full_mvg': max_cap,
        'old_unknown_released': False, 'new_dispatch_authority': False}
    if capability_actual is not None:
        sources.require(type(capability_actual) is int and 0 <= capability_actual <= 96,
            'recovery.capability-actual', 'verified nonnegative actual native Cap count at most96')
        total = charged + capability_actual + 192
        result.update(full_mvg_fundable=total <= 290,
            full_mvg_campaign_ceiling=total, required_topup=max(0, total - 240),
            capability_actual=capability_actual)
    return result


REUSE_SCHEMA = 'newrouge.b-route-completed-extraction-reuse.v1'
ORIGINAL_COORDINATOR = {
    'scripts/python/_b_route_source_audit.py': 'sha256:c726d6667caff28dc9d1b9b72790f784b109376340dac1ad0563da6f3e1f68a7',
    'scripts/python/_b_route_sources.py': 'sha256:bc418655699be7c8cc39de3cfe039e8ffb657eb5acd8ffb1877c277003a6171f',
}


def coordinator_transition(original, current, *, runner_ref):
    """Bind the v4 proof extension separately from the unchanged model contract.

    Existing two-file compatibility stays strict. This explicit version permits
    only the original pinned coordinator -> this installed coordinator, this
    recovery verifier, and one frozen runner entry. All full actual identities
    remain recorded; absolute current source paths are not relabeled in proof.
    """
    before, after = deepcopy(original), deepcopy(current)
    old_tools, new_tools = before.pop('tools'), after.pop('tools')
    sources.require(before == after and before.get('expected_reasoning_effort') == 'high',
        'recovery.v4-contract', 'same complete high model/producer/environment contract')
    code_root = Path(__file__).resolve().parents[2]
    def logical(path):
        item = Path(path)
        return item.relative_to(code_root).as_posix() if item.is_absolute() and item.is_relative_to(code_root) else path
    normalized = {}
    for path, value in new_tools.items():
        key = logical(path)
        # The conservative import closure can include both the original root's
        # unchanged copy and the installed copy. Keep both actual paths in the
        # returned identity; coalesce only equal pinned original bytes here.
        if key in normalized:
            sources.require(normalized[key] == value == old_tools.get(key),
                'recovery.v4-tools', 'exact unchanged counterpart dependency bytes')
        normalized[key] = value
    expected = dict(old_tools)
    for path, pair in HOST_REPAIR.items():
        sources.require(old_tools.get(path) == pair[0], 'recovery.v4-host', 'pinned original host IO source', path)
        expected[path] = pair[1]
    for path, original_hash in ORIGINAL_COORDINATOR.items():
        sources.require(old_tools.get(path) == original_hash, 'recovery.v4-coordinator', 'pinned original coordinator', path)
        expected[path] = codec.raw_digest((code_root/path).read_bytes())
    helper = 'scripts/python/_b_route_audit_recovery.py'
    expected[helper] = codec.raw_digest((code_root/helper).read_bytes())
    codec.validate_reference_path(runner_ref)
    sources.require(runner_ref.startswith('logs/ci/') and runner_ref.endswith('/codex_isolated_model_runner.py')
        and runner_ref not in old_tools, 'recovery.v4-runner', 'new explicitly frozen audit runner entry')
    sources.require(runner_ref in normalized, 'recovery.v4-runner', 'complete runner entry bytes captured')
    expected[runner_ref] = normalized[runner_ref]
    sources.require(normalized == expected, 'recovery.v4-tool-closure', 'only exact host/coordinator/runner extension')
    return {'schema_version': 'newrouge.b-route-audit-phase-transition.v4',
        'original_identity_digest': codec.canonical_digest(original),
        'current_identity_digest': codec.canonical_digest(current),
        'actual_current_tools': current['tools'], 'model_visible_contract_unchanged': True}


def verify_reuse_reference(obs, ref, *, identity, expected, current_description, current_runner_ref):
    """Native typed step proof; original invocation paths remain original paths."""
    value = obs.json(ref)
    required = {'schema_version', 'original_prefix', 'original_files', 'parent_authority_ref',
        'old_unknown_refs', 'original_identity_digest', 'current_identity_digest',
        'source_input_digest', 'extraction_digest', 'runner_ref', 'phase_transition'}
    sources.require(type(value) is dict and set(value) == required and value['schema_version'] == REUSE_SCHEMA,
        'recovery.reference', 'complete closed versioned extraction-step reference')
    sources.require(expected['phase'] == 'extract', 'recovery.phase', 'extraction reuse only')
    sources.require(value['runner_ref'] == current_runner_ref, 'recovery.runner', 'actual captured successor runner')
    parent = value['parent_authority_ref']
    sources.require(set(parent) == {'path', 'raw_digest'} and
        codec.raw_digest(obs.read(parent['path'])) == parent['raw_digest'],
        'recovery.parent', 'unchanged original authority')
    sources.require(type(value['original_files']) is dict and value['original_files'],
        'recovery.originals', 'complete retained original manifest')
    for path, digest in value['original_files'].items():
        sources.require(codec.raw_digest(obs.read(path)) == digest, 'recovery.originals', 'exact original bytes', path)
    prefix = value['original_prefix']
    sources.require(prefix.startswith('logs/ci/') and '/b-route-source-audit/' in prefix,
        'recovery.origin', 'original native audit execution namespace')
    original = obs.json(prefix + '/input.json')
    old_identity = obs.json(prefix + '/identity.json')
    old_description = obs.json(prefix + '/runner.json')
    sources.require(codec.canonical_digest(original) == value['source_input_digest'] and
        codec.canonical_digest(old_identity) == value['original_identity_digest'] and
        codec.canonical_digest(identity) == value['current_identity_digest'],
        'recovery.identities', 'complete original/current phase and input identities')
    sources.require(bool(old_description.get('synthetic')) == bool(current_description.get('synthetic')),
        'recovery.evidence-class', 'both phases retain their actual evidence class')
    transition = coordinator_transition(old_identity, identity, runner_ref=value['runner_ref'])
    sources.require(transition == value['phase_transition'], 'recovery.transition', 'exact source-bound v4 phase transition')
    request = obs.json(prefix + '/request.json')
    sources.require(expected == audit.phase_input('extract', original, file=original['files'][0],
        citation_guidance=old_identity.get('citation_guidance')), 'recovery.input', 'same complete extraction request')
    unknown = value['old_unknown_refs']
    sources.require(set(unknown) == {'reservation', 'request', 'protocol'},
        'recovery.unknown-link', 'explicit retained unknown permit/request/protocol')
    for field, path in [('reservation', prefix + '/steps/compare/reservation.json'),
                        ('request', prefix + '/steps/compare/request.txt')]:
        sources.require(unknown[field] == path and path in value['original_files'],
            'recovery.unknown-link', 'original comparison evidence path', field)
    sources.require(unknown['protocol'].startswith(prefix + '/steps/compare/workspace/') and
        unknown['protocol'].endswith('.app-server.jsonl') and unknown['protocol'] in value['original_files'],
        'recovery.unknown-link', 'original persisted comparison protocol')
    permit = obs.json(unknown['reservation'])
    sources.require(permit['run_id'] == request['run_id'] and permit['step'] == 'compare',
        'recovery.unknown-permit', 'original separately retained comparison liability')
    checked = validate_completed_extraction(obs, prefix=prefix, expected_bundle=original, current_identity=old_identity)
    sources.require(checked['extraction_identity'] == value['extraction_digest'],
        'recovery.output', 'exact original validated extraction output')
    return checked['extraction']
