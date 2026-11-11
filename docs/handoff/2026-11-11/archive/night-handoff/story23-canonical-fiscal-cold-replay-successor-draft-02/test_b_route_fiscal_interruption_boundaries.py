"""UNEXECUTED interruption mechanisms using actual original DATA primitives.

Neutral byte graph and JSON publication, not genuine native/financial authority.
No helper/global/function is replaced. Root supplies OWNED_PARENT and preloads
frozen physical helper/store/prefix/neutral-fixture modules as in store03 tests.
"""
from contextlib import contextmanager
from copy import deepcopy
from functools import partial
import json
from pathlib import Path
import tempfile
import unittest
import _Root_story23_financial_store_helpers as helpers
import segmented_financial_prefix as prefix
import segmented_financial_prefix_store as storage
from test_segmented_financial_prefix import neutral_graph, events_of
import _b_route_segmented_journal as journal

OWNED_PARENT=None
MARKER=b'owned-neutral-fiscal-interruption.v1\n'


class FiscalInterruptionMechanismTests(unittest.TestCase):
    @contextmanager
    def owned(self):
        self.assertIsNotNone(OWNED_PARENT)
        parent=helpers.plain(Path(OWNED_PARENT),directory=True)
        temp=tempfile.TemporaryDirectory(prefix='nr23-boundary-',dir=parent)
        temp._finalizer.detach()
        root=Path(temp.name)
        marker=root/'OWNED.marker';marker.write_bytes(MARKER)
        identity=(marker.stat().st_dev,marker.stat().st_ino)
        try:yield root
        finally:
            self.assertEqual(root.parent,parent)
            self.assertTrue(root.name.startswith('nr23-boundary-'))
            self.assertEqual((marker.stat().st_dev,marker.stat().st_ino),identity)
            self.assertEqual(marker.read_bytes(),MARKER)
            temp.cleanup()

    def intent(self,root):
        home=root/'finance';home.mkdir()
        graph=neutral_graph(completed=0,pending=True,persisted=False)
        store=storage.FinitePrefixStore(home,expected_claim=graph['expected_claim'],helpers=helpers,prefix=prefix)
        with store.held():
            first=store.create_claim()
            current=store.append_event(events_of(graph['members'])[1],native_before=[],
                    native_after=graph['native_observations'],expected_snapshot=first['snapshot'])
        return store,graph,current

    def test_native_partial_publication_leaves_one_financial_intent_fullhold_and_no_retry(self):
        with self.owned() as root:
            store,graph,current=self.intent(root)
            first=root/'native/first.json';first.parent.mkdir()
            collision=root/'native/claim.json';collision.mkdir()
            publication=root/'native-publication.json'
            journal.create_journal(root,publication,{first:{'neutral':'first-side-effect'},collision:{'neutral':'second'}},
                                   {},{'neutral_DATA':True})
            with self.assertRaises(OSError):
                journal.resume_journal(root,publication,partial(journal._original_writer,root))
            self.assertEqual(json.loads(first.read_text(encoding='utf-8')),{'neutral':'first-side-effect'})
            self.assertEqual(json.loads(publication.read_text(encoding='utf-8'))['status'],'pending')
            cold=store.inspect_readonly(native_observations=graph['native_observations'],expected_state='open-prefix')
            self.assertEqual(cold['facts']['intent_count'],1)
            self.assertEqual(cold['facts']['hold'],8)
            self.assertEqual(cold['facts']['paid_or_unknown'],84)
            self.assertEqual(cold['facts']['guard_occupancy'],189)
            self.assertEqual(cold['facts']['prefix_disposition'],'unsettled-intent')
            self.assertIs(cold['facts']['redispatch_allowed'],False)
            self.assertIs(cold['facts']['native_qualification_verified'],False)
            self.assertEqual(cold['snapshot'],current['snapshot'])

    def test_native_DATA_complete_then_corrupt_fiscal_outcome_keeps_both_original_evidences(self):
        with self.owned() as root:
            store,graph,current=self.intent(root)
            complete_graph=neutral_graph(completed=1)
            event=events_of(complete_graph['members'])[-1]
            actual=root/'native-result.json';publication=root/'native-complete-publication.json'
            journal.create_journal(root,publication,{actual:{'neutral_DATA':'completed-no-real-model'}},{},{'neutral_DATA':True})
            journal.resume_journal(root,publication,partial(journal._original_writer,root))
            # Explicit owned truncated-write data, not an injected exception or
            # a claim that the real provider completed. Root code is unchanged.
            broken=store.ledger/'000003.json';broken.write_bytes(b'{')
            with store.held():
                with self.assertRaisesRegex(storage.StoreError,'exact_preappend_member_raw_identity_CAS'):
                    store.append_event(event,native_before=complete_graph['native_observations'],
                        native_after=complete_graph['native_observations'],expected_snapshot=current['snapshot'])
            with self.assertRaises(prefix.PrefixError):
                store.inspect_readonly(native_observations=complete_graph['native_observations'],expected_state='open-prefix')
            self.assertEqual(broken.read_bytes(),b'{')
            self.assertEqual(json.loads(publication.read_text(encoding='utf-8'))['status'],'complete')
            self.assertEqual(json.loads(actual.read_text(encoding='utf-8')),{'neutral_DATA':'completed-no-real-model'})
            self.assertEqual((store.ledger/'000002.json').read_bytes(),current['snapshot']['members']['000002.json']['raw'])
