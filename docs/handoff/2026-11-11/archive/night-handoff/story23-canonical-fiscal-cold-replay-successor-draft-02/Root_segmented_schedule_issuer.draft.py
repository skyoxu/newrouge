"""Canonical-config finite schedule issuer candidate. UNEXECUTED; no live inputs.

Old issuer06 closes original liabilities. Its one-host rows parser is not reused
as a multistage writer. Fresh/cold integration candidate. All business/control execution is UNEXECUTED.
"""
from copy import deepcopy
from contextlib import contextmanager
import os
from pathlib import Path
import hashlib
import sys
import threading

TASK = Path(r'C:\Users\Administrator\Documents\Codex\2026-11-05\task')
LEGACY_PATH = TASK / 'night-handoff/story29-unit-profile-funding-issuer-followup06/Root_unit_profile_issuer.draft.py'
LEGACY_SHA = 'd3730bcf61520ecfe962e39e3ebaf1ca892f10d27d3edf3c6754da8411d9307f'
HELPER_PATH = TASK / 'story29-host2-controller-draft-01/host2_controller.py'
HELPER_SHA = '1a3277d2c7d32d5560dc346ca21708bd31935173f3b7212902b45e7f1270b457'
SCHEMA = 'task.segmented-schedule-funding.v1'
HOME = TASK / 'story29-unit-profile-allocation-Root-02'
BASIS = 'newrouge.b-route-segmented-budget-basis.v1'
SCHEDULE = 'newrouge.b-route-segmented-schedule-assessment.v1'
CLAIM = 'task.segmented-schedule-funding.v1'
RUN = 'newrouge.b-route-segmented-planning-run.fiscal-v2'
BORN = 'newrouge.b-route-segmented-born.fiscal-v2'
PROOF = 'newrouge.b-route-segmented-fiscal-proof.v1'
_LOCK_API = ('canonical', 'digest', 'parse', 'plain', 'read', 'pinned', 'verify_host1_precreation', 'verify_runtime_observation')
_LEGACY_API = ('_budget', '_closed_chain', '_host3_graph')
_OWNER_API = {
    'runtime': ('verify_plan_authority', '_validate_plan_source', 'policy_identity'),
    'workflow': ('validate_plan',),
    'planner': ('_limits',),
}
_MODULE_NAMES = {'runtime': '_b_route_segmented_runtime.py',
                 'workflow': '_b_route_segmented_workflow.py',
                 'planner': '_b_route_segmented_plan.py'}

class SegmentedFiscalError(ValueError):
    pass

def need(value, reason):
    if not value:
        raise SegmentedFiscalError('segmented_fiscal:' + reason)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def bounded_schedule_liability(paid, guard, count, native_limit):
    """Pure DATA arithmetic, not a basis/grant or currentness approval."""
    need(all(type(v) is int for v in (paid, guard, count, native_limit)), 'integer_counts')
    need(0 <= paid <= guard <= 290 and native_limit in (96, 192), 'original_liability_bounds')
    need(0 < count <= native_limit and guard + count <= 290, 'complete_schedule_not_affordable')
    return {'paid_or_unknown_before': paid, 'outside_guard': guard, 'schedule_hold': count,
            'guard_if_held': guard + count, 'campaign_limit': 290, 'released': 0,
            'dispatch_authorized': False}

class RootSegmentedIssuer:
    """Canonical Root config owner with readonly assessment and finite held scope.

    Source/config/pair checks precede old financial reads and run again around
    capture. Original graph closure is reused, not caller-supplied totals.
    A readonly observation is not an atomic allocation lease or financial grant.
    """
    __slots__ = ('h', 'legacy', 'facade', 'owners', 'config_path', 'self_path', 'self_sha',
                 'functions', 'config_raw', 'config_sha', 'c', 'basis', 'pending_basis',
                 'thread', 'source', 'root', 'mint_identity', 'store_module', 'prefix',
                 'store', 'authority', 'plan', 'grant', 'pending_grant', 'assessment',
                 'native_state', 'integration', 'archive_state', 'pending_dispatch')

    def __init__(self, config_path, expected_sha256, *, host2_helpers, legacy_issuer,
                 facade, runtime, workflow, planner, prefix_store=None, prefix=None):
        # Null future authority must reject without opening even config_path.
        need(type(expected_sha256) is str and len(expected_sha256) == 64
             and all(c in '0123456789abcdef' for c in expected_sha256), 'actual_root_config_pin_required')
        self.h, self.legacy, self.facade = host2_helpers, legacy_issuer, facade
        self.owners = {'runtime': runtime, 'workflow': workflow, 'planner': planner}
        self.config_path = Path(config_path).absolute()
        need(self.config_path == HOME / 'config.json', 'original_canonical_config_role')
        self.self_path = Path(__file__).absolute()
        self.self_sha = sha(self.self_path)
        self._identity(self.h, HELPER_PATH, HELPER_SHA)
        self._identity(self.legacy, LEGACY_PATH, LEGACY_SHA)
        self.functions = {}
        for name in _LOCK_API:
            self._remember('helper.' + name, self.h, getattr(self.h, name))
        for name in _LEGACY_API:
            self._remember('legacy.' + name, self.legacy, getattr(self.legacy.RootProfileIssuer, name))
        self.config_raw = self.h.read(self.config_path)
        need(self.h.digest(self.config_raw) == expected_sha256, 'actual_root_config_raw')
        self.config_sha = expected_sha256
        self.c = self.h.parse(self.config_raw)
        self.store_module, self.prefix = prefix_store, prefix
        self.store = self.authority = self.plan = self.grant = None
        self.pending_grant = self.assessment = self.native_state = self.integration = None
        self.archive_state = None
        self.pending_dispatch = None
        self.basis = None
        self.pending_basis = None
        self.thread = threading.get_ident()
        self._static()

    def _identity(self, module, path, digest):
        need(Path(module.__file__).absolute() == path and sha(path) == digest, 'actual_original_source')
        need(sys.modules.get(module.__name__) is module, 'registered_original_module')

    def _remember(self, key, module, function):
        need(function.__globals__ is module.__dict__
             and Path(function.__code__.co_filename).absolute() == Path(module.__file__).absolute(),
             'original_code_globals_file')
        self.functions[key] = (module, function, function.__code__)

    def _pair(self, pins):
        # Facade pins issuer; existing config source_files pins facade.
        # Existing Root_authority binds this issuer and binding, without a
        # separate pair-authority/carrier/registration.
        facade_path = self.source / 'scripts/python/_b_route_segmented_funding.py'
        need(str(facade_path) in pins, 'source_contains_facade')
        self._identity(self.facade, facade_path, pins[str(facade_path)])
        need(self.facade.ROOT_ISSUER_PATH == self.self_path
             and self.facade.ROOT_ISSUER_SHA256 == self.self_sha
             and sys.modules.get(self.facade.ROOT_ISSUER_NAME) is sys.modules.get(__name__),
             'paired_facade_pins_actual_new_issuer')
        functions = tuple(getattr(self.facade, name) for name in
                          ('_issue_basis_from_root', '_issue_schedule_from_root', '_resume_schedule_from_root'))
        need(all(fn.__globals__ is self.facade.__dict__
                 and Path(fn.__code__.co_filename).absolute() == facade_path for fn in functions),
             'original_facade_mint_code_globals')
        identities = tuple((fn, fn.__code__) for fn in functions)
        if hasattr(self, 'mint_identity'):
            need(identities == self.mint_identity, 'facade_mint_unchanged')
        self.mint_identity = identities

    def _static(self):
        need(type(self) is RootSegmentedIssuer, 'exact_original_readonly_owner_type')
        for name, (function, code) in _ORIGINAL_METHODS.items():
            actual = getattr(RootSegmentedIssuer, name)
            need(actual is function and getattr(actual, '__wrapped__', actual).__code__ is code
                 and getattr(actual, '__wrapped__', actual).__globals__ is globals(),
                 'original_issuer_methods_unchanged')
        need(threading.get_ident() == self.thread, 'same_readonly_owner_thread')
        need(self.h.read(self.config_path) == self.config_raw and sha(self.self_path) == self.self_sha,
             'canonical_config_issuer_stable')
        self._identity(self.h, HELPER_PATH, HELPER_SHA)
        self._identity(self.legacy, LEGACY_PATH, LEGACY_SHA)
        c = self.c
        fields = {'schema', 'Root_sealed', 'namespace', 'source_root', 'owner_root',
                  'source_files', 'input_files', 'runtime_files', 'binding',
                  'Root_authority', 'budget_snapshot'}
        need(type(c) is dict and fields <= set(c) and c['schema'] == SCHEMA
             and c['Root_sealed'] is True and c['namespace'] == HOME.name,
             'original_canonical_config_family')
        self.source = Path(c['source_root']).absolute()
        self.root = Path(c['owner_root']).absolute()
        need(self.source.is_relative_to(TASK) and self.source != TASK
             and self.root.is_relative_to(TASK) and self.root != TASK, 'finite_actual_source_owner')
        pins = {}
        for key in ('source_files', 'input_files', 'runtime_files'):
            need(type(c[key]) is list and c[key], 'complete_actual_pin_lists')
            for ref in c[key]:
                need(type(ref) is dict and set(ref) == {'path', 'sha256'}, 'exact_pin_shape')
                name = str(Path(ref['path']).absolute())
                need(name not in pins, 'no_duplicate_pin_roles')
                pins[name] = ref['sha256']
                self.h.pinned(ref, metadata=False)
        self._pair(pins)  # Must pass before the original _budget graph is opened.
        for owner, names in _OWNER_API.items():
            module = self.owners[owner]
            path = self.source / 'scripts/python' / _MODULE_NAMES[owner]
            need(str(path) in pins, 'actual_segmented_owner_in_source')
            self._identity(module, path, pins[str(path)])
            for name in names:
                key = owner + '.' + name
                function = getattr(module, name)
                if key not in self.functions:
                    self._remember(key, module, function)
                else:
                    need((module, function, function.__code__) == self.functions[key], 'owner_function_unchanged')
        for key, (module, fn, code) in self.functions.items():
            family, name = key.split('.')
            actual = getattr(module.RootProfileIssuer, name) if family == 'legacy' else getattr(module, name)
            need(actual is fn and fn.__code__ is code and fn.__globals__ is module.__dict__, 'original_functions_stable')
        b = c['binding']
        need(type(b) is dict and set(b) == {'root', 'run_id', 'planner', 'epoch', 'source_policy_digest'}
             and b['root'] == str(self.root) and type(b['run_id']) is str and b['run_id']
             and b['planner'] in ('capability', 'mvg') and type(b['epoch']) is int and b['epoch'] >= 0,
             'exact_bound_readonly_source_run_epoch')
        # Existing U06 authority shape: explicit family, current controller and
        # existing binding. No additional authority file/schema is introduced.
        expected = {'schema': SCHEMA, 'namespace': HOME.name,
                    'controller_sha256': self.self_sha,
                    'binding_sha256': self.h.digest(self.h.canonical(b)),
                    'Root_sole_campaign_model_executor': True,
                    'no_other_campaign_allocation_writer_active': True,
                    'old99_and_failed_unknown_retained': True, 'released': 0}
        need(self.h.parse(self.h.pinned(c['Root_authority'])) == expected,
             'original_root_config_authority')

    # Exact original functions, their globals and hardcoded old namespaces remain
    # intact. In particular _closed_chain still verifies its one-host prefix.
    def _closed_chain(self, *args, **kwargs):
        return self.legacy.RootProfileIssuer._closed_chain(self, *args, **kwargs)

    def _host3_graph(self, *args, **kwargs):
        return self.legacy.RootProfileIssuer._host3_graph(self, *args, **kwargs)

    def _budget(self):
        return self.legacy.RootProfileIssuer._budget(self)

    def _snapshot(self):
        self._static()
        need(not (self.legacy.HOME / 'ledger').exists(), 'legacy_unit02_allocation_not_in_readonly_graph')
        first = self._budget()
        self._static()
        second = self._budget()
        need(not (self.legacy.HOME / 'ledger').exists(), 'legacy_unit02_allocation_appeared')
        need(first == second, 'original_liabilities_changed_during_readonly_capture')
        paid, guard = second
        need(type(paid) is int and type(guard) is int and 0 <= paid <= guard <= 290,
             'original_paid_guard_overlap')
        return {'schema_version': BASIS, 'binding': deepcopy(self.c['binding']),
                'paid_or_unknown_before': paid, 'outside_guard': guard, 'campaign_limit': 290,
                'released': 0, 'config_sha256': self.config_sha, 'issuer_sha256': self.self_sha,
                'dispatch_authorized': False, 'allocation_namespace': None,
                'coverage': 'original_issuer06_outside_graph_canonical_own_absence_only'}

    def capture_segmented_budget(self):
        need(self.basis is None, 'one_readonly_basis_per_owner')
        data = self._snapshot()
        self.pending_basis = deepcopy(data)
        try:
            self.basis = self.facade._issue_basis_from_root(self, data)
        finally:
            self.pending_basis = None
        return self.basis

    def close_basis(self, basis):
        need(basis is self.basis and self.basis is not None, 'actual_original_basis')
        current = self._snapshot()
        need(current == self.facade._basis_record(basis, self), 'readonly_basis_stale')
        return deepcopy(current)

    def assess_schedule(self, basis, root, authority, plan):
        """Complete original semantic/plan/native checks; still NO permission."""
        before = self.close_basis(basis)
        root = Path(root).absolute()
        need(root == self.root, 'same_actual_owner_root')
        runtime = self.owners['runtime']
        facts = runtime.verify_plan_authority(root, authority)
        issued = authority._facts()  # Reached only after genuine original type/seal check.
        runtime._validate_plan_source(plan, issued['source'])
        self.owners['workflow'].validate_plan(plan)
        self.owners['planner']._limits(facts, plan['nodes'])
        b = self.c['binding']
        need(facts['run_id'] == b['run_id'] == plan['run_id']
             and facts['planner'] == b['planner'] == plan['planner']
             and facts['registry_epoch'] == b['epoch']
             and self.h.digest(self.h.canonical(facts['source_policy'])) == b['source_policy_digest'],
             'actual_plan_source_policy_epoch_binding')
        profile = runtime.PROFILE[plan['planner']]
        data = bounded_schedule_liability(before['paid_or_unknown_before'], before['outside_guard'],
                                          len(plan['nodes']), profile[1])
        need(runtime.verify_plan_authority(root, authority) == facts
             and self.close_basis(basis) == before, 'plan_financial_source_changed')
        return {**data, 'schema_version': SCHEDULE, 'plan_digest': plan['plan_digest'],
                'node_catalog_digest': self.h.digest(self.h.canonical(plan['nodes'])),
                'native_profile': profile[0], 'authority_digest': facts['authority_digest'],
                'basis_digest': self.h.digest(self.h.canonical(before)),
                'claim_ref': None, 'born_ref': None, 'proof_ref': None}

    def _paid_owners(self):
        """Require the actual integrated original owners BEFORE lock/claim writes.

        Hook bodies are source-pinned in the existing config. No caller supplies
        a readiness flag, replacement reader, native reservation or grant.
        """
        self._static()
        # Original U06 paid admission/currentness requirements are reused from
        # this same config, not an additional carrier or environment registry.
        c = self.c
        need(c.get('official_runtime_evidence') and c.get('process_environment_sha256'),
             'original_paid_runtime_and_environment_admission')
        self.h.verify_runtime_observation(self.h.parse(self.h.pinned(c['official_runtime_evidence'])))
        need(self.h.digest(self.h.canonical({k: os.environ.get(k) for k in self.h.ENV_KEYS}))
             == c['process_environment_sha256'], 'original_paid_environment_stable')
        self._integration_owners()

    def _integration_owners(self):
        self._static()
        need(self.store_module is not None and self.prefix is not None,
             'original_store03_and_prefix_required')
        self._identity(self.store_module, TASK / 'night-handoff/story23-segmented-financial-prefix-store-followup03-draft/segmented_financial_prefix_store.py',
                       '399da40f13de11fa50f80101c83678b651610e052b98c1ce0f00390ecc645cc0')
        self._identity(self.prefix, TASK / 'night-handoff/story23-segmented-financial-prefix-validator-draft-01/segmented_financial_prefix.py',
                       'faa4da6183374d00603ddb213bc87a1cf82f0f8263630aef1d23bc1e8eb14adb')
        runtime = self.owners['runtime']
        # The original runtime owns native source/currentness, birth, reservation
        # and completed-result replay. An absent implementation refuses here,
        # before even original locked() is entered.
        names = ('financial_preclaim', 'financial_current', 'financial_reservation',
                 'financial_persisted', 'financial_outcome', 'financial_birth', 'financial_reference', 'financial_funding', 'financial_archive', 'financial_reconcile_outcome',
                 'financial_archive_reference', 'financial_archive_funding', 'financial_repair_birth', 'financial_dispatch_contract')
        functions = {}
        for name in names:
            fn = getattr(runtime, name, None)
            need(callable(fn) and fn.__globals__ is runtime.__dict__
                 and Path(fn.__code__.co_filename).absolute() == Path(runtime.__file__).absolute(),
                 'native_financial_owner_not_integrated:' + name)
            functions[name] = (fn, fn.__code__)
        if self.integration is not None:
            need(functions == self.integration, 'native_financial_owner_unchanged')
        self.integration = functions

    def _outside(self):
        # U06's graph excludes its own canonical HOME02 by construction; its
        # legacy01 refusal and all old99/H1/H2/H3 originals remain unchanged.
        self._static()
        first = self._budget()
        self._static()
        need(self._budget() == first, 'outside_liabilities_changed')
        return first

    @contextmanager
    def hold_segmented_plan(self, root, authority, plan):
        self._paid_owners()  # Paired facade + native hooks before any lock write.
        need(self.store is None and self.grant is None, 'one_canonical_schedule')
        basis = self.capture_segmented_budget()
        self.assessment = self.assess_schedule(basis, root, authority, plan)
        self.authority, self.plan = authority, deepcopy(plan)
        runtime = self.owners['runtime']
        # Genuine owner function replays PlanAuthority/full plan and constructs
        # the finite claim from actual native/source/runtime/time facts. It
        # never accepts the assessment as permission or caller totals.
        claim, native_state = runtime.financial_preclaim(self, authority, plan)
        self.prefix._claim(claim)
        need(claim['base_paid_or_unknown'] >= self.assessment['paid_or_unknown_before']
             and claim['outside_guard'] >= self.assessment['outside_guard']
             and claim['hold'] == len(plan['nodes'])
             and claim['binding']['plan_digest'] == plan['plan_digest'],
             'complete_original_claim_not_assessment_permission')
        self.store = self.store_module.FinitePrefixStore(HOME, expected_claim=claim,
                                                        helpers=self.h, prefix=self.prefix)
        with self.store.held():  # The ONE original H.Controller.locked lease.
            self._paid_owners()
            need(runtime.financial_preclaim(self, authority, plan) == (claim, native_state),
                 'fresh_preclaim_source_native_outside_CAS')
            self.native_state = native_state
            created = self.store.create_claim()
            self.pending_grant = {'claim': deepcopy(claim), 'snapshot': created['snapshot']}
            try:
                self.grant = self.facade._issue_schedule_from_root(self)
            finally:
                self.pending_grant = None
            try:
                with self.facade._schedule_scope(self, self.grant):
                    try:
                        yield self.grant
                        closed = self._current_schedule(self.grant)
                        need(closed['facts']['prefix_disposition'] == 'complete', 'incomplete_schedule_retains_full_hold')
                    except BaseException as error:
                        # Keep the actual scope/lease live while retaining STOP;
                        # preserve the original failure if close itself fails.
                        try:
                            current = self._current_schedule(self.grant)
                            if current['facts']['prefix_disposition'] != 'retained-stop':
                                self.store.retain_stop(type(error).__name__,
                                    native_observations=current['native'], expected_snapshot=current['snapshot'])
                        except BaseException as close_error:
                            error.add_note('financial_STOP_not_written:' + str(close_error))
                        raise
            finally:
                self.grant = None

    def _current_schedule(self, grant):
        need(grant is self.grant and grant is not None and self.store is not None,
             'actual_current_schedule_grant')
        self.store._held()
        self._paid_owners()
        need(self._outside() == self.native_state['outside_root_budget'],
             'outside_graph_drift_retains_own_full_hold')
        # This actual native owner returns exact bytes/read observations from
        # original run/journal, never caller-provided native DATA.
        native = self.owners['runtime'].financial_current(self, self.native_state)
        state = 'retained-stop' if os.path.lexists(HOME / 'ledger/STOP.json') else 'open-prefix'
        inspected = self.store.inspect_readonly(native_observations=native, expected_state=state)
        return {**inspected, 'native': native}

    def before_native_reserve(self, grant, session, node, reservation, claim, claim_path):
        before = self._current_schedule(grant)
        event, after_native = self.owners['runtime'].financial_reservation(
            self, session, node, reservation, claim, claim_path, before)
        return self.store.append_event(event, native_before=before['native'], native_after=after_native,
                                       expected_snapshot=before['snapshot'])

    def after_native_persist(self, grant, session, reservation):
        self.owners['runtime'].financial_persisted(self, session, reservation)
        return self._current_schedule(grant)

    def assert_paid_node(self, grant, session, reservation):
        current = self._current_schedule(grant)
        self.owners['runtime'].financial_persisted(self, session, reservation)
        need(current['facts']['unsettled_node_id'] is not None,
             'actual_financial_intent_before_original_dispatch')
        self.pending_dispatch = (session, reservation)
        return None

    def after_native_outcome(self, grant, session, reservation, verified_result):
        before = self._current_schedule(grant)
        event = self.owners['runtime'].financial_outcome(self, session, reservation, verified_result, before)
        return self.store.append_event(event, native_before=before['native'], native_after=before['native'],
                                       expected_snapshot=before['snapshot'])

    def paid_dispatch_contract(self, grant):
        need(grant is self.grant and grant is not None and self.pending_dispatch is not None,
             'actual_pending_original_paid_node')
        session, reservation = self.pending_dispatch
        return self.owners['runtime'].financial_dispatch_contract(self, session, reservation)

    def birth_inputs(self, grant, root, plan, native_funding, runtime_identity):
        need(grant is self.grant and grant is not None, 'actual_birth_grant')
        self.store._held()
        self._paid_owners()
        return self.owners['runtime'].financial_birth(self, root, plan, native_funding, runtime_identity)

    def financial_reference(self, grant, root, plan):
        need(grant is self.grant and grant is not None, 'actual_reference_grant')
        self.store._held()
        return self.owners['runtime'].financial_reference(self, root, plan)

    def _existing_prefix(self):
        self._static()
        self._integration_owners()
        # Actual fixed old records, never supplied claim/native dictionaries.
        first = self.h.parse(self.h.read(HOME / 'ledger/000001.json'))
        claim = first['event']
        self.prefix._claim(claim)
        b, expected = claim['binding'], self.c['binding']
        need(b['root'] == str(self.root) and b['source_root'] == str(self.source)
             and all(b[key] == expected[key] for key in ('run_id', 'planner', 'epoch', 'source_policy_digest')),
             'actual_existing_claim_config_binding')
        runtime = self.owners['runtime']
        run = runtime._homes(self.root, b['planner'], b['run_id'])
        plan_path = run / 'b/plan.json'
        if os.path.lexists(plan_path):
            plan = runtime.value(self.root, plan_path.relative_to(self.root).as_posix())
        else:
            # Before native birth, reuse the full actual plan already admitted
            # in existing config.input_files (the original CLI --plan input).
            # No plan reconstructed from a summary, digest or caller dictionary.
            plans = []
            for ref in self.c['input_files']:
                raw = self.h.pinned(ref, metadata=False)
                try:
                    value = runtime.codec.strict_json_loads(raw)
                except ValueError:
                    continue
                if type(value) is dict and value.get('schema_version') == self.owners['workflow'].PLAN                         and value.get('plan_digest') == b['plan_digest']:
                    plans.append(value)
            need(len(plans) == 1, 'actual_full_plan_input_unavailable_or_ambiguous')
            plan = plans[0]
        self.owners['workflow'].validate_plan(plan)
        need(plan['plan_digest'] == b['plan_digest'] and plan['nodes'] == claim['nodes'],
             'actual_native_archived_complete_plan')
        if self.store is None:
            self.store = self.store_module.FinitePrefixStore(HOME, expected_claim=claim, helpers=self.h, prefix=self.prefix)
        else:
            need(self.store._claim() == claim, 'same_existing_prefix_owner')
        if self.plan is not None:
            need(self.plan == plan, 'same_existing_plan_owner')
        self.plan = plan
        return run

    def inspect_archived_fiscal_proof(self):
        """Independent readonly actual replay, not a grant or new claim.

        The transient archive scope only lets the original native verifier read
        the actual financial birth reference. It has no reservation/mint API.
        """
        need(self.grant is None, 'archive_not_live_dispatch_scope')
        run = self._existing_prefix()
        before = self.store._fresh_snapshot()
        with self.facade._archive_scope(self):
            replay = self.owners['runtime'].financial_archive(self, run)
        need(self.store._fresh_snapshot() == before, 'archive_prefix_read_closure')
        self._static()
        self.archive_state = replay
        return {k: deepcopy(v) for k, v in replay.items() if k not in ('native_state', 'verified_results', 'snapshot', 'native')}

    @contextmanager
    def resume_segmented_claim(self, *, planning_contract=None, semantic_catalog_ref=None):
        self._paid_owners()
        need(self.grant is None, 'no_parallel_financial_scope')
        self._existing_prefix()
        with self.store.held():
            self._paid_owners()
            run = self.owners['runtime']._homes(self.root, self.plan['planner'], self.plan['run_id'])
            if not os.path.lexists(run):
                # Same existing claim, zero financial intents. Source/native
                # admission is fresh through the real original factory; no old
                # PlanAuthority dict or fabricated empty target is accepted.
                need(planning_contract is not None, 'original_source_request_required_before_native_birth')
                runtime = self.owners['runtime']
                self.authority = runtime.capture_plan_authority(self.root, run_id=self.plan['run_id'],
                    planner=self.plan['planner'], planning_contract=planning_contract,
                    semantic_catalog_ref=semantic_catalog_ref)
                rebuilt, native_state = runtime.financial_preclaim(self, self.authority, self.plan)
                rebuilt['context_limit'] = self.store._claim()['context_limit']
                need(rebuilt == self.store._claim(), 'same_prebirth_claim_actual_source_and_budget')
                inspected = self.store.inspect_readonly(native_observations=[], expected_state='open-prefix')
                self.archive_state = {**inspected, 'native_state':native_state, 'native_blocked':None,
                                      'same_original_claim_at_current_source':True, 'native_birth_present':False}
            else:
                self.inspect_archived_fiscal_proof()
            replay = self.archive_state
            # STOP/partial/unknown never grants next-node dispatch. Completed
            # cold replay is readonly through inspect, with no fresh intent.
            need(replay['facts']['prefix_disposition'] == 'open-settled-prefix'
                 and replay['native_blocked'] is None and replay['same_original_claim_at_current_source'] is True,
                 'retained_or_completed_or_stale_prefix_not_dispatchable')
            self.native_state = replay['native_state']
            self.pending_grant = {'claim': self.store._claim(), 'snapshot': replay['snapshot']}
            try:
                self.grant = self.facade._resume_schedule_from_root(self)
            finally:
                self.pending_grant = None
            try:
                with self.facade._schedule_scope(self, self.grant):
                    try:
                        yield self.grant
                        need(self._current_schedule(self.grant)['facts']['prefix_disposition'] == 'complete',
                             'resumed_schedule_incomplete_retains_full_hold')
                    except BaseException as error:
                        try:
                            current = self._current_schedule(self.grant)
                            if current['facts']['prefix_disposition'] != 'retained-stop':
                                self.store.retain_stop(type(error).__name__, native_observations=current['native'],
                                                       expected_snapshot=current['snapshot'])
                        except BaseException as close_error:
                            error.add_note('financial_STOP_not_written:' + str(close_error))
                        raise
            finally:
                self.grant = None

    def reconcile_completed_intent(self):
        """Explicit zero-model fiscal outcome roll-forward; never redispatch.

        An immutable STOP forbids append. A native completion is accepted only
        through the original stored-result replay factory and actual journal.
        """
        self._paid_owners()
        self._existing_prefix()
        with self.store.held():
            self.inspect_archived_fiscal_proof()
            replay = self.archive_state
            need(not os.path.lexists(HOME / 'ledger/STOP.json')
                 and replay['facts']['prefix_disposition'] == 'unsettled-intent',
                 'only_open_pending_intent_may_reconcile')
            with self.facade._archive_scope(self):
                result = self.owners['runtime'].financial_reconcile_outcome(self, replay)
            return {**result, 'redispatch_authorized': False, 'released': 0}

    def repair_native_birth(self, *, planning_contract, semantic_catalog_ref=None):
        self._paid_owners()
        run = self._existing_prefix()
        with self.store.held():
            with self.facade._archive_scope(self):
                return self.owners['runtime'].financial_repair_birth(self,run,planning_contract,semantic_catalog_ref)

    verify_archived_fiscal_proof = inspect_archived_fiscal_proof

# Captured at the original source load, not from a caller descriptor.
_ORIGINAL_METHODS = {name: (getattr(RootSegmentedIssuer, name),
    getattr(getattr(RootSegmentedIssuer, name), '__wrapped__', getattr(RootSegmentedIssuer, name)).__code__)
    for name in ('__init__', '_identity', '_remember', '_pair', '_static', '_closed_chain', '_host3_graph', '_budget', '_snapshot', 'capture_segmented_budget', 'close_basis', 'assess_schedule', '_paid_owners', '_integration_owners', '_outside', 'hold_segmented_plan', '_current_schedule', 'before_native_reserve', 'after_native_persist', 'assert_paid_node', 'after_native_outcome', 'paid_dispatch_contract', 'birth_inputs', 'financial_reference', '_existing_prefix', 'inspect_archived_fiscal_proof', 'resume_segmented_claim', 'reconcile_completed_intent', 'repair_native_birth')}
