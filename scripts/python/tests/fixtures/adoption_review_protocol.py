"""Construct explicitly synthetic OS/protocol fixtures; never launch a process."""
import base64
import json
from pathlib import Path

import _b_route_adoption_review as review
import _b_route_codec as codec
import _codex_app_server as transport
from fixtures.codex_app_server_protocol import protocol, encoded


def completed(root, operation_id, *, blocked=False, effort='high', tool=False, incomplete=False,
              thread_id='independent-review-thread', prompt_override=None):
    root = Path(root).resolve()
    subject = review.read_subject(root, operation_id)
    home = root / review.location(operation_id)
    workspace = home / 'w'
    checks = [{'id': key, 'verdict': 'approved', 'rationale': 'Synthetic protocol fixture only: ' + key}
              for key in review.obligations(subject)]
    if blocked:
        checks[0]['verdict'] = 'blocked'
    result = {'schema_version': review.VERDICT, 'subject_digest': codec.canonical_digest(subject),
        'verdict': 'blocked' if blocked else 'approved',
        'findings': [checks[0]['rationale']] if blocked else [], 'checks': checks}
    output = json.dumps(result, separators=(',', ':'))
    rows = protocol(workspace, prompt=prompt_override or review.request_payload(subject),
                    output=output, schema=review.verdict_schema(subject), provider='openai')
    for row in rows:
        message = row['message']
        if row['direction'] == 'client' and message.get('method') == 'thread/start':
            message['params']['config']['model_reasoning_effort'] = 'high'
        if message.get('result', {}).get('thread'):
            message['result']['reasoningEffort'] = 'high'
        def rename(value):
            if isinstance(value, dict):
                return {key: rename(child) for key, child in value.items()}
            if isinstance(value, list):
                return [rename(child) for child in value]
            return thread_id if value == 'fresh-thread' else value
        row['message'] = rename(message)
    # Obtain a coherent baseline proof, then mutate raw evidence for negative cases.
    output_text, proof = transport.replay(encoded(rows))
    if effort != 'high':
        for row in rows:
            message = row['message']
            if row['direction'] == 'client' and message.get('method') == 'thread/start':
                message['params']['config']['model_reasoning_effort'] = effort
            if message.get('result', {}).get('thread'):
                message['result']['reasoningEffort'] = effort
    if tool:
        rows[-2]['message']['params']['item']['type'] = 'commandExecution'
    if incomplete:
        rows.pop()
    if tool or incomplete or effort != 'high':
        proof['protocol_jsonl_base64'] = base64.b64encode(encoded(rows)).decode('ascii')
    receipt = {'schema_version': 'newrouge.isolated-model-runner-receipt.v1',
        'model': proof['model'], 'model_provider': proof['model_provider'], 'model_identity': 'openai/' + proof['model'],
        'model_identity_source': transport.SOURCE, 'model_identity_scope': 'runtime_configuration',
        'evidence_policy': transport.POLICY, 'runtime_identity_verified': True, 'model_identity_verified': False,
        'provider_identity_verified': False, 'provider_reported_model': None, 'provider_dispatch_count': 'unknown',
        'model_identity_evidence': [proof], 'model_tools': [], 'request_count_observable': True,
        'model_request_count': 1, 'runner_invocations': 1, 'workspace': workspace.as_posix(),
        'output_chars': len(output_text)}
    stdout = json.dumps(receipt) + '\n'
    execution = {'command': review.runner_command(root, operation_id), 'status': 'completed', 'returncode': 0,
        'runner_dispatch_count': 1, 'active_elapsed_seconds': 1.0, 'stdout': stdout,
        'stdout_base64': base64.b64encode(stdout.encode()).decode('ascii')}
    (home / 'synthetic-fixture-origin.txt').write_text('Offline constructed bytes; no provider/OS execution.\n', encoding='utf-8')
    (home / 'execution.json').write_bytes(review.raw(execution))
    (workspace / 'output.json').write_bytes(output_text.encode())
    return execution, receipt, result
