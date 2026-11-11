"""New segmented fiscal types. No constructor/dict/JSON grants authority.

Candidate finite ScheduleGrant follows a real canonical claim and held lease.
Cold archive/replay and settled-prefix resume are source candidates; UNEXECUTED.
"""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import hashlib
import sys
import weakref

ROOT_ISSUER_NAME = '_Root_story23_segmented_schedule_issuer'
ROOT_ISSUER_PATH = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task\night-handoff\story23-canonical-fiscal-cold-replay-successor-draft-02\Root_segmented_schedule_issuer.draft.py')
ROOT_ISSUER_SHA256 = '61eff74abe2d43f09a3acdb151a914cd3d9e9f13ce0db57e196d91735dad25d0'
_ISSUED = weakref.WeakKeyDictionary()
_SCHEDULES = weakref.WeakKeyDictionary()
_CURRENT = ContextVar('segmented_financial_original_scope', default=None)
_ARCHIVE = ContextVar('segmented_financial_original_archive', default=None)
FISCAL_RUN = 'newrouge.b-route-segmented-planning-run.fiscal-v2'
FISCAL_BORN = 'newrouge.b-route-segmented-born.fiscal-v2'
FISCAL_PROOF = 'newrouge.b-route-segmented-fiscal-proof.v1'

class SegmentedFundingError(ValueError):
    pass

def _need(value, reason):
    if not value:
        raise SegmentedFundingError('segmented_funding:' + reason)

class BudgetBasis:
    __slots__ = ('__weakref__',)
    def __new__(cls, *args, **kwargs):
        raise SegmentedFundingError('segmented_funding:original_root_readonly_capture_required')
    def __reduce__(self):
        raise SegmentedFundingError('segmented_funding:process_local_basis_not_serializable')
    def close_current(self):
        return close_budget_basis(self)
    def assess_schedule(self, root, authority, plan):
        return _owner(self).assess_schedule(self, root, authority, plan)

class SegmentedScheduleGrant:
    __slots__ = ('__weakref__',)
    def __new__(cls, *args, **kwargs):
        raise SegmentedFundingError('segmented_funding:actual_canonical_lease_required')
    def __reduce__(self):
        raise SegmentedFundingError('segmented_funding:grant_not_serializable')
    def retained_plan_authority(self):
        return _schedule_owner(self).authority
    def current_funding(self, native_funding):
        owner = _schedule_owner(self)
        return owner.owners['runtime'].financial_funding(owner, native_funding)
    def paid_dispatch_contract(self):
        return _schedule_owner(self).paid_dispatch_contract(self)
    def before_birth(self, root, plan, funding, identity):
        return _schedule_owner(self).birth_inputs(self, root, plan, funding, identity)
    def financial_reference(self, root, plan):
        return _schedule_owner(self).financial_reference(self, root, plan)
    def before_reserve(self, session, node, reservation, claim, claim_path):
        return _schedule_owner(self).before_native_reserve(self, session, node, reservation, claim, claim_path)
    def after_persist(self, session, reservation):
        return _schedule_owner(self).after_native_persist(self, session, reservation)
    def before_dispatch(self, session, reservation):
        return _schedule_owner(self).assert_paid_node(self, session, reservation)
    def after_outcome(self, session, reservation, verified_result):
        return _schedule_owner(self).after_native_outcome(self, session, reservation, verified_result)

def _module():
    module = sys.modules.get(ROOT_ISSUER_NAME)
    _need(module is not None and Path(module.__file__).absolute() == ROOT_ISSUER_PATH
          and hashlib.sha256(ROOT_ISSUER_PATH.read_bytes()).hexdigest() == ROOT_ISSUER_SHA256,
          'actual_paired_root_issuer')
    return module

def _owner(basis):
    _need(type(basis) is BudgetBasis and basis in _ISSUED, 'genuine_readonly_basis_not_dict_or_grant')
    owner, _data = _ISSUED[basis]
    module = _module()
    _need(type(owner) is module.RootSegmentedIssuer and owner.facade is sys.modules[__name__],
          'actual_original_basis_owner')
    return owner

def _basis_record(basis, owner):
    _need(_owner(basis) is owner, 'same_basis_owner')
    return deepcopy(_ISSUED[basis][1])

def _issue_basis_from_root(owner, data):
    module = _module()
    _need(type(owner) is module.RootSegmentedIssuer and owner.facade is sys.modules[__name__],
          'actual_root_readonly_owner')
    for name, (original, code) in module._ORIGINAL_METHODS.items():
        actual = getattr(module.RootSegmentedIssuer, name)
        _need(actual is original and getattr(actual, '__wrapped__', actual).__code__ is code
              and getattr(actual, '__wrapped__', actual).__globals__ is module.__dict__,
              'original_issuer_methods_unchanged')
    function = module.RootSegmentedIssuer.capture_segmented_budget
    frame = sys._getframe(1)
    _need(frame.f_code is function.__code__ and frame.f_globals is module.__dict__
          and frame.f_locals.get('self') is owner
          and Path(function.__code__.co_filename).absolute() == ROOT_ISSUER_PATH,
          'actual_original_capture_frame')
    _need(owner.pending_basis is not None and owner.pending_basis == data and owner.basis is None,
          'actual_pending_readonly_capture')
    _need(data.get('dispatch_authorized') is False and data.get('allocation_namespace') is None,
          'readonly_never_dispatch')
    basis = object.__new__(BudgetBasis)
    _ISSUED[basis] = (owner, deepcopy(data))
    return basis

def require_budget_basis(basis):
    _owner(basis).close_basis(basis)
    return basis

def close_budget_basis(basis):
    return _owner(basis).close_basis(basis)

def _unsupported(*args, **kwargs):
    raise SegmentedFundingError('segmented_funding:explicit_fiscal_verifier_required')

def require_original_owner(owner):
    module = _module()
    _need(type(owner) is module.RootSegmentedIssuer and owner.facade is sys.modules[__name__],
          'actual_original_canonical_owner')
    owner._static()
    return owner


def _schedule_owner(grant):
    _need(type(grant) is SegmentedScheduleGrant and grant in _SCHEDULES,
          'actual_original_schedule_grant')
    owner = require_original_owner(_SCHEDULES[grant])
    _need(owner.grant is grant and owner.store is not None, 'same_live_original_schedule')
    owner.store._held()
    return owner


def _issue_schedule_from_root(owner):
    module = _module()
    require_original_owner(owner)
    body = module.RootSegmentedIssuer.hold_segmented_plan.__wrapped__
    frame = sys._getframe(1)
    _need(frame.f_code is body.__code__ and frame.f_globals is module.__dict__
          and frame.f_locals.get('self') is owner and owner.pending_grant is not None
          and owner.grant is None, 'actual_claimed_original_schedule_frame')
    owner.store._held()
    _need(owner.store._fresh_snapshot() == owner.pending_grant['snapshot'], 'actual_claim_readback_before_mint')
    grant = object.__new__(SegmentedScheduleGrant)
    _SCHEDULES[grant] = owner
    return grant


@contextmanager
def _schedule_scope(owner, grant):
    _need(_schedule_owner(grant) is owner and _CURRENT.get() is None, 'one_original_schedule_scope')
    token = _CURRENT.set(grant)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current_schedule_grant():
    grant = _CURRENT.get()
    _schedule_owner(grant)
    return grant


def require_schedule_grant(grant):
    _schedule_owner(grant)
    return grant


def _resume_schedule_from_root(owner):
    module = _module()
    require_original_owner(owner)
    body = module.RootSegmentedIssuer.resume_segmented_claim.__wrapped__
    frame = sys._getframe(1)
    _need(frame.f_code is body.__code__ and frame.f_globals is module.__dict__
          and frame.f_locals.get('self') is owner and owner.pending_grant is not None
          and owner.grant is None and owner.archive_state is not None,
          'actual_existing_prefix_replay_frame')
    owner.store._held()
    _need(owner.store._fresh_snapshot() == owner.pending_grant['snapshot']
          and owner.archive_state['facts']['prefix_disposition'] == 'open-settled-prefix'
          and owner.archive_state['native_blocked'] is None, 'actual_settled_prefix_before_resume')
    grant = object.__new__(SegmentedScheduleGrant)
    _SCHEDULES[grant] = owner
    return grant


@contextmanager
def _archive_scope(owner):
    module = _module()
    require_original_owner(owner)
    _need(_CURRENT.get() is None and _ARCHIVE.get() is None and owner.grant is None,
          'independent_readonly_archive_scope')
    methods = (module.RootSegmentedIssuer.inspect_archived_fiscal_proof,
               module.RootSegmentedIssuer.reconcile_completed_intent,
               module.RootSegmentedIssuer.repair_native_birth)
    frame = sys._getframe(1)
    found = False
    while frame is not None:
        if any(frame.f_code is fn.__code__ and frame.f_globals is module.__dict__ for fn in methods):
            _need(frame.f_locals.get('self') is owner, 'same_actual_original_archive_owner')
            found = True
            break
        frame = frame.f_back
    _need(found, 'actual_original_archive_replay_frame')
    token = _ARCHIVE.set(owner)
    try:
        yield
    finally:
        _ARCHIVE.reset(token)


def _archive_owner():
    owner = _ARCHIVE.get()
    require_original_owner(owner)
    _need(owner.grant is None and owner.store is not None, 'readonly_archive_never_grant')
    return owner


def in_archive_scope(owner):
    return _ARCHIVE.get() is owner and owner.grant is None


def financial_birth_reference(root, plan):
    if _CURRENT.get() is not None:
        return current_schedule_grant().financial_reference(root, plan)
    owner = _archive_owner()
    return owner.owners['runtime'].financial_archive_reference(owner, root, plan)


def current_fiscal_funding(native_funding):
    if _CURRENT.get() is not None:
        return current_schedule_grant().current_funding(native_funding)
    owner = _archive_owner()
    return owner.owners['runtime'].financial_archive_funding(owner, native_funding)


def verify_archived_fiscal_proof(owner):
    return require_original_owner(owner).inspect_archived_fiscal_proof()


def resume_segmented_claim(owner):
    return require_original_owner(owner).resume_segmented_claim()

def reject_fiscal_record_in_legacy_reader(state):
    """Legacy reader boundary only; fiscal bytes use their explicit verifier."""
    _need(type(state) is dict, 'record_mapping')
    schema = state.get('schema_version')
    if schema in (FISCAL_RUN, FISCAL_BORN, FISCAL_PROOF) or any(
            key in state for key in ('segmented_fiscal_claim', 'segmented_fiscal_proof', 'segmented_fiscal_family')):
        _unsupported()
    # Original caller continues original closed v1 validation unchanged.
    return None
