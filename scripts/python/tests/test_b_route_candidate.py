"""3B structure fixtures use an explicit audit assembly seam, never real admission.

Actual synthetic audit rejection is covered separately by the unchanged 3B input
suite. No test invokes a real model, creates a Task, or grants runtime authority.
"""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import _b_route_candidate as candidate
import _b_route_codec as codec
import _b_route_planning_input as planning
import _b_route_schema_resources as schemas
import _b_route_records as records
import _b_route_sources as sources
import dev_cli
import dev_cli_builders as builders
import plan_capabilities
import plan_mvg
import test_b_route_planning_input as input_tests
import test_b_route_records as record_tests


def use(fid="FLOW", owner="proposal-owner"):
    return {"kind":"flow","definition_id":fid,"proposed_owner_key":owner}


def point(node, flow="FLOW"):
    return {"flow_id":flow,"node_id":node}


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = input_tests.PlanningInputTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.put = self.fixture.put
        self.native_proof = self.fixture.proof
        self.fixture.verify.side_effect = self.proof
        self.manifest = {"source_revision":"revision  1 ","manifest_sha256":"sha256:"+"1"*64,
                         "sources":[{"path":"docs/source.md"},{"path":"docs/empty.md"}]}
        self.ledger = {"source_revision":"revision  1 ","source_manifest_sha256":"sha256:"+"1"*64,
            "blocks":[{"block_id":"B1","source_path":"docs/source.md","text":"Rule"},
                      {"block_id":"B2","source_path":"docs/empty.md","text":""}]}
        self.proposal = {"proposal_id":"proposal:keep-original","source_block_ids":["B1"],
            "acceptance_intent":"Keep original  \r\n","prior_requirement_ids":["FR-EXISTING"],"non_task_sinks":["SINK"]}
        self.proposals = [self.proposal]
        self.put("native-manifest.json",self.manifest)
        self.put("native-ledger.json",self.ledger)
        self.prepared = self.fixture.prepare()
        self.frozen = self.fixture.frozen(self.prepared)
        self.value = self.envelope()
        self.count = 0

    def proof(self,obs,reference,*,scope_id):
        value = self.native_proof(obs,reference,scope_id=scope_id)
        for name in ("native-manifest.json","native-ledger.json"):
            obs.read(name)
        value["bundle"].update(manifest=deepcopy(self.manifest),ledger=deepcopy(self.ledger),
                              proposals={"proposals":deepcopy(self.proposals)})
        return value

    def owned(self,owner,path):
        return {"owner":owner,"ref":path,"files":[{"path":path,"raw_digest":codec.raw_digest((self.root/path).read_bytes())}]}

    def flow(self,fid="FLOW"):
        owner=use(fid)
        nodes=[{"id":name,"responsibility":"Keep exact  \r\n","owner":deepcopy(owner),"command_uses":[],"state_uses":[]}
               for name in ("entry","act","success","optional")]
        edges=[{"id":"edge"+str(i),"from":point(a,fid),"to":point(b,fid),"condition":"Declared condition",
                "responsibility":"Flow owner", "owner":deepcopy(owner)}
               for i,(a,b) in enumerate((("entry","act"),("act","success"),("success","entry")))]
        boundaries=[{"id":name,"kind":name,"node":point(name,fid),"condition":"Declared boundary",
                     "required":True,"rationale":"Source obligation"} for name in ("entry","success")]
        obligation={"applicability":"not_applicable","rationale":"Source describes pure logical rule.",
                    "responsibilities":[],"owner":deepcopy(owner)}
        return {"id":fid,"proposed_owner_key":"proposal-owner","requirement_ids":[self.proposal["proposal_id"]],
            "capability_ids":["proposal:capability-main","CAP-EXISTING"],
            "source_block_ids":["B1"],"entry_condition":"Enter when requested",
            "branches":[{"kind":k,"applicability":"not_applicable","rationale":"No such source obligation", "boundary_ids":[]}
                        for k in ("failure","cancel","return")],
            "handoffs":[],"state_owners":[],"parts":[{"kind":k,"applicability":"applicable" if k=="domain_rules" else "not_applicable",
                "rationale":"Source-backed logical applicability","responsibilities":["Keep rule"] if k=="domain_rules" else []}
                for k in sorted(candidate.PARTS)],"observable_result":"Visible rule result","verification_targets":["Observe result"],
            "ui":{**deepcopy(obligation),"inputs":[],"feedback":[],"scene_entry":[],"scene_return":[]},
            "human_verification":deepcopy(obligation),"graph":{"nodes":nodes,"edges":edges,"boundaries":boundaries,
                "loops":[{"id":"retry","anchors":[point("act",fid)],"exit_boundary_ids":["success"],
                          "description":"Successful boundary allows reentry","exit_condition":"Success observed"}]}}

    def envelope(self):
        rid=self.proposal["proposal_id"]
        verification={"requirement_id":rid,"disposition":"flow","flow_id":"FLOW","rationale":"Observable result",
                      "sink_id":None,"verification_ref":None,"authority_ref":None,"evidence_ids":[]}
        return {"schema_version":candidate.SCHEMA,"input_stage":"3b","input_identity":self.frozen["input_identity"],
            "provenance":{"kind":"manual","declaration":"Complete manually supplied candidate", "upstream_model_history":"unknown",
                          "draft_chain":[],"final_draft_identity":None},
            "content":{"source_identity":{"manifest_ref":self.owned("source_manifest","native-manifest.json"),
                "ledger_ref":self.owned("source_ledger","native-ledger.json"),"source_revision":self.manifest["source_revision"],
                "source_manifest_digest":self.manifest["manifest_sha256"]},
                "requirements":[{"requirement_id":rid,**{k:deepcopy(self.proposal[k]) for k in
                    ("source_block_ids","acceptance_intent","prior_requirement_ids","non_task_sinks")}}],
                "out_of_scope_requirement_ids":[],"selected_dependencies":[],
                "definitions":{"flows":[self.flow()],"commands":[],"states":[]},"logical_references":[],
                "requirement_verification":[verification],"coverage_table":[{k:v for k,v in verification.items() if k!="evidence_ids"}],
                "requirement_route_memberships":[{"requirement_id":rid,"flow_id":"FLOW","observable_role":"Primary visible result"}],
                "requirement_evidence":[],"evidence_source_refs":[],
                "applicability":[{"requirement_id":rid,"disposition":"flow","rationale":"Observable result","other_verification_refs":[]}],
                "unresolved":[],"implementation_objects":[{"id":"planned-scene","kind":"scene","availability":"planned",
                    "owner":use(),"expected_type":"LaterScene","lifecycle":"Bound later","target_ref":None,
                    "later_checks":["type","compile","binding","engine"]}]}}

    def run_check(self,value=None,run=None):
        self.count+=1
        self.put("candidate.json",self.value if value is None else value)
        with patch.object(subprocess,"run",side_effect=AssertionError("No subprocess")):
            return candidate.validate(self.root,run_id=run or "candidate"+str(self.count),
                prepared_ref=self.prepared["resume_ref"],candidate="candidate.json")

    def passes(self,value=None):
        report=self.run_check(value)
        self.assertEqual(report["status"],"passed",report)
        self.assertEqual(report["claim"],"candidate_structure_only")
        self.assertFalse(report["formal_adoption"] or report["runtime_verified"] or report["readiness"])
        return report

    def rejects(self,value):
        report=self.run_check(value)
        self.assertEqual(report["status"],"blocked",report)
        self.assertTrue(report["diagnostics"])
        return report

    def test_complete_planned_reentry_scc_and_optional_unreachable_node(self):
        report=self.passes()
        facts=report["facts"]
        self.assertEqual(len(facts["graph"]["cyclic_components"]),1)
        self.assertEqual(len(facts["graph"]["cyclic_components"][0]),3)
        self.assertFalse(facts["graph"]["termination_proven"])
        self.assertEqual(facts["upstream_model_history"],"unknown")
        saved=codec.strict_json_loads((self.root/report["output_ref"]/"candidate.json").read_bytes())
        self.assertEqual(saved,self.value)
        self.assertEqual(saved["content"]["source_identity"]["source_revision"],"revision  1 ")

    def test_same_node_multiple_boundary_roles_and_self_loop(self):
        value=deepcopy(self.value)
        graph=value["content"]["definitions"]["flows"][0]["graph"]
        graph["nodes"]=graph["nodes"][:1]
        graph["edges"]=[{**graph["edges"][0],"from":point("entry"),"to":point("entry")}]
        graph["boundaries"][1]["node"]=point("entry")
        graph["loops"][0]["anchors"]=[point("entry")]
        self.passes(value)

    def test_original_internal_ids_and_responsibility_whitespace_are_preserved(self):
        value=deepcopy(self.value)
        graph=value["content"]["definitions"]["flows"][0]["graph"]
        graph["nodes"][0]["id"]=" entry : original  "
        for row in candidate.walk(graph):
            if set(row)=={"flow_id","node_id"} and row["node_id"]=="entry":
                row["node_id"]=" entry : original  "
        report=self.passes(value)
        saved=codec.strict_json_loads((self.root/report["output_ref"]/"candidate.json").read_bytes())
        self.assertEqual(saved,value)

    def test_one_explanation_can_cover_two_sccs_without_sink_rules(self):
        value=deepcopy(self.value)
        graph=value["content"]["definitions"]["flows"][0]["graph"]
        for ident,start,end in (("optional-self","optional","optional"),("optional-success","optional","success")):
            graph["edges"].append({**deepcopy(graph["edges"][0]),"id":ident,"from":point(start),"to":point(end)})
        graph["loops"][0]["anchors"].append(point("optional"))
        self.assertEqual(len(self.passes(value)["facts"]["graph"]["cyclic_components"]),2)

    def test_retry_cycle_can_reach_success_without_returning_to_entry(self):
        value=deepcopy(self.value)
        graph=value["content"]["definitions"]["flows"][0]["graph"]
        graph["edges"][2].update({"from":point("act"),"to":point("act")})
        self.passes(value)

    def test_cross_flow_same_internal_ids_and_shared_requirement_routes(self):
        value=deepcopy(self.value)
        content=value["content"]
        second=self.flow("FLOW:2")
        content["definitions"]["flows"].append(second)
        first=content["definitions"]["flows"][0]
        first["graph"]["edges"].append({**deepcopy(first["graph"]["edges"][0]),"id":"cross",
            "from":point("act"),"to":point("entry","FLOW:2")})
        content["requirement_route_memberships"].append({"requirement_id":self.proposal["proposal_id"],"flow_id":"FLOW:2",
                                                       "observable_role":"Shared secondary behavior"})
        report=self.passes(value)
        self.assertEqual(report["facts"]["accounting"]["unique_requirement_count"],1)
        self.assertEqual(report["facts"]["accounting"]["route_membership_count"],2)

    def test_graph_invalid_endpoints_duplicate_ids_owner_reachability_and_exits(self):
        mutations=[lambda f:f["graph"]["edges"][0]["to"].update(node_id="unknown"),
            lambda f:f["graph"]["nodes"].append(deepcopy(f["graph"]["nodes"][0])),
            lambda f:f["graph"]["edges"].append(deepcopy(f["graph"]["edges"][0])),
            lambda f:f["graph"]["boundaries"].append(deepcopy(f["graph"]["boundaries"][0])),
            lambda f:f["graph"]["nodes"][1]["owner"].update(proposed_owner_key="missing"),
            lambda f:f["graph"]["boundaries"][1].update(node=point("optional")),
            lambda f:f["graph"].update(loops=[]),
            lambda f:f["graph"]["loops"][0].update(exit_boundary_ids=["unknown"]),
            lambda f:f["graph"]["loops"][0].update(anchors=[point("optional")]),
            lambda f:f["parts"].pop(),
            lambda f:f["branches"][0].update(applicability="applicable"),
            lambda f:f["state_owners"].append(use())]
        for mutation in mutations:
            value=deepcopy(self.value)
            mutation(value["content"]["definitions"]["flows"][0])
            with self.subTest(mutation=mutation): self.rejects(value)

    def test_same_node_id_with_different_valid_body_is_semantically_ambiguous(self):
        value=deepcopy(self.value)
        graph=value["content"]["definitions"]["flows"][0]["graph"]
        duplicate={**deepcopy(graph["nodes"][0]),"responsibility":"A distinct valid declaration for the same node"}
        graph["nodes"].append(duplicate)
        schemas.validate(value,candidate.SCHEMA,auxiliary=True)
        report=self.rejects(value)
        self.assertIn("unique Flow-local node",json.dumps(report))

    def test_entered_cycle_must_reach_required_success_despite_optional_cancel_exit(self):
        value=deepcopy(self.value)
        flow=value["content"]["definitions"]["flows"][0]
        graph=flow["graph"]
        graph["nodes"].append({**deepcopy(graph["nodes"][0]),"id":"cancel"})
        template=graph["edges"][0]
        graph["edges"]=[{**deepcopy(template),"id":"edge"+str(index),"from":point(start),"to":point(end)}
                        for index,(start,end) in enumerate((("entry","success"),("entry","act"),("act","act"),("act","cancel")))]
        graph["boundaries"].append({"id":"cancel","kind":"cancel","node":point("cancel"),
            "condition":"Optional cancellation","required":False,"rationale":"Declared optional exit"})
        graph["loops"][0]["exit_boundary_ids"]=["cancel"]
        next(row for row in flow["branches"] if row["kind"]=="cancel").update(applicability="applicable",boundary_ids=["cancel"])
        report=self.rejects(value)
        self.assertIn("required boundaries reachable from related cycle positions",json.dumps(report))

    def test_parallel_declared_edges_are_counted_without_duplicate_traversal_edges(self):
        value=deepcopy(self.value)
        graph=value["content"]["definitions"]["flows"][0]["graph"]
        graph["edges"].append({**deepcopy(graph["edges"][0]),"id":"parallel-alternative","condition":"A different declared condition"})
        report=self.passes(value)
        self.assertEqual(report["facts"]["graph"]["edge_count"],4)
        self.assertEqual(len(report["facts"]["graph"]["cyclic_components"]),1)

    def test_implementation_objects_retain_all_four_later_checks(self):
        checks=["type","compile","binding","engine"]
        self.passes()
        for omitted in checks:
            value=deepcopy(self.value)
            value["content"]["implementation_objects"][0]["later_checks"]=[item for item in checks if item!=omitted]
            report=self.rejects(value)
            self.assertEqual(report["diagnostics"][0]["stage"],"schema")
        value=deepcopy(self.value)
        value["content"]["implementation_objects"][0]["later_checks"]=["engine"]
        self.rejects(value)

    def test_ui_and_human_obligations_cannot_be_empty_labels(self):
        for field in ("ui","human_verification"):
            value=deepcopy(self.value)
            obligation=value["content"]["definitions"]["flows"][0][field]
            obligation.update(applicability="applicable")
            self.rejects(value)
            obligation["responsibilities"]=["Inspect visible result"]
            if field=="ui":
                self.rejects(value)
                for key in ("inputs","feedback","scene_entry","scene_return"):
                    obligation[key]=["Explicit source-backed " + key]
            self.passes(value)

    def test_projection_domains_membership_and_owner_duplicates_fail(self):
        mutations=[lambda c:c["coverage_table"][0].update(rationale="drift"),
                   lambda c:c["requirement_verification"].append(deepcopy(c["requirement_verification"][0])),
                   lambda c:c.update(requirement_route_memberships=[]),
                   lambda c:c["definitions"]["flows"].append(deepcopy(c["definitions"]["flows"][0])),
                   lambda c:c["requirements"][0].update(requirement_id="FR-EXISTING"),
                   lambda c:c["requirements"][0].update(prior_requirement_ids=[]),
                   lambda c:c.update(out_of_scope_requirement_ids=["invented"])]
        for mutate in mutations:
            value=deepcopy(self.value); mutate(value["content"])
            self.rejects(value)

    def nonflow(self,disposition):
        value=deepcopy(self.value); content=value["content"]
        content["definitions"]["flows"]=[]
        content["implementation_objects"]=[]
        content["requirement_route_memberships"]=[]
        verification=content["requirement_verification"][0]
        verification.update(disposition=disposition,flow_id=None,rationale="Source-backed disposition")
        app=content["applicability"][0]
        app.update(disposition=disposition,rationale="Source-backed disposition")
        if disposition=="source_gap":
            content["unresolved"]=[{"requirement_id":self.proposal["proposal_id"],"reason":"Needs independent clarification","source_block_ids":["B1"]}]
        else:
            owner="authority" if disposition=="deferred" else "other_verification"
            reference=self.owned(owner,"docs/constraint.md")
            verification["authority_ref" if disposition=="deferred" else "verification_ref"]="docs/constraint.md"
            if disposition=="other_verification":
                verification["sink_id"]="SINK"
                app["other_verification_refs"]=[reference]
            content["evidence_source_refs"]=[reference]
        content["coverage_table"]=[{k:v for k,v in verification.items() if k!="evidence_ids"}]
        return value

    def test_nonflow_other_deferred_and_explicit_source_gap(self):
        for disposition in ("other_verification","deferred","source_gap"):
            value=self.nonflow(disposition)
            self.passes(value)
            value["content"]["applicability"][0]["rationale"]="  \r\n"
            self.rejects(value)
        value=self.nonflow("source_gap"); value["content"]["unresolved"]=[]; self.rejects(value)
        value=self.nonflow("other_verification"); value["content"]["evidence_source_refs"]=[]; self.rejects(value)

    def test_shared_evidence_deduplicated_and_wrong_requirement_scope_rejected(self):
        value=deepcopy(self.value); content=value["content"]
        rid=self.proposal["proposal_id"]
        evidence={"requirement_id":rid,"evidence_id":"evidence-original","kind":"implementation_reference",
            "source_ref":"docs/constraint.md","covered_behavior":"Original descriptive reference","flow_ids":["FLOW"],"test_ids":[]}
        content["requirement_evidence"]=[evidence]
        content["evidence_source_refs"]=[self.owned("implementation_reference","docs/constraint.md")]
        content["requirement_verification"][0]["evidence_ids"]=["evidence-original"]
        self.assertEqual(self.passes(value)["facts"]["accounting"]["unique_evidence_count"],1)
        content["requirement_evidence"].append(deepcopy(evidence)); self.rejects(value)
        content["requirement_evidence"].pop(); evidence["flow_ids"]=["missing"]; self.rejects(value)
        evidence["flow_ids"]=["FLOW"]; evidence["requirement_id"]="OTHER"; self.rejects(value)

    def test_model_original_chain_and_no_request_preflight_or_fallback(self):
        value=deepcopy(self.value)
        chain=[]
        for ordinal in range(1,len(self.frozen["transport"]["batches"])+2):
            chain.append({"schema_version":planning.DRAFT,"input_identity":value["input_identity"],
                "stage":"batch" if ordinal<=len(self.frozen["transport"]["batches"]) else "synthesis","ordinal":ordinal,
                "parent_draft_identities":[codec.canonical_digest(d) for d in chain],"content":deepcopy(value["content"])})
        value["provenance"]={"kind":"model_draft","declaration":"Original full chain supplied","upstream_model_history":"declared_model",
            "draft_chain":chain,"final_draft_identity":codec.canonical_digest(chain[-1])}
        with patch.object(planning,"build_request",side_effect=AssertionError("No next request")), \
             patch.object(planning,"prepare_successor",side_effect=AssertionError("No successor")):
            self.passes(value)
        mutations=[lambda v:v["provenance"]["draft_chain"].reverse(),lambda v:v["provenance"]["draft_chain"].pop(0),
            lambda v:v["provenance"]["draft_chain"][-1]["content"].update(unresolved=[{}]),
            lambda v:v["provenance"]["draft_chain"][-1].update(parent_draft_identities=[]),
            lambda v:v["provenance"]["draft_chain"][-1].update(stage="batch")]
        for mutate in mutations:
            broken=deepcopy(value); mutate(broken); self.rejects(broken)
        # Original DRAFT content remains schema-open. Its exact JSON identity
        # must still distinguish a number from the candidate's boolean.
        broken=deepcopy(value)
        broken["provenance"]["draft_chain"][-1]["content"]["definitions"]["flows"][0]["graph"]["boundaries"][0]["required"]=1
        broken["provenance"]["final_draft_identity"]=codec.canonical_digest(broken["provenance"]["draft_chain"][-1])
        planning.validate_draft_chain(self.frozen,broken["provenance"]["draft_chain"])
        report=self.rejects(broken)
        self.assertIn("exact final original candidate content and identity",json.dumps(report))

    def test_current_binding_raw_tampering_and_read_only_reuse(self):
        first=self.run_check(run="reuse")
        self.assertEqual(first["status"],"passed",first)
        before=self.fixture.snapshot()
        again=candidate.validate(self.root,run_id="reuse",prepared_ref=self.prepared["resume_ref"],candidate="candidate.json")
        self.assertEqual(first,again)
        self.assertEqual(before,self.fixture.snapshot())
        value=deepcopy(self.value); value["input_identity"]="sha256:"+"0"*64; self.rejects(value)
        self.put("docs/source.md",b"Changed governed source\n")
        self.rejects(self.value)

    def rewrite_cached_event(self,report,*,change_report=None,change_artifact=None):
        directory=self.root/report["output_ref"]
        report_path=directory/"report.json"
        saved=json.loads(report_path.read_bytes())
        event=json.loads((directory/"event.json").read_bytes())
        if change_report is not None:
            change_report(saved)
            report_path.write_bytes(record_tests.encoded(saved))
        if change_artifact is not None:
            change_artifact(directory)
        event={**saved,"artifacts":{name:codec.raw_digest((directory/name).read_bytes()) for name in event["artifacts"]}}
        (directory/"event.json").write_bytes(record_tests.encoded(event))
        return directory,{path:path.read_bytes() for path in directory.rglob("*") if path.is_file()}

    def assert_tampered_reuse_rejected_without_repair(self,report,original):
        directory,before=original
        rejected=candidate.validate(self.root,run_id=report["run_id"],prepared_ref=self.prepared["resume_ref"],candidate="candidate.json")
        self.assertEqual(rejected["status"],"blocked",rejected)
        self.assertFalse(rejected["formal_adoption"] or rejected["runtime_verified"] or rejected["readiness"])
        self.assertIn("/failures/",rejected["resume_ref"])
        self.assertEqual(before,{path:path.read_bytes() for path in directory.rglob("*") if path.is_file()})

    def test_reuse_rejects_self_consistent_fabricated_flags_and_graph_facts(self):
        mutations=[lambda report:report.update(formal_adoption=True,runtime_verified=True),
            lambda report:report["facts"]["graph"].update(edge_count=99999),
            lambda report:report.update(formal_adoption=0)]
        for index,mutation in enumerate(mutations):
            report=self.run_check(run="tampered-report"+str(index))
            self.assertEqual(report["status"],"passed",report)
            original=self.rewrite_cached_event(report,change_report=mutation)
            self.assert_tampered_reuse_rejected_without_repair(report,original)

    def test_reuse_rejects_candidate_artifact_changes_with_updated_event_digests(self):
        def alter_json(directory):
            path=directory/"candidate.json"
            value=json.loads(path.read_bytes())
            value["content"]["definitions"]["flows"][0]["observable_result"]="Fabricated cached result"
            path.write_bytes(record_tests.encoded(value))
        mutations=[lambda directory:(directory/"candidate.raw.json").write_bytes(b'{"different":"original bytes"}\n'),alter_json]
        for index,mutation in enumerate(mutations):
            report=self.run_check(run="tampered-artifact"+str(index))
            self.assertEqual(report["status"],"passed",report)
            original=self.rewrite_cached_event(report,change_artifact=mutation)
            self.assert_tampered_reuse_rejected_without_repair(report,original)

    def test_schema_drift_creates_new_check_identity_and_keeps_prior_event(self):
        import tempfile
        first=self.run_check(run="schema-drift")
        self.assertEqual(first["status"],"passed",first)
        original={p:p.read_bytes() for p in (self.root/first["output_ref"]).rglob("*") if p.is_file()}
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            for name in schemas.FORMAL+schemas.AUXILIARY:
                shutil.copyfile(schemas.DIRECTORY/(name+".schema.json"),directory/(name+".schema.json"))
            path=directory/"planning-candidate.schema.json"
            path.write_bytes(path.read_bytes().replace(b"reviewable",b"Reviewable"))
            with patch.object(schemas,"DIRECTORY",directory):
                second=self.run_check(run="schema-drift")
        self.assertEqual(second["status"],"passed",second)
        self.assertNotEqual(first["check_identity"],second["check_identity"])
        self.assertEqual(original,{p:p.read_bytes() for p in (self.root/first["output_ref"]).rglob("*") if p.is_file()})

    def test_archived_byte_tampering_is_rejected(self):
        prefix=(self.root/self.prepared["resume_ref"]).parent
        row=json.loads((prefix/"raw-index.json").read_bytes())[0]
        (prefix/row["archive"]).write_bytes(b"changed")
        self.rejects(self.value)

    def test_narrow_scope_preserves_global_denominator_and_outside_disposition(self):
        self.proposals.append({**deepcopy(self.proposal),"proposal_id":"proposal:outside","source_block_ids":["B2"]})
        self.put("docs/relations.json",{"planning_relations":{"schema_version":planning.RELATIONS,
            "dependency_coverage":"complete","entities":[
                {"kind":"capability","id":"CAP-ONE","source_paths":["docs/source.md"],"source_block_ids":["B1"],"depends_on":[]},
                {"kind":"capability","id":"CAP-TWO","source_paths":["docs/empty.md"],"source_block_ids":["B2"],"depends_on":[]}]}})
        self.fixture.source_paths.append("docs/relations.json")
        self.ledger["blocks"].append({"block_id":"B3","source_path":"docs/relations.json"})
        self.manifest["sources"].append({"path":"docs/relations.json"})
        self.put("native-manifest.json",self.manifest); self.put("native-ledger.json",self.ledger)
        contract=deepcopy(self.fixture.contract)
        contract["scope"]={"scope_id":"scope","kind":"capability","ids":["CAP-ONE"]}
        self.prepared=self.fixture.prepare("narrow",contract=contract)
        self.frozen=self.fixture.frozen(self.prepared)
        self.assertEqual(self.frozen["inputs"]["closure"]["mode"],"governed_transitive_closure")
        value=self.envelope(); value["content"]["out_of_scope_requirement_ids"]=["proposal:outside"]
        facts=self.passes(value)["facts"]["scope"]
        self.assertEqual(facts["global_requirement_ids"],["proposal:keep-original","proposal:outside"])
        value["content"]["out_of_scope_requirement_ids"]=[]; self.rejects(value)

    def selected_plan(self, *, current=False):
        fixture=record_tests.MatrixFixture()
        plan=fixture.models[record_tests.plan_path()]
        plan["definitions"]["commands"]=[{"id":"SHARED-CMD","requirement_ids":[],"responsibility":"Shared logical rule","uses":[]}]
        path=record_tests.plan_path()
        fixture.artifacts[path]=record_tests.encoded(plan)
        # A different unselected revision declaring the same command is frozen
        # evidence, not a competing effective owner.
        historical=deepcopy(plan); historical["revision"]=1
        self.dependency_fixture=fixture
        self.dependency_models={path:plan,record_tests.plan_path(revision=1):historical}
        self.dependency_paths=[path]
        self.dependency_context_formats={}
        self.omitted_dependency_contexts=set()
        if current:
            self.fixture.source_paths.append("sources/input.md")
            self.manifest["sources"].append({"path":"sources/input.md"})
            self.ledger["blocks"].append({"block_id":"B3","source_path":"sources/input.md"})
            self.put("native-manifest.json",self.manifest)
            self.put("native-ledger.json",self.ledger)
        self.freeze_dependencies("selected",out_of_scope=[] if current else ["REQ-p"])
        if current:
            self.add_existing_requirement(plan)
        return deepcopy(self.value["content"]["selected_dependencies"][0])

    def freeze_dependencies(self,run,*,out_of_scope):
        fixture=self.dependency_fixture
        for name,value in self.dependency_models.items():
            fixture.artifacts[name]=record_tests.encoded(value)
        contract=deepcopy(self.fixture.contract)
        for name,raw in fixture.artifacts.items():
            self.put(name,raw)
            if name not in self.omitted_dependency_contexts:
                contract["contexts"].append({"kind":"capability","path":name,
                    "format":self.dependency_context_formats.get(name,"text"),"required":True,"absence":None})
        self.prepared=self.fixture.prepare(run,contract=contract)
        self.frozen=self.fixture.frozen(self.prepared)
        self.value=self.envelope()
        self.value["content"]["selected_dependencies"]=[self.dependency_ref(path) for path in self.dependency_paths]
        self.value["content"]["logical_references"]=[record_tests.logical("command","SHARED-CMD","p",2)]
        self.value["content"]["out_of_scope_requirement_ids"]=out_of_scope

    def dependency_ref(self,path):
        plan=self.dependency_models[path]
        return {"path":path,"schema_version":plan["schema_version"],"entity_id":plan["plan_id"],"revision":plan["revision"],
            "digest":codec.raw_digest(record_tests.encoded(plan)),"verification_mode":"raw","codec_version":None}

    def add_existing_requirement(self,plan):
        content=self.value["content"]
        original=plan["requirements"][0]
        content["requirements"].append({**deepcopy(original),"prior_requirement_ids":[]})
        for field in ("requirement_verification","coverage_table","applicability"):
            content[field].append(deepcopy(plan[field][0]))
        content["unresolved"].append({"requirement_id":original["requirement_id"],"reason":"Retain the explicit frozen source gap",
                                      "source_block_ids":deepcopy(original["source_block_ids"])})

    def test_unselected_history_text_json_equivalence_does_not_activate_requirements(self):
        self.selected_plan()
        text=self.passes()
        historical=record_tests.plan_path(revision=1)
        original=(self.root/historical).read_bytes()
        # A wholly unrelated Requirement body and unknown old block in the
        # unselected JSON must neither activate the domain nor compete for owner.
        self.dependency_models[historical]["requirements"][0].update(requirement_id="REQ-UNSELECTED",source_block_ids=["OLD-UNKNOWN"])
        for field in ("requirement_verification","coverage_table","applicability"):
            self.dependency_models[historical][field][0]["requirement_id"]="REQ-UNSELECTED"
        self.freeze_dependencies("unselected-text",out_of_scope=["REQ-p"])
        text=self.passes()
        original=(self.root/historical).read_bytes()
        self.dependency_context_formats[historical]="json"
        self.freeze_dependencies("unselected-json",out_of_scope=["REQ-p"])
        structured=self.passes()
        self.assertEqual((self.root/historical).read_bytes(),original)
        self.assertEqual(text["facts"]["scope"],structured["facts"]["scope"])
        self.assertNotIn("REQ-UNSELECTED",structured["facts"]["scope"]["global_requirement_ids"])

    def test_selected_existing_requirement_uses_own_ledger_and_preserves_identity(self):
        self.selected_plan(current=True)
        plan=self.dependency_models[record_tests.plan_path()]
        report=self.passes()
        self.assertEqual(report["facts"]["scope"]["applicable_requirement_ids"],["REQ-p","proposal:keep-original"])
        original=next(row for row in self.value["content"]["requirements"] if row["requirement_id"]=="REQ-p")
        self.assertEqual(original,{**plan["requirements"][0],"prior_requirement_ids":[]})
        self.assertEqual(original["source_block_ids"],["BLOCK-1"])
        self.assertNotIn("BLOCK-1",{row["block_id"] for row in self.ledger["blocks"]})
        changed=deepcopy(self.value)
        changed["content"]["definitions"]["flows"][0]["source_block_ids"]=["BLOCK-1"]
        self.rejects(changed)
        for field,replacement in (("requirement_id","REQ-RENAMED"),("source_block_ids",["B3"]),
                                  ("acceptance_intent","Rewritten intent"),("non_task_sinks",[])):
            changed=deepcopy(self.value)
            next(row for row in changed["content"]["requirements"] if row["requirement_id"]=="REQ-p")[field]=replacement
            self.rejects(changed)

    def test_selected_existing_requirement_outside_scope_is_not_deferred(self):
        self.selected_plan()
        report=self.passes()
        self.assertEqual(report["facts"]["scope"]["out_of_scope_requirement_ids"],["REQ-p"])
        self.assertEqual(report["facts"]["scope"]["global_requirement_ids"],["REQ-p","proposal:keep-original"])
        self.assertEqual(len(self.value["content"]["requirement_verification"]),1)
        self.value["content"]["out_of_scope_requirement_ids"]=[]
        self.rejects(self.value)

    def link_dependency_history(self):
        current=record_tests.plan_path()
        historical=record_tests.plan_path(revision=1)
        self.dependency_models[current]["lineage"]["previous_plan_ref"]=self.dependency_ref(historical)

    def test_explicit_selected_same_requirement_requires_same_body_and_source_meaning(self):
        self.selected_plan()
        second_path=record_tests.plan_path("q",2)
        second=deepcopy(self.dependency_models[record_tests.plan_path()])
        second["plan_id"]="q"
        second["definitions"]["commands"]=[]
        self.dependency_models[second_path]=second
        self.dependency_paths.append(second_path)
        self.freeze_dependencies("same-selected-requirement",out_of_scope=["REQ-p"])
        facts=self.passes()["facts"]["scope"]
        self.assertEqual(facts["global_requirement_ids"],["REQ-p","proposal:keep-original"])
        second["requirements"][0]["acceptance_intent"]="A conflicting selected body"
        self.freeze_dependencies("conflicting-body",out_of_scope=["REQ-p"])
        report=self.rejects(self.value)
        self.assertIn("identical frozen Requirement body and source meaning",json.dumps(report))
        second["requirements"][0]["acceptance_intent"]=self.dependency_models[record_tests.plan_path()]["requirements"][0]["acceptance_intent"]
        ledger=json.loads(self.dependency_fixture.artifacts["sources/ledger.json"])
        ledger["blocks"][0]["text"]="Conflicting meaning for the same block ID and path"
        self.dependency_fixture.artifacts["sources/alternate-ledger.json"]=record_tests.encoded(ledger)
        second["source_identity"]["ledger_ref"]=self.dependency_fixture.owned("source_ledger","sources/alternate-ledger.json")
        self.freeze_dependencies("conflicting-source",out_of_scope=["REQ-p"])
        report=self.rejects(self.value)
        self.assertIn("identical frozen Requirement body and source meaning",json.dumps(report))

    def test_historical_lineage_different_old_requirement_body_is_not_current(self):
        self.selected_plan()
        historical=record_tests.plan_path(revision=1)
        old=self.dependency_models[historical]
        old["requirements"][0]["acceptance_intent"]="Earlier legitimate intent preserved as history"
        self.link_dependency_history()
        self.freeze_dependencies("different-history-body",out_of_scope=["REQ-p"])
        report=self.passes()
        self.assertEqual(report["facts"]["scope"]["global_requirement_ids"],["REQ-p","proposal:keep-original"])
        # Pure provenance still requires its original bytes and exact references.
        self.dependency_models[record_tests.plan_path()]["lineage"]["previous_plan_ref"]["digest"]="sha256:"+"0"*64
        self.freeze_dependencies("tampered-history-ref",out_of_scope=["REQ-p"])
        report=self.rejects(self.value)
        self.assertIn("exact frozen dependency digest",json.dumps(report))
        self.link_dependency_history()
        self.omitted_dependency_contexts.add(historical)
        self.freeze_dependencies("missing-history-bytes",out_of_scope=["REQ-p"])
        self.assertTrue((self.root/historical).exists())
        report=self.rejects(self.value)
        self.assertIn("unresolved_reference",json.dumps(report))

    def test_selected_ledger_missing_bytes_missing_block_or_wrong_identity_rejected(self):
        self.selected_plan()
        self.omitted_dependency_contexts.add("sources/ledger.json")
        self.freeze_dependencies("missing-ledger",out_of_scope=["REQ-p"])
        self.assertTrue((self.root/"sources/ledger.json").exists(),"Physical bytes must not become a fallback")
        report=self.rejects(self.value)
        self.assertIn("unresolved_reference",json.dumps(report))
        self.omitted_dependency_contexts.clear()
        fixture=self.dependency_fixture
        ledger=json.loads(fixture.artifacts["sources/ledger.json"])
        ledger["blocks"]=[]
        fixture.artifacts["sources/ledger.json"]=record_tests.encoded(ledger)
        self.dependency_models[record_tests.plan_path()]["source_identity"]["ledger_ref"]=fixture.owned("source_ledger","sources/ledger.json")
        self.freeze_dependencies("missing-old-block",out_of_scope=["REQ-p"])
        report=self.rejects(self.value)
        self.assertIn("known original source blocks in owning ledger",json.dumps(report))
        ledger["blocks"]=[{"block_id":"BLOCK-1","source_path":"sources/input.md"}]
        ledger["source_revision"]="Wrong old revision"
        fixture.artifacts["sources/ledger.json"]=record_tests.encoded(ledger)
        self.dependency_models[record_tests.plan_path()]["source_identity"]["ledger_ref"]=fixture.owned("source_ledger","sources/ledger.json")
        self.freeze_dependencies("wrong-old-source-identity",out_of_scope=["REQ-p"])
        report=self.rejects(self.value)
        self.assertIn("matching native source revision and manifest digest",json.dumps(report))

    def test_dependency_evidence_requires_binding_and_exact_frozen_bytes(self):
        self.selected_plan()
        fixture=self.dependency_fixture
        plan=self.dependency_models[record_tests.plan_path()]
        reference="evidence/implementation.txt"
        fixture.artifacts[reference]=b"Original declared implementation reference.\n"
        plan["requirement_evidence"]=[{"requirement_id":"REQ-p","evidence_id":"EXISTING-EVIDENCE",
            "kind":"implementation_reference","source_ref":reference,"covered_behavior":"Retained declaration",
            "flow_ids":[],"test_ids":[]}]
        plan["requirement_verification"][0]["evidence_ids"]=["EXISTING-EVIDENCE"]
        self.freeze_dependencies("missing-evidence-binding",out_of_scope=["REQ-p"])
        report=self.rejects(self.value)
        self.assertIn("exactly one owner/locator binding",json.dumps(report))
        plan["evidence_source_refs"]=[fixture.owned("implementation_reference",reference)]
        self.freeze_dependencies("valid-evidence-binding",out_of_scope=["REQ-p"])
        self.passes()
        self.omitted_dependency_contexts.add(reference)
        self.freeze_dependencies("missing-frozen-evidence",out_of_scope=["REQ-p"])
        self.assertTrue((self.root/reference).exists())
        report=self.rejects(self.value)
        self.assertIn("unresolved_reference",json.dumps(report))

    def test_owning_manifest_must_bind_each_requirement_source_path_exactly_once(self):
        self.selected_plan()
        fixture=self.dependency_fixture
        plan=self.dependency_models[record_tests.plan_path()]
        original=json.loads(fixture.artifacts["sources/manifest.json"])
        for label,bindings in (("absent",[]),("duplicate",original["sources"]*2)):
            manifest={**deepcopy(original),"sources":bindings}
            fixture.artifacts["sources/manifest.json"]=record_tests.encoded(manifest)
            plan["source_identity"]["manifest_ref"]=fixture.owned("source_manifest","sources/manifest.json")
            self.freeze_dependencies("manifest-binding-"+label,out_of_scope=["REQ-p"])
            report=self.rejects(self.value)
            self.assertIn("exactly one owning manifest source binding",json.dumps(report))

    def test_selected_exact_snapshot_owner_and_unselected_history(self):
        reference=self.selected_plan()
        self.passes()
        value=deepcopy(self.value); value["content"]["logical_references"][0]["owner_revision"]=1
        self.rejects(value)
        value=deepcopy(self.value); value["content"]["selected_dependencies"][0]["digest"]="sha256:"+"0"*64
        self.rejects(value)
        value=deepcopy(self.value)
        value["content"]["definitions"]["commands"]=[{"id":"SHARED-CMD","proposed_owner_key":"proposal-owner",
            "requirement_ids":[],"responsibility":"Competing rule","uses":[]}]
        self.rejects(value)
        value=deepcopy(self.value); value["content"]["selected_dependencies"]=[]
        self.rejects(value)

    def test_existing_ref_and_missing_frozen_endpoint_do_not_fall_back_to_disk(self):
        self.value["content"]["implementation_objects"][0].update(availability="existing")
        self.rejects(self.value)
        self.value["content"]["implementation_objects"][0]["target_ref"]=self.owned("implementation_reference","docs/constraint.md")
        self.passes()
        self.put("unfrozen.cs",b"public class NotInPrepared {}")
        self.value["content"]["implementation_objects"][0]["target_ref"]=self.owned("implementation_reference","unfrozen.cs")
        self.rejects(self.value)

    def test_cross_flow_handoff_and_typed_state_owner(self):
        value=deepcopy(self.value); content=value["content"]
        content["definitions"]["states"]=[{"id":"STATE","proposed_owner_key":"state-owner","requirement_ids":[],
            "responsibility":"Single declared state owner","uses":[]}]
        state={"kind":"state","definition_id":"STATE","proposed_owner_key":"state-owner"}
        first=content["definitions"]["flows"][0]
        first["state_owners"]=[state]
        first["graph"]["nodes"][1]["state_uses"]=[state]
        first["handoffs"]=[{"id":"handoff","from":point("entry"),"to":point("act"),"owner":use(),
            "state_uses":[state],"responsibility":"Move state once","result":"Next owner observes state"}]
        self.passes(value)
        first["handoffs"][0]["to"]=point("optional"); self.rejects(value)

    def test_reachable_node_and_handoff_state_uses_require_declared_flow_owners(self):
        value=deepcopy(self.value)
        content=value["content"]
        state={"kind":"state","definition_id":"STATE","proposed_owner_key":"shared-state-owner"}
        extra={"kind":"state","definition_id":"EXTRA","proposed_owner_key":"extra-state-owner"}
        content["definitions"]["states"]=[{"id":item["definition_id"],"proposed_owner_key":item["proposed_owner_key"],
            "requirement_ids":[],"responsibility":"Declared shared state responsibility","uses":[]} for item in (state,extra)]
        flow=content["definitions"]["flows"][0]
        flow["graph"]["nodes"][1]["state_uses"]=[state]
        report=self.rejects(value)
        self.assertIn("direct State use represented in Flow state_owners",json.dumps(report))
        flow["state_owners"]=[state,extra]
        self.passes(value)
        flow["graph"]["nodes"][1]["state_uses"]=[]
        flow["state_owners"]=[]
        flow["handoffs"]=[{"id":"state-handoff","from":point("entry"),"to":point("act"),"owner":use(),
            "state_uses":[state],"responsibility":"Transfer shared state","result":"State observed"}]
        report=self.rejects(value)
        self.assertIn("direct State use represented in Flow state_owners",json.dumps(report))
        flow["state_owners"]=[state,extra]
        self.passes(value)
        second=self.flow("SECOND")
        second["state_owners"]=[state]
        second["graph"]["nodes"][1]["state_uses"]=[state]
        content["definitions"]["flows"].append(second)
        content["requirement_route_memberships"].append({"requirement_id":self.proposal["proposal_id"],
            "flow_id":"SECOND","observable_role":"Shared State observed by a second Flow"})
        self.passes(value)

    def test_handoff_affiliation_rejects_unrelated_flow_and_allows_cross_flow(self):
        value=deepcopy(self.value)
        content=value["content"]
        first=content["definitions"]["flows"][0]
        second=self.flow("SECOND")
        content["definitions"]["flows"].append(second)
        content["requirement_route_memberships"].append({"requirement_id":self.proposal["proposal_id"],
            "flow_id":"SECOND","observable_role":"Shared observable behavior"})
        second["handoffs"]=[{"id":"affiliation","from":point("entry"),"to":point("act"),"owner":use(),
            "state_uses":[],"responsibility":"Declared transfer","result":"Transfer observed"}]
        report=self.rejects(value)
        self.assertIn("handoff belongs to at least one endpoint Flow",json.dumps(report))
        first["graph"]["edges"].append({**deepcopy(first["graph"]["edges"][0]),"id":"cross-edge",
            "from":point("act"),"to":point("entry","SECOND")})
        second["handoffs"][0].update({"from":point("act"),"to":point("entry","SECOND")})
        self.passes(value)

    @unittest.skipUnless(os.name=="nt","Windows lexical root and candidate boundary")
    def test_windows_real_junction_root_and_candidate_aliases_fail_closed(self):
        self.put("candidate.json",self.value)
        actual=self.root/"real"; actual.mkdir()
        junction=self.root/"junction"
        process=subprocess.run(["cmd","/c","mklink","/J",str(junction),str(actual)],capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)
        self.addCleanup(lambda:os.rmdir(junction) if junction.exists() else None)
        (actual/"candidate.json").write_bytes(json.dumps(self.value).encode())
        for module,stage in ((plan_capabilities,"validate-candidate"),(plan_mvg,"validate")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code=module.main(["--repo-root",str(junction),stage,"--run-id","alias","--input-stage","3b",
                    "--prepared-ref",self.prepared["resume_ref"],"--candidate","candidate.json"])
            self.assertEqual(code,2,output.getvalue())
        for alias in ("junction/candidate.json","real/../candidate.json","CANDIDATE.json"):
            report=candidate.validate(self.root,run_id="candidate-alias",prepared_ref=self.prepared["resume_ref"],candidate=alias)
            self.assertEqual(report["status"],"blocked",report)

    def test_write_failures_keep_honest_partial_location_and_never_repair_event(self):
        writer=sources.write
        for target in ("candidate.json","raw-index.json","report.json","event.json"):
            def fail(path,value):
                if "b-route-candidate-check" in path.parts and "failures" not in path.parts and path.name==target:
                    raise OSError(32,"Windows sharing failure",str(path))
                return writer(path,value)
            with patch.object(sources,"write",side_effect=fail):
                report=self.run_check()
            self.assertEqual(report["status"],"blocked",report)
            self.assertEqual(report["termination_reason"],"partial_write")
            self.assertIn("b-route-candidate-check",report["partial_ref"])
            self.assertTrue((self.root/report["resume_ref"]).is_file())
            self.assertTrue(report["partial_exists"])
            if target=="event.json":
                original=self.root/report["partial_ref"]
                before={p:p.read_bytes() for p in original.rglob("*") if p.is_file()}
                retry=candidate.validate(self.root,run_id=report["run_id"],prepared_ref=self.prepared["resume_ref"],candidate="candidate.json")
                self.assertEqual(retry["status"],"blocked")
                self.assertFalse((original/"event.json").exists())
                self.assertEqual(before,{p:p.read_bytes() for p in original.rglob("*") if p.is_file()})

    def test_directory_and_failure_report_persistence_are_honest(self):
        directory=planning.new_directory
        def fail_directory(root,relative):
            if "b-route-candidate-check" in relative and "/failures/" not in relative:
                raise OSError(5,"Windows access denied",str(root/relative))
            return directory(root,relative)
        with patch.object(planning,"new_directory",side_effect=fail_directory):
            report=self.run_check()
        # No successful candidate site was created; a new diagnostic event is
        # permitted. It must not claim the attempted success site is complete.
        self.assertEqual(report["status"],"blocked")
        self.assertIn("/failures/",report["resume_ref"])
        with patch.object(sources,"write",side_effect=OSError(5,"No diagnostic persistence")):
            report=self.run_check()
        self.assertEqual(report["status"],"blocked")
        self.assertEqual(report["termination_reason"],"partial_write")
        self.assertIsNone(report["resume_ref"])

    def test_both_direct_cli_read_before_legacy_run_or_manifest(self):
        self.put("candidate.json",self.value)
        for module,stage in ((plan_capabilities,"validate-candidate"),(plan_mvg,"validate")):
            with patch.object(module,"_load_run",side_effect=AssertionError("No legacy run")), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code=module.main(["--repo-root",str(self.root),stage,"--run-id",module.__name__,"--input-stage","3b",
                    "--prepared-ref",self.prepared["resume_ref"],"--candidate","candidate.json"])
            self.assertEqual(code,0,output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["claim"],"candidate_structure_only")

    def test_cli_builder_routes_and_legacy_mixing_rejected(self):
        parser=dev_cli.build_parser()
        self.put("candidate.json",self.value)
        for command,stage,builder,module in (("plan-capabilities","validate-candidate",builders.build_plan_capabilities_cmd,plan_capabilities),
                                            ("plan-mvg","validate",builders.build_plan_mvg_cmd,plan_mvg)):
            args=parser.parse_args([command,"--stage",stage,"--run-id","cli","--input-stage","3b",
                "--repo-root",str(self.root),"--prepared-ref",self.prepared["resume_ref"],"--candidate","candidate.json"])
            cmd=builder(args)
            self.assertEqual(cmd.count("--input-stage"),1)
            self.assertEqual(cmd[cmd.index("--input-stage")+1],"3b")
            self.assertEqual(cmd[cmd.index("--prepared-ref")+1],self.prepared["resume_ref"])
            self.assertEqual(cmd[cmd.index("--candidate")+1],"candidate.json")
            self.assertEqual(Path(cmd[1]).name,module.__name__+".py")
            with patch.object(module,"_load_run",side_effect=AssertionError("No legacy run")), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code=module.main(cmd[2:])
            self.assertEqual(code,0,output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["claim"],"candidate_structure_only")
            args.planning_contract="contract.json"
            with self.assertRaises(ValueError): builder(args)
            args.planning_contract=""; args.task_id=["15"]
            with self.assertRaises(ValueError): builder(args)


class SchemaAndAlgorithmTests(unittest.TestCase):
    def test_actual_byte_cache_invalidates_even_same_length_and_mtime(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            for name in schemas.FORMAL+schemas.AUXILIARY:
                shutil.copyfile(schemas.DIRECTORY/(name+".schema.json"),directory/(name+".schema.json"))
            one=schemas.validator(candidate.SCHEMA,directory,auxiliary=True)
            path=directory/"planning-candidate.schema.json"
            before=path.stat(); raw=path.read_bytes()
            self.assertIn(b'"3b"',raw)
            path.write_bytes(raw.replace(b'"3b"',b'"4b"'))
            os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
            two=schemas.validator(candidate.SCHEMA,directory,auxiliary=True)
            self.assertIsNot(one,two)
            self.assertNotEqual(one.schema,two.schema)

    def test_formal_only_registry_needs_no_auxiliary_and_unknown_ref_stays_offline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            for name in schemas.FORMAL:
                shutil.copyfile(schemas.DIRECTORY/(name+".schema.json"),directory/(name+".schema.json"))
            self.assertIsNotNone(schemas.validator("newrouge.b-route-plan.v1",directory))
            with self.assertRaises(codec.CodecError): schemas.validator(candidate.SCHEMA,directory)
            path=directory/"plan.schema.json"
            value=json.loads(path.read_bytes()); value["$ref"]="https://invalid.example/unknown"
            path.write_text(json.dumps(value),encoding="utf8")
            with self.assertRaises(codec.CodecError): schemas.validate({},"newrouge.b-route-plan.v1",directory)

    def test_scc_handles_long_ring_and_collision_free_tuple_keys(self):
        count=4000
        graph={(str(i),"node"): {(str((i+1)%count),"node")} for i in range(count)}
        groups=candidate.components(graph)
        self.assertEqual(len(groups),1)
        self.assertEqual(len(groups[0]),count)
        graph={("a:b","c"):set(),("a","b:c"):set()}
        self.assertEqual(len(candidate.components(graph)),2)

    def test_long_dag_scc_is_correct_and_reverse_work_scales_linearly(self):
        count=4000
        graph={(str(index),"node"):{(str(index+1),"node")} if index+1<count else set() for index in range(count)}
        groups=candidate.components(graph)
        self.assertEqual({frozenset(group) for group in groups},{frozenset([node]) for node in graph})

        def work(size):
            graph={(str(index),"node"):{(str(index+1),"node")} if index+1<size else set() for index in range(size)}
            events=0
            def trace(frame,event,arg):
                nonlocal events
                if event=="line" and frame.f_code.co_filename==candidate.__file__ and frame.f_code.co_name in {"components","reachable"}:
                    events+=1
                return trace
            previous=sys.gettrace()
            try:
                sys.settrace(trace)
                result=candidate.components(graph)
            finally:
                sys.settrace(previous)
            self.assertEqual(len(result),size)
            return events
        small,large=work(128),work(512)
        self.assertGreater(small,0)
        self.assertLessEqual(large,small*6,"Four times the DAG size must retain bounded linear traversal work")


if __name__=="__main__":
    unittest.main()
