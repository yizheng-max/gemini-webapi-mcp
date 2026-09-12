"""Launch gemini-webapi-mcp with optional Windows DPAPI credentials."""

from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _external_path(raw: str, variable: str) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise RuntimeError(f"{variable} must be an absolute path")
    path = candidate.resolve()
    repository = Path(__file__).resolve().parents[2]
    if path == repository or repository in path.parents:
        raise RuntimeError(f"{variable} must point outside the Git repository")
    return path


def _unprotect(encoded: str) -> str:
    encrypted = base64.b64decode(encoded)
    source_buffer = ctypes.create_string_buffer(encrypted)
    source = DATA_BLOB(len(encrypted), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _server_command() -> str:
    configured = os.environ.get("GEMINI_MCP_SERVER")
    if configured:
        return str(Path(configured).expanduser().resolve())
    repository = Path(__file__).resolve().parents[2]
    for relative in (
        Path(".venv") / "Scripts" / "gemini-webapi-mcp.exe",
        Path(".venv312") / "Scripts" / "gemini-webapi-mcp.exe",
    ):
        candidate = repository / relative
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Set GEMINI_MCP_SERVER to gemini-webapi-mcp.exe")


def _load_credentials(path: Path) -> tuple[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    psid = _unprotect(payload["psid"])
    psidts = _unprotect(payload["psidts"])
    if not psid or not psidts:
        raise RuntimeError("Local Gemini credentials are incomplete")
    return psid, psidts


def _system_proxy() -> str | None:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0])
            value = str(winreg.QueryValueEx(key, "ProxyServer")[0]).strip()
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not enabled or not value:
        return None
    if "=" in value:
        entries = dict(item.split("=", 1) for item in value.split(";") if "=" in item)
        value = entries.get("https") or entries.get("http") or ""
    if not value:
        return None
    return value if "://" in value else f"http://{value}"


def main() -> int:
    child_env = os.environ.copy()
    credential_raw = os.environ.get("GEMINI_CREDENTIAL_FILE")
    if credential_raw:
        credential_file = _external_path(credential_raw, "GEMINI_CREDENTIAL_FILE")
        if not credential_file.exists():
            raise RuntimeError(f"Credential file does not exist: {credential_file}")
        psid, psidts = _load_credentials(credential_file)
        child_env["GEMINI_PSID"] = psid
        child_env["GEMINI_PSIDTS"] = psidts

    binding_raw = os.environ.get("GEMINI_BINDING_FILE")
    if not binding_raw:
        raise RuntimeError("Set GEMINI_BINDING_FILE to an absolute path outside the repository")
    child_env["GEMINI_BINDING_FILE"] = str(
        _external_path(binding_raw, "GEMINI_BINDING_FILE")
    )

    temp_raw = os.environ.get("GEMINI_MCP_TEMP")
    if not temp_raw:
        raise RuntimeError("Set GEMINI_MCP_TEMP to a writable temporary directory")
    task_temp = _external_path(temp_raw, "GEMINI_MCP_TEMP")
    task_temp.mkdir(parents=True, exist_ok=True)
    child_env.update(
        {
            "TEMP": str(task_temp),
            "TMP": str(task_temp),
            "PYTHONPYCACHEPREFIX": str(task_temp / "pycache"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    proxy = _system_proxy()
    if proxy and not child_env.get("GEMINI_PROXY"):
        child_env["GEMINI_PROXY"] = proxy
    return subprocess.call([_server_command()], env=child_env)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"gemini MCP launcher error: {exc}", file=sys.stderr)
        raise SystemExit(1)
