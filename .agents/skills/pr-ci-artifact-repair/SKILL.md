---
name: pr-ci-artifact-repair
description: Analyze a failing PR or GitHub Actions run from downloaded CI artifacts or run ids, classify whether the failure is wrapper noise, shared-state test pollution, or a real product regression, then implement the smallest safe fix, record a decision log, validate recovery docs, commit, and push. Use when the user asks to inspect a failing PR, a GitHub Actions run, CI artifact zip files, or repeated dotnet/selfcheck failures.
---

# PR CI Artifact Repair

Use this skill for `newrouge` when a PR or GitHub Actions run is red and the user wants artifact-based diagnosis plus a direct fix.

## Inputs you should expect

- A GitHub Actions `run id`
- Downloaded artifact zips such as `F:\gitlog\ci-logs*.zip` and `F:\gitlog\selfcheck-logs*.zip`
- A request to inspect repeated CI failures, patch the repo, commit, and push

## Non-negotiable repo rules

- Communicate with the user in Chinese.
- Prefer Windows/PowerShell commands.
- Put evidence under `logs/**` and write the repair note to `decision-logs/YYYY-MM-DD-run-<runid>-failure-analysis.md`.
- Validate with `py -3 scripts/python/validate_recovery_docs.py --dir all` before commit.
- Never revert unrelated user changes in the dirty worktree.
- Commit only the files needed for the CI repair.

## Workflow

1. Read the latest artifacts first.
   - If the user gives zip files, unpack them under `F:\gitlog\<name>_unpacked`.
   - Read at least:
     - `ci-pipeline-summary.json`
     - `dotnet-test-output.txt`
     - `run-dotnet-console.txt`
     - `selfcheck-summary.json`
   - Confirm whether hard gates or Godot selfcheck are already green.

2. Classify the failure before editing code.
   - `Wrapper false-red / retry policy issue`
     - Signals: zero real failed tests, `Passed! - Failed: 0`, `Test Run Aborted`, `Results File:`, `Attachments:`, host crash after green body.
   - `Shared-state pollution inside tests`
     - Signals: very early fan-out `Could not load file or assembly 'Game.Core'`, unknown test case reporting, one test mutates shared repo files or launches nested build/test flows.
   - `Real functional failure`
     - Signals: stable named red tests with coherent assertions, no suite-wide assembly-load collapse.

3. Prefer the smallest layer for the fix.
   - Wrapper/orchestration layer first if the evidence is infrastructure noise.
   - Test-harness isolation second if one test pollutes shared state.
   - Production code only if the failure is a real behavior regression.

4. Validate the exact hypothesis locally.
   - Use targeted test filters instead of full-suite reruns whenever possible.
   - For wrapper changes, add or update regression tests first when practical.
   - For shared-state races, prove the risky pair or group with filtered `dotnet test`.

5. Write the repair note.
   - Create `decision-logs/YYYY-MM-DD-run-<runid>-failure-analysis.md`.
   - Capture:
     - why now
     - artifact-backed context
     - decision
     - consequences
     - recovery impact
     - validation commands

6. Finalize cleanly.
   - Run `py -3 scripts/python/validate_recovery_docs.py --dir all`
   - Review staged diff only for repair files
   - Commit with a run-specific message
   - Push the active branch

## Stable patterns from this PR history

### 1. `run_dotnet.py` retry and artifact isolation

Check `scripts/python/run_dotnet.py` and `scripts/sc/tests/test_run_dotnet_solution_resolution.py` first when CI shows post-run abort noise.

Known good rules:

- Isolate each `dotnet test` attempt into `Game.Core.Tests/TestResults/attempt-N`
- On retry, clean:
  - `Game.Core.Tests/TestResults`
  - `Game.Core.Tests/bin/<Configuration>`
  - `Game.Core/bin/<Configuration>`
- Do not delete `obj` during retry cleanup
- Retry only retryable post-run aborts
- Do not retry deterministic red tests
- Treat exhausted all-green retryable aborts as success with warning

### 2. Shared mutable file or output races inside tests

Look for tests that:

- rewrite `Game.Core/Game.Core.csproj`
- run `dotnet build` or `dotnet restore`
- spawn `acceptance_check.py`, `quality_gates.py`, or other scripts that can trigger nested dotnet work
- read/write repo-root artifacts used by other tests

Known good repairs:

- Serialize shared mutators with an xUnit collection
- Isolate external build outputs with temporary `BaseOutputPath`
- Keep `obj` when `--no-restore` relies on existing assets
- Remove nested acceptance/build/test execution from unit tests; use deterministic fixtures or prebuilt summaries instead

### 3. Decision boundary for `real bug` vs `CI noise`

Treat it as CI noise if:

- build succeeds
- many unrelated tests fail almost immediately
- stack traces collapse into the same missing assembly or unknown test case pattern

Treat it as a real bug if:

- failures stay localized
- assertion messages are coherent
- the same test remains red in filtered local runs without suite interference

## Files to inspect first

- `scripts/python/run_dotnet.py`
- `scripts/sc/tests/test_run_dotnet_solution_resolution.py`
- `Game.Core.Tests/Tasks/Task0092AcceptanceTests.cs`
- `Game.Core.Tests/Tasks/Task2RootBuildGateTests.cs`
- `Game.Core.Tests/Tasks/Task0046AcceptanceTests.cs`
- latest `decision-logs/2026-05-22-run-*-failure-analysis.md`

## Output contract

When you use this skill, do all of the following unless blocked:

- state the classified failure type
- cite the artifact files that proved it
- apply the smallest fix
- run targeted validation
- write the decision log
- validate recovery docs
- commit and push

If you cannot complete one of these steps, say exactly what blocked it.
