"""Typed DATA transformation regressions, never owner/model qualification."""
from copy import deepcopy
import unittest

import _b_route_compensation_partition as partition
import _b_route_compact_literal as compact


class PreservingPartitionDataTests(unittest.TestCase):
    def test_identity_spelling_roundtrip_is_ordered_typed_and_full_width(self):
        digest='sha256:'+bytes(range(32)).hex()
        value={digest:[digest,'~h64:literal','~~literal','sha256:'+'A'*64,True,1,1.0,-0.0]}
        before=deepcopy(value)
        wire=partition.identity_spelling(value)
        self.assertEqual(48,len(next(iter(wire))))
        self.assertEqual(partition.materials.ordered(value),partition.materials.ordered(
            partition.identity_spelling(wire,decode=True)))
        self.assertEqual(before,value)
        for invalid in ('~unknown','~h64:'+'A'*42,'~h64:'+'A'*43+'=', '~h64:'+'A'*42+'B'):
            with self.subTest(invalid=invalid),self.assertRaises(partition.NotApplicable):
                partition.identity_spelling(invalid,decode=True)
        with self.assertRaises(partition.NotApplicable):
            partition.identity_spelling({next(iter(wire)):1,digest:2},decode=True)

    def test_revision_rebind_is_exact_typed_self_use_only(self):
        original={'plan_id':'P','revision':1,'lineage':{},'uses':[
            {'kind':'command','definition_id':'C','owner_plan_id':'P','owner_revision':1},
            {'kind':'state','definition_id':'S','owner_plan_id':'Other','owner_revision':8}],
            'meaning':{'raw':'full native meaning','values':[True,1,1.0,-0.0]}}
        before=deepcopy(original)
        resources=partition._Resources(compact._work(None))
        result,count=partition._new_plan(original,2,{'previous':'exact P1'},resources)
        self.assertEqual(1,count);self.assertEqual(2,result['uses'][0]['owner_revision'])
        self.assertEqual(8,result['uses'][1]['owner_revision']);self.assertEqual(before,original)
        self.assertEqual(original['meaning'],result['meaning'])

    def test_business_object_with_same_named_fields_is_not_normalized(self):
        original={'plan_id':'P','revision':1,'lineage':{},
            'business':{'owner_plan_id':'P','owner_revision':1,'meaning':'not a typed owner use'}}
        with self.assertRaises(partition.NotApplicable):partition._new_plan(original,2,{})

    def test_exact_atom_restoration_and_wrong_type_overlap_rejection(self):
        atoms={'A':{'meaning':'complete 中文','types':[True,1,1.0,-0.0]},'B':{'meaning':'complete B'}}
        r=partition._Resources(compact._work(None))
        value={'business_atoms_digest':r.digest(atoms),'governance_packet':[
            {'reviewed_business_atom':'A'},{'reviewed_business_atom':'B'}],
            'exact_replacements':[{'path':[0],'atom':'A'},{'path':[1],'atom':'B'}]}
        self.assertEqual([atoms['A'],atoms['B']],partition.restore_governance(value,atoms,r))
        for kind in ('bool','duplicate','wrong_atom','missing'):
            changed=deepcopy(value)
            if kind=='bool':changed['exact_replacements'][1]['path']=[True]
            elif kind=='duplicate':changed['exact_replacements'].append(deepcopy(changed['exact_replacements'][0]))
            elif kind=='wrong_atom':changed['exact_replacements'][0]['atom']='B'
            else:changed['exact_replacements'].pop()
            with self.subTest(kind=kind),self.assertRaises(partition.NotApplicable):
                partition.restore_governance(changed,atoms)

    def test_existing_formal_dependency_uses_whole_fallback(self):
        # DATA selector prefix is sufficient: this branch must return before
        # parsing/transforming any unsupported multi-plan semantic inputs.
        packet={'materials':{'frames':[
            {'subject_schema':'newrouge.b-route-qualified-compensation-review-subject.v3',
             'semantic_fields':{'task_definitions':{},'request':{'selection':{'binding_ref':None}},
               'preview':{'compensation':{'retained_plan_refs':[{'id':'other'}],'retained_binding_refs':[]},'targets':[{}]}}},
            {'subject_schema':'newrouge.b-route-adoption-review-subject.v3',
             'semantic_fields':{'review_scope':{'protection':{'tasks':[],'cumulative':[],'triplet_counts':{}}},
               'native_content':{'selected_dependencies':[]},'allocations':{}}}]}}
        with self.assertRaises(partition.NotApplicable):partition._prepare_data(packet,compact._work(None))


if __name__=='__main__':unittest.main()
