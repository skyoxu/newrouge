"""UNEXECUTED focused current-source checks, not paid integration evidence.

Root preloads the physical Task issuer/facade and current-source runtime using
its existing SourceOnly harness. These tests never open config/ledger/native
DATA; file reads below are the declared original and candidate source only.
"""
import ast
from pathlib import Path
import unittest
import _Root_story23_segmented_schedule_issuer as issuer
import _b_route_segmented_funding as funding
import _b_route_segmented_runtime as runtime


class CanonicalFiscalIntegrationTests(unittest.TestCase):
    def test_null_config_pin_still_rejects_before_path_or_helpers(self):
        class NoPath:
            def __fspath__(self):
                raise AssertionError('no path read')
        with self.assertRaisesRegex(issuer.SegmentedFiscalError, 'actual_root_config_pin_required'):
            issuer.RootSegmentedIssuer(NoPath(), None, host2_helpers=None, legacy_issuer=None,
                facade=None, runtime=None, workflow=None, planner=None)

    def test_separate_carrier_config_role_is_not_canonical_owner(self):
        with self.assertRaisesRegex(issuer.SegmentedFiscalError, 'original_canonical_config_role'):
            issuer.RootSegmentedIssuer(issuer.TASK / 'night-handoff/Root.segmented-budget.json', '0'*64,
                host2_helpers=None, legacy_issuer=None, facade=None, runtime=None, workflow=None, planner=None)

    def test_no_caller_constructed_or_dictionary_schedule_grant(self):
        with self.assertRaisesRegex(funding.SegmentedFundingError, 'actual_canonical_lease_required'):
            funding.SegmentedScheduleGrant()
        for value in ({}, True, None, object.__new__(funding.SegmentedScheduleGrant)):
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(funding.SegmentedFundingError, 'actual_original_schedule_grant'):
                    funding.require_schedule_grant(value)
        with self.assertRaisesRegex(funding.SegmentedFundingError, 'grant_not_serializable'):
            object.__new__(funding.SegmentedScheduleGrant).__reduce__()

    def test_only_new_sibling_delta_is_added_and_own_hold_is_not_added_twice(self):
        native = {'paid_or_unknown_before_run': 78, 'subsequent_full_reservation': 0}
        self.assertEqual(runtime.merge_outside_liabilities(83, 181, native, 0), (83, 181))
        native.update(paid_or_unknown_before_run=85, subsequent_full_reservation=0)
        self.assertEqual(runtime.merge_outside_liabilities(83, 181, native, 7), (90, 188))
        self.assertEqual(issuer.bounded_schedule_liability(83,181,8,96)['guard_if_held'], 189)

    def test_existing_integer_and_290_bounds_remain_closed(self):
        for paid, guard, native in ((True,181,{'paid_or_unknown_before_run':78,'subsequent_full_reservation':0}),
            (83,181,{'paid_or_unknown_before_run':78,'subsequent_full_reservation':True}),
            (83,291,{'paid_or_unknown_before_run':78,'subsequent_full_reservation':0}),
            (182,181,{'paid_or_unknown_before_run':78,'subsequent_full_reservation':0})):
            with self.subTest(paid=paid,guard=guard):
                with self.assertRaises(ValueError):
                    runtime.merge_outside_liabilities(paid,guard,native,0)
        with self.assertRaisesRegex(issuer.SegmentedFiscalError, 'complete_schedule_not_affordable'):
            issuer.bounded_schedule_liability(83,181,192,192)

    def test_v1_branch_bodies_equal_original_current_r59(self):
        original = issuer.TASK / 'r59/scripts/python'
        def node(text, name):
            return next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
        def body(n):
            return [ast.dump(x,include_attributes=False) for x in n.body]
        for old, new in (('prepare_run','_prepare_run_v1'),('_birth','_birth_v1'),
                         ('segmented_run_contract','_segmented_run_contract_v1')):
            before = node((original/'_b_route_segmented_runtime.py').read_text(encoding='utf-8'),old)
            after = node(Path(runtime.__file__).read_text(encoding='utf-8'),new)
            self.assertEqual(body(before),body(after))

    def test_new_born_versions_and_cold_api_reject_caller_data(self):
        self.assertEqual(runtime.FISCAL_RUN, funding.FISCAL_RUN)
        self.assertEqual(runtime.FISCAL_BORN, funding.FISCAL_BORN)
        self.assertNotEqual(runtime.FISCAL_RUN, runtime.RUN)
        for api in (funding.resume_segmented_claim, funding.verify_archived_fiscal_proof):
            with self.assertRaisesRegex(funding.SegmentedFundingError, 'actual_original_canonical_owner'):
                api(object())

    def test_callback_insertions_surround_original_native_publications(self):
        def calls(function):
            tree=ast.parse(Path(function.__code__.co_filename).read_text(encoding='utf-8'))
            for n in ast.walk(tree):
                if isinstance(n,ast.FunctionDef) and n.name==function.__name__:
                    return [(a.lineno,a.func.attr) for a in ast.walk(n)
                            if isinstance(a,ast.Call) and isinstance(a.func,ast.Attribute)]
            raise AssertionError('function source absent')
        import _b_route_segmented_journal as journal
        import _b_route_segmented_workflow as workflow
        reserve=calls(journal._Session.reserve)
        self.assertLess(next(n for n,k in reserve if k=='before_reserve'),next(n for n,k in reserve if k=='_transaction'))
        self.assertGreater(next(n for n,k in reserve if k=='after_persist'),next(n for n,k in reserve if k=='_transaction'))
        complete=calls(journal._Session.complete)
        self.assertGreater(next(n for n,k in complete if k=='after_outcome'),next(n for n,k in complete if k=='_transaction'))
        dispatch=calls(workflow._execute_verified)
        self.assertTrue(any(k=='before_dispatch' for _,k in dispatch))
        # Exact tested faa4/store03 facts ABI, rather than an invented key.
        original_prefix = issuer.TASK / 'night-handoff/story23-segmented-financial-prefix-validator-draft-01/segmented_financial_prefix.py'
        tree = ast.parse(original_prefix.read_text(encoding='utf-8'))
        validate = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_prefix')
        returned = next(n.value for n in validate.body if isinstance(n,ast.Return))
        keys = {k.value for k in returned.keys if isinstance(k,ast.Constant)}
        self.assertIn('prefix_disposition', keys)
        for method in (issuer.RootSegmentedIssuer.hold_segmented_plan.__wrapped__, runtime.financial_reservation):
            source = Path(method.__code__.co_filename).read_text(encoding='utf-8')
            self.assertNotIn("['facts']['disposition']", source)
