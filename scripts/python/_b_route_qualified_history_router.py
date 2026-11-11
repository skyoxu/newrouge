"""Explicit same-journal routing; no caller proof/dictionary qualification seam."""
from pathlib import Path
import _planning_apply_journal as journal
import _b_route_qualified_history_host as old
import _b_route_qualified_history_host_v3 as new
from _b_route_qualified_historical_v3_protocol import family

AUTHENTICATED_TYPES = (old.AuthenticatedHistory, new.AuthenticatedHistory)


def authenticate(root, operation_id):
    root = Path(root).absolute()
    operation = journal.read_operation(root, operation_id=operation_id)
    owner = new if family(operation)=='v3' else old
    value = owner.authenticate(root, operation_id)
    value.checked_original(root, operation)
    return value
