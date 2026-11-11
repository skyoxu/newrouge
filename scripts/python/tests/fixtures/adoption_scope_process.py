"""Hold real adoption scopes against real inventory in a test-owned process."""
import json
from pathlib import Path
import sys

scripts = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(scripts), *json.loads(sys.argv[3])]
import _b_route_operation_scope as scope
import _planning_apply_journal as journal

root, operation_id = Path(sys.argv[1]), sys.argv[2]
original = journal.read_operation(root, operation_id=operation_id)
with scope.scope_guard(root, original['frozen']['scope_ids'], prepare_under_lease=lambda: None,
                       operation_id=operation_id):
    inventory = journal.operation_inventory(root)
    print(json.dumps({'status': 'holding', 'operation_id': operation_id, 'inventory_count': len(inventory),
        'frozen_digest': original['frozen_digest'], 'scopes': original['frozen']['scope_ids']}), flush=True)
    sys.stdin.readline()
print(json.dumps({'status': 'released'}), flush=True)
