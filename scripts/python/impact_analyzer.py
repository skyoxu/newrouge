#!/usr/bin/env python3
"""Deterministic, bounded v1 impact analyzer built on Impact Index Core."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from impact_analysis_handoff import EXIT_CODES
    from impact_analysis_index import (
        FULL_SHA,
        ImpactIndexError,
        GitTreeSnapshot,
        artifact_json_bytes,
        normalize_repository_path,
        validate_index_bytes,
        validate_manifest_bytes,
        validate_aliases,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.python.impact_analysis_handoff import EXIT_CODES
    from scripts.python.impact_analysis_index import (
        FULL_SHA,
        ImpactIndexError,
        GitTreeSnapshot,
        artifact_json_bytes,
        normalize_repository_path,
        validate_index_bytes,
        validate_manifest_bytes,
        validate_aliases,
    )


REPORT_SCHEMA = "newrouge.impact-analysis.v1"
ANALYZER_IMPLEMENTATION_REVISION = "newrouge.impact-analyzer.v1"
RISK_POLICY_REVISION = "newrouge.impact-risk.v1"
RELATIONS = {"references", "implements", "inherits", "consumes", "binds", "tests", "documents"}
TARGET_KINDS = {
    "file", "scene", "resource", "class", "interface", "method", "event", "contract",
    "system", "symbol", "signal", "node", "test_file", "test_symbol", "task", "acceptance", "adr", "decision",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _line_anchor(text: str, start: int, end: int | None = None) -> str:
    return f"line:{start}-{end or start}"


def _safe_rel(root: Path, value: str) -> Path:
    try:
        normalized = normalize_repository_path(value)
        candidate = (root / Path(*normalized.split("/"))).resolve()
        candidate.relative_to(root.resolve())
        return candidate
    except Exception as exc:
        raise ImpactIndexError("path_outside_repository", f"invalid repository-relative path: {value}") from exc


@dataclass(frozen=True)
class Symbol:
    kind: str
    identity: str
    path: str
    line: int
    declaration: str


@dataclass(frozen=True)
class ResolvedTarget:
    kind: str
    identity: str
    canonical_path: str
    source_sha256: str
    resolution_method: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "identity": self.identity,
            "canonical_path": self.canonical_path,
            "source_sha256": self.source_sha256,
            "resolution_method": self.resolution_method,
        }


class SymbolIndex:
    """Restricted textual C# symbol view; intentionally not a compiler or call graph."""

    TYPE_RE = re.compile(r"\b(class|interface|struct|record)\s+([A-Za-z_]\w*)(?:\s*<([^>]+)>)?\s*(?::\s*([^\{]+))?", re.MULTILINE)
    EVENT_RE = re.compile(r"\bevent\s+[\w.<>,?\[\]]+\s+([A-Za-z_]\w*)")
    METHOD_RE = re.compile(r"^\s*(?:public|private|protected|internal|static|virtual|override|async|sealed|partial|new|unsafe|extern|\s)+[\w.<>,?\[\]]+\s+([A-Za-z_]\w*)\s*(?:<([^>]+)>)?\s*\(([^)]*)\)", re.MULTILINE)
    USING_RE = re.compile(r"^\s*using\s+(?:static\s+)?([A-Za-z_][\w.]*)\s*;", re.MULTILINE)
    NAMESPACE_RE = re.compile(r"\bnamespace\s+([A-Za-z_][\w.]*)\s*[;{]")

    def __init__(self, sources: dict[str, str], hashes: dict[str, str]):
        self.sources = sources
        self.hashes = hashes
        self.symbols: list[Symbol] = []
        self.usings: dict[str, list[tuple[str, int]]] = {}
        self.types_by_path: dict[str, list[Symbol]] = {}
        for path, text in sorted(sources.items()):
            self._parse(path, text)

    @staticmethod
    def _namespace(text: str, match_end: int) -> str:
        matches = list(SymbolIndex.NAMESPACE_RE.finditer(text[:match_end]))
        return matches[-1].group(1) if matches else ""

    def _parse(self, path: str, text: str) -> None:
        self.usings[path] = [(m.group(1), text.count("\n", 0, m.start()) + 1) for m in self.USING_RE.finditer(text)]
        for m in self.TYPE_RE.finditer(text):
            name, generic, bases = m.group(2), m.group(3), m.group(4)
            ns = self._namespace(text, m.start())
            arity = 0 if not generic else len([x for x in generic.split(",") if x.strip()])
            identity = f"{ns + '.' if ns else ''}{name}" + (f"`{arity}" if arity else "")
            kind = "interface" if m.group(1) == "interface" else "class"
            normalized_path = path.replace("\\", "/")
            if kind != "interface" and (normalized_path.startswith("Game.Core/Contracts/") or name.endswith("Event")):
                # Event records are a distinct target kind; remaining contract declarations
                # under Contracts are treated as contract symbols.
                kind = "event" if name.endswith("Event") else "contract"
            symbol = Symbol(kind, identity, path, text.count("\n", 0, m.start()) + 1, m.group(0).strip())
            self.symbols.append(symbol)
            self.types_by_path.setdefault(path, []).append(symbol)
            if bases:
                for base in [b.strip() for b in bases.split(",") if b.strip()]:
                    base_name = re.sub(r"\s+", "", base)
                    self.symbols.append(Symbol("__base__", f"{identity}|{base_name}", path, symbol.line, base_name))
        for m in self.EVENT_RE.finditer(text):
            ns = self._namespace(text, m.start())
            identity = f"{ns + '.' if ns else ''}{m.group(1)}"
            self.symbols.append(Symbol("event", identity, path, text.count("\n", 0, m.start()) + 1, m.group(0).strip()))
        for m in self.METHOD_RE.finditer(text):
            ns = self._namespace(text, m.start())
            owner = self._owner_for_line(path, text.count("\n", 0, m.start()) + 1)
            if owner:
                generic = m.group(2)
                arity = 0 if not generic else len([x for x in generic.split(",") if x.strip()])
                params = self._normalize_params(m.group(3))
                identity = f"{owner.identity}::{m.group(1)}" + (f"`{arity}" if arity else "") + f"({','.join(params)})"
                self.symbols.append(Symbol("method", identity, path, text.count("\n", 0, m.start()) + 1, m.group(0).strip()))

    def _owner_for_line(self, path: str, line: int) -> Symbol | None:
        candidates = [s for s in self.types_by_path.get(path, []) if s.line <= line]
        return candidates[-1] if candidates else None

    @staticmethod
    def _normalize_params(raw: str) -> list[str]:
        if not raw.strip():
            return []
        aliases = {"string": "System.String", "int": "System.Int32", "bool": "System.Boolean", "object": "System.Object", "long": "System.Int64", "double": "System.Double", "float": "System.Single", "decimal": "System.Decimal", "void": "System.Void"}
        result = []
        for item in raw.split(","):
            item = item.strip()
            item = re.sub(r"\b(ref|out|in|params)\s+", "", item)
            parts = item.split()
            typ = parts[0] if parts else item
            typ = aliases.get(typ, typ)
            if "?" in typ:
                typ = typ.replace("?", "")
                typ = f"System.Nullable`1<{typ}>"
            result.append(typ + ("&" if re.search(r"\b(ref|out|in)\b", item) else ""))
        return result

    def find(self, kind: str, identity: str) -> list[Symbol]:
        return [s for s in self.symbols if s.kind == kind and s.identity == identity]


class TargetResolver:
    def __init__(self, index_document: dict[str, Any], sources: dict[str, str], hashes: dict[str, str], aliases: dict[str, Any] | None = None):
        self.index = index_document
        self.sources = sources
        self.hashes = hashes
        self.aliases = aliases or {"aliases": {"event": {}, "contract": {}}}
        try:
            validate_aliases(self.aliases)
        except Exception as exc:
            raise ImpactIndexError("invalid_manifest", f"invalid target alias table: {exc}") from exc
        self.symbol_index = SymbolIndex(sources, hashes)

    def resolve(self, target: dict[str, Any] | str) -> ResolvedTarget:
        if isinstance(target, str):
            try:
                target = json.loads(target)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ImpactIndexError("unsupported_target", "target must be valid JSON") from exc
        if not isinstance(target, dict) or set(target) != {"type", "id"}:
            raise ImpactIndexError("unsupported_target", "target must be an object with type and id")
        kind = str(target.get("type") or "").strip().lower()
        ident = str(target.get("id") or "").strip()
        if kind not in TARGET_KINDS or not ident:
            raise ImpactIndexError("unsupported_target", "unsupported or empty target kind/id")
        if kind in {"file", "scene", "resource", "task", "adr", "decision", "acceptance"}:
            path = normalize_repository_path(ident)
            if path not in self.hashes:
                raise ImpactIndexError("target_not_found", f"target path not found: {path}")
            return ResolvedTarget(kind, path, path, self.hashes[path], "exact-path")
        if kind == "method":
            # Namespace.Type::Method(Signature) is mandatory; basename lookup is unsafe.
            if "::" not in ident or "(" not in ident or not ident.endswith(")") or "." not in ident.split("::", 1)[0]:
                raise ImpactIndexError("underqualified_target", "method target requires namespace, declaring type, name and signature")
        lookup = ident
        aliases = self.aliases.get("aliases", {}).get(kind, {}) if isinstance(self.aliases, dict) else {}
        lookup = aliases.get(lookup, lookup)
        candidates = [s for s in self.symbol_index.symbols if s.kind == kind and s.identity == lookup]
        if not candidates and kind in {"event", "contract"} and "." not in lookup:
            raise ImpactIndexError("underqualified_target", "event/contract target requires a qualified identity")
        if not candidates:
            raise ImpactIndexError("target_not_found", f"target symbol not found: {ident}")
        if len(candidates) > 1:
            raise ImpactIndexError("ambiguous_target", f"target resolves to multiple symbols: {ident}")
        item = candidates[0]
        return ResolvedTarget(kind, item.identity, item.path, self.hashes[item.path], "exact-index-symbol")


def _edge(from_kind: str, from_id: str, to_kind: str, to_id: str, relation: str, path: str, anchor: str, digest: str) -> dict[str, str]:
    if relation not in RELATIONS:
        raise ImpactIndexError("unsupported_relation", relation)
    if not re.fullmatch(r"(?:line:\d+-\d+|symbol:[^\s]+|json-pointer:/.*|markdown:[^#]+#[^\s]+)", anchor):
        raise ImpactIndexError("source_read_failure", f"invalid evidence anchor: {anchor}")
    allowed = {
        "references": ({"file", "symbol", "class", "interface", "method"}, {"file", "symbol", "class", "interface", "method"}),
        "implements": ({"class", "interface", "symbol"}, {"interface", "contract", "symbol"}),
        "inherits": ({"class", "interface", "symbol"}, {"class", "interface", "symbol"}),
        "consumes": ({"class", "symbol", "system", "file"}, {"event", "contract", "symbol"}),
        "binds": ({"scene", "node", "script", "resource", "symbol"}, {"node", "script", "signal", "resource", "symbol", "event", "contract"}),
        "tests": ({"test_file", "test_symbol"}, {"file", "symbol", "task", "acceptance", "event", "contract", "class"}),
        "documents": ({"adr", "task", "contract", "decision"}, set(TARGET_KINDS)),
    }
    frm, to = allowed[relation]
    if from_kind not in frm or to_kind not in to:
        raise ImpactIndexError("unsupported_relation", f"invalid endpoint kinds for {relation}: {from_kind}->{to_kind}")
    return {"from": from_id, "from_kind": from_kind, "to": to_id, "to_kind": to_kind, "relation": relation, "evidence_path": path, "evidence_anchor": anchor, "evidence_sha256": digest}


def _sort_edges(edges: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {(e["from_kind"], e["from"], e["to_kind"], e["to"], e["relation"], e["evidence_path"], e["evidence_anchor"]): e for e in edges}
    return [unique[k] for k in sorted(unique)]


def classify_risk(target: ResolvedTarget, edges: list[dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    path = target.canonical_path.lower()
    matched: list[str] = []
    reasons: list[str] = []
    if target.kind in {"event", "contract"} or "/contracts/" in path:
        matched.append("event-target" if target.kind == "event" else "contract-target"); reasons.append(f"{target.kind} target")
        return "high", matched, reasons
    if "save" in path or target.kind in {"system"}:
        matched.append("save-format-target" if "save" in path else "system-target"); reasons.append("save/core system target" if "save" in path else "system target")
        return "medium", matched, reasons
    if "/services/" in path or target.kind == "class" and any("Service" in str(e.get("from")) for e in edges):
        matched.append("service-target"); reasons.append("service target"); return "medium", matched, reasons
    if path.startswith("game.godot/") or path.startswith("game.ui/") or "/ui/" in path or "/ui" in path:
        matched.append("ui-only-target"); reasons.append("UI-only target"); return "low", matched, reasons
    matched.append("insufficient-evidence"); reasons.append("insufficient deterministic evidence"); return "unknown", matched, reasons


class ImpactAnalyzer:
    def __init__(self, repository_root: Path, index_path: Path, revision: str, trusted_ref: str | None = None):
        self.root = repository_root.resolve(); self.revision = revision.lower(); self.trusted_ref = trusted_ref
        try:
            self.index_path = index_path.resolve(); index_bytes = self.index_path.read_bytes()
        except OSError as exc:
            raise ImpactIndexError("missing_index", f"unable to read impact index: {exc}") from exc
        self.index_sha256 = _sha(index_bytes); self.index = validate_index_bytes(index_bytes)
        if self.index["repository_revision"] != self.revision:
            raise ImpactIndexError("revision_mismatch", "index revision differs from requested revision")
        manifest_path = self.index_path.with_name("index-manifest.v1.json")
        if not manifest_path.is_file():
            raise ImpactIndexError("missing_index", "index manifest is missing")
        manifest_bytes = manifest_path.read_bytes(); manifest = validate_manifest_bytes(manifest_bytes, index_bytes=index_bytes, expected_index=self.index)
        if trusted_ref and manifest.get("trusted_ref") != trusted_ref:
            raise ImpactIndexError("revision_mismatch", "trusted ref differs from index manifest")
        self.manifest = manifest
        self.sources: dict[str, str] = {}; self.hashes: dict[str, str] = {}
        snapshot = GitTreeSnapshot(self.root, self.revision, trusted_ref)
        snapshot.verify_worktree(self.index["source_manifest"])
        tree_entries = {entry.path: entry for entry in snapshot.entries}
        for entry in self.index["source_manifest"]:
            if not entry.get("included"): continue
            path = entry["path"]
            try:
                data = snapshot.read_blob(tree_entries[path])
            except Exception as exc: raise ImpactIndexError("source_read_failure", f"unable to read source: {path}") from exc
            digest = _sha(data)
            if digest != entry["sha256"]: raise ImpactIndexError("stale_index", f"source hash differs: {path}")
            self.hashes[path] = digest
            if entry.get("parser_family") != "binary-hash":
                try: self.sources[path] = data.decode("utf-8")
                except UnicodeDecodeError as exc: raise ImpactIndexError("source_read_failure", f"source is not UTF-8: {path}") from exc
        alias_path = self.root / "scripts/python/impact_target_aliases.v1.json"
        try:
            alias_bytes = alias_path.read_bytes()
            aliases = json.loads(alias_bytes.decode("utf-8"))
            validate_aliases(aliases)
            if _sha(alias_bytes) != self.index.get("alias_table_sha256"):
                raise ValueError("alias table hash differs from index")
            if aliases.get("alias_table_revision") != self.index.get("alias_table_revision"):
                raise ValueError("alias table revision differs from index")
        except Exception as exc:
            raise ImpactIndexError("invalid_manifest", f"invalid alias table: {exc}") from exc
        self.resolver = TargetResolver(self.index, self.sources, self.hashes, aliases)

    def analyze(self, target_input: dict[str, Any] | str, knowledge_binding: dict[str, Any] | None = None, frozen_context: str | None = None, consumer: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        target = self.resolver.resolve(target_input)
        edges: list[dict[str, Any]] = []
        tests: list[dict[str, Any]] = []
        target_simple = target.identity.rsplit(".", 1)[-1].split("`", 1)[0]
        for path, text in sorted(self.sources.items()):
            if not path.lower().endswith(".cs"): continue
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                if path == target.canonical_path: continue
                token_match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(target_simple)}(?![A-Za-z0-9_])", line)
                if not token_match and target.identity not in line and target.canonical_path not in line: continue
                digest = self.hashes[path]; anchor = _line_anchor(text, i)
                from_kind = "test_file" if (".Tests/" in path or path.startswith("Tests.") or path.startswith("Tests/")) else "file"
                from_id = path
                if from_kind == "test_file" and re.search(r"Refs\s*:", line, re.I):
                    relation = "tests"
                elif target.kind in {"event", "contract"} and re.search(rf"(?:new\s+|[<(]\s*|:\s*){re.escape(target_simple)}\b", line):
                    relation = "consumes"
                else:
                    relation = "references"
                    if target.kind in {"event", "contract"}:
                        continue
                to_kind = target.kind
                edge = _edge(from_kind, from_id, to_kind, target.identity, relation, path, anchor, digest)
                edges.append(edge)
                if relation == "tests": tests.append({"path": path, "target": target.identity, "evidence_path": path, "evidence_anchor": anchor, "evidence_sha256": digest})
            if target.kind in {"class", "interface", "contract"}:
                for sym in self.resolver.symbol_index.types_by_path.get(path, []):
                    if sym.identity == target.identity: continue
                    for base in [s for s in self.resolver.symbol_index.symbols if s.kind == "__base__" and s.path == path and s.identity.startswith(sym.identity + "|")]:
                        base_name = base.declaration
                        if base_name == target_simple or base_name == target.identity or base_name.rsplit(".", 1)[-1] == target_simple:
                            rel = "implements" if target.kind in {"interface", "contract"} else "inherits"
                            source_kind = "class" if sym.kind == "contract" else sym.kind
                            edges.append(_edge(source_kind, sym.identity, target.kind, target.identity, rel, path, f"line:{sym.line}-{sym.line}", self.hashes[path]))
        for path, text in sorted(self.sources.items()):
            if not path.endswith(".tscn"): continue
            if target.canonical_path in text or Path(target.canonical_path).name in text:
                line = next((i for i, l in enumerate(text.splitlines(), 1) if target.canonical_path in l or Path(target.canonical_path).name in l), 1)
                edges.append(_edge("scene", path, target.kind, target.identity, "binds", path, _line_anchor(text, line), self.hashes[path]))
        for path, text in sorted(self.sources.items()):
            if not (path.startswith("docs/") or path.startswith(".taskmaster/") or path.startswith("decision-logs/") or path.startswith("execution-plans/")): continue
            if target_simple not in text and target.identity not in text and target.canonical_path not in text: continue
            kind = "adr" if path.startswith("docs/adr/") else ("task" if path.startswith(".taskmaster/") or path.startswith("execution-plans/") else "decision")
            anchor = _line_anchor(text, next((i for i, l in enumerate(text.splitlines(), 1) if target_simple in l), 1))
            edges.append(_edge(kind, path, target.kind, target.identity, "documents", path, anchor, self.hashes[path]))
        edges = _sort_edges(edges)
        risk, rules, reasons = classify_risk(target, edges)
        affected_files = sorted({target.canonical_path, *(e["evidence_path"] for e in edges)}, key=lambda x: x.encode("utf-8"))
        affected_symbols = sorted({target.identity, *(e["from"] for e in edges if e["from_kind"] in {"class", "interface", "symbol", "method"})}, key=lambda x: x.encode("utf-8"))
        report: dict[str, Any] = {
            "schema_version": REPORT_SCHEMA, "status": "ok", "repository_revision": self.revision,
            "trusted_ref": self.trusted_ref or self.manifest.get("trusted_ref", f"detached:{self.revision}"),
            "index_id": self.index["index_id"], "index_sha256": self.index_sha256,
            "analyzer_implementation_revision": ANALYZER_IMPLEMENTATION_REVISION,
            "analysis_config_revision": self.index["analysis_config_revision"],
            "toolchain": {"python": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}"},
            "target": target.as_dict(), "affected_files": affected_files, "affected_symbols": affected_symbols,
            "impact_edges": edges, "tests": sorted(tests, key=lambda x: (x["path"], x["evidence_anchor"])), "runtime_refs": [e for e in edges if e["relation"] == "binds"],
            "knowledge_refs": [e for e in edges if e["relation"] == "documents"], "risk_level": risk,
            "risk_policy_revision": RISK_POLICY_REVISION, "matched_risk_rules": rules, "risk_reasons": reasons,
            "generated_at": _utc(), "failure_reason": None,
        }
        validate_knowledge_binding(knowledge_binding, consumer=consumer, task_id=task_id)
        report["knowledge_binding"] = knowledge_binding
        validate_report_document(report)
        return report


def load_frozen_binding(root: Path, path: str, revision: str, consumer: str | None = None, task_id: str | None = None) -> dict[str, Any]:
    frozen_path = _safe_rel(root, path)
    try: data = frozen_path.read_bytes(); frozen = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise ImpactIndexError("invalid_kcp_binding", f"unable to read frozen context: {exc}") from exc
    if not isinstance(frozen, dict) or frozen.get("schema_version") != "newrouge.knowledge-frozen-context.v1" or frozen.get("freeze_state") != "frozen":
        raise ImpactIndexError("invalid_kcp_binding", "frozen context is not a valid frozen artifact")
    snap = frozen.get("snapshot") if isinstance(frozen.get("snapshot"), dict) else {}
    if str(snap.get("commit") or "").lower() != revision.lower(): raise ImpactIndexError("revision_mismatch", "frozen context revision differs")
    actual_consumer = consumer or str(frozen.get("consumer") or "")
    if actual_consumer not in {"chapter4", "chapter5", "chapter6", "review"}: raise ImpactIndexError("invalid_kcp_binding", "consumer binding is invalid")
    frozen_task = frozen.get("task_id")
    if consumer and consumer != frozen.get("consumer"): raise ImpactIndexError("invalid_kcp_binding", "consumer mismatch")
    if task_id is not None and task_id != frozen_task: raise ImpactIndexError("invalid_kcp_binding", "task mismatch")
    if actual_consumer in {"chapter4", "chapter5", "chapter6"}:
        task_id = task_id or frozen_task
        if not isinstance(task_id, str) or not task_id.strip(): raise ImpactIndexError("invalid_kcp_binding", "task binding is required")
    # Publication lineage must be explicit; context/source-bundle identifiers are
    # not interchangeable with the published catalog generation or byte hash.
    publication_sha = frozen.get("publication_sha256")
    publication_generation = frozen.get("publication_generation") or frozen.get("generation_id")
    binding = {
        "consumer": actual_consumer, "task_id": None if actual_consumer == "review" else task_id,
        "frozen_context_path": frozen_path.relative_to(root).as_posix(), "frozen_context_sha256": _sha(data),
        "decision_set_sha256": str(frozen.get("decision_set_sha256") or ""), "freeze_point": str(frozen.get("freeze_point") or ""),
        "publication_generation": str(publication_generation or ""), "publication_sha256": str(publication_sha or ""),
    }
    if not binding["decision_set_sha256"] or not binding["freeze_point"] or not binding["publication_generation"] or not binding["publication_sha256"]:
        raise ImpactIndexError("invalid_kcp_binding", "frozen context lineage fields are incomplete")
    return binding


def validate_knowledge_binding(binding: dict[str, Any] | None, *, consumer: str | None = None, task_id: str | None = None) -> None:
    if not isinstance(binding, dict):
        raise ImpactIndexError("invalid_kcp_binding", "successful report requires frozen-context knowledge binding")
    required = {"consumer", "task_id", "frozen_context_path", "frozen_context_sha256", "decision_set_sha256", "freeze_point", "publication_generation", "publication_sha256"}
    if set(binding) != required:
        raise ImpactIndexError("invalid_kcp_binding", "knowledge binding fields are invalid")
    actual = binding.get("consumer")
    if actual not in {"chapter4", "chapter5", "chapter6", "review"}:
        raise ImpactIndexError("invalid_kcp_binding", "consumer binding is invalid")
    if consumer and actual != consumer:
        raise ImpactIndexError("invalid_kcp_binding", "consumer binding mismatch")
    if actual == "review":
        if binding.get("task_id") is not None:
            raise ImpactIndexError("invalid_kcp_binding", "review task_id must be null")
    elif not isinstance(binding.get("task_id"), str) or not binding["task_id"].strip():
        raise ImpactIndexError("invalid_kcp_binding", "task binding is required")
    if task_id and binding.get("task_id") != task_id:
        raise ImpactIndexError("invalid_kcp_binding", "task binding mismatch")
    for key in required - {"consumer", "task_id"}:
        if not isinstance(binding.get(key), str) or not binding[key].strip():
            raise ImpactIndexError("invalid_kcp_binding", f"knowledge binding field missing: {key}")


def validate_report_document(report: dict[str, Any]) -> None:
    required = {"schema_version", "status", "repository_revision", "trusted_ref", "index_id", "index_sha256", "analyzer_implementation_revision", "analysis_config_revision", "toolchain", "target", "affected_files", "affected_symbols", "impact_edges", "tests", "runtime_refs", "knowledge_refs", "risk_level", "risk_policy_revision", "matched_risk_rules", "risk_reasons", "generated_at", "failure_reason", "knowledge_binding"}
    if set(report) != required or report.get("schema_version") != REPORT_SCHEMA or report.get("status") != "ok":
        raise ImpactIndexError("invalid_manifest", "impact report envelope is invalid")
    if report.get("risk_level") not in {"high", "medium", "low", "unknown"}:
        raise ImpactIndexError("invalid_manifest", "impact report risk level is invalid")
    if not isinstance(report.get("impact_edges"), list):
        raise ImpactIndexError("invalid_manifest", "impact report edges are invalid")
    expected = _sort_edges(report["impact_edges"])
    if report["impact_edges"] != expected:
        raise ImpactIndexError("invalid_manifest", "impact edges are not canonically ordered")
    validate_knowledge_binding(report["knowledge_binding"])


def atomic_write_json(path: Path, document: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True); data = artifact_json_bytes(document); digest = _sha(data)
    temp = path.parent / f".{path.name}.{uuid.uuid4()}.tmp"
    try:
        with temp.open("xb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return digest


def failure_report(target_input: Any, revision: str | None, reason: ImpactIndexError, index: dict[str, Any] | None = None, index_sha256: str | None = None) -> dict[str, Any]:
    report = {"schema_version": REPORT_SCHEMA, "status": reason.code, "repository_revision": revision or "", "target": target_input if isinstance(target_input, dict) else {"type": "", "id": str(target_input or "")}, "affected_files": [], "affected_symbols": [], "impact_edges": [], "tests": [], "runtime_refs": [], "knowledge_refs": [], "risk_level": "unknown", "risk_policy_revision": RISK_POLICY_REVISION, "matched_risk_rules": ["insufficient-evidence"], "risk_reasons": [reason.reason], "generated_at": _utc(), "failure_reason": {"code": reason.code, "reason": reason.reason}}
    if index: report.update({"index_id": index.get("index_id", ""), "index_sha256": index_sha256 or "", "analyzer_implementation_revision": ANALYZER_IMPLEMENTATION_REVISION, "analysis_config_revision": index.get("analysis_config_revision", "")})
    return report
