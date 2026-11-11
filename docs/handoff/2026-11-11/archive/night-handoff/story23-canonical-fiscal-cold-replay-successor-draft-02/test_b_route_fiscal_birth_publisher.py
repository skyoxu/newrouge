"""UNEXECUTED real original DATA-publisher behavior; no authority/model fixture.

Root's existing owned-TEMP SourceOnly host runs these2 methods. No legacy test
imports, helpers patched, native reservation, model, finance config or grant.
"""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
import _b_route_segmented_journal as journal


OWNED_PARENT = None
MARKER = b'owned-neutral-fiscal-birth.v1\n'


class FiscalBirthPublisherTests(unittest.TestCase):
    @contextmanager
    def owned(self):
        self.assertIsNotNone(OWNED_PARENT, 'Root must supply existing owned fixture parent')
        parent=Path(OWNED_PARENT).resolve()
        temp=tempfile.TemporaryDirectory(prefix='nr23-born-',dir=parent)
        temp._finalizer.detach()
        root=Path(temp.name)
        marker=root/'OWNED.marker'
        marker.write_bytes(MARKER)
        identity=(marker.stat().st_dev,marker.stat().st_ino)
        try:
            yield temp.name
        finally:
            self.assertEqual(root.parent,parent)
            self.assertTrue(root.name.startswith('nr23-born-'))
            self.assertEqual((marker.stat().st_dev,marker.stat().st_ino),identity)
            self.assertEqual(marker.read_bytes(),MARKER)
            temp.cleanup()

    def fixture(self, directory, *, fiscal=True):
        root=Path(directory).resolve()
        run=root/'runs/neutral-cap'
        store=root/'logs/ci/mvg-recovery'
        store.mkdir(parents=True)
        registry={'epoch':7}
        (store/'registry.json').write_text(json.dumps(registry)+'\n',encoding='utf-8')
        run_schema='newrouge.b-route-segmented-planning-run.fiscal-v2' if fiscal else 'newrouge.b-route-segmented-planning-run.v1'
        born_schema='newrouge.b-route-segmented-born.fiscal-v2' if fiscal else 'newrouge.b-route-segmented-born.v1'
        # Explicitly neutral DATA; this primitive never qualifies the facts.
        proof={'schema_version':'neutral.financial-support.DATA','hold':8,'released':0}
        state={'schema_version':run_schema,'run_id':'neutral-cap','recovery':{'store':str(store)},
               'capability_selection':{'calls':[],'total_invocations':0}}
        if fiscal:state['segmented_fiscal_claim']=proof
        initial=deepcopy(state)
        born={'schema_version':born_schema,'run_id':'neutral-cap','initial_calls':0,
              'plan_digest':'sha256:'+'1'*64,'protocol':'newrouge.b-route-segmented-workflow.v1',
              'initial_run_ref':{'path':'runs/neutral-cap/b/initial-run.json','schema_version':run_schema,
                                 'raw_digest':'sha256:'+'2'*64}}
        if fiscal:born['segmented_fiscal_claim']=proof
        files={run/'run.json':state,run/'b/initial-run.json':initial,run/'b/born.json':born,
               run/'b/claim.json':{'schema_version':'neutral.birth-claim.DATA'}}
        after={**registry,'segmented_runs':{'schema_version':'newrouge.b-route-segmented-run-index.v1',
               'campaign':'story25','runs':[{'run_path':'runs/neutral-cap/run.json'}]}}
        return root,run,store,files,after

    def test_real_fiscal_publish_uses_original_journal_and_no_native_qualification(self):
        with self.owned() as directory:
            root,run,store,files,after=self.fixture(directory)
            result=journal.publish_born(root,run,files=files,registry_after=after)
            self.assertEqual(result['model_calls'],0)
            self.assertIs(result['native_qualified'],False)
            saved=json.loads((root/result['journal_ref']).read_text(encoding='utf-8'))
            self.assertEqual(saved['status'],'complete')
            self.assertEqual(saved['result']['verb'],'born')
            self.assertEqual(json.loads((store/'registry.json').read_text(encoding='utf-8')),after)
            for path,value in files.items():
                self.assertEqual(json.loads(path.read_text(encoding='utf-8')),value)

    def test_mixed_born_state_or_initial_ref_rejects_before_publication(self):
        for mutation in ('old-born','old-state','old-initial'):
            with self.subTest(mutation=mutation):
                with self.owned() as directory:
                    root,run,store,files,after=self.fixture(directory)
                    before=(store/'registry.json').read_bytes()
                    if mutation=='old-born':files[run/'b/born.json']['schema_version']='newrouge.b-route-segmented-born.v1'
                    elif mutation=='old-state':files[run/'run.json']['schema_version']='newrouge.b-route-segmented-planning-run.v1'
                    else:files[run/'b/initial-run.json']['schema_version']='newrouge.b-route-segmented-planning-run.v1'
                    with self.assertRaises(ValueError):
                        journal.publish_born(root,run,files=files,registry_after=after)
                    self.assertFalse(run.exists())
                    self.assertFalse((store/'activity').exists())
                    self.assertEqual((store/'registry.json').read_bytes(),before)
