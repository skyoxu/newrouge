# Segmented model-input wire format

This is a transport boundary for the explicit shared segmented workflow. It does not activate an old native run, change semantic closure, qualify a model result, grant adoption/readiness, release an unknown charge, or select a candidate. The original frozen source material, candidate objects, previous generation/synthesis bodies, global constraints, metadata and output schema remain complete.

## Fixed representation

Every new model workspace still contains exactly `prompt.txt`, `input.json` and `output-schema.json` before dispatch. `input.json` is one canonical compact JSON object plus a single LF, with exactly these fields in this order:

```json
{
  "schema_version": "newrouge.b-route-segmented-wire-input.v1",
  "codec": "newrouge.b-route-compact-literal.v2",
  "original_json_raw_digest": "sha256:<64 lowercase hexadecimal digits>",
  "literal": "<the entire canonical v2 data literal>"
}
```

The example is displayed with whitespace for readability; the actual JSON file has no optional whitespace and ends with one LF. `literal` is exactly the unchanged `_b_route_compact_literal.dumps(logical_envelope, schema=compact.CURRENT_SCHEMA)` result. The fixed CURRENT_SCHEMA is v2. This transport accepts neither v1, v3 nor a raw-envelope fallback, and does not modify the codec source.

`original_json_raw_digest` hashes the exact UTF-8 bytes of the ordered compact JSON logical envelope, without a trailing LF. It preserves object field order, array order, every original string and JSON type. It is distinct from the logical canonical `envelope_digest`, the actual wire input file hash and the complete official model-request wrapper hash. Each has its original purpose and none substitutes for the others.

V2 uses complete visible string/subtree sharing and a closed data grammar. It does not use the v3 phrase-discovery algorithm, offsets into unseen text, opaque compression, projections or summaries. The logical segmented envelope and logical response schemas remain unchanged. The physical response uses the separately versioned citation-set representation below.

## Owner APIs

`_b_route_segmented_requests.encode_input_envelope(envelope)` returns the fixed four-field wire object after the existing full logical envelope checks. `decode_input_envelope(value)` requires that closed representation and fixed v2 literal version, invokes the original safe canonical codec loader, checks the complete ordered logical JSON hash, then applies the existing logical envelope checks. AST parsing and the original closed parser inspect data only; no Python literal is evaluated as code.

`read_input_envelope(root, workspace)` opens only the fixed `workspace/input.json`. Lexical project-local and sensitive-path checks precede filesystem I/O; the reader rejects reparse/alias files, duplicate JSON keys, nonfinite values, unknown fields, noncanonical JSON/LF, other codec versions, changed original hashes and logical omissions. It closes the actual input bytes, file identity, directory identities and membership. It never reads a caller-selected sidecar or treats observed output members as authorized artifacts.

`wire_instruction(instruction)` produces the one fixed transport explanation, the complete original v2 decoder instructions, and the unchanged phase instructions. `render_request` alone applies it. Core callers pass their original phase instructions and compare actual prompt bytes against this same helper, avoiding duplicate prefixes. Every request is independent and contains its own complete decoder and required material; references do not imply model memory from other requests.

## Measurement, claims and recovery

The official `workspace_payload` sees the real three files, including the complete decoder text and the JSON-escaped literal. The measured request remains the exact native compact JSON wrapper containing that full prompt and the actual complete physical output schema. Input must be at most 70,000 estimated tokens, and input plus the independently reserved output must be at most 96,000. Existing byte, counter, exact identity and no-truncation rules remain unchanged. A smaller logical object or a prototype token count is not a substitute for measuring the actual final wrapper.

The permanent input-only archive stores these real wire bytes and real prompt/schema bytes unchanged. Cold reconstruction uses the unchanged official serializer on that exact three-file archive, compares all three original model-workspace inputs, and binds the actual reservation's raw references, final request hash, schema, measurement and output reserve. The observation's `envelope` is the fully decoded logical envelope, while `input_files` and the claim continue to identify the actual wire bytes. Existing model output, protocol and stderr sidecars are never moved, masked, archived as inputs or fed back to the model.

Real paid claims, official source-only runner transport, high/no-tools/fresh protocol replay, candidate ancestry, same-basis comparison, complete related source closure, cross-segment interaction review and final business predicates remain with their existing owners. The wire reader grants none of those authorities.

## Versioned physical response citation sets

The model must actually return the new physical schema
`newrouge.b-route-segmented-response-citation-wire.v1`. Its exact outer fields
are `schema_version`, `citation_sets` and `result`. `result` retains the complete
logical `newrouge.b-route-segmented-response.v1` identity and every logical
response field. Only the enumerated proof rows use `citation_set_index` instead
of `citations`; the complete nonempty citation arrays appear once in
`citation_sets` in canonical first-use order.

Traversal is coverage, decisions, unresolved, findings, checks, comparisons
(each comparison immediately followed by its cross_impacts), candidate_pieces,
product_checks, joint_checks. All arrays retain their original order. Repeated
sets reuse their index. Duplicate or unused table entries, an out-of-order first
reference, missing references, boolean/float/negative/out-of-range indices,
unknown fields and wrong versions are rejected. Each citation remains the full
original segment ID, start/end and raw digest. Table order follows actual first
use; it is not an independently reorderable source catalog.

Host expansion has the separately named policy
`newrouge.b-route-segmented-response-expansion-limits.v1`: at most 16MiB of
expanded compact-JSON UTF-8 and 100,000 expanded JSON nodes, counting object
keys as string nodes. These are finite host CPU/memory accounting limits, not
model token windows, output reserves or a smaller business denominator. They
apply before any model-result or citation-entry deepcopy. Exact table-entry
costs multiplied by their actual row-reference counts are checked with
saturating arithmetic; a complete iterative walk then includes every result
row, key, original business string and all substituted citations. Strings are
costed with JSON escaping and strict UTF-8 without allocating their encoded
copies. Repeated objects count at every occurrence. Oversize data is explicitly
blocked, never truncated, summarized or partially accepted.

The public decoder has no caller override for these limits. Private arithmetic
tests lower the policy on a small fixture and install a model-subtree deepcopy
sentinel, proving rejection precedes expansion without constructing a large
tree. The normal small response's bytes are unchanged. The original 70k input,
26k maximum output reserve and 96k combined model policies remain separate and
unchanged; the real physical response must still satisfy them.

No recursive field-name replacement occurs. In particular, `value_json`, old
generation bodies, other business data and any embedded property named
`citations` or `citation_set_index` are preserved literally. Every slot check,
joint member digest/edge/source obligation, candidate-by-dimension comparison,
cross-impact, finding and unresolved item remains present. The representation
does not turn a finding into approval or discharge any missing denominator.

The private `_b_route_segmented_response_wire.py` owns the closed physical
schema, strict expansion and pure producer/fixture encoder. Core exposes
`encode_response_wire(logical_response)` and
`decode_response_wire(physical_response, envelope)`. The first is not a paid
output rewriting API and grants no qualification. `output_schema(envelope)` is
the actual new physical schema supplied to the official runner. After genuine
receipt replay, live execution, cold replay and issued-result validation decode
the actual output and run all original logical schema/source/business/fairness
checks. Current code never falls back to a raw logical response. Historical
results remain verifiable only with their original frozen producer and policy;
they are not relabeled as this wire version.

The original physical output bytes, hash, schema, paid request identity, receipt
and execution binding remain unchanged and authoritative. The model's new
physical output itself must fit the existing output reserve and 1MiB byte cap;
host expansion cannot retroactively make an oversized old response acceptable.
All input/combined limits, high/no-tools/fresh execution and original campaign,
profile, lineage and time accounting remain unchanged. The response helper is
explicitly pinned in current source policy. No prior failed output or retained
scene is rewritten, refunded or granted admission by this change.

The dedicated `test_b_route_segmented_response_wire.py` contains eight pure
representation/schema test methods. Author checks are AST-only; Root owns
execution of these and the real shared workflow regressions after the common
source barrier. These tests do not supply native or semantic acceptance.

## Evidence limits

Root's saved capacity prototype in `logs/ci/2026-11-07/r23-capacity-scene-07/wire-prototypes-01/result.json` is diagnostic evidence for the earlier exact scene, not admission of this implementation. This author performed only static reading and stdlib AST/hash checks. The focused renderer tests use explicit fake payload/counter boundaries; Root must execute the final source epoch's targeted tests and measure the actual complete official wrapper before claiming a capacity PASS or any model qualification. Existing failed fixtures and earlier source/test epochs remain evidence.


## 2026-11-07 Root实际检查点

此前AST/未执行记述是历史时点。上一源码纪元的实际执行结果与失败边界见 `../../logs/ci/2026-11-07/segmented-wire-v1-checkpoint/report.md`；86/87受影响方法已有通过记录，1项输出容量错误仍保留，不能称完整通过或真实模型/原生资格。


## 新response wire实际离线结果

Root在完整723项源码/文档屏障下实际执行31项定向测试，全部通过、无跳过，前后hash一致：新wire/展开守卫8、原paid单节点协议/冷回放1、完整workflow13和candidate9。原64551B/29262输出失败保留在前一c55e3b07检查点，未事后改判。独立只读复核未发现可确认新增P1/P2，仅在其明确静态范围内。

证据见 `../../logs/ci/2026-11-07/segmented-response-wire-freeze/report.md`。未重跑不受影响的先前测试，不声称整套121同时全绿。项目原生模型/资格/OS子进程调用均0，本轮只有合成离线协议；真实模型质量、正式资格、默认B启用仍未取得。此段与换行规范化是测试后状态更新，测试当时文档原字节已归档，所有生产/测试代码字节未再改。


## R58 isolated integration status (planned)

Original R23 evidence above retains its original epoch. The R58 combination
with current R57 shared owners is not yet validated or formally enabled.
See `execution-plans/2026-11-10-r23-segmented-to-r58-opt-in-migration.md`.
No model/native/funding authority, default activation or old-proof requalification
is granted by this transplant. Existing ADR-0042 thresholds remain unchanged.
