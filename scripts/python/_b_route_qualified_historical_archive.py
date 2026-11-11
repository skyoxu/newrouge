"""DRAFT historical archive verifier; no admission/current-state authority.

Installed only in the NEW consumer historical worker, while original owner
modules remain imported from their actual retained R52 paths. The original
protection verifier and its fresh verify_live call are unchanged.

This is the original _load_snapshot archive algorithm with qualified helper
references and one explicit change: fresh verify_live is replaced by archive
initial_legacy.rederive. All original raw/inventory/codec/closure checks remain.
"""
from pathlib import Path
import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_protection as _original_protection

HISTORICAL_ARCHIVE = 'newrouge.b-route-qualified-historical-archive.v1'

def load_historical_snapshot(root: Path, path: str) -> tuple[dict, dict, dict[str, bytes]]:
    data = _original_protection._read(root, path)
    observed = {path: data}

    def read_artifact(source: str) -> bytes:
        raw = _original_protection._read(root, source)
        if source in observed and observed[source] != raw:
            _original_protection._fail(codec.ReasonCode.FILE_CHANGED, source, codec.raw_digest(observed[source]), codec.raw_digest(raw))
        observed[source] = raw
        return raw
    snapshot = codec.strict_json_loads(data)
    if type(snapshot) is not dict or snapshot.get('schema_version') != _original_protection.SCHEMA:
        _original_protection._fail(codec.ReasonCode.UNKNOWN_SCHEMA, path, _original_protection.SCHEMA, snapshot.get('schema_version') if type(snapshot) is dict else type(snapshot).__name__)
    if snapshot.get('content_codec') != codec.CODEC_VERSION or snapshot.get('projection_codec') != codec.PROJECTION_CODEC:
        _original_protection._fail(codec.ReasonCode.UNKNOWN_CODEC_VERSION, path, [codec.CODEC_VERSION, codec.PROJECTION_CODEC], [snapshot.get('content_codec'), snapshot.get('projection_codec')])
    if not _original_protection._same_json(snapshot.get('authorization'), _original_protection.AUTHORIZATION):
        _original_protection._fail(codec.ReasonCode.CONFLICT, path, _original_protection.AUTHORIZATION, snapshot.get('authorization'))
    expected = _original_protection._checked_digest(snapshot.get('snapshot_digest'), path)
    actual = codec.canonical_digest({key: value for key, value in snapshot.items() if key != 'snapshot_digest'})
    if actual != expected:
        _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, path, expected, actual)
    parent = path.rsplit('/', 1)[0] if '/' in path else ''

    def artifact(name: str) -> str:
        return parent + '/' + name if parent else name
    inv_ref = snapshot.get('inventory')
    if type(inv_ref) is not dict or inv_ref.get('artifact') != 'inventory.json':
        _original_protection._fail(codec.ReasonCode.INVALID_REFERENCE, path, 'inventory.json artifact', inv_ref)
    inv_data = read_artifact(artifact('inventory.json'))
    if codec.raw_digest(inv_data) != inv_ref.get('raw_digest'):
        _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, artifact('inventory.json'), inv_ref.get('raw_digest'), codec.raw_digest(inv_data))
    report = codec.strict_json_loads(inv_data)
    _original_protection._inventory_identity(report)
    if inv_ref.get('content_identity') != report['content_identity'] or inv_ref.get('adoptable') is not (report.get('adoptable') is True) or (not _original_protection._same_json(inv_ref.get('diagnostics'), report.get('diagnostics'))):
        _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, path, 'original inventory metadata', 'different snapshot metadata')
    original = _original_protection._inventory_rows(report)
    raw_files, observations = ({}, {})
    if type(snapshot.get('raw_files')) is not list:
        _original_protection._fail(codec.ReasonCode.INVALID_TYPE, path, 'complete raw archive index', snapshot.get('raw_files'))
    for row in snapshot['raw_files']:
        if type(row) is not dict:
            _original_protection._fail(codec.ReasonCode.INVALID_TYPE, path, 'raw archive observation', row)
        source = row.get('path')
        try:
            inventory.canonical_path(source, allow_logs=True)
        except ValueError:
            _original_protection._fail(codec.ReasonCode.UNSAFE_PATH, str(source), 'original canonical path', source)
        if source.casefold() in {key.casefold() for key in observations}:
            _original_protection._fail(codec.ReasonCode.CONFLICT, source, 'unique archived original paths', source)
        observations[source] = row
        if row.get('exists') is False:
            if any((row.get(field) is not None for field in ('raw_digest', 'canonical_digest', 'size_bytes', 'artifact'))):
                _original_protection._fail(codec.ReasonCode.INVALID_REFERENCE, source, 'no fabricated identity for missing bytes', row)
            continue
        if row.get('exists') is not True:
            _original_protection._fail(codec.ReasonCode.INVALID_TYPE, source, 'boolean exists', row.get('exists'))
        digest = _original_protection._checked_digest(row.get('raw_digest'), source)
        if row.get('artifact') != 'raw/' + digest[7:] + '.bin':
            _original_protection._fail(codec.ReasonCode.UNSAFE_PATH, source, 'content-addressed raw archive path', row.get('artifact'))
        raw = read_artifact(artifact(row['artifact']))
        if codec.raw_digest(raw) != digest or not _original_protection._same_json(len(raw), row.get('size_bytes')):
            _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, source, digest, codec.raw_digest(raw))
        canonical = None
        if source.endswith('.json'):
            try:
                canonical = codec.canonical_digest(codec.strict_json_loads(raw))
            except codec.CodecError:
                pass
        if canonical != row.get('canonical_digest'):
            _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, source, row.get('canonical_digest'), canonical)
        raw_files[source] = raw
    if not set(original) <= set(observations):
        _original_protection._fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, path, 'full original inventory archive index', sorted(set(original) - set(observations)))
    for source, row in original.items():
        archived = observations[source]
        if archived['exists'] is not row['exists'] or archived.get('raw_digest') != row['raw_sha256'] or (not _original_protection._same_json(archived.get('roles'), row.get('roles'))):
            _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, source, row, archived)
    triplet, tasks, cumulative, frozen = _original_protection._materials(report, raw_files)
    for field, actual_value in (('triplet', triplet), ('tasks', tasks), ('cumulative', cumulative), ('frozen_a', frozen)):
        if not _original_protection._same_json(snapshot.get(field), actual_value):
            _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, path, 'raw-derived ' + field, 'different ' + field)
    from _b_route_initial_legacy import summary
    if not _original_protection._same_json(snapshot.get('legacy_manifest_requirement'), summary(report)):
        _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, path, 'raw-derived initial legacy boundary', 'different boundary summary')
    if snapshot.get('status_authority') != inventory.TRIPLET['master']:
        _original_protection._fail(codec.ReasonCode.CONFLICT, path, inventory.TRIPLET['master'], snapshot.get('status_authority'))
    if snapshot.get('stable') is not True or not _original_protection._same_json(snapshot.get('diagnostics'), []):
        _original_protection._fail(codec.ReasonCode.FILE_CHANGED, path, 'stable raw collection without capture errors', 'invalid or unstable snapshot')
    if snapshot.get('capture_complete') is not (report.get('adoptable') is True):
        _original_protection._fail(codec.ReasonCode.CONFLICT, path, 'capture completeness derived from inventory', snapshot.get('capture_complete'))
    history = snapshot.get('historical_inventory')
    allowed_extra = set()
    if history is not None:
        if type(history) is not dict or history.get('current_proof') is not False:
            _original_protection._fail(codec.ReasonCode.INVALID_REFERENCE, path, 'historical backlink without current proof', history)
        source = history.get('path')
        if source not in raw_files or codec.raw_digest(raw_files[source]) != history.get('raw_digest'):
            _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, source, 'archived historical report', 'missing or mismatched report')
        previous = codec.strict_json_loads(raw_files[source])
        _original_protection._inventory_identity(previous)
        if history.get('integrity_verified') is not True or history.get('content_identity') != previous['content_identity'] or history.get('original_adoptable') is not previous['adoptable'] or (not _original_protection._same_json(history.get('original_diagnostics'), previous['diagnostics'])) or (not _original_protection._same_json(history.get('diagnostics'), [])):
            _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, source, 'historical metadata rebuilt from archived report', 'different historical metadata')
        allowed_extra = set(_original_protection._inventory_rows(previous)) | {source}
        comparisons = history.get('input_comparison')
        if type(comparisons) is not list or len(comparisons) != len(previous['inputs']):
            _original_protection._fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, source, 'complete historical input comparison', 'incomplete comparison')
        previous_rows = _original_protection._inventory_rows(previous)
        seen = set()
        for item in comparisons:
            original_path = item.get('path') if type(item) is dict else None
            if original_path not in previous_rows or original_path in seen:
                _original_protection._fail(codec.ReasonCode.INVALID_REFERENCE, source, 'unique historical input comparison', original_path)
            seen.add(original_path)
            archived_raw = raw_files.get(original_path)
            current_digest = codec.raw_digest(archived_raw) if archived_raw is not None else None
            expected_digest = previous_rows[original_path]['raw_sha256']
            expected_state = 'missing-or-unreadable' if archived_raw is None else 'unchanged' if current_digest == expected_digest else 'changed'
            if item.get('expected_raw_digest') != expected_digest or item.get('current_raw_digest') != current_digest or item.get('state') != expected_state:
                _original_protection._fail(codec.ReasonCode.DIGEST_MISMATCH, source, 'raw-derived historical difference', item)
    if set(observations) - set(original) - allowed_extra:
        _original_protection._fail(codec.ReasonCode.INVALID_REFERENCE, path, 'only current and historical raw closure', 'unexplained archived inputs')
    from _b_route_initial_legacy import rederive
    state = rederive(report, raw_files)
    if state != report['legacy_manifest_requirement']['state']:
        _original_protection._fail(codec.ReasonCode.CONFLICT, path, 'archive-rederived original boundary', state)
    for source, original_data in observed.items():
        current_data = _original_protection._read(root, source)
        if current_data != original_data:
            _original_protection._fail(codec.ReasonCode.FILE_CHANGED, source, codec.raw_digest(original_data), codec.raw_digest(current_data))
    return (snapshot, report, raw_files)
