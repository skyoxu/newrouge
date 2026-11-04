# Story 2.2 scoped migration checkpoint

This branch is a temporary migration carrier, not a release or acceptance claim.
The owner explicitly authorized publication of selected project specifications,
stage records and private evidence after being told the repository is public and
PR-time deletion cannot retract Git history or copies. No credentials or sessions
are included. This later authorization changes the earlier code-only publication
boundary for this migration only; the archived spec and session remain unmodified.

## Restore

1. Fetch this branch into a new, isolated directory. Do not overwrite an existing
   repository. Prefer /workspace/newrouge-b-story-1-1 only if that path is absent.
2. Pin the full commit SHA provided in the transfer receipt. Verify each manifest
   file's byte count, SHA-256 and Git blob SHA before using it. Git blob bytes are
   authoritative if checkout line-ending conversion differs.
3. Continue the existing snapshot identified in session.json and the manifest.
   Verify BMAD 6.12.4 installation/dependencies independently. This carrier includes
   configuration and the existing rendered snapshot, not the full installation.
   Do not rerender the Story as if it were new. A different root needs explicit
   path rebinding in active configuration, with archived proof kept unchanged.
4. The original HEAD is provenance only, not this migration branch HEAD. Missing
   original baseline history and older proof remain in the private checkpoint;
   do not invent them or treat spec/Sprint statuses as their substitutes.
5. Keep Story2.2 in-progress at native Step3. Windows run41831324047 passed
   175 tests with one POSIX-only skip and 29 synthetic CLI calls. Real independent
   model semantic acceptance is still incomplete. Do not rerun completed Windows
   CI or start dependent Story2.3 just because these files are restored.

## Codex initialization

The old instance recorded EROFS at its noncredential client state paths. One
formally approved execution passed initialization and then hit the inherited
proxy's CONNECT403. This is not proof that a new instance is fixed. On the new
instance inspect its own policy and sanctioned client write scope first. Use a
supported approval for the exact required operation when appropriate; do not copy
credentials, relocate CODEX_HOME, read restricted sessions, change permissions or
bypass network policy. There was no new model call in preparing this checkpoint.

## Before any future PR

No PR is authorized or created by this migration. In a separate future PR branch,
restore the temporary transfer paths to parent commit
18f54b10a4a2811eb8c167bc6289791d43c2c3e5, then deliberately retain only reviewed
product changes. This removes newly added paths and restores existing paths to
that parent version; do not delete the old workspace or private checkpoint.
At minimum exclude _bmad/** and logs/**. Review specs, Sprint state and handoff
records individually. Deleting files never retracts this public commit's history.
The exact transferred paths and hashes are in manifest.json.
