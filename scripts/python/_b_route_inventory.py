"""Read-only Story 1.1 inventory; never invokes a producer or planner."""
from __future__ import annotations

import ast
import datetime as dt
import fnmatch
import hashlib
import html
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from _planning_skill_common import canonical_sha, file_sha, repo_path
from build_source_ledger import resolve_sources, SUPPORTED_SUFFIXES
from _mvg_manifest import manifest_sha256, validate_manifest

SCHEMA = "newrouge.b-route-baseline-inventory.v3"
SOURCE_SET = "docs/workflows/chapter3-source-set.json"
TRIPLET = {name: f".taskmaster/tasks/tasks{suffix}.json" for name, suffix in
           (("master", ""), ("back", "_back"), ("gameplay", "_gameplay"))}
MASTER_STATES = {"pending", "in-progress", "done", "deferred", "cancelled", "blocked"}
VIEW_STATES = MASTER_STATES | {"review", "in_progress", "inprogress", "completed", "complete"}

# A reviewable inventory, not a claim of automatic semantic completeness.
# Paths/symbols are checked against the collected bytes, without importing consumers.
GROUPS = (
    ("source-ledger-audit", "Reads source declarations and projects/audits requirements; producers can write planning artifacts.",
     "Move independent source audit before Task planning; inventory only here.", "Epic2", (
         ("scripts/python/build_source_ledger.py", "resolve_sources"),
         ("scripts/python/project_semantics_from_sources.py", "prepare"),
         ("scripts/python/project_semantics_from_sources.py", "compile_projection"),
         ("scripts/python/validate_semantic_conservation.py", "validate"),
         ("scripts/python/audit_task_candidate_coverage.py", "audit"))),
    ("capability-mvg", "Reads source/Task/readiness inputs; prepares and adopts Capability/MVG plans.",
     "Support governed Task-independent adoption while retaining current gates until migrated.", "Epic2", (
         ("scripts/python/plan_capabilities.py", "prepare"),
         ("scripts/python/plan_mvg.py", "prepare"))),
    ("worker-checkpoint-recovery", "Existing workers, durable checkpoints and completed-capability recovery read/write their own records.",
     "Reuse existing mechanisms; extend identity/adoption bindings instead of rebuilding workers.", "Epic2", (
         ("scripts/python/_mvg_capability_worker.py", "run_candidate"),
         ("scripts/python/_mvg_capability_checkpoint.py", "commit_checkpoint"),
         ("scripts/python/_mvg_capability_recovery.py", "try_adopt"))),
    ("business-triplet", "Reads business views and master; governed compilers write triplet preserving master status.",
     "Compile reviewed reuse/gap deltas with stable Task identities and history.", "Epic3", (
         ("scripts/python/normalize_task_intents.py", "main"),
         ("scripts/python/compile_task_triplet.py", "main"),
         ("scripts/python/build_taskmaster_tasks.py", "main"),
         ("scripts/python/audit_task_triplet_delivery.py", "find_view_task"),
         ("scripts/python/validate_task_master_triplet.py", "validate_taskmaster_mapping"))),
    ("chapter4-5", "Reads Tasks, overlays and contracts; Chapter4 generates overlays and Chapter5 writes reconciliation/readiness.",
     "Bind applicable adopted plans and common current inputs before implementation.", "Epic3", (
         ("scripts/sc/llm_generate_overlays_batch.py", "main"),
         ("scripts/python/chapter5_semantic_reconciliation.py", "build_task_authority_scope"),
         ("scripts/python/chapter5_semantic_reconciliation.py", "build_chapter5_input_fingerprint"),
         ("scripts/python/chapter5_semantic_reconciliation.py", "reconcile"))),
    ("chapter6-direct-resume-route", "Reads Task/readiness and MVG obligations; direct/resume/route entrypoints can execute implementation workflows.",
     "Share implementation eligibility; missing B bindings must not imply legacy eligibility.", "Epic3", (
         ("scripts/python/run_single_task_chapter6_lane.py", "main"),
         ("scripts/python/resume_task.py", "main"),
         ("scripts/python/chapter6_route.py", "main"),
         ("scripts/python/_mvg_obligations.py", "check_task_obligations"))),
    ("chapter7", "Reads UI backlog and implementation evidence; writes wiring/gap workflow artifacts.",
     "Close the target slice and reuse verified UI obligations.", "Epic3", (
         ("scripts/python/run_chapter7_ui_wiring.py", "main"),
         ("scripts/python/run_chapter7_backlog_gap.py", "main"))),
    ("manifest-runner-handoff", "Reads cumulative manifests/handoffs; runners execute tests and write evidence.",
     "Execute governed verification scope and preserve all three classes of obligation.", "Epic4", (
         ("scripts/python/_mvg_manifest.py", "validate_manifest"),
         ("scripts/python/run_mvg_acceptance.py", "main"),
         ("scripts/python/_mvg_execution.py", "execute_test"),
         ("scripts/python/milestone_incremental_handoff.py", "build_task_handoff"))),
    ("knowledge-planning-page", "Reads authoritative planning data; catalog builders/publishers and page actions can write derived records/pointers.",
     "Derive planning/implementation/runtime identities; workspace preview never publishes.", "Epic4", (
         ("scripts/python/build_knowledge_catalog.py", "main"),
         ("scripts/python/publish_knowledge_catalog.py", "publish"),
         ("scripts/python/_project_health_planning.py", "run_job"),
         ("scripts/python/project_health_planning.js", None))),
    ("cli-skill-routing-examples", "Documents/routes public commands; CLI dispatch can invoke producers and implementation workflows.",
     "Align every consumer in Epic4; switch defaults only under Epic5 conditions.", "Epic4/Epic5", (
         ("scripts/python/dev_cli.py", "main"),
         ("scripts/python/dev_cli_builders.py", None),
         ("AGENTS.md", None), ("workflow.md", None),
         ("docs/workflows/stable-public-entrypoints.md", None),
         ("docs/workflows/script-entrypoints-index.md", None),
         ("docs/workflows/mvg-integration-acceptance.md", None))),
)
DISCOVERY = (
    ("authority", "docs/adr/ADR-*.md"),
    ("authority", "docs/architecture/base/**/*"),
    ("authority", "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/**/*"),
    ("authority", "Game.Core/Contracts/**/*"),
    ("skill", ".agents/skills/workflow-chapter[3-7]*/**/*"),
    ("capability-skill", ".agents/skills/plan-capabilities/**/*"),
    ("mvg-skill", ".agents/skills/plan-mvg/**/*"),
    ("example", "examples/**/*"),
    ("example", "docs/workflows/examples/**/*"),
    ("manifest", "docs/testing/mvg/*.json"),
)
REQUIRED_CHAPTER_SKILLS = (
    ".agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md",
    ".agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md",
    ".agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md",
    ".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md",
    ".agents/skills/workflow-chapter7-ui-wiring-closure/SKILL.md",
)
BINARY_RESOURCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
                            ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".bin"}


class GitCommandTimeout(ValueError):
    """A bounded Git read failed to complete."""


def require_runtime() -> None:
    if sys.version_info < (3, 12):
        raise ValueError("Python 3.12 or later is required for Windows reparse-point checks")


def canonical_path(value: str, *, allow_logs: bool = False, pattern: bool = False) -> str:
    """Reject Windows aliases on every host, before PurePath can normalize them."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or value.startswith("/"):
        raise ValueError(f"Expected a canonical repository-relative POSIX path: {value!r}")
    parts = value.split("/")
    for part in parts:
        if (not part or part in {".", ".."} or part.rstrip(" .") != part
                or any(ord(c) < 32 for c in part) or any(c in part for c in '<>"|')
                or (not pattern and any(c in part for c in "*?"))):
            raise ValueError(f"Noncanonical path component: {value!r}")
        stem = part.split(".")[0].casefold()
        if stem in {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}:
            raise ValueError(f"Windows device alias is not allowed: {value!r}")
    if parts[0].casefold() == ".git" or (parts[0].casefold() == "logs" and not allow_logs):
        raise ValueError(f"Forbidden input tree: {value!r}")
    if allow_logs and parts[0].casefold() == "logs" and parts[0] != "logs":
        raise ValueError(f"Noncanonical logs alias: {value!r}")
    return value


def no_reparse(path: Path) -> None:
    """lstat detects Windows reparse attributes even without Path.is_junction."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Symlink or reparse point is forbidden: {path.name}")


def safe_input(root: Path, value: str, *, allow_logs: bool = False) -> Path:
    canonical_path(value, allow_logs=allow_logs)
    current = root
    for ancestor in reversed((current, *current.parents)):
        no_reparse(ancestor)
    for part in value.split("/"):
        # Existing names must use their actual spelling, including on Windows.
        if current.is_dir():
            aliases = [p.name for p in current.iterdir() if p.name.casefold() == part.casefold()]
            if aliases and (len(aliases) != 1 or aliases[0] != part):
                raise ValueError(f"Case alias or collision: {value!r}")
        current /= part
        no_reparse(current)
    return repo_path(root, value)


def safe_source_pattern(root: Path, pattern: str) -> None:
    """Check directory boundaries before the reused resolver enumerates matches."""
    canonical_path(pattern, pattern=True)
    parts = pattern.split("/")
    wildcard = next((i for i, part in enumerate(parts) if any(c in part for c in "*?[")), len(parts))
    if wildcard == 0:
        raise ValueError("Source patterns require a literal non-log tree prefix")
    base = safe_input(root, "/".join(parts[:wildcard]))
    if wildcard < len(parts) and base.is_dir():
        def traversal_error(exc: OSError) -> None:
            raise ValueError("Source traversal failed: " + str(exc).replace(str(root), "{root}")) from exc
        for directory, dirs, _files in os.walk(base, followlinks=False, onerror=traversal_error):
            for name in dirs:
                no_reparse(Path(directory, name))


def git(root: Path, *args: str, optional: bool = False, environment: dict | None = None) -> bytes:
    child_env = dict(os.environ if environment is None else environment)
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
                 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_CONFIG_PARAMETERS'):
        child_env.pop(name, None)
    child_env.update(GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1', GIT_REPLACE_REF_BASE='refs/replace',
        GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1',
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_COUNT='0', GIT_TRACE='0', GIT_TRACE_SETUP='0',
        GIT_TRACE_PACKET='0', GIT_TRACE2='0', GIT_TRACE2_EVENT='0', GIT_TRACE2_PERF='0')
    try:
        proc = subprocess.run(["git", "--no-optional-locks", "--no-replace-objects",
            "-c", "protocol.allow=never", "-c", "core.hooksPath=" + os.devnull,
            "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false", "-C", str(root), *args],
            capture_output=True, timeout=30, env=child_env)
    except subprocess.TimeoutExpired as exc:
        raise GitCommandTimeout(f"Git {' '.join(args[:2])} timed out after {exc.timeout} seconds") from exc
    if proc.returncode and not optional:
        raise ValueError(f"Git {' '.join(args[:2])} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def validate_git_root(root: Path) -> None:
    for ancestor in reversed((root.absolute(), *root.absolute().parents)):
        no_reparse(ancestor)
    top = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip())
    if top.resolve() != root.resolve():
        raise ValueError("Explicit root must be the Git repository top-level directory")


def git_identity(root: Path) -> dict:
    validate_git_root(root)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise ValueError("Git HEAD is not a full object identity")
    branch = git(root, "symbolic-ref", "--quiet", "HEAD", optional=True).decode().strip() or None
    raw = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", ".", ":(exclude)logs")
    fields, changes, index = raw.split(b"\0"), [], 0
    while index < len(fields) and fields[index]:
        item = fields[index]
        row = {"status": item[:2].decode("ascii"), "path": os.fsdecode(item[3:])}
        index += 1
        if "R" in row["status"] or "C" in row["status"]:
            row["original_path"] = os.fsdecode(fields[index])
            index += 1
        changes.append(row)
    blobs = {}
    for record in git(root, "ls-tree", "-r", "-z", head).split(b"\0"):
        if record:
            metadata, name = record.split(b"\t", 1)
            mode, kind, oid = metadata.split(b" ")
            blobs[os.fsdecode(name)] = {"mode": mode.decode(), "kind": kind.decode(), "oid": oid.decode()}
    return {"head": head, "branch": branch, "detached": branch is None,
            "status_porcelain_z_sha256": digest(raw), "changes": changes,
            "diff_head_sha256": digest(git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--", ".", ":(exclude)logs")),
            "diff_index_sha256": digest(git(root, "diff", "--no-ext-diff", "--no-textconv", "--cached", "--binary", "HEAD", "--", ".", ":(exclude)logs")),
            "diff_worktree_sha256": digest(git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "--", ".", ":(exclude)logs")),
            "status_scope": "Repository excluding logs; output is never a source", "blobs": blobs}


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def rule_identity() -> dict[str, str]:
    """Exact installed collector rules supported by the current protection owner.

    This is a policy identity, not an attestation that a collection event ran.
    """
    rule_files = [Path(__file__), Path(__file__).with_name("inventory_b_route_baseline.py"),
                  Path(__file__).with_name("_planning_skill_common.py"),
                  Path(__file__).with_name("build_source_ledger.py"), Path(__file__).with_name("_mvg_manifest.py"),
                  Path(__file__).with_name("_b_route_initial_legacy.py"), Path(__file__).with_name("_b_route_records.py"),
                  Path(__file__).with_name("_b_route_codec.py"), Path(__file__).with_name("_b_route_schema_resources.py")]
    from _b_route_schema_resources import resources
    return {**{path.name: file_sha(path) for path in rule_files},
            **{"schema:"+name: digest(raw) for name,raw in resources()}}


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict:
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError(f"Duplicate JSON key: {key}")
            output[key] = value
        return output
    def invalid_constant(value: str) -> None:
        raise ValueError(f"Non-JSON numeric constant: {value}")
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid_constant)


def frontmatter(raw: bytes) -> dict:
    """Read the explicit scalar/list subset used by the canonical epic header."""
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("Epics frontmatter is missing")
    end = lines.index("---", 1)
    output, key = {}, None
    for line in lines[1:end]:
        item = re.fullmatch(r"\s+-\s+(.+)", line)
        if item and key:
            if not isinstance(output[key], list):
                raise ValueError(f"Malformed frontmatter list: {key}")
            value = item[1].strip()
            output[key].append(json.loads(value) if value.startswith('"') else value.strip("'"))
        elif line and not line.startswith((" ", "#")) and ":" in line:
            key, value = line.split(":", 1)
            if key in output:
                raise ValueError(f"Duplicate frontmatter field: {key}")
            output[key] = value.strip().strip("\"'") if value.strip() else []
    return output


def markdown_status_lines(text: str):
    """Keep real Markdown/frontmatter lines, excluding code and HTML comments."""
    fence = None
    comment = False
    for number, original in enumerate(text.splitlines(), 1):
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}\s*", original):
                fence = None
            continue
        if not comment and original.expandtabs(4).startswith("    "):
            continue
        line, remaining = "", original
        while remaining:
            if comment:
                end = remaining.find("-->")
                if end < 0:
                    remaining = ""
                else:
                    comment, remaining = False, remaining[end + 3:]
            else:
                start = remaining.find("<!--")
                if start < 0:
                    line += remaining
                    remaining = ""
                else:
                    line += remaining[:start]
                    comment, remaining = True, remaining[start + 4:]
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if opening:
            fence = opening[1][0], len(opening[1])
            continue
        if not line.expandtabs(4).startswith("    "):
            yield number, line


class Snapshot:
    def __init__(self, root: Path, epics: str, *, read_bytes=None, virtual_files=(), historical_inventory=None):
        self.root, self.epics = root, epics
        self.historical_inventory = historical_inventory
        self.read_bytes = read_bytes
        self.virtual_files = tuple(virtual_files)
        self.inputs: dict[str, dict] = {}
        self.cache: dict[str, bytes | None] = {}
        self.diagnostics: list[dict] = []
        self.references: list[dict] = []
        self.consumers: list[dict] = []
        self.git_start = git_identity(root)

    def diagnostic(self, code: str, location: str, message: str, severity: str = "error") -> None:
        item = {"code": code, "location": location, "message": message, "severity": severity}
        if item not in self.diagnostics:
            self.diagnostics.append(item)

    def read(self, path: str, role: str, *, required: bool = True, evidence: bool = False) -> bytes | None:
        safe = False
        try:
            target = safe_input(self.root, path, allow_logs=evidence)
            safe = True
            if path in self.cache:
                if role not in self.inputs[path]["roles"]:
                    self.inputs[path]["roles"].append(role)
                if self.cache[path] is None:
                    self.diagnostic("missing-input", path, "Required file is missing" if required else "Optional file is missing",
                                    "error" if required else "warning")
                return self.cache[path]
            raw = target.read_bytes() if self.read_bytes is None else self.read_bytes(path)
            if raw is None:
                raise FileNotFoundError(path)
        except (OSError, ValueError) as exc:
            self.diagnostic("missing-input" if isinstance(exc, FileNotFoundError) else "unsafe-or-unreadable-input",
                            path, str(exc).replace(str(self.root), "{root}"),
                            "warning" if not required and isinstance(exc, FileNotFoundError) else "error")
            if path in self.cache:
                return None
            raw = None
        if safe:
            self.cache[path] = raw
        roles = list(self.inputs.get(path, {}).get("roles", []))
        if role not in roles:
            roles.append(role)
        self.inputs[path] = {"path": path, "roles": roles, "exists": raw is not None,
                             "raw_sha256": digest(raw) if raw is not None else None,
                             "normalized_sha256": manifest_sha256(raw) if raw is not None else None,
                             "size_bytes": len(raw) if raw is not None else None,
                             "head_blob": self.git_start["blobs"].get(path)}
        return raw

    def json(self, path: str, role: str) -> Any:
        raw = self.read(path, role)
        if raw is None:
            return None
        try:
            return strict_json(raw)
        except (ValueError, UnicodeError) as exc:
            self.diagnostic("invalid-json", path, str(exc))
            return None

    def discover(self) -> list[tuple[str, str]]:
        found = []
        for role, pattern in DISCOVERY:
            # No logs wildcard is allowed, even when reached via a directory alias.
            canonical_path(pattern, pattern=True)
            prefix = pattern.split("/")
            prefix = prefix[:next((i for i, part in enumerate(prefix) if any(c in part for c in "*?[")), len(prefix))]
            base = self.root.joinpath(*prefix)
            if not base.exists():
                continue
            try:
                safe_input(self.root, "/".join(prefix))
            except (OSError, ValueError) as exc:
                self.diagnostic("unsafe-discovery-root", "/".join(prefix), str(exc).replace(str(self.root), "{root}"))
                continue
            def traversal_error(exc: OSError) -> None:
                location = str(exc.filename or pattern).replace(str(self.root), "{root}")
                self.diagnostic("unreadable-discovery", location, str(exc).replace(str(self.root), "{root}"))
            for directory, dirs, files in os.walk(base, followlinks=False, onerror=traversal_error):
                dirs.sort()
                for name in list(dirs):
                    path = Path(directory, name)
                    try:
                        no_reparse(path)
                    except (OSError, ValueError):
                        self.read(path.relative_to(self.root).as_posix(), role)
                        dirs.remove(name)
                    if name == "__pycache__" and name in dirs:
                        dirs.remove(name)
                for name in sorted(files):
                    path = Path(directory, name)
                    value = path.relative_to(self.root).as_posix()
                    if any(fnmatch.fnmatchcase(value, candidate) for candidate in (pattern, pattern.replace("/**/", "/"))):
                        self.read(value, role)
                        found.append((role, value))
        found.sort()
        return found

    def consumer(self, category: str, path: str, symbol: str | None, responsibility: str, difference: str, epic: str) -> None:
        raw = self.read(path, "consumer")
        line = None
        resource = symbol is None and Path(path).suffix.lower() in BINARY_RESOURCE_SUFFIXES
        if raw is not None and not resource:
            try:
                text = raw.decode("utf-8-sig")
                line = 1
                if symbol is not None:
                    if path.endswith(".py"):
                        nodes = [n for n in ast.walk(ast.parse(text))
                                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == symbol]
                        if not nodes:
                            raise ValueError(f"Missing Python symbol: {symbol}")
                        line = min(n.lineno for n in nodes)
                    else:
                        raise ValueError("Symbol locators are supported only for Python consumers")
            except (SyntaxError, UnicodeError, ValueError) as exc:
                self.diagnostic("invalid-consumer-locator", path, str(exc))
                line = None
        self.consumers.append({"category": category, "path": path, "symbol": symbol,
                               "locator": f"{path}:{line}" if line else path,
                               "line": line, "locator_kind": "resource" if resource else ("symbol" if symbol else "document"),
                               "responsibility": responsibility, "current_a_to_target_b": difference,
                               "followup_epic": epic, "invoked": False})

    def reference(self, owner: str, pointer: str, task_id: Any, master_id: Any, field: str, value: Any,
                  *, required: bool = True) -> None:
        # Roles come from the owning field, never from Task status or a caller
        # supplied exemption. An attachment is not an operation prerequisite.
        if field == "evidence_refs":
            required = False
            reference_role = "historical-debug-attachment"
        else:
            reference_role = "current-input" if required else "planned-input"
        row = {"owner_file": owner, "json_pointer": pointer, "task_id": task_id,
               "master_id": master_id, "field": field, "raw_reference": value,
               "reference_role": reference_role, "required": required}
        self.references.append(row)
        if not isinstance(value, str) or not value.strip():
            row.update(state="unknown", reason="Reference must be a nonempty original string")
            self.diagnostic("invalid-reference", owner + "#" + pointer, row["reason"])
            return
        if re.search(r"<[^>]+>", value):
            row.update(state="unknown", reason="Historical template is not a concrete file or runtime proof")
            self.diagnostic("historical-reference-template", owner + "#" + pointer, value, "warning")
            return
        if field == "source_refs" and "/" not in value and not re.search(r"\.[a-zA-Z]+(?::\d+)?$", value):
            row.update(state="unknown", reason="Semantic/event identifier is not a file reference")
            self.diagnostic("non-file-source-reference", owner + "#" + pointer, value, "warning")
            return
        match = re.fullmatch(r"(.+?):([1-9][0-9]*)(?:[-:]([1-9][0-9]*))?", value)
        path, start, end = (match[1], int(match[2]), int(match[3] or match[2])) if match else (value, None, None)
        row.update(path=path, line_start=start, line_end=end)
        raw = self.read(path, "task-reference:" + field, required=required,
                        evidence=field == "evidence_refs")
        row.update(state="present" if raw is not None else "missing",
                   raw_sha256=digest(raw) if raw is not None else None)
        if raw is None:
            row["reason"] = "Referenced file is missing or cannot be verified; no runtime proof inferred"
        elif start is not None:
            try:
                if end < start or end > len(raw.decode("utf-8-sig").splitlines()):
                    raise ValueError("Line locator is outside the referenced file")
            except (ValueError, UnicodeError) as exc:
                row.update(state="unknown", reason=str(exc))
                self.diagnostic("invalid-reference-locator", owner + "#" + pointer, str(exc))

    def tasks(self) -> dict:
        documents = {name: self.json(path, "triplet") for name, path in TRIPLET.items()}
        master_doc = documents["master"]
        rows = master_doc.get("master", {}).get("tasks") if isinstance(master_doc, dict) and isinstance(master_doc.get("master"), dict) else None
        raw_rows = {"master": rows, "back": documents["back"], "gameplay": documents["gameplay"]}
        indexes: dict[str, dict[int, tuple[int, dict]]] = {name: {} for name in TRIPLET}
        for name, data in raw_rows.items():
            path = TRIPLET[name]
            if not isinstance(data, list):
                self.diagnostic("invalid-task-container", path, "Expected a task array at the original contract location")
                continue
            business_ids = set()
            for index, row in enumerate(data):
                pointer = ("/master/tasks/" if name == "master" else "/") + str(index)
                loc = path + "#" + pointer
                if not isinstance(row, dict):
                    self.diagnostic("invalid-task-row", loc, "Task must be an object")
                    continue
                own_id, mid = row.get("id"), row.get("id" if name == "master" else "taskmaster_id")
                if name != "master":
                    if not isinstance(own_id, str) or not own_id.strip() or own_id != own_id.strip() or own_id in business_ids:
                        self.diagnostic("invalid-view-id", loc + "/id", "Business ID must be a nonempty unique original string")
                    if isinstance(own_id, str):
                        business_ids.add(own_id)
                if type(mid) is not int or mid < 1 or mid in indexes[name]:
                    self.diagnostic("invalid-master-join-id", loc, "Master ID/taskmaster_id must be a unique positive integer within its view")
                else:
                    indexes[name][mid] = index, row
                allowed = MASTER_STATES if name == "master" else VIEW_STATES
                if not isinstance(row.get("status"), str) or row["status"] not in allowed:
                    self.diagnostic("invalid-task-status", loc + "/status", "Missing or invalid original status string")
                for field in ("source_refs", "test_refs", "evidence_refs"):
                    if field not in row:
                        continue
                    if not isinstance(row[field], list):
                        self.diagnostic("invalid-reference-container", loc + "/" + field, "Expected an original reference array")
                        continue
                    for ref_index, value in enumerate(row[field]):
                        self.reference(path, f"{pointer}/{field}/{ref_index}", own_id, mid, field, value)
        differences = []
        for name in ("back", "gameplay"):
            for mid, (index, row) in indexes[name].items():
                if mid not in indexes["master"]:
                    self.diagnostic("orphan-view-join", TRIPLET[name] + f"#/{index}/taskmaster_id", f"No master task {mid}")
                    continue
                mi, master = indexes["master"][mid]
                if row.get("status") != master.get("status"):
                    differences.append({"master_id": mid, "view": name, "view_id": row.get("id"),
                                        "master_status": master.get("status"), "view_status": row.get("status"),
                                        "master_pointer": f"/master/tasks/{mi}/status", "view_pointer": f"/{index}/status",
                                        "authority": TRIPLET["master"], "action": "report-only"})
        for mid, (index, _) in indexes["master"].items():
            if mid not in indexes["back"] and mid not in indexes["gameplay"]:
                self.diagnostic("missing-business-mapping", TRIPLET["master"] + f"#/master/tasks/{index}",
                                f"Master task {mid} requires at least one mapped business view")
        return {"documents": documents, "status_authority": TRIPLET["master"], "status_differences": differences,
                "counts": {name: len(value) if isinstance(value, list) else None for name, value in raw_rows.items()}}

    def source_set(self) -> dict:
        """Native source declaration, path, resolver and member checks."""
        source_set = self.json(SOURCE_SET, "source-set")
        active_sources = []
        try:
            if not isinstance(source_set, dict) or source_set.get("schema_version") != "chapter3.source-set.v1":
                raise ValueError("Unsupported source-set schema")
            patterns = source_set.get("active_patterns")
            declared = source_set.get("active_sources")
            if not isinstance(patterns, list) or not patterns or not isinstance(declared, list):
                raise ValueError("Source-set requires active_patterns and active_sources arrays")
            for pattern in patterns:
                safe_source_pattern(self.root, pattern)
            for value in declared:
                canonical_path(value)
                self.read(value, "declared-active-source")
            paths, missing = (resolve_sources(self.root, patterns, explicit=True) if not self.virtual_files else
                resolve_sources(self.root, patterns, explicit=True, virtual_files=self.virtual_files))
            for pattern in missing:
                self.diagnostic("missing-source-pattern", SOURCE_SET, pattern)
            for path in paths:
                value = path.relative_to(self.root).as_posix()
                self.read(value, "resolved-active-source")
                active_sources.append(value)
            if sorted(declared) != sorted(active_sources):
                self.diagnostic("source-set-mismatch", SOURCE_SET, "Declared active_sources differ from resolved active_patterns")
            for retirement in source_set.get("retirements", []):
                canonical_path(retirement["path"])
                self.read(retirement["path"], "historical-retired-source", required=False)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.diagnostic("invalid-source-set", SOURCE_SET, str(exc))

        return {"path": SOURCE_SET, "document": source_set, "resolved_active_sources": active_sources}

    def manifests(self, paths, *, requirement=None) -> list[dict]:
        """Native manifest rules and required/planned reference observations."""
        manifests = []
        for path in paths:
            doc = self.json(path, "cumulative-manifest")
            if not isinstance(doc, dict):
                self.diagnostic("invalid-manifest", path, "Manifest must be an object")
                continue
            try:
                errors = (validate_manifest(self.root, doc, executable=False) if self.read_bytes is None else
                    validate_manifest(self.root, doc, executable=False, read_bytes=self.read_bytes))
                for error in errors:
                    self.diagnostic("invalid-manifest", path, error)
                for index, test in enumerate(doc.get("tests", [])):
                    self.reference(path, f"/tests/{index}/path", test.get("id"), None, "manifest-test", test["path"],
                                   required=test.get("state") != "planned")
                for index, flow in enumerate(doc.get("flows", [])):
                    for si, source in enumerate(flow.get("source_paths", [])):
                        self.reference(path, f"/flows/{index}/source_paths/{si}", flow.get("id"), None, "manifest-source", source)
                    for hi, edge in enumerate(flow.get("handoffs", [])):
                        self.reference(path, f"/flows/{index}/handoffs/{hi}/contract_ref", flow.get("id"), None,
                                       "manifest-contract", edge["contract_ref"])
                manifests.append({"path": path, "document": doc, "static_validation_errors": errors,
                                  "execution_claim": "not-run; static inventory is not runtime evidence"})
            except (KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
                self.diagnostic("invalid-manifest", path, str(exc))
        if not manifests and (requirement or {}).get("state") != "initially_absent":
            self.diagnostic("missing-manifests", "docs/testing/mvg", "No cumulative manifest could be inventoried")
        return manifests

    def _canonical_inputs(self) -> dict:
        raw = self.read(self.epics, "epics")
        header = {}
        try:
            header = frontmatter(raw) if raw is not None else {}
            if header.get("status") != "final":
                raise ValueError("Epics frontmatter status must be final")
            sources = header.get("inputDocuments")
            if not isinstance(sources, list) or len(sources) != 10:
                raise ValueError("Epics must declare exactly ten canonical inputDocuments")
            identities = set()
            for path in sources:
                canonical_path(path)
                folded = path.casefold()
                if folded in identities:
                    raise ValueError("Canonical inputDocuments must identify ten distinct files")
                identities.add(folded)
                if Path(path).suffix.lower() not in SUPPORTED_SUFFIXES:
                    raise ValueError(f"Unsupported canonical source format: {path}")
                source = self.read(path, "canonical-source")
                if source is not None:
                    source.decode("utf-8-sig")
                    if Path(path).suffix.lower() == ".json":
                        strict_json(source)
            for key in ("codeBaselineCommit", "inputSnapshotCommit"):
                value = header.get(key)
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40,64}", value):
                    raise ValueError(f"Missing or invalid declared {key}")
                resolved = git(self.root, "rev-parse", "--verify", value + "^{commit}", optional=True).decode().strip()
                if resolved != value:
                    self.diagnostic("unresolved-declared-commit", self.epics, f"Cannot verify {key}: {value}")
        except (ValueError, UnicodeError, TypeError) as exc:
            self.diagnostic("invalid-epics", self.epics, str(exc))

        return header

    def collect(self) -> dict:
        header = self._canonical_inputs()
        if self.historical_inventory is not None:
            self.read(self.historical_inventory, "historical-inventory", required=False, evidence=True)
        discovered = self.discover()
        for prefix in ("docs/adr/", "docs/architecture/base/", "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/", "Game.Core/Contracts/"):
            if not any(path.startswith(prefix) for _, path in discovered):
                self.diagnostic("missing-authority-set", prefix, "Required authority discovery set is empty")
        for category, responsibility, difference, epic, entries in GROUPS:
            for path, symbol in entries:
                self.consumer(category, path, symbol, responsibility, difference, epic)
        for role, path in discovered:
            if role in {"skill", "example", "capability-skill", "mvg-skill"}:
                category = "capability-mvg" if role in {"capability-skill", "mvg-skill"} else "cli-skill-routing-examples"
                if role == "example":
                    responsibility = "Read-only example of Task/document schema; template data is not current Task authority."
                    difference = "Align examples with governed B bindings without changing current task records."
                elif role in {"capability-skill", "mvg-skill"}:
                    responsibility = "Skill reads planning authorities and routes Capability/MVG producer commands that write planning and adoption records."
                    difference = "Replace Task-dependent planning prerequisites with governed Task-independent adoption."
                else:
                    responsibility = "Skill reads workflow authorities and routes Chapter3-7 commands; invoked producers can write their workflow artifacts."
                    difference = "Align stage bindings and shared B gates while retaining current entrypoints until governed migration."
                self.consumer(category, path, None, responsibility, difference, "Epic2/Epic4/Epic5")
        for needed in (".agents/skills/plan-capabilities/SKILL.md", ".agents/skills/plan-mvg/SKILL.md"):
            self.read(needed, "required-planning-skill")
        for needed in REQUIRED_CHAPTER_SKILLS:
            self.read(needed, "required-chapter-skill")
        for needed in ("docs/architecture/ADR_INDEX_GODOT.md", "DELIVERY_PROFILE.md",
                       "docs/workflows/run-protocol.md", "docs/workflows/local-hard-checks.md"):
            self.read(needed, "authority")
        adrs = []
        for role, path in discovered:
            if path.startswith("docs/adr/ADR-"):
                raw = self.cache[path]
                try:
                    text = raw.decode("utf-8-sig") if raw is not None else ""
                    declarations = []
                    for number, line in markdown_status_lines(text):
                        match = re.match(r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:status|状态)(?:\*\*)?\s*[:：]\s*(.+?)\s*$", line, re.I)
                        if match:
                            status_text = match[1].strip("* ").casefold()
                            token = re.fullmatch(r"(accepted|proposed|superseded|deprecated|rejected)(?:\s*[（(][^）)]*[）)])?", status_text)
                            declarations.append({"line": number, "raw_status": match[1],
                                                 "status": token[1] if token else status_text})
                    states = {item["status"] for item in declarations}
                    known = {"accepted", "proposed", "superseded", "deprecated", "rejected"}
                    state = next(iter(states)) if len(states) == 1 and states <= known else "unknown"
                    if state == "unknown":
                        self.diagnostic("unknown-adr-status", path, "ADR body status is missing, unrecognized or conflicting")
                    adrs.append({"path": path, "status": state, "body_declarations": declarations})
                except UnicodeError as exc:
                    self.diagnostic("invalid-adr-text", path, str(exc))

        source_set_summary = self.source_set()
        tasks = self.tasks()
        from _b_route_initial_legacy import observe
        manifest_paths = [path for role,path in discovered if role == "manifest"]
        requirement = observe(self, tasks, manifest_paths, header)
        if requirement["state"] == "unknown":
            self.diagnostic("legacy-manifest-requirement-unknown", "docs/testing/mvg", requirement["reason"])
        manifests = self.manifests(manifest_paths, requirement=requirement)
        rules = rule_identity()
        git_end = git_identity(self.root)
        if self.git_start != git_end:
            self.diagnostic("git-drift-within-pass", "git", "Git identity changed during collection; recollect")
        git_report = {key: value for key, value in self.git_start.items() if key != "blobs"}
        for row in self.inputs.values():
            row["roles"].sort()
        return {"schema_version": SCHEMA, "git": git_report, "declared_code_baseline": header.get("codeBaselineCommit"),
                "declared_input_snapshot": header.get("inputSnapshotCommit"), "epics": self.epics,
                "canonical_inputs": header.get("inputDocuments"), "discovery": discovered,
                "inputs": [self.inputs[key] for key in sorted(self.inputs)], "rules": rules,
                "source_set": source_set_summary, "historical_inventory_ref": self.historical_inventory,
                "tasks": tasks, "task_and_manifest_references": self.references, "adrs": adrs,
                "manifests": manifests, "legacy_manifest_requirement": requirement,
                "consumers": self.consumers, "diagnostics": self.diagnostics}


def collect_inventory(root: Path, epics: str, *, between_passes: Callable[[], None] | None = None,
                      historical_inventory: str | None = None) -> dict:
    require_runtime()
    root = root.absolute()
    safe_input(root, epics)
    first = Snapshot(root, epics, historical_inventory=historical_inventory).collect()
    if between_passes is not None:
        between_passes()
    second = Snapshot(root, epics, historical_inventory=historical_inventory).collect()
    first_sha, second_sha = canonical_sha(first), canonical_sha(second)
    stable = first_sha == second_sha and not any(d["code"] == "git-drift-within-pass" for d in first["diagnostics"] + second["diagnostics"])
    diagnostics = list(first["diagnostics"])
    for diagnostic in second["diagnostics"]:
        if diagnostic not in diagnostics:
            diagnostics.append(diagnostic)
    first_inputs = {row["path"]: row for row in first["inputs"]}
    second_inputs = {row["path"]: row for row in second["inputs"]}
    drift = {"added_inputs": sorted(second_inputs.keys() - first_inputs.keys()),
             "removed_inputs": sorted(first_inputs.keys() - second_inputs.keys()),
             "changed_inputs": sorted(path for path in first_inputs.keys() & second_inputs.keys()
                                      if first_inputs[path] != second_inputs[path]),
             "git_changed": first["git"] != second["git"], "rules_changed": first["rules"] != second["rules"]}
    if not stable:
        diagnostics.append({"code": "unstable-inputs", "location": "collection", "severity": "error",
                            "message": "Input set, raw bytes, derived closure or Git identity changed; recollect. " + json.dumps(drift, ensure_ascii=False)})
    first.update(content_identity=first_sha, second_pass_identity=second_sha, drift=drift,
                 collection={"event_id": str(uuid.uuid4()), "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                             "root_real": str(root.resolve())},
                 stable=stable, adoptable=stable and not any(d["severity"] == "error" for d in diagnostics),
                 status="unstable" if not stable else ("invalid" if any(d["severity"] == "error" for d in diagnostics) else "stable"),
                 diagnostics=diagnostics,
                 verification_limits=["No lock against external concurrent writers; double-read observation only.",
                                      "Consumer checklist verifies locations, not semantic completeness.",
                                      "Historical debug attachments retain missing/unknown observations, never runtime proof or operation prerequisites.",
                                      "Formal protection baseline belongs to Story 1.5; default route is unchanged."])
    return first


def markdown(report: dict) -> str:
    def cell(value: Any) -> str:
        return html.escape(str(value)).replace("|", "\\|").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    lines = ["# B route baseline inventory", "", f"Status: {report['status']}; adoptable: {report['adoptable']}",
             f"Content identity: {report['content_identity']}", f"Collection event: {report['collection']['event_id']}",
             f"HEAD: {report['git']['head']}", f"Branch: {report['git']['branch']}",
             f"Declared code baseline: {report['declared_code_baseline']}",
             f"Declared input snapshot: {report['declared_input_snapshot']}", "", "## Worktree changes", "",
             "| Status | Path | Original path (rename/copy) |", "| --- | --- | --- |"]
    for row in report["git"]["changes"]:
        lines.append("| " + " | ".join(cell(x) for x in (row["status"], row["path"], row.get("original_path", ""))) + " |")
    lines += ["", "## Inputs", "",
             "| File | Raw SHA256 | HEAD blob | Roles |", "| --- | --- | --- | --- |"]
    for row in report["inputs"]:
        lines.append("| " + " | ".join(cell(x) for x in (row["path"], row["raw_sha256"],
                     (row["head_blob"] or {}).get("oid"), ", ".join(row["roles"]))) + " |")
    lines += ["", "## Consumer matrix", "", "| Category | File / symbol | Read/write responsibility | Current A / target B | Follow-up |",
              "| --- | --- | --- | --- | --- |"]
    for row in report["consumers"]:
        lines.append("| " + " | ".join(cell(row[key]) for key in
                     ("category", "locator", "responsibility", "current_a_to_target_b", "followup_epic")) + " |")
    lines += ["", "## Task status differences (master authority; report only)", "",
              "| Master | View / ID | Master status | View status | Master pointer | View pointer |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in report["tasks"]["status_differences"]:
        lines.append("| " + " | ".join(cell(x) for x in (row["master_id"], f"{row['view']} / {row['view_id']}",
                     row["master_status"], row["view_status"], row["master_pointer"], row["view_pointer"])) + " |")
    lines += ["", "## Reference closure", "", "| Owner / pointer | Original reference | Role / required | State | Raw SHA256 / reason |",
              "| --- | --- | --- | --- | --- |"]
    for row in report["task_and_manifest_references"]:
        lines.append("| " + " | ".join(cell(x) for x in (row["owner_file"] + "#" + row["json_pointer"],
                     row["raw_reference"], f"{row['reference_role']} / {row['required']}", row["state"],
                     row.get("raw_sha256") or row.get("reason", ""))) + " |")
    lines += ["", "## ADR body status", ""]
    lines += [f"- {cell(row['path'])}: {row['status']}" for row in report["adrs"]]
    lines += ["", "## Cumulative manifests", ""]
    lines += [f"- {cell(row['path'])}: {row['execution_claim']}" for row in report["manifests"]]
    lines += ["", "## Diagnostics", ""]
    lines += [f"- {row['severity']}: {row['code']} at {cell(row['location'])}: {cell(row['message'])}" for row in report["diagnostics"]]
    lines += ["", "## Verification limits", ""] + ["- " + x for x in report["verification_limits"]]
    return "\n".join(lines) + "\n"


def create_run_directory(root: Path, run_id: str) -> Path:
    require_runtime()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id):
        raise ValueError("run-id must contain 1-96 ASCII letters, digits, hyphens or underscores")
    canonical_path(run_id)
    root = root.absolute()
    no_reparse(root)
    relative = "logs/ci/" + dt.datetime.now(dt.timezone.utc).date().isoformat() + "/b-route-baseline-inventory/" + run_id
    target = safe_input(root, relative, allow_logs=True)
    # Create one component at a time and recheck attributes after each creation.
    current = root
    for component in relative.split("/")[:-1]:
        current /= component
        current.mkdir(exist_ok=True)
        no_reparse(current)
    target.mkdir(exist_ok=False)
    no_reparse(target)
    return target
