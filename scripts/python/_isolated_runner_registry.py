"""Central registry of official replayable Plane B isolated model runners."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

ROUTING_SCHEMA = "newrouge.llm-routing.v1"
ROUTING_REL_PATH = "docs/workflows/llm-routing.json"

CODEX_RUNNER_SCRIPT = "codex_isolated_model_runner.py"
GEMINI_RUNNER_SCRIPT = "gemini_isolated_model_runner.py"
OFFICIAL_RUNNER_SCRIPTS = (CODEX_RUNNER_SCRIPT, GEMINI_RUNNER_SCRIPT)

CODEX_PROTOCOL = "codex-app-server-stdio"
GEMINI_PROTOCOL = "gemini-cli-stream-json"

CODEX_EVIDENCE_POLICY = "official-codex-runtime-bound.v1"
GEMINI_EVIDENCE_POLICY = "official-gemini-cli-runtime-bound.v1"

CODEX_IDENTITY_SOURCE = "codex-app-server-runtime-configuration"
GEMINI_IDENTITY_SOURCE = "gemini-cli-runtime-configuration"

CODEX_STREAM_SUFFIXES = (".app-server.jsonl", ".app-server.stderr.txt")
GEMINI_STREAM_SUFFIXES = (".gemini-stream.jsonl", ".gemini-stream.stderr.txt")
ALL_STREAM_SUFFIXES = (*CODEX_STREAM_SUFFIXES, *GEMINI_STREAM_SUFFIXES)


@dataclass(frozen=True)
class IsolatedRunnerSpec:
    key: str
    script_name: str
    script_rel_path: str
    provider: str
    model: str
    protocol: str
    evidence_policy: str
    identity_source: str
    stream_suffixes: tuple[str, str]
    reasoning_effort: str
    system_instruction: str | None = None

    @property
    def model_identity(self) -> str:
        return f"{self.provider}/{self.model}"


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _validate_routing_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != ROUTING_SCHEMA:
        raise ValueError("llm_routing_schema_invalid")
    plane_b = payload.get("plane_b")
    plane_a = payload.get("plane_a")
    if not isinstance(plane_b, dict) or not isinstance(plane_b.get("runners"), dict):
        raise ValueError("llm_routing_plane_b_invalid")
    if not isinstance(plane_a, dict) or not isinstance(plane_a.get("backends"), dict):
        raise ValueError("llm_routing_plane_a_invalid")
    default_runner = plane_b.get("default_runner")
    if not isinstance(default_runner, str) or not default_runner.strip():
        raise ValueError("llm_routing_plane_b_default_runner_missing")
    for key, expected_script, expected_provider in (
        ("codex", f"scripts/python/{CODEX_RUNNER_SCRIPT}", "openai"),
        ("gemini", f"scripts/python/{GEMINI_RUNNER_SCRIPT}", "google"),
    ):
        entry = plane_b["runners"].get(key)
        if not isinstance(entry, dict):
            raise ValueError(f"llm_routing_runner_missing:{key}")
        if entry.get("script") != expected_script or entry.get("provider") != expected_provider:
            raise ValueError(f"llm_routing_runner_mismatch:{key}")
        model = entry.get("model")
        if not isinstance(model, str) or not model.strip() or any(ch.isspace() for ch in model):
            raise ValueError(f"llm_routing_runner_model_invalid:{key}")
    if key_model := str(plane_b["runners"]["gemini"]["model"]):
        if key_model.casefold() in {"auto", "automatic", "default", "environment-default", "gemini-cli-default"}:
            raise ValueError("llm_routing_gemini_model_not_pinned")
    sys_inst = plane_b["runners"]["gemini"].get("system_instruction")
    if not isinstance(sys_inst, str) or not sys_inst.strip():
        raise ValueError("llm_routing_gemini_system_instruction_missing")
    agy_cfg = plane_a["backends"].get("agy-subagent")
    if isinstance(agy_cfg, dict) and agy_cfg.get("plane_b_forbidden") is not True:
        raise ValueError("llm_routing_agy_subagent_must_forbid_plane_b")
    return payload


def load_llm_routing(root: Path | None = None, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source_env = os.environ if env is None else env
    override = str(source_env.get("NEWROGUE_LLM_ROUTING_PATH") or "").strip()
    candidates: list[Path] = []
    if override:
        override_path = Path(override)
        if not override_path.is_file():
            raise ValueError(f"llm_routing_override_missing:{override}")
        candidates.append(override_path)
    else:
        if root is not None:
            candidates.append(Path(root) / ROUTING_REL_PATH)
        candidates.append(default_repo_root() / ROUTING_REL_PATH)
    for candidate in candidates:
        if candidate.is_file():
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"llm_routing_load_failed:{exc}") from exc
            return _validate_routing_payload(raw)
    raise ValueError("llm_routing_config_missing")


def is_official_isolated_runner_name(name: str) -> bool:
    if not isinstance(name, str) or not name.strip():
        return False
    normalized = name.strip().replace("\\", "/")
    if normalized in OFFICIAL_RUNNER_SCRIPTS:
        return True
    return normalized in {f"scripts/python/{script}" for script in OFFICIAL_RUNNER_SCRIPTS}


_RUNNER_ALIASES: dict[str, str] = {
    "codex": "codex",
    "codex-cli": "codex",
    "gemini": "gemini",
    "gemini-cli": "gemini",
}


def _script_name_from_identifier(runner_path: str | Path) -> str:
    raw = str(runner_path).strip()
    lowered = raw.casefold()
    if lowered == "auto":
        return resolve_plane_b_runner(default_repo_root()).name
    alias = _RUNNER_ALIASES.get(lowered)
    if alias == "codex" or raw == CODEX_RUNNER_SCRIPT:
        return CODEX_RUNNER_SCRIPT
    if alias == "gemini" or raw == GEMINI_RUNNER_SCRIPT:
        return GEMINI_RUNNER_SCRIPT
    name = Path(raw.replace("\\", "/")).name
    if name in OFFICIAL_RUNNER_SCRIPTS:
        return name
    raise ValueError(f"unsupported_isolated_runner:{runner_path}")


def is_official_isolated_runner(runner_path: str | Path, root: Path | None = None) -> bool:
    try:
        effective_root = Path(root).resolve() if root is not None else default_repo_root()
        candidate = Path(runner_path)
        resolved = (effective_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    except OSError:
        return False
    expected_dir = (effective_root / "scripts" / "python").resolve()
    return (
        resolved.parent == expected_dir
        and resolved.name in OFFICIAL_RUNNER_SCRIPTS
        and resolved.is_file()
    )


def describe_runner_protocol(runner_path: str | Path) -> str:
    script_name = _script_name_from_identifier(runner_path)
    if script_name == CODEX_RUNNER_SCRIPT:
        return CODEX_PROTOCOL
    if script_name == GEMINI_RUNNER_SCRIPT:
        return GEMINI_PROTOCOL
    raise ValueError(f"unsupported_isolated_runner:{runner_path}")


def governed_model_for_provider(provider: str, root: Path | None = None) -> str:
    routing = load_llm_routing(root, env={})
    normalized = str(provider or "").strip().casefold()
    if normalized == "google":
        return str(routing["plane_b"]["runners"]["gemini"]["model"])
    if normalized == "openai":
        return "auto"
    raise ValueError(f"unsupported_isolated_runner_provider:{provider}")


def resolve_runner_spec(
    runner_path: str | Path,
    root: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> IsolatedRunnerSpec:
    effective_target: str | Path = runner_path
    if str(runner_path).strip().casefold() == "auto":
        effective_target = resolve_plane_b_runner(
            Path(root) if root is not None else default_repo_root(),
            env=env,
        )
    script_name = _script_name_from_identifier(effective_target)
    routing = load_llm_routing(root, env=env)
    runners = routing["plane_b"]["runners"]
    if script_name == CODEX_RUNNER_SCRIPT:
        entry = runners["codex"]
        return IsolatedRunnerSpec(
            key="codex",
            script_name=CODEX_RUNNER_SCRIPT,
            script_rel_path=str(entry["script"]),
            provider=str(entry["provider"]),
            model=str(entry["model"]),
            protocol=CODEX_PROTOCOL,
            evidence_policy=CODEX_EVIDENCE_POLICY,
            identity_source=CODEX_IDENTITY_SOURCE,
            stream_suffixes=CODEX_STREAM_SUFFIXES,
            reasoning_effort=str(entry.get("reasoning_effort") or "high"),
            system_instruction=entry.get("system_instruction"),
        )
    entry = runners["gemini"]
    return IsolatedRunnerSpec(
        key="gemini",
        script_name=GEMINI_RUNNER_SCRIPT,
        script_rel_path=str(entry["script"]),
        provider=str(entry["provider"]),
        model=str(entry["model"]),
        protocol=GEMINI_PROTOCOL,
        evidence_policy=GEMINI_EVIDENCE_POLICY,
        identity_source=GEMINI_IDENTITY_SOURCE,
        stream_suffixes=GEMINI_STREAM_SUFFIXES,
        reasoning_effort=str(entry.get("reasoning_effort") or "high"),
        system_instruction=str(entry["system_instruction"]),
    )


def resolve_plane_b_runner(
    root: Path,
    requested_runner: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    effective_root = Path(root).resolve()
    source_env = os.environ if env is None else env
    routing = load_llm_routing(effective_root, env=source_env)
    runners = routing["plane_b"]["runners"]

    req_raw = str(requested_runner).strip() if requested_runner is not None else ""
    if req_raw.casefold() == "auto":
        req_raw = ""
    env_raw = str(source_env.get("NEWROGUE_PLANE_B_RUNNER") or "").strip()
    if env_raw.casefold() == "auto":
        env_raw = ""

    if req_raw:
        raw_choice = req_raw
    elif env_raw:
        raw_choice = env_raw
    else:
        raw_choice = str(routing["plane_b"]["default_runner"]).strip()

    normalized_alias = _RUNNER_ALIASES.get(raw_choice.casefold(), raw_choice)
    if normalized_alias in runners:
        rel_script = str(runners[normalized_alias]["script"])
        return (effective_root / rel_script).resolve()

    candidate = Path(raw_choice)
    if candidate.is_absolute():
        return candidate.resolve()
    return (effective_root / candidate).resolve()


def stream_suffixes_for_runner(runner_path: str | Path | None = None) -> tuple[str, ...]:
    if runner_path is None:
        return ALL_STREAM_SUFFIXES
    script_name = _script_name_from_identifier(runner_path)
    if script_name == CODEX_RUNNER_SCRIPT:
        return CODEX_STREAM_SUFFIXES
    return GEMINI_STREAM_SUFFIXES


def execution_output_name(
    name: str,
    output_name: str,
    runner_path: str | Path | None = None,
) -> bool:
    if not isinstance(name, str) or not isinstance(output_name, str):
        return False
    if not name.startswith(output_name + ".") or Path(name).name != name:
        return False
    for suffix in stream_suffixes_for_runner(runner_path):
        if name.endswith(suffix):
            identifier = name[len(output_name) + 1 : -len(suffix)]
            return len(identifier) == 32 and all(char in "0123456789abcdef" for char in identifier)
    return False


def resolve_reasoning_effort(
    env: Mapping[str, str] | None = None,
    *,
    default: str | None = None,
    allowed: tuple[str, ...] = ("high",),
) -> str | None:
    source_env = os.environ if env is None else env
    gemini_raw = source_env.get("NEWROGUE_GEMINI_REASONING_EFFORT")
    codex_raw = source_env.get("NEWROGUE_CODEX_REASONING_EFFORT")
    if gemini_raw is not None and gemini_raw not in allowed:
        raise ValueError(f"unsupported_requested_reasoning_effort:{gemini_raw}")
    if codex_raw is not None and codex_raw not in allowed:
        raise ValueError(f"unsupported_requested_reasoning_effort:{codex_raw}")
    if gemini_raw is not None and codex_raw is not None and gemini_raw != codex_raw:
        raise ValueError(
            f"conflicting_requested_reasoning_effort:gemini={gemini_raw};codex={codex_raw}"
        )
    if gemini_raw is not None:
        return gemini_raw
    if codex_raw is not None:
        return codex_raw
    if default is not None and default not in allowed:
        raise ValueError(f"unsupported_requested_reasoning_effort:{default}")
    return default


def runner_environment(
    runner_path: str | Path,
    *,
    reasoning_effort: str | None = "high",
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    _script_name_from_identifier(runner_path)
    source_env = dict(os.environ if base_env is None else base_env)
    effective_effort = resolve_reasoning_effort(
        source_env,
        default=reasoning_effort,
        allowed=("low", "high"),
    )
    source_env["PYTHONDONTWRITEBYTECODE"] = "1"
    source_env["NEWROGUE_EXECUTION_PLANE"] = "plane_b"
    if effective_effort is not None:
        if (
            "NEWROGUE_GEMINI_REASONING_EFFORT" in source_env
            and source_env["NEWROGUE_GEMINI_REASONING_EFFORT"] != effective_effort
        ) or (
            "NEWROGUE_CODEX_REASONING_EFFORT" in source_env
            and source_env["NEWROGUE_CODEX_REASONING_EFFORT"] != effective_effort
        ):
            raise ValueError("conflicting_requested_reasoning_effort")
        source_env["NEWROGUE_CODEX_REASONING_EFFORT"] = effective_effort
        source_env["NEWROGUE_GEMINI_REASONING_EFFORT"] = effective_effort
    return source_env
