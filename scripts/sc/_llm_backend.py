#!/usr/bin/env python3
"""
Internal LLM backend seam for Plane A sc scripts.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

KNOWN_LLM_BACKENDS = (
    "codex-cli",
    "gemini-cli",
    "agy-subagent",
    "openai-api",
    "gemini-api",
)

ROUTING_SCHEMA = "newrouge.llm-routing.v1"
ROUTING_REL_PATH = "docs/workflows/llm-routing.json"

_SC_SCRUBBED_GEMINI_ENV_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_GCA",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GEMINI_CLI_SYSTEM_DEFAULTS_PATH",
)


_MODULE_REPO_ROOT = str(Path(__file__).resolve().parents[2])


def _default_repo_root() -> str:
    return _MODULE_REPO_ROOT


def _load_plane_a_routing(root: Path | str | None = None) -> dict[str, object]:
    override = str(os.environ.get("NEWROGUE_LLM_ROUTING_PATH") or "").strip()
    candidates: list[str] = []
    if override:
        candidates.append(override)
    else:
        if root is not None:
            candidates.append(os.path.join(str(root), ROUTING_REL_PATH))
        candidates.append(os.path.join(_default_repo_root(), ROUTING_REL_PATH))
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == ROUTING_SCHEMA:
            plane_a = payload.get("plane_a")
            if isinstance(plane_a, dict):
                return plane_a
    return {}


def _in_plane_b_context() -> bool:
    plane = str(os.environ.get("NEWROGUE_EXECUTION_PLANE") or "").strip().lower()
    flag = str(os.environ.get("SC_PLANE_B_CONTEXT") or "").strip().lower()
    return plane in {"plane_b", "b"} or flag in {"1", "true", "yes"}


def is_plane_b_forbidden_backend(
    backend: str | None, *, root: Path | str | None = None
) -> bool:
    backend_name = resolve_llm_backend(backend, root=root)
    if backend_name == "agy-subagent":
        return True
    plane_a = _load_plane_a_routing(root)
    backends = plane_a.get("backends")
    if isinstance(backends, dict):
        cfg = backends.get(backend_name)
        if isinstance(cfg, dict) and cfg.get("plane_b_forbidden") is True:
            return True
    return False


def resolve_llm_backend(raw: str | None, *, root: Path | str | None = None) -> str:
    explicit = str(
        raw
        or os.environ.get("SC_LLM_BACKEND")
        or os.environ.get("NEWROGUE_PLANE_A_BACKEND")
        or ""
    ).strip().lower()
    if explicit:
        return explicit
    plane_a = _load_plane_a_routing(root)
    governed_default = str(plane_a.get("default_backend") or "").strip().lower()
    if governed_default in KNOWN_LLM_BACKENDS:
        return governed_default
    return "codex-cli"


def _find_gemini_executable() -> str:
    override = str(os.environ.get("NEWROGUE_GEMINI_BIN") or "").strip()
    if override:
        if os.path.isfile(override):
            return override
        found_override = shutil.which(override)
        if found_override:
            return found_override
        return ""
    homes: list[str] = []
    env_home = str(os.environ.get("HOME") or "").strip()
    if env_home:
        homes.append(env_home)
    if os.name == "nt":
        up = str(os.environ.get("USERPROFILE") or "").strip()
        if up and up not in homes:
            homes.append(up)
    else:
        try:
            import pwd

            pw_home = pwd.getpwuid(os.getuid()).pw_dir
            if pw_home and pw_home not in homes:
                homes.append(pw_home)
        except (ImportError, KeyError, AttributeError, OSError):
            pass
    prefer_agy = any(
        os.path.isfile(os.path.join(h, ".gemini", "antigravity-cli", "antigravity-oauth-token"))
        for h in homes
    )
    agy_names = ("agy.exe", "agy.cmd", "agy") if os.name == "nt" else ("agy",)
    gemini_names = ("gemini.cmd", "gemini") if os.name == "nt" else ("gemini", "gemini.cmd")
    ordered_names = (*agy_names, *gemini_names) if prefer_agy else (*gemini_names, *agy_names)
    for name in ordered_names:
        found = shutil.which(name)
        if found:
            return found
    for home in homes:
        agy_cands = (
            (
                os.path.join(home, "AppData", "Local", "agy", "bin", "agy.exe"),
                os.path.join(home, ".local", "bin", "agy.exe"),
            )
            if os.name == "nt"
            else (os.path.join(home, ".local", "bin", "agy"),)
        )
        gem_cands = (
            (
                os.path.join(home, "AppData", "Roaming", "npm", "gemini.cmd"),
                os.path.join(home, ".local", "bin", "gemini.cmd"),
            )
            if os.name == "nt"
            else (os.path.join(home, ".local", "bin", "gemini"),)
        )
        for cand in ((*agy_cands, *gem_cands) if prefer_agy else (*gem_cands, *agy_cands)):
            if os.path.isfile(cand):
                return cand
    return ""


def _resolve_gemini_model(root: Path | None = None) -> str:
    env_model = str(os.environ.get("SC_GEMINI_MODEL") or os.environ.get("GEMINI_MODEL") or "").strip()
    if env_model:
        return env_model
    plane_a = _load_plane_a_routing(root)
    backends = plane_a.get("backends")
    if isinstance(backends, dict):
        gemini_cfg = backends.get("gemini-cli")
        if isinstance(gemini_cfg, dict):
            cfg_model = str(gemini_cfg.get("model") or "").strip()
            if cfg_model:
                return cfg_model
    return "gemini-4-carbon-high"


def inspect_llm_backend(backend: str | None, *, root: Path | None = None) -> dict[str, object]:
    backend_name = resolve_llm_backend(backend, root=root)
    payload: dict[str, object] = {
        "backend": backend_name,
        "available": False,
        "blocking_errors": [],
    }
    if backend_name == "codex-cli":
        executable = shutil.which("codex")
        payload["executable"] = executable or ""
        if not executable:
            payload["blocking_errors"] = ["codex executable not found in PATH"]
            return payload
        payload["available"] = True
        return payload

    if backend_name == "gemini-cli":
        executable = _find_gemini_executable()
        model = _resolve_gemini_model(root)
        payload["executable"] = executable or ""
        payload["model"] = model
        if not executable:
            payload["blocking_errors"] = ["gemini executable not found in PATH"]
            return payload
        payload["available"] = True
        return payload

    if backend_name == "agy-subagent":
        blocking_errors: list[str] = []
        bridge_cmd = str(
            os.environ.get("SC_AGY_SUBAGENT_CMD")
            or os.environ.get("NEWROGUE_AGY_SUBAGENT_CMD")
            or ""
        ).strip()
        payload["isolation_scope"] = "host_subagent_with_read_tools"
        payload["plane_b_forbidden"] = True
        payload["bridge_command_configured"] = bool(bridge_cmd)
        if _in_plane_b_context():
            blocking_errors.append("agy-subagent backend is forbidden on Plane B")
        if not bridge_cmd:
            blocking_errors.append("SC_AGY_SUBAGENT_CMD is not configured for host subagent dispatch")
        payload["blocking_errors"] = blocking_errors
        payload["available"] = len(blocking_errors) == 0
        return payload

    if backend_name == "openai-api":
        module_spec = importlib.util.find_spec("openai")
        api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
        blocking_errors = []
        payload["python_module"] = "openai"
        payload["python_module_found"] = bool(module_spec)
        payload["api_key_env"] = "OPENAI_API_KEY"
        payload["api_key_present"] = bool(api_key)
        if module_spec is None:
            blocking_errors.append("python package 'openai' is not installed")
        if not api_key:
            blocking_errors.append("OPENAI_API_KEY is not set")
        payload["blocking_errors"] = blocking_errors
        payload["available"] = len(blocking_errors) == 0
        return payload

    if backend_name == "gemini-api":
        api_key = str(
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        ).strip()
        model = _resolve_gemini_model(root)
        blocking_errors = []
        payload["api_key_env"] = "GEMINI_API_KEY"
        payload["api_key_present"] = bool(api_key)
        payload["model"] = model
        payload["opt_in_only"] = True
        if not api_key:
            blocking_errors.append("GEMINI_API_KEY is not set")
        payload["blocking_errors"] = blocking_errors
        payload["available"] = len(blocking_errors) == 0
        return payload

    payload["blocking_errors"] = [f"unsupported llm backend: {backend_name}"]
    return payload


def _extract_reasoning_effort(codex_configs: list[str] | None) -> str:
    for item in list(codex_configs or []):
        text = str(item or "").strip()
        if not text.startswith("model_reasoning_effort="):
            continue
        _, raw = text.split("=", 1)
        value = raw.strip().strip('"').strip("'").strip().lower()
        if value in {"low", "medium", "high", "none", "minimal"}:
            return value
    return ""


def _resolve_openai_model() -> str:
    return (
        str(os.environ.get("SC_OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or "auto").strip()
        or "auto"
    )


def _extract_response_output_text(response: object) -> str:
    direct = str(getattr(response, "output_text", "") or "").strip()
    if direct:
        return direct
    output_items = getattr(response, "output", None)
    if isinstance(output_items, list):
        chunks: list[str] = []
        for item in output_items:
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for part in content:
                text = str(getattr(part, "text", "") or "").strip()
                if text:
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks).strip()
    if isinstance(response, dict):
        direct = str(response.get("output_text") or "").strip()
        if direct:
            return direct
    return ""


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith(("```", "~~~")):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith(("```", "~~~")):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _extract_gemini_cli_text(raw_stdout: str) -> str:
    text = (raw_stdout or "").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            if isinstance(parsed.get("response"), str):
                return parsed["response"].strip()
            res_obj = parsed.get("result")
            if isinstance(res_obj, dict) and isinstance(res_obj.get("response"), str):
                return res_obj["response"].strip()
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            parsed_line = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed_line, dict):
            if isinstance(parsed_line.get("response"), str):
                return parsed_line["response"].strip()
            res_obj = parsed_line.get("result")
            if isinstance(res_obj, dict):
                if res_obj.get("structured_output") is not None:
                    return json.dumps(
                        res_obj["structured_output"],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                if isinstance(res_obj.get("response"), str):
                    return res_obj["response"].strip()
    return text


def _is_paid_api_allowed() -> bool:
    for key in ("NEWROGUE_ALLOW_PAID_API", "SC_ALLOW_PAID_API"):
        if str(os.environ.get(key) or "").strip().lower() in {"1", "true", "yes"}:
            return True
    return False


def _cleanup_sc_temp_dir(temp_dir: tempfile.TemporaryDirectory[str]) -> None:
    sandbox_path = Path(temp_dir.name)
    for attempt in range(3):
        try:
            temp_dir.cleanup()
            return
        except PermissionError:
            if attempt < 2:
                time.sleep(0.05 * (attempt + 1))
        except OSError:
            return
    if sandbox_path.exists():
        shutil.rmtree(sandbox_path, ignore_errors=True)


def _kill_timed_out_proc(proc: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
    else:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        pass


def run_llm_exec(
    *,
    backend: str,
    root: Path,
    prompt: str,
    output_last_message: Path,
    timeout_sec: int,
    codex_configs: list[str] | None = None,
    output_schema: Path | None = None,
) -> tuple[int, str, list[str]]:
    backend_name = resolve_llm_backend(backend, root=root)
    if is_plane_b_forbidden_backend(backend_name, root=root) and _in_plane_b_context():
        return 2, f"{backend_name} backend is forbidden on Plane B\n", [backend_name]

    if backend_name == "openai-api":
        info = inspect_llm_backend(backend_name, root=root)
        blocking_errors = [
            str(item).strip() for item in list(info.get("blocking_errors") or []) if str(item).strip()
        ]
        if blocking_errors:
            details = "; ".join(blocking_errors)
            return 2, f"openai-api backend is not runnable: {details}\n", [backend_name]
        try:
            openai_module = sys.modules.get("openai")
            if openai_module is None:
                import openai as openai_module  # type: ignore
            OpenAI = getattr(openai_module, "OpenAI")
        except Exception as exc:  # noqa: BLE001
            return 1, f"openai-api backend failed to import SDK: {exc}\n", [backend_name]
        if getattr(openai_module, "__spec__", None) is not None and not _is_paid_api_allowed():
            return (
                2,
                "openai-api is opt-in only; pass --allow-paid-api or set NEWROGUE_ALLOW_PAID_API=1\n",
                [backend_name],
            )

        model = _resolve_openai_model()
        reasoning_effort = _extract_reasoning_effort(codex_configs)
        kwargs: dict[str, object] = {
            "model": model,
            "input": prompt,
        }
        if output_schema is not None:
            try:
                schema = json.loads(output_schema.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return 1, f"openai-api output schema could not be loaded: {exc}\n", [backend_name]
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "newrouge_mvg_review",
                    "strict": True,
                    "schema": schema,
                }
            }
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        try:
            client = OpenAI(timeout=float(timeout_sec))
            response = client.responses.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return 1, f"openai-api request failed: {exc}\n", [backend_name]

        output_text = _extract_response_output_text(response)
        if output_text:
            output_last_message.parent.mkdir(parents=True, exist_ok=True)
            output_last_message.write_text(output_text.rstrip() + "\n", encoding="utf-8")
        trace = {
            "backend": backend_name,
            "model": model,
            "reasoning_effort": reasoning_effort or None,
            "response_id": str(getattr(response, "id", "") or ""),
            "output_chars": len(output_text),
        }
        return (
            (0 if output_text else 1),
            json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
            [backend_name, model],
        )

    if backend_name == "gemini-api":
        if not _is_paid_api_allowed():
            return (
                2,
                "gemini-api is opt-in only; pass --allow-paid-api or set NEWROGUE_ALLOW_PAID_API=1\n",
                [backend_name],
            )
        info = inspect_llm_backend(backend_name, root=root)
        blocking_errors = [
            str(item).strip() for item in list(info.get("blocking_errors") or []) if str(item).strip()
        ]
        if blocking_errors:
            details = "; ".join(blocking_errors)
            return 2, f"gemini-api backend is not runnable: {details}\n", [backend_name]
        api_key = str(
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        ).strip()
        model = _resolve_gemini_model(root)
        effective_prompt = prompt
        gen_config: dict[str, object] = {}
        if output_schema is not None:
            try:
                schema = json.loads(output_schema.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return 1, f"gemini-api output schema could not be loaded: {exc}\n", [backend_name]
            gen_config["responseMimeType"] = "application/json"
            effective_prompt = (
                prompt.rstrip()
                + "\n\nReturn ONLY valid JSON conforming to this JSON Schema:\n"
                + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
        base_url = (
            str(
                os.environ.get("SC_GEMINI_API_BASE_URL")
                or "https://generativelanguage.googleapis.com/v1beta"
            )
            .strip()
            .rstrip("/")
        )
        url = f"{base_url}/models/{model}:generateContent"
        req_body: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": effective_prompt}]}],
        }
        if gen_config:
            req_body["generationConfig"] = gen_config
        req = urllib.request.Request(
            url,
            data=json.dumps(req_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=float(timeout_sec)) as resp:
                resp_payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return 1, f"gemini-api request failed: {exc}\n", [backend_name]

        parts_text: list[str] = []
        for candidate in list(resp_payload.get("candidates") or []):
            if not isinstance(candidate, dict):
                continue
            content_obj = candidate.get("content")
            if not isinstance(content_obj, dict):
                continue
            for part in list(content_obj.get("parts") or []):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts_text.append(part["text"])
        output_text = "\n".join(parts_text).strip()
        if output_schema is not None and output_text:
            output_text = _strip_markdown_fence(output_text)
        if output_text:
            output_last_message.parent.mkdir(parents=True, exist_ok=True)
            output_last_message.write_text(output_text.rstrip() + "\n", encoding="utf-8")
        trace = {
            "backend": backend_name,
            "model": model,
            "output_chars": len(output_text),
        }
        return (
            (0 if output_text else 1),
            json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
            [backend_name, model],
        )

    if backend_name == "agy-subagent":
        info = inspect_llm_backend(backend_name, root=root)
        blocking_errors = [
            str(item).strip() for item in list(info.get("blocking_errors") or []) if str(item).strip()
        ]
        if blocking_errors:
            details = "; ".join(blocking_errors)
            return 2, f"agy-subagent backend is not runnable: {details}\n", [backend_name]
        bridge_raw = str(
            os.environ.get("SC_AGY_SUBAGENT_CMD")
            or os.environ.get("NEWROGUE_AGY_SUBAGENT_CMD")
            or ""
        ).strip()
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            argc = ctypes.c_int(0)
            cmd_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
            cmd_line_to_argv.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
            cmd_line_to_argv.restype = ctypes.POINTER(wintypes.LPWSTR)
            argv_ptr = cmd_line_to_argv(bridge_raw, ctypes.byref(argc))
            if not argv_ptr:
                return 2, "agy-subagent bridge command could not be parsed\n", [backend_name]
            try:
                cmd = [argv_ptr[i] for i in range(argc.value)]
            finally:
                ctypes.windll.kernel32.LocalFree(argv_ptr)
        else:
            cmd = shlex.split(bridge_raw, posix=True)
        child_env = dict(os.environ)
        child_env["SC_AGY_OUTPUT_LAST_MESSAGE"] = str(output_last_message)
        child_env["SC_AGY_OUTPUT_SCHEMA"] = str(output_schema or "")
        child_env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                cwd=str(root),
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                stdout, _ = proc.communicate(input=prompt, timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                _kill_timed_out_proc(proc)
                return 124, "agy-subagent exec timeout\n", cmd
        except Exception as exc:  # noqa: BLE001
            return 1, f"agy-subagent exec failed to start: {exc}\n", cmd
        rc = proc.returncode or 0
        out_text = (stdout or "").strip()
        if rc == 0 and not output_last_message.is_file() and out_text:
            output_last_message.parent.mkdir(parents=True, exist_ok=True)
            output_last_message.write_text(out_text + "\n", encoding="utf-8")
        return rc, stdout or "", cmd

    if backend_name == "gemini-cli":
        exe = _find_gemini_executable()
        if not exe:
            return 127, "gemini executable not found in PATH\n", ["gemini"]
        model = _resolve_gemini_model(root)
        exe_stem = Path(str(exe).replace("\\", "/")).stem.casefold()
        is_agy = exe_stem in {"agy", "antigravity-cli"} or exe_stem.startswith("agy_") or "_agy_" in exe_stem

        schema: dict[str, object] | None = None
        effective_prompt = prompt
        if output_schema is not None:
            try:
                loaded_schema = json.loads(output_schema.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return 1, f"gemini-cli output schema could not be loaded: {exc}\n", [backend_name]
            if not isinstance(loaded_schema, dict):
                return 1, "gemini-cli output schema must be a JSON object\n", [backend_name]
            schema = loaded_schema
            effective_prompt = (
                prompt.rstrip()
                + "\n\nReturn ONLY valid JSON matching this JSON Schema (no Markdown code fences):\n"
                + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )

        if is_agy:
            args = [
                "--sandbox",
                "--disable-slash-commands",
                "--model",
                model,
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
            ]
            if schema is not None:
                args.extend(["--json-schema", "../schema.json"])
        else:
            args = [
                "-m",
                model,
                "--approval-mode",
                "plan",
                "--output-format",
                "json",
                "--raw-output",
                "--accept-raw-output-risk",
                "--skip-trust",
            ]
        if exe.casefold().endswith(".py"):
            cmd = [sys.executable, "-B", exe, *args]
        else:
            cmd = [exe, *args]

        child_env = dict(os.environ)
        if not _is_paid_api_allowed():
            scrub_upper = {key.upper() for key in _SC_SCRUBBED_GEMINI_ENV_KEYS}
            child_env = {
                key: val
                for key, val in child_env.items()
                if key not in _SC_SCRUBBED_GEMINI_ENV_KEYS and key.upper() not in scrub_upper
            }
        child_env["NO_COLOR"] = "1"
        child_env["CI"] = "1"
        child_env["PYTHONDONTWRITEBYTECODE"] = "1"
        if os.name != "nt":
            path_parts = [p for p in str(child_env.get("PATH") or "").split(os.pathsep) if p]
            for extra_dir in (str(Path(exe).resolve().parent), "/usr/local/bin", "/usr/bin", "/bin"):
                if extra_dir and Path(extra_dir).is_dir() and extra_dir not in path_parts:
                    path_parts.append(extra_dir)
            child_env["PATH"] = os.pathsep.join(path_parts)

        temp_dir: tempfile.TemporaryDirectory[str] | None = None
        proc: subprocess.Popen[str] | None = None
        stdout: str | None = None
        try:
            temp_dir = tempfile.TemporaryDirectory(prefix="newrouge-sc-gemini-")
            try:
                sandbox_root = Path(temp_dir.name).resolve()
                empty_cwd = sandbox_root / "empty_cwd"
                empty_cwd.mkdir(parents=True, exist_ok=True)
                sys_settings_path = sandbox_root / "system-settings.json"
                isolated_settings = {
                    "tools": {"core": [], "allowed": []},
                    "mcpServers": {},
                    "security": {"folderTrust": {"enabled": False}},
                }
                sys_settings_path.write_text(
                    json.dumps(isolated_settings, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                child_env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(sys_settings_path)
                stdin_text = effective_prompt
                if is_agy:
                    agy_home = sandbox_root / "agy_home"
                    agy_cfg = agy_home / ".gemini" / "antigravity-cli"
                    agy_cfg.mkdir(parents=True, exist_ok=True)
                    for home_cand in (
                        str(os.environ.get("HOME") or ""),
                        str(os.environ.get("USERPROFILE") or ""),
                    ):
                        if not home_cand:
                            continue
                        tok_src = Path(home_cand) / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
                        if tok_src.is_file():
                            tok_dst = agy_cfg / "antigravity-oauth-token"
                            tok_dst.write_bytes(tok_src.read_bytes())
                            try:
                                os.chmod(tok_dst, 0o600)
                            except OSError:
                                pass
                            break
                    (agy_cfg / "settings.json").write_text(
                        json.dumps({"toolPermission": "request-review"}) + "\n",
                        encoding="utf-8",
                    )
                    child_env["HOME"] = str(agy_home)
                    child_env["USERPROFILE"] = str(agy_home)
                    if schema is not None:
                        (sandbox_root / "schema.json").write_text(
                            json.dumps(schema, ensure_ascii=False, separators=(",", ":")) + "\n",
                            encoding="utf-8",
                        )
                    stdin_text = (
                        json.dumps(
                            {"event": "user", "message": {"content": effective_prompt}},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )

                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    cwd=str(empty_cwd),
                    env=child_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                try:
                    stdout, _ = proc.communicate(input=stdin_text, timeout=timeout_sec)
                except subprocess.TimeoutExpired:
                    _kill_timed_out_proc(proc)
                    return 124, "gemini exec timeout\n", cmd
            except Exception as exc:  # noqa: BLE001
                return 1, f"gemini exec failed to start: {exc}\n", cmd
            finally:
                if proc is not None:
                    if proc.poll() is None:
                        _kill_timed_out_proc(proc)
                    for pipe_name in ("stdin", "stdout", "stderr"):
                        pipe_obj = getattr(proc, pipe_name, None)
                        if pipe_obj is not None and not pipe_obj.closed:
                            try:
                                pipe_obj.close()
                            except OSError:
                                pass
        finally:
            if temp_dir is not None:
                try:
                    _cleanup_sc_temp_dir(temp_dir)
                except BaseException:
                    pass

        rc = proc.returncode or 0
        if rc == 0:
            extracted = _extract_gemini_cli_text(stdout or "")
            if schema is not None:
                stripped = extracted.strip()
                if not stripped:
                    return 1, "gemini-cli returned empty output for schema request\n", cmd
                if (
                    stripped.startswith("```")
                    or stripped.startswith("~~~")
                    or stripped.endswith("```")
                    or stripped.endswith("~~~")
                ):
                    return 1, "gemini-cli returned forbidden markdown fence for schema output\n", cmd
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    return 1, f"gemini-cli returned invalid JSON for schema output: {exc}\n", cmd
                try:
                    import jsonschema  # type: ignore

                    jsonschema.Draft202012Validator(schema).validate(parsed)
                except Exception as exc:  # noqa: BLE001
                    return 1, f"gemini-cli output failed JSON Schema validation: {exc}\n", cmd
                output_last_message.parent.mkdir(parents=True, exist_ok=True)
                output_last_message.write_text(stripped + "\n", encoding="utf-8")
            elif extracted:
                output_last_message.parent.mkdir(parents=True, exist_ok=True)
                output_last_message.write_text(extracted.rstrip() + "\n", encoding="utf-8")
        return rc, stdout or "", cmd

    if backend_name != "codex-cli":
        return 2, f"unsupported llm backend: {backend_name}\n", [backend_name]

    exe = shutil.which("codex")
    if not exe:
        return 127, "codex executable not found in PATH\n", ["codex"]

    extra_config = [c for c in (codex_configs or []) if str(c).strip()]
    extra_config_args: list[str] = []
    for item in extra_config:
        extra_config_args.extend(["-c", str(item)])

    cmd = [
        exe,
        "exec",
        "--ephemeral",
        *extra_config_args,
        "-s",
        "read-only",
        "-C",
        str(root),
        "--output-last-message",
        str(output_last_message),
    ]
    if output_schema is not None:
        cmd.extend(["--output-schema", str(output_schema)])
    cmd.append("-")
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            stdout, _ = proc.communicate(input=prompt, timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            _kill_timed_out_proc(proc)
            return 124, "codex exec timeout\n", cmd
    except Exception as exc:  # noqa: BLE001
        return 1, f"codex exec failed to start: {exc}\n", cmd
    return proc.returncode or 0, stdout or "", cmd
