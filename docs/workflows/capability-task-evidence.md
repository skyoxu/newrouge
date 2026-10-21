# Lossless task-view evidence trial

The default Capability transport remains `raw`. The optional `lossless-v1`
trial changes task-view representation only. It does not summarize evidence,
change topology rules, write inferred links to authority, or enable formal
generation without the existing Chapter 5 and isolation gates.

## Codec and admission

`_capability_task_evidence.py` groups views by the existing master task identity.
It shares a field only when it exists in every view of that task and the full
JSON values are strictly equal. View-specific fields remain independent. Unknown
fields, missing versus null, empty containers, string versus number, boolean
versus number, and array order survive expansion. Source Block objects and raw
text are kept complete in `content_objects.context`.

Each task-only request contains one representation: the original complete rows
or a packet with `relation_index`, `content_objects`, and external source
pointers. An encoded request also carries a fixed format guide. It has no
references to previous requests. Output schemas still use the original IDs.

The relation index recognizes only explicit task `taskmaster_id`,
`requirement_ids`, `semantic_refs`, `requirement_refs`, `requirement_ref`,
`source_block_ids`, `adr_refs`, and `test_refs`; Requirement objects additionally
support explicit `dependency_ids`. Requirement dependencies use an exact-ID
closure, including cycles, without deriving or rewriting topology. Other fields
stay intact in the semantic objects and do not acquire new machine-inferred
relations. Missing optional fields are undeclared. A declared missing target
blocks dispatch, including an unresolved template in `test_refs`.

ADR IDs resolve against exact `ADR-NNNN` filename identities under `docs/adr`;
test paths resolve exactly. Preparation freezes the target paths, names, hashes,
and existence status in a machine-only catalog. These targets join the authority
fingerprint. The isolated runner does not search outside its prepared workspace.
External pointers are citation targets, not a claim that ADR/test bodies have
been included. Each indexed Requirement and Source Block has its full body.

Before dispatch, the shared admission helper verifies:

1. Prepared-file identity and explicit relation targets.
2. Recursive historical-Capability field/schema exclusion. Authored GDD text
   containing Capability boundaries or IDs is preserved.
3. Exact packet derivation, rejecting extra side-channel objects and nested
   payloads, followed by `expand(compress(input)) == input` using strict JSON
   equality rather than Python's `True == 1` equality.
4. Field-address expansion coverage, JSON Pointers, source files, and hashes.
5. Complete request size, including context, format guide, indexes, and output
   schema. Encoded bytes **and** the conservative token estimate must both be
   smaller; otherwise the same complete input is sent in raw form. Integrity
   failures never trigger this size fallback.

Existing historical filtering stays separate from encoding. Task coverage
receipts explicitly partition every original view ID into retained or excluded
IDs, without overlap; excluded entries carry status, reason, pointer, and hash.
Source Block exclusion continues to protect blocks referenced by active
Requirements. No semantic content is filtered by the codec.

## Reproduce the audit

```powershell
py -3 scripts/python/check_capability_task_evidence.py --out-dir logs/ci/task-evidence-audit
```

This verifies the complete repository Taskmaster triplet both before and after
the existing blinding transformation. It saves snapshots, packets,
`expansion-map.json`, partition coverage, hashes, and missing declared targets.
Corpus byte savings measure the codec only; they are not final request savings.
The command never invents missing Chapter 5 readiness or a source manifest.

The same command prepares a fixed raw/encoded comprehension probe. To invoke
two fresh sessions through an explicitly selected runner:

```powershell
py -3 scripts/python/check_capability_task_evidence.py --out-dir logs/ci/task-evidence-model-check --model-runner scripts/python/codex_isolated_model_runner.py
```

The expected answers stay outside both model workspaces. The probe tests
different acceptance arrays, a state-advance prohibition, explicit versus
undeclared links, full source text, unknown fields, and absent versus null.
Both responses must match the fixed oracle. Probe results are a limited
comprehension check, not full Capability acceptance or proof of model identity
and filesystem isolation. No fake/model-free test counts as a real-model pass.
Missing CLI/authentication or failed responses are recorded without enabling
the trial. The command returns nonzero for missing declared targets or a
blocked/failed requested model check.

## Controlled workflow trial

After reviewing the audit and real-model probe, opt in **before preparing a new
run** in the existing local environment:

```powershell
$env:SC_CAPABILITY_TASK_VIEW_ENCODING = 'lossless-v1'
py -3 scripts/python/dev_cli.py plan-capabilities --stage prepare --run-id <new-id> --task-id <ready-task-id>
Remove-Item Env:SC_CAPABILITY_TASK_VIEW_ENCODING
```

Preparation freezes the mode into the hash-bound analysis index. Later changes
to the environment do not switch existing runs or candidates. The web job uses
the same prepare path; an explicit environment opt-in must be set on its server
before a new job. `raw` remains the default, and there is no automatic promotion
following the probe. Existing generate/review/align/apply commands are unchanged.

In the trial, paired views stay in one task chunk, and original per-view row
positions remain in the expansion map. A single task group exceeding the chunk
target remains whole; final byte/token admission can still block it.

Each runner workspace saves machine-only files under
`evidence-transport/task-views-NNN/`: `authoritative-input.json`, `packet.json`,
`expansion-map.json`, and `metrics.json`. Metrics record both complete request
hashes, byte/token counts and counter, row/object counts, coverage, savings,
selection, and validation status. These files and the reference catalog are
excluded from model payload enumeration, including repeated preflight/resume.
The original evidence and expansion map are not prerequisites for model-side
understanding or cross-request lookup.

The trial must not become the default until current-source references resolve,
the real-model comprehension check passes in the intended environment, and a
controlled Capability run confirms source fidelity and boundaries. The earlier
Codex isolation/model-identity review findings remain separate prerequisites;
this codec does not establish a stronger sandbox by reporting one.
