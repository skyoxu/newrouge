# Cross-Repository Migration Reconciliation

Purpose: make bounded source-to-target repository migrations auditable instead of relying on remembered diff review.

This protocol is repository-neutral. A source repository may be a template, sibling business repository, or another governed upstream. A target repository keeps its own business semantics and generated state.

## Manifest contract

Store target-owned manifests under docs/migration/reconciliation/*.json.

Schema: repo.cross-repo-migration-reconciliation.v1

Each manifest freezes:

- source repository in owner/name form;
- merged source PR number;
- full source merge commit SHA;
- complete source PR changed-file list;
- changed_file_count;
- optional changed_files_sha256, computed from the sorted JSON changed-file array and checked when present;
- target repository;
- exactly one classification entry for every source changed file.

## Classifications

- copy_exact: shared repository-neutral content that should stay byte-identical. Requires one target path and the frozen source Git blob SHA.
- adapt_target_native: reusable behavior localized to the target repository. Requires target paths and target-owned validation evidence.
- already_present: equivalent target behavior already exists. Requires target paths and validation evidence.
- derived_regenerate: generated state must not be copied from the source. Requires the target regeneration command.
- business_only_drop: source business behavior is intentionally outside target scope. Must not name target paths.
- protocol_name_retain: upstream protocol/schema identifiers intentionally keep their compatible namespace. Requires target paths, validation evidence, and retained identifiers.

## Offline validation

Run:

~~~powershell
py -3 scripts/python/check_cross_repo_migration.py --manifest docs/migration/reconciliation/<source>-<pr>.json
~~~

For repositories that have adopted reconciliation as a mandatory migration gate:

~~~powershell
py -3 scripts/python/check_cross_repo_migration.py --require-manifests
~~~

Offline validation is deterministic. It verifies manifest structure, any declared changed-file inventory checksum, one-to-one classification coverage, target evidence paths, and copy_exact Git blob identity.

## Source GitHub verification

The embedded source inventory is still target-owned evidence. During migration creation or audit, independently verify it against the merged source PR:

~~~powershell
$env:GITHUB_TOKEN = "<token with source repo read access>"
py -3 scripts/python/check_cross_repo_migration.py --manifest docs/migration/reconciliation/<source>-<pr>.json --verify-source-github
~~~

This mode verifies:

- the source PR is merged;
- GitHub merge_commit_sha equals the frozen manifest commit;
- GitHub's complete paginated changed-file set equals the manifest inventory.

Do not make ordinary hard gates depend on cross-repository network availability unless the repository explicitly accepts that dependency. The recommended model is remote verification at migration creation/review, deterministic offline verification on every target hard gate.

## Example skeleton

~~~json
{
  "schema_version": "repo.cross-repo-migration-reconciliation.v1",
  "source": {
    "repo": "owner/source",
    "pr": 123,
    "merge_commit": "0123456789abcdef0123456789abcdef01234567",
    "changed_file_count": 2,
    "changed_files": [
      "scripts/python/shared.py",
      "Game.Core/SourceOnly.cs"
    ],
    "changed_files_sha256": "<canonical inventory sha256>"
  },
  "target": {
    "repo": "owner/target",
    "pr": 456,
    "branch": "sync-source-123"
  },
  "entries": [
    {
      "source_path": "scripts/python/shared.py",
      "classification": "copy_exact",
      "target_paths": ["scripts/python/shared.py"],
      "source_blob_sha": "<source git blob sha>",
      "rationale": "Repository-neutral control-plane code."
    },
    {
      "source_path": "Game.Core/SourceOnly.cs",
      "classification": "business_only_drop",
      "rationale": "Source business behavior is not part of target migration scope."
    }
  ]
}
~~~

## Migration completion rule

A bounded source PR is not reconciled until:

1. its source merge commit and full changed-file inventory are frozen;
2. remote source verification has been run at least once during creation/review;
3. every source file is classified exactly once;
4. copy_exact files match the frozen source blob;
5. every target-native adaptation has target-owned validation evidence;
6. generated source publication state is regenerated from target inputs instead of copied;
7. target protected checks are green.

A source PR that only publishes generated state should still receive an explicit derived_regenerate reconciliation record when the target tracks source evolution by PR.

## Boundaries

This mechanism is not a call graph, merge engine, or automatic business-semantic equivalence proof. It proves inventory reconciliation and evidence obligations. Human/domain review still decides whether an adapt_target_native implementation is behaviorally appropriate.
