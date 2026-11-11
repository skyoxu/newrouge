"""Coordinator validation must not promote runtime configuration to provider identity."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
import _b_route_source_audit as audit
import _codex_app_server as transport
from fixtures.codex_app_server_protocol import protocol, encoded


class RuntimeReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)/"workspace"
        self.workspace.mkdir()
        self.schema = {"type":"object"}
        (self.workspace/"schema.json").write_text(json.dumps(self.schema),encoding="utf-8")
        (self.workspace.parent/"request.txt").write_text("complete input",encoding="utf-8")
        self.output,proof=transport.replay(encoded(protocol(self.workspace,schema=self.schema)))
        self.receipt={"schema_version":"newrouge.isolated-model-runner-receipt.v1",
            "model":"fixture-model","model_provider":"fixture","model_identity":"fixture/fixture-model",
            "model_identity_source":transport.SOURCE,"evidence_policy":transport.POLICY,
            "model_identity_verified":False,"runtime_identity_verified":True,"model_identity_scope":"runtime_configuration",
            "provider_identity_verified":False,"provider_reported_model":None,"provider_dispatch_count":"unknown",
            "model_tools":[],"request_count_observable":True,"model_request_count":1,"runner_invocations":1,
            "workspace":self.workspace.as_posix(),"output_chars":len(self.output),"model_identity_evidence":[proof]}

    def validate(self,receipt=None,output=None):
        receipt=receipt or self.receipt
        stdout=json.dumps(receipt)+"\n"
        execution={"status":"completed","returncode":0,"runner_dispatch_count":1,"stdout":stdout,
            "stdout_base64":base64.b64encode(stdout.encode()).decode(),"active_elapsed_seconds":0.5}
        audit.validate_execution(self.workspace,execution,receipt,"fixture/fixture-model",(output or self.output).encode())

    def test_runtime_configuration_is_accepted_with_explicit_unknown_provider(self):
        self.validate()

    def test_provider_identity_cannot_be_invented_or_scope_hidden(self):
        for key,value in [("provider_identity_verified",True),("provider_reported_model","fixture-model"),
                          ("model_identity_verified",True),("model_identity_scope","provider"),
                          ("runtime_identity_verified",False),("evidence_policy","other")]:
            with self.subTest(key=key):
                receipt=copy.deepcopy(self.receipt);receipt[key]=value
                with self.assertRaises(ValueError):self.validate(receipt)

    def test_complete_input_schema_output_and_protocol_cannot_be_substituted(self):
        with self.assertRaises(ValueError):self.validate(output='{"altered":true}')
        for path,text in [(self.workspace.parent/"request.txt","truncated"),(self.workspace/"schema.json",'{"type":"array"}')]:
            before=path.read_bytes();path.write_text(text,encoding="utf-8")
            with self.assertRaises(ValueError):self.validate()
            path.write_bytes(before)
        receipt=copy.deepcopy(self.receipt)
        receipt["model_identity_evidence"][0]["protocol_sha256"]="sha256:tampered"
        with self.assertRaises(ValueError):self.validate(receipt)

    def test_catalog_changes_only_tool_capabilities(self):
        source={"models":[{"slug":"fixture-model","model_messages":{"base_instructions":"unchanged"},
            "context_window":96000,"tool_mode":"code_mode_only","experimental_supported_tools":["clock"]}]}
        actual=json.loads(transport.restricted_catalog(json.dumps(source).encode()))
        expected=copy.deepcopy(source);expected["models"][0].update(transport.TOOL_CATALOG_OVERRIDES)
        self.assertEqual(expected,actual)

    def test_raw_span_locator_preserves_utf8_crlf_bare_cr_and_native_json(self):
        raw = '# Header\r\n\r\n完整正文.\r'.encode('utf-8')
        start,end=audit.block_byte_span(raw,{'line_start':3,'line_end':3})
        self.assertEqual('完整正文.\r'.encode('utf-8'),raw[start:end])
        self.assertEqual(len('# Header\r\n\r\n'.encode()),start)
        self.assertEqual(len(raw),end)
        raw='["完整"]\r\n'.encode('utf-8')
        start,end=audit.block_byte_span(raw,{'source_char_start':1,'source_char_end_exclusive':5})
        self.assertEqual('"完整"'.encode('utf-8'),raw[start:end])

    def test_schema_and_prompt_preserve_existing_blocking_semantic_rule(self):
        severity=audit.output_schema('compare')['properties']['findings']['items']['properties']['severity']
        self.assertEqual(['blocking'],severity['enum'])
        self.assertIn('MUST use severity=blocking',audit.PROMPTS['compare'])
