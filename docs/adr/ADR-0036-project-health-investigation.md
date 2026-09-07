# ADR-0036: Local Project Health Investigation Boundary

- Status: Proposed
- Date: 2026-09-07
- Context: The existing loopback project-health host needs interactive main-only knowledge, Impact and task/scene investigation.
- Decision:
  - Add `/knowledge/` to the existing host with fixed CLI-backed endpoints; no arbitrary shell or automatic LLM execution.
  - Read the local `refs/heads/main` Git tree without fetch, checkout, or worktree creation. Without Git, use explicitly configured directory sources with a content digest, never a fabricated commit. Never substitute developer branch content for main facts.
  - Gate POST operations by exact loopback Host, same Origin, per-process token, bounded JSON and fixed operations.
  - Keep local configuration separate from committed source provenance. Configured extra GDDs are supplementary, not automatically published KCP authority.
  - Keep exploratory Impact output under a distinct non-handoff schema. Unsupported method signatures are explicit omissions only in exploration; formal analysis remains strict.
  - Task status remains tasks.json authority. Scene attachment declarations plus static checks are not runtime or acceptance proof.
- Consequences: Source discovery becomes accessible without changing chapter skills; incomplete static coverage and cached snapshot age remain visible. No public hosting or broader file access is introduced.
- Supersedes: None
- References: `docs/adr/ADR-0035-repository-knowledge-control-plane.md`, `docs/workflows/project-health-knowledge.md`.
