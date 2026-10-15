"""Unique Requirement dispositions and hash-bound shared evidence accounting.

The projection is descriptive and never grants MVG runtime verification. Legacy
rows are copied verbatim; merely naming a test or flow creates no evidence.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import PurePosixPath

from _mvg_requirement_routes import memberships

VERIFICATION = 'requirement_verification'
EVIDENCE = 'requirement_evidence'
PROTOCOL = 'newrouge.requirement-accounting.v1'
PROTOCOL_FIELD = 'requirement_accounting_protocol'
KINDS = ['implementation_reference', 'verification_record', 'runtime_acceptance']


def source_path(ref):
    """Reject aliases so every source has one repository-relative identity."""
    if not isinstance(ref, str) or not ref or ref != ref.strip() or '\\' in ref or ':' in ref:
        raise ValueError('requirement_evidence_source_ref_invalid:' + str(ref))
    path = ref.split('#', 1)[0]
    parts = path.split('/')
    if PurePosixPath(path).is_absolute() or any(part in {'', '.', '..'} for part in parts):
        raise ValueError('requirement_evidence_source_ref_invalid:' + ref)
    return path


def normalized_source(data):
    if not isinstance(data, bytes):
        raise ValueError('source_bytes_required')
    return data.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')


def string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def runtime_paths(ref, summary):
    import re
    path = source_path(ref)
    if not re.fullmatch(r'logs/ci/mvg-acceptance/[^/]+/summary\.json', path):
        raise ValueError('requirement_runtime_receipt_path_invalid:' + path)
    if not isinstance(summary, dict):
        raise ValueError('requirement_runtime_receipt_invalid:' + path)
    manifest = source_path(summary.get('manifest'))
    directory = str(PurePosixPath(path).parent)
    return directory + '/input-manifest.json', directory + '/snapshot/' + manifest


def runtime_record_errors(row, summary, manifest, read_source, expected_manifest_path):
    """Verify the formal receipt against its derived immutable snapshot companions."""
    import re
    import hashlib
    from _mvg_manifest import manifest_sha256
    from _project_health_runtime_snapshot import snapshot_digest
    address = str(row.get('requirement_id')) + ':' + str(row.get('evidence_id'))
    try:
        if not isinstance(summary, dict) or read_source is None:
            raise ValueError('receipt_or_companion_missing')
        if summary.get('manifest') != source_path(expected_manifest_path):
            raise ValueError('manifest_path_mismatch')
        input_ref, manifest_ref = runtime_paths(row['source_ref'], summary)
        inventory = json.loads(normalized_source(read_source(input_ref)))
        if not isinstance(inventory, dict):
            raise ValueError('inventory_invalid')
        data = read_source(manifest_ref)
        frozen_manifest = json.loads(normalized_source(data))
        files = inventory.get('files')
        if not isinstance(files, dict) or not files or any(
                not isinstance(path, str) or not isinstance(digest, str)
                or not re.fullmatch('[a-f0-9]{64}', digest) for path, digest in files.items()):
            raise ValueError('inventory_invalid')
        for path in files:
            source_path(path)
        digest = snapshot_digest(files)
        mode, revision = inventory.get('mode'), inventory.get('source_revision')
        base = summary.get('base_commit')
        if not isinstance(base, str) or not re.fullmatch('[a-f0-9]{40}', base):
            raise ValueError('base_commit_invalid')
        if mode == 'main':
            if revision != base:
                raise ValueError('main_revision_invalid')
        elif mode == 'workspace':
            if revision != 'workspace:' + digest:
                raise ValueError('workspace_revision_invalid')
        else:
            raise ValueError('snapshot_mode_unsupported')
        if (summary.get('schema_version') != 'newrouge.mvg-acceptance.v1'
                or summary.get('mode') != 'run' or summary.get('status') != 'passed'
                or summary.get('runtime_verified') is not True
                or summary.get('source_revision') != revision
                or inventory.get('snapshot_digest') != digest or summary.get('snapshot_digest') != digest
                or files.get(summary['manifest']) != hashlib.sha256(data).hexdigest()
                or summary.get('manifest_sha256') != manifest_sha256(data) or frozen_manifest != manifest):
            raise ValueError('receipt_binding_mismatch')
        return []
    except (ValueError, TypeError, KeyError, OSError, UnicodeError) as exc:
        return ['requirement_runtime_receipt_invalid:' + address + ':' + str(exc)]


def manifest_key_errors(proposal):
    errors = []
    manifest = proposal.get('manifest_candidate', {})
    if not isinstance(manifest, dict):
        return ['requirement_accounting_manifest_invalid']
    for family in ('flows', 'tests'):
        rows = manifest.get(family, proposal.get('tests', []) if family == 'tests' else [])
        if not isinstance(rows, list):
            errors.append('requirement_accounting_' + family + '_not_array')
            continue
        seen = set()
        for index, row in enumerate(rows):
            address = f'{family}[{index}]'
            if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                errors.append('requirement_accounting_object_key_invalid:' + address)
                continue
            if row['id'] in seen:
                errors.append('requirement_accounting_object_key_duplicate:' + address + ':' + row['id'])
            seen.add(row['id'])
            for field in ('requirement_ids', 'test_ids') if family == 'flows' else ():
                if field in row and not string_list(row[field]):
                    errors.append('requirement_accounting_object_scope_invalid:' + address + ':' + field)
    return errors


def protocol_errors(index, proposal=None):
    value = index.get(PROTOCOL_FIELD)
    if value is None:
        return []
    if value != PROTOCOL:
        return ['requirement_accounting_protocol_unknown:' + str(value)]
    return ([key + '_required_by_protocol' for key in (VERIFICATION, EVIDENCE) if key not in proposal]
            if proposal is not None else [])


def verification_rows(proposal):
    if VERIFICATION in proposal:
        return deepcopy(proposal[VERIFICATION])
    return [{**deepcopy(row), 'disposition': row.get('disposition', 'flow' if row.get('flow_id') else ''),
             'evidence_ids': ['legacy-verification'] if row.get('disposition') == 'other_verification'
             and row.get('verification_ref') else []}
            for row in (proposal.get('coverage_table') or []) if isinstance(row, dict)]


def evidence_rows(proposal):
    if EVIDENCE in proposal:
        return deepcopy(proposal[EVIDENCE])
    return [{'requirement_id': row.get('requirement_id'), 'evidence_id': 'legacy-verification',
             'kind': 'implementation_reference', 'source_ref': row['verification_ref'],
             'covered_behavior': row.get('rationale') or row.get('coverage') or '',
             'flow_ids': [], 'test_ids': []} for row in (proposal.get('coverage_table') or [])
            if isinstance(row, dict) and row.get('disposition') == 'other_verification' and row.get('verification_ref')]


def project_accounting(proposal, *, read_text=None):
    result = deepcopy(proposal)
    result[VERIFICATION] = verification_rows(proposal)
    result[EVIDENCE] = evidence_rows(proposal)
    if EVIDENCE not in proposal and read_text is not None:
        for row in result[EVIDENCE]:
            candidate = {**row, 'kind': 'verification_record'}
            text = read_text(row['source_ref'].split('#', 1)[0])
            if text is not None and not source_record_errors(candidate, text, proposal.get('manifest_candidate', {})):
                row['kind'] = 'verification_record'
    return result


def schemas(coverage_item, requirement_ids, flow_ids=None, test_ids=None):
    def identifier(values):
        return {'type': 'string', 'enum': sorted(values)} if values is not None else {'type': 'string', 'minLength': 1}
    def array(item):
        return {'type': 'array', 'items': item}
    verification = deepcopy(coverage_item)
    verification['properties']['evidence_ids'] = array(identifier(None))
    verification['required'] = list(verification['properties'])
    evidence = {'type': 'object', 'properties': {
        'requirement_id': identifier(requirement_ids), 'evidence_id': identifier(None),
        'kind': {'type': 'string', 'enum': KINDS}, 'source_ref': identifier(None),
        'covered_behavior': identifier(None), 'flow_ids': array(identifier(flow_ids)),
        'test_ids': array(identifier(test_ids))}, 'additionalProperties': False}
    evidence['required'] = list(evidence['properties'])
    return {VERIFICATION: array(verification), EVIDENCE: array(evidence)}


def key_errors(proposal):
    errors = []
    coverage = proposal.get('coverage_table', [])
    if not isinstance(coverage, list):
        return ['requirement_accounting_coverage_not_array']
    for index, row in enumerate(coverage):
        if not isinstance(row, dict) or not isinstance(row.get('requirement_id'), str):
            errors.append(f'requirement_accounting_coverage_key_invalid:coverage_table[{index}]')
    coverage_ids = [row['requirement_id'] for row in coverage if isinstance(row, dict)
                    and isinstance(row.get('requirement_id'), str)]
    errors.extend('coverage_requirement_duplicate:' + rid for rid in sorted(set(coverage_ids))
                  if coverage_ids.count(rid) > 1)
    for field, keys in ((VERIFICATION, ('requirement_id',)), (EVIDENCE, ('requirement_id', 'evidence_id'))):
        rows = verification_rows(proposal) if field == VERIFICATION else evidence_rows(proposal)
        if not isinstance(rows, list):
            errors.append(field + '_not_array')
            continue
        seen = set()
        for index, row in enumerate(rows):
            address = f'{field}[{index}]'
            if not isinstance(row, dict):
                errors.append('requirement_accounting_row_invalid:' + address)
                continue
            pair = tuple(row.get(key) for key in keys)
            if any(not isinstance(value, str) or not value.strip() for value in pair):
                errors.append('requirement_accounting_key_invalid:' + address)
                continue
            if pair in seen:
                errors.append(field + '_duplicate:' + ':'.join(pair) + ':' + address)
            seen.add(pair)
            if field == VERIFICATION and 'evidence_ids' in row and not string_list(row['evidence_ids']):
                errors.append('requirement_verification_evidence_ids_invalid:' + address)
    return errors


def accounting_errors(proposal, requirement_ids, *, complete=True, check_test_links=True):
    errors = key_errors(proposal) + manifest_key_errors(proposal)
    if any('key_invalid:' in error or 'row_invalid:' in error or 'evidence_ids_invalid:' in error
           or error.endswith('_not_array') for error in errors):
        return errors
    rows, evidence = verification_rows(proposal), evidence_rows(proposal)
    if not isinstance(rows, list) or not isinstance(evidence, list):
        return errors
    if any(error.startswith('requirement_accounting_object_') or error.startswith('requirement_accounting_manifest_')
           or error.startswith('requirement_accounting_flows_') or error.startswith('requirement_accounting_tests_') for error in errors):
        return errors
    known = set(requirement_ids)
    routes = memberships(proposal)
    pairs = {(row['requirement_id'], row['flow_id']) for row in routes if isinstance(row, dict)
             and isinstance(row.get('requirement_id'), str) and isinstance(row.get('flow_id'), str)} if isinstance(routes, list) else set()
    flows = {row.get('id'): row for row in proposal.get('manifest_candidate', {}).get('flows', []) if isinstance(row, dict)}
    tests = {row.get('id'): row for row in proposal.get('manifest_candidate', {}).get('tests', proposal.get('tests', [])) if isinstance(row, dict)}
    errors.extend('requirement_accounting_flow_test_missing:' + fid + ':' + tid
                  for fid, flow in flows.items() for tid in flow.get('test_ids', []) if tid not in tests)
    errors.extend('requirement_accounting_test_flow_mismatch:' + tid + ':' + str(test.get('flow_id'))
                  for tid, test in tests.items() if test.get('flow_id') is not None
                  and check_test_links and (not isinstance(test['flow_id'], str) or test['flow_id'] not in flows
                       or tid not in flows[test['flow_id']].get('test_ids', [])))
    coverage = {row['requirement_id']: row for row in proposal.get('coverage_table', [])
                if isinstance(row, dict) and isinstance(row.get('requirement_id'), str)}
    evidence_keys = {(row.get('requirement_id'), row.get('evidence_id')) for row in evidence if isinstance(row, dict)
                     and isinstance(row.get('requirement_id'), str) and isinstance(row.get('evidence_id'), str)}
    seen = set()
    referenced = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('requirement_id'), str):
            continue
        rid = row['requirement_id']
        seen.add(rid)
        if rid not in known:
            errors.append('requirement_verification_unknown_requirement:' + rid)
        if row.get('disposition') not in ('flow', 'other_verification', 'deferred', 'source_gap'):
            errors.append('requirement_verification_disposition_invalid:' + rid)
        if not isinstance(row.get('rationale', row.get('coverage')), str) or not row.get('rationale', row.get('coverage', '')).strip():
            errors.append('requirement_verification_rationale_missing:' + rid)
        ids = row.get('evidence_ids')
        if not isinstance(ids, list) or any(not isinstance(value, str) or not value.strip() for value in ids):
            errors.append('requirement_verification_evidence_ids_invalid:' + rid)
        else:
            if len(set(ids)) != len(ids):
                errors.append('requirement_verification_evidence_ids_duplicate:' + rid)
            errors.extend('requirement_verification_evidence_missing:' + rid + ':' + eid for eid in ids if (rid, eid) not in evidence_keys)
            referenced.update((rid, eid) for eid in ids)
        if rid in coverage:
            legacy = coverage[rid]
            if any(row.get(key) != value for key, value in legacy.items()) or any(
                    key not in legacy and value is not None for key, value in row.items()
                    if key != 'evidence_ids' and not (key == 'disposition' and value == ('flow' if legacy.get('flow_id') else ''))):
                errors.append('requirement_verification_coverage_mismatch:' + rid)
        elif VERIFICATION in proposal:
            errors.append('requirement_verification_coverage_missing:' + rid)
        if 'satisfied' in row or 'runtime_verified' in row:
            errors.append('requirement_verification_self_report_forbidden:' + rid)
    if complete:
        errors.extend('requirement_verification_missing:' + rid for rid in sorted(known - seen))
    if VERIFICATION in proposal:
        errors.extend('requirement_verification_missing:' + rid for rid in sorted(set(coverage) - seen)
                      if not complete or rid not in known)
    for row in evidence:
        if not isinstance(row, dict):
            continue
        rid, eid = row.get('requirement_id'), row.get('evidence_id')
        address = str(rid) + ':' + str(eid)
        if not isinstance(rid, str) or not isinstance(eid, str) or (rid, eid) not in referenced:
            errors.append('requirement_evidence_unreferenced:' + address)
        if not isinstance(rid, str) or rid not in known or rid not in seen:
            errors.append('requirement_evidence_unknown_requirement:' + address)
        if set(row) != {'requirement_id', 'evidence_id', 'kind', 'source_ref', 'covered_behavior', 'flow_ids', 'test_ids'}:
            errors.append('requirement_evidence_fields_invalid:' + address)
        for field in ('source_ref', 'covered_behavior'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append('requirement_evidence_' + field + '_missing:' + address)
        try:
            source_path(row.get('source_ref'))
        except ValueError:
            errors.append('requirement_evidence_source_ref_invalid:' + address)
        if row.get('kind') not in KINDS:
            errors.append('requirement_evidence_kind_invalid:' + address)
        for field in ('flow_ids', 'test_ids'):
            values = row.get(field)
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                errors.append('requirement_evidence_scope_invalid:' + address + ':' + field)
                continue
            if len(set(values)) != len(values):
                errors.append('requirement_evidence_scope_duplicate:' + address + ':' + field)
            for value in values:
                valid = (value in flows and (rid, value) in pairs) if field == 'flow_ids' else (
                    value in tests and isinstance(row.get('flow_ids'), list) and any(
                        value in flows.get(fid, {}).get('test_ids', []) for fid in row['flow_ids'] if isinstance(fid, str)))
                if not valid:
                    errors.append('requirement_evidence_scope_invalid:' + address + ':' + field + ':' + value)
    return errors


def source_record_errors(row, text, manifest, *, read_source=None, expected_manifest_path=None):
    """Accept explicit frozen records, never infer passed status from file type.

    A verification record is JSON (or a JSON fenced block in a document) with
    status=passed, requirement_ids, covered_behavior, flow_ids and test_ids.
    source_ref fragments select an evidence_id in a records array.
    """
    import re
    if row.get('kind') == 'implementation_reference':
        return []
    if row.get('kind') not in KINDS:
        return ['requirement_evidence_kind_invalid:' + str(row.get('evidence_id'))]
    if any(not isinstance(row.get(field), list) or any(not isinstance(value, str) for value in row[field])
           for field in ('flow_ids', 'test_ids')):
        return ['requirement_evidence_scope_invalid:' + str(row.get('evidence_id'))]
    address = f"{row.get('requirement_id')}:{row.get('evidence_id')}"
    if row.get('kind') == 'runtime_acceptance':
        try:
            summary = json.loads(text)
        except (TypeError, ValueError):
            summary = None
        return runtime_record_errors(row, summary, manifest, read_source, expected_manifest_path)
    payloads = [text] + re.findall(r'```json\s*\n(.*?)\n```', text, re.S)
    records = []
    for payload in payloads:
        try:
            value = json.loads(payload)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            records += value.get('records', [value]) if isinstance(value.get('records', [value]), list) else []
    fragment = row.get('source_ref', '').partition('#')[2]
    records = [record for record in records if isinstance(record, dict) and (not fragment or record.get('evidence_id') == fragment)]
    valid = any(record.get('status') == 'passed'
            and isinstance(record.get('requirement_ids'), list)
            and row.get('requirement_id') in record['requirement_ids']
            and record.get('covered_behavior') == row.get('covered_behavior')
            and isinstance(record.get('flow_ids'), list) and all(isinstance(value, str) for value in record['flow_ids'])
            and isinstance(record.get('test_ids'), list) and all(isinstance(value, str) for value in record['test_ids'])
            and set(row.get('flow_ids', [])) <= set(record['flow_ids'])
            and set(row.get('test_ids', [])) <= set(record['test_ids']) for record in records)
    return [] if valid else ['requirement_evidence_record_invalid:' + address]


def prepared_evidence_validation(root, proposal, prepared, *, check_originals=True):
    from _planning_skill_common import file_sha, load_json, normalized_file_sha, repo_path
    index = load_json(prepared / 'analysis-index.json', {})
    errors, valid = [], set()
    def read_prepared(ref):
        ref = source_path(ref)
        path = repo_path(root, ref)
        copies = [prepared / prefix / ref for prefix in ('sources', 'references')
                  if f'{prefix}/{ref}' in index.get('files', {})]
        expected = index.get('authority_inputs', {}).get(ref)
        if not expected or not copies or any(not copy.is_file() for copy in copies):
            raise ValueError('not_prepared:' + ref)
        if (any(file_sha(copy) != index['files'][copy.relative_to(prepared).as_posix()] for copy in copies)
                or expected not in {file_sha(copies[0]), normalized_file_sha(copies[0])}
                or (check_originals and (not path.is_file() or any(
                    normalized_source(copy.read_bytes()) != normalized_source(path.read_bytes()) for copy in copies)))):
            raise ValueError('source_drift:' + ref)
        return copies[0].read_bytes()
    rows = evidence_rows(proposal)
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get('source_ref'), str):
            continue
        address = f"{row.get('requirement_id')}:{row.get('evidence_id')}"
        try:
            ref = source_path(row['source_ref'])
            text = normalized_source(read_prepared(ref))
        except (ValueError, OSError, UnicodeError) as exc:
            errors.append('requirement_evidence_' + str(exc) + ':' + address)
            continue
        expected_path = index.get('input_envelope', {}).get('predecessor', {}).get('path')
        record_errors = source_record_errors(row, text, proposal.get('manifest_candidate', {}),
            read_source=read_prepared, expected_manifest_path=expected_path)
        errors += record_errors
        if not record_errors:
            valid.add((row.get('requirement_id'), row.get('evidence_id')))
    return errors, valid


def boundary_errors(proposal, requirement_ids, *, root=None, prepared=None, check_originals=True,
                    complete=True, enforce_protocol=True, check_test_links=True):
    """Use the same deterministic accounting boundary for admission and replay.

    Callers verify original artifact hashes before invoking this read-only view.
    Journal recovery checks frozen copies here; its transaction authority gate
    checks live inputs while allowing that transaction's own partial writes.
    """
    from _mvg_requirement_routes import route_errors, protocol_errors as route_protocol_errors
    from _planning_skill_common import load_json
    if not isinstance(proposal, dict):
        return ['requirement_accounting_proposal_invalid']
    errors = manifest_key_errors(proposal) + key_errors(proposal)
    if errors:
        return sorted(set(errors))
    if prepared is not None and enforce_protocol:
        index = load_json(prepared / 'analysis-index.json', {})
        errors += route_protocol_errors(index, proposal) + protocol_errors(index, proposal)
    errors += route_errors(proposal, requirement_ids, complete=complete)
    errors += accounting_errors(proposal, requirement_ids, complete=complete, check_test_links=check_test_links)
    if check_test_links:
        manifest = proposal.get('manifest_candidate', {})
        tests = {row['id'] for row in manifest.get('tests', proposal.get('tests', []))}
        assigned = {tid for flow in manifest.get('flows', []) for tid in flow.get('test_ids', [])}
        errors += ['requirement_accounting_test_flow_missing:' + tid for tid in sorted(tests - assigned)]
    if not errors and prepared is not None:
        from _mvg_planning_review import coverage_errors, prepared_evidence_errors
        semantics = load_json(prepared / 'semantic-requirements.v1.json', {})
        capabilities = load_json(prepared / 'capabilities.v1.json', {})
        task_rows = [row for name in ('tasks_back.json', 'tasks_gameplay.json')
                     for row in load_json(prepared / 'task-views' / name, [])]
        if complete or proposal.get('coverage_table'):
            coverage_proposal = deepcopy(proposal)
            coverage_proposal['manifest_candidate']['flows'] = [flow for flow in proposal['manifest_candidate'].get('flows', [])
                if set(flow.get('requirement_ids', [])).intersection(requirement_ids)]
            errors += coverage_errors(root, coverage_proposal, semantics, capabilities, task_rows,
                set(requirement_ids), check_accounting=False, prepared=prepared,
                check_originals=check_originals)
        errors += prepared_evidence_errors(root, proposal, prepared, check_originals=check_originals)
    return sorted(set(errors))


def freeze_accounting_sources(proposal, prepared):
    from _planning_skill_common import file_sha, load_json
    sources = {}
    refs = []
    for row in evidence_rows(proposal):
        ref = source_path(row['source_ref'])
        refs.append(ref)
        if row.get('kind') == 'runtime_acceptance':
            for family in ('sources', 'references'):
                path = prepared / family / ref
                if path.is_file():
                    refs.extend(runtime_paths(ref, json.loads(normalized_source(path.read_bytes()))))
                    break
    for ref in dict.fromkeys(refs):
        for family in ('sources', 'references'):
            path = prepared / family / ref
            if path.is_file():
                from _planning_skill_common import text_sha
                text = normalized_source(path.read_bytes())
                sources[ref] = {'sha256': text_sha(text), 'original_sha256': file_sha(path), 'text': text}
                break
    return {'requirement_accounting_sources': sources}


def trace_evidence_validation(proposal, *, read_source=None):
    from _planning_skill_common import text_sha
    errors, valid = [], set()
    sources = proposal.get('requirement_accounting_sources', {})
    def read_bound(ref):
        ref = source_path(ref)
        source = sources.get(ref) if isinstance(sources, dict) else None
        actual = read_source(ref) if read_source is not None else None
        if (not isinstance(source, dict) or not isinstance(source.get('text'), str)
                or text_sha(source['text']) != source.get('sha256') or not isinstance(actual, bytes)
                or text_sha(normalized_source(actual)) != source.get('sha256')
                or normalized_source(actual) != source['text']):
            raise ValueError('requirement_evidence_trace_source_unavailable:' + ref)
        return actual
    rows = evidence_rows(proposal)
    for row in rows if isinstance(rows, list) else []:
        try:
            ref = source_path(row['source_ref'])
            text = normalized_source(read_bound(ref))
        except (ValueError, KeyError, OSError, UnicodeError, TypeError) as exc:
            errors.append('requirement_evidence_trace_source_unavailable:' + str(exc))
            continue
        found = source_record_errors(row, text, proposal.get('manifest_candidate', {}),
            read_source=read_bound, expected_manifest_path=proposal.get('applied_manifest_path'))
        errors += found
        if not found:
            valid.add((row['requirement_id'], row['evidence_id']))
    return errors, valid


def accounting_summary(proposal, *, valid_evidence_keys=()):
    """Count Requirements and evidence pairs once, including incomplete legacy rows."""
    verified = set(valid_evidence_keys)
    rows = verification_rows(proposal)
    evidence = evidence_rows(proposal)
    evidence = evidence if isinstance(evidence, list) else []
    pairs = {(row.get('requirement_id'), row.get('evidence_id')): row for row in evidence if isinstance(row, dict)
             and isinstance(row.get('requirement_id'), str) and isinstance(row.get('evidence_id'), str)}
    result = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get('requirement_id'), str):
            continue
        rid = row['requirement_id']
        ids = row.get('evidence_ids') if isinstance(row.get('evidence_ids'), list) else []
        required = {(rid, eid) for eid in ids if isinstance(eid, str)
                    and pairs.get((rid, eid), {}).get('kind') != 'implementation_reference'}
        valid = {pair for pair in required if pair in verified and pairs.get(pair, {}).get('kind') in ('verification_record', 'runtime_acceptance')}
        route_rows = memberships(proposal)
        routes = {route.get('flow_id') for route in route_rows if isinstance(route, dict)
                  and route.get('requirement_id') == rid and isinstance(route.get('flow_id'), str)} if isinstance(route_rows, list) else set()
        covered = {fid for pair in valid for fid in pairs[pair].get('flow_ids', [])}
        satisfied = row.get('disposition') in ('flow', 'other_verification') and bool(required) and required == valid and routes <= covered
        result[rid] = {'requirement_id': rid, 'disposition': row.get('disposition'), 'accounted': True,
                       'satisfied': satisfied, 'evidence_ids': ids,
                       'gaps': [] if satisfied else ['source_gap' if row.get('disposition') == 'source_gap' else 'evidence_unsatisfied']}
    return {'requirements': list(result.values()), 'accounted_count': len(result),
            'satisfied_count': sum(row['satisfied'] for row in result.values()), 'evidence_count': len(pairs),
            'planning_complete': not any(row['disposition'] == 'source_gap' for row in result.values())}
