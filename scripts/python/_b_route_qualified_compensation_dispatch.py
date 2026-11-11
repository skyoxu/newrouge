"""Known version routing only. Genuine owners retain every qualification check.

No module selection mints an opaque history or changes a proof. The callers use
actual journal/current Snapshot bytes; their selected owners independently replay
those exact inputs before use. Legacy default3/explicit4 are untouched.
"""
from contextlib import contextmanager
import _b_route_codec as codec
import _planning_apply_journal as journal
import _b_route_qualified_compensation_review as old
import _b_route_qualified_compensation_review_v2 as new
from _b_route_qualified_historical_v3_protocol import family,need


def for_operation(operation):
    request=operation['frozen']['request']
    if operation['schema_version']=='newrouge.b-route-adoption-operation.v2':
        return new if family(operation)=='v3' else old
    proof=request.get('host_review_ref',{}).get('schema_version','')
    if proof==new.PROOF:return new
    if proof==old.PROOF:return old
    need(not proof.startswith('newrouge.b-route-qualified-compensation-review-proof.'),
         'unknown qualified proof cannot downgrade')
    return old


def for_subject(subject):
    version=subject.get('schema_version')
    if version==new.SUBJECT:return new
    need(not str(version).startswith('newrouge.b-route-qualified-compensation-review-subject.')
         or version==old.SUBJECT, 'unknown qualified subject cannot downgrade')
    return old


def for_snapshot(snapshot, *, original):
    selected=for_operation(original)
    for name,pin in list(snapshot.files.items()):
        if pin is None or not name.endswith('.json') or name.startswith(old.review.BASE+'/'):continue
        data=snapshot.read(name)
        try:value=codec.strict_json_loads(data)
        except codec.CodecError:continue
        if type(value) is not dict or not str(value.get('schema_version','')).startswith('newrouge.b-route-qualified-origin-capsule.'):continue
        need(value['schema_version']=='newrouge.b-route-qualified-origin-capsule.v1','known actual capsule schema')
        operation=journal.read_operation(snapshot.root,operation_id=value['operation_id'])
        ref=operation['frozen']['request']['material']['handoff_ref']
        need(name==ref['path'] and codec.raw_digest(data)==ref['raw_digest'],
             'same actual journal capsule reference before version selection')
        if for_operation(operation) is new:selected=new
    return selected


@contextmanager
def action():
    with old.action(),new.action():
        yield


def bind_action(snapshot):
    old.bind_action(snapshot)
    new.bind_action(snapshot)
