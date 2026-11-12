"""Typed native-candidate projection; original proof remains the complete source.

No filesystem write, identity allocation, provider call or admission occurs here.
The caller must bind native_candidate_ref to the actual verified handoff content.
"""
from copy import deepcopy

import _b_route_codec as codec
import _b_route_schema_resources as schemas

FIELDS = ('source_identity', 'requirements', 'definitions', 'logical_references',
          'requirement_verification', 'requirement_route_memberships',
          'requirement_evidence', 'evidence_source_refs', 'coverage_table', 'applicability')
RETAINED_IN_NATIVE_PROOF = ('out_of_scope_requirement_ids', 'selected_dependencies',
                            'unresolved', 'implementation_objects')
_KINDS = {'flow': 'flows', 'command': 'commands', 'state': 'states'}
_PROPOSED_USE = {'kind', 'definition_id', 'proposed_owner_key'}
_EXISTING_USE = {'kind', 'definition_id', 'owner_plan_id', 'owner_revision'}


def _fail(code, expected, actual):
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.CONTENT,
        expected=expected, actual=actual))


def _validate_content(content):
    codec.validate_json_value(content)
    validator = schemas.validator('newrouge.b-route-planning-candidate.v1', auxiliary=True).evolve(
        schema={'$ref': 'newrouge.b-route-planning-candidate.v1#/properties/content'})
    error = next(validator.iter_errors(content), None)
    if error is not None:
        _fail(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, 'complete original native candidate content', error.message)


def _mapping(allocations, name, domain, *, required):
    mapping = allocations.get(name)
    if mapping is None and not required:
        return {identity: identity for identity in domain}
    if type(mapping) is not dict or set(mapping) != domain:
        _fail(codec.ReasonCode.MAPPING_MISMATCH, 'complete typed allocation domain: ' + name,
              sorted(mapping) if type(mapping) is dict else type(mapping).__name__)
    for identity in mapping.values():
        codec.validate_business_id(identity)
    if len(set(mapping.values())) != len(mapping):
        _fail(codec.ReasonCode.DUPLICATE_OWNER, 'one-to-one typed allocations', name)
    return dict(mapping)


def project_content(content, allocations):
    """Return the ten shared plan fields with exact typed ID/owner adaptation.

    Denominators, dependencies, unresolved facts, implementation objects and
    proposed-owner provenance stay complete in the required original native ref.
    Existing logical references are never rebound to the newly allocated owner.
    """
    _validate_content(content)
    codec.validate_json_value(allocations)
    if type(allocations) is not dict:
        _fail(codec.ReasonCode.INVALID_TYPE, 'host allocation object', type(allocations).__name__)
    plan_id = codec.validate_business_id(allocations.get('plan_id'))
    revision = allocations.get('plan_revision')
    if type(revision) is not int or revision < 1:
        _fail(codec.ReasonCode.INVALID_TYPE, 'positive host plan revision', revision)
    requirement_ids = [row['requirement_id'] for row in content['requirements']]
    if len(set(requirement_ids)) != len(requirement_ids):
        _fail(codec.ReasonCode.MAPPING_MISMATCH, 'unique native Requirement identities', requirement_ids)
    maps = {'requirements': _mapping(allocations, 'requirements', set(requirement_ids), required=True)}
    owners = {}
    for kind, plural in _KINDS.items():
        ids = [row['id'] for row in content['definitions'][plural]]
        if len(set(ids)) != len(ids):
            _fail(codec.ReasonCode.DUPLICATE_OWNER, 'unique native definition identities per kind', kind)
        maps[plural] = _mapping(allocations, plural, set(ids), required=(kind == 'flow'))
        for row in content['definitions'][plural]:
            owners[(kind, row['id'], row['proposed_owner_key'])] = maps[plural][row['id']]

    def visit(value):
        if type(value) is list:
            return [visit(item) for item in value]
        if type(value) is not dict:
            return deepcopy(value)
        if set(value) == _EXISTING_USE:
            return deepcopy(value)
        if 'proposed_owner_key' in value:
            if set(value) != _PROPOSED_USE:
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, 'exact proposed logical use', sorted(value))
            key = (value['kind'], value['definition_id'], value['proposed_owner_key'])
            if key not in owners:
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, 'declared exact typed proposed owner', list(key))
            return {'kind': value['kind'], 'definition_id': owners[key],
                    'owner_plan_id': plan_id, 'owner_revision': revision}
        result = {}
        for field, item in value.items():
            if field in ('requirement_id', 'requirement_ids'):
                mapping = maps['requirements']
                result[field] = [mapping.get(x, x) for x in item] if type(item) is list else mapping.get(item, item)
            elif field in ('flow_id', 'flow_ids'):
                mapping = maps['flows']
                result[field] = [mapping.get(x, x) for x in item] if type(item) is list else mapping.get(item, item)
            else:
                result[field] = visit(item)
        return result

    projected = {name: visit(content[name]) for name in FIELDS if name != 'definitions'}
    projected['definitions'] = {}
    for kind, plural in _KINDS.items():
        rows = []
        for row in content['definitions'][plural]:
            definition = {field: deepcopy(value) for field, value in row.items() if field != 'proposed_owner_key'}
            definition['id'] = maps[plural][row['id']]
            rows.append(visit(definition))
        projected['definitions'][plural] = rows
    return {name: projected[name] for name in FIELDS}


def project_retained_fields(content, allocations):
    """View-only host identity interpretation; storage remains the exact original ref."""
    project_content(content, allocations)  # Existing complete typed allocation validator.
    maps = {'requirements': _mapping(allocations, 'requirements',
        {r['requirement_id'] for r in content['requirements']}, required=True)}
    owners = {}
    for kind, plural in _KINDS.items():
        maps[plural] = _mapping(allocations, plural, {r['id'] for r in content['definitions'][plural]}, required=(kind == 'flow'))
        for row in content['definitions'][plural]:
            owners[(kind, row['id'], row['proposed_owner_key'])] = {'kind': kind,
                'definition_id': maps[plural][row['id']], 'owner_plan_id': allocations['plan_id'],
                'owner_revision': allocations['plan_revision']}
    def visit(value):
        if type(value) is list:
            return [visit(item) for item in value]
        if type(value) is not dict:
            return deepcopy(value)
        if set(value) == _EXISTING_USE:
            return deepcopy(value)
        if 'proposed_owner_key' in value:
            key = (value.get('kind'), value.get('definition_id'), value.get('proposed_owner_key'))
            if set(value) != _PROPOSED_USE or key not in owners:
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, 'exact retained native proposed owner', sorted(value))
            return deepcopy(owners[key])
        result = {}
        for field, item in value.items():
            if field in ('requirement_id', 'requirement_ids', 'flow_id', 'flow_ids'):
                mapping = maps['requirements' if field.startswith('requirement') else 'flows']
                result[field] = [mapping.get(x, x) for x in item] if type(item) is list else mapping.get(item, item)
            else:
                result[field] = visit(item)
        return result
    return {name: visit(content[name]) for name in sorted(RETAINED_IN_NATIVE_PROOF)}
