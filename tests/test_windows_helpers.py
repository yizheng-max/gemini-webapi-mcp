import importlib.util
from pathlib import Path
import sys

import pytest


if sys.platform != "win32":
    pytest.skip("Windows DPAPI helpers require Windows", allow_module_level=True)


ROOT = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


capture = _load(
    "capture_gemini_cookies",
    "scripts/windows/capture_gemini_cookies.py",
)
launcher = _load(
    "gemini_mcp_launcher",
    "scripts/windows/gemini_mcp_launcher.py",
)


def test_dpapi_round_trip_does_not_use_plaintext_storage():
    plaintext = "local-test-cookie-value"

    encrypted = capture._protect(plaintext)

    assert plaintext not in encrypted
    assert launcher._unprotect(encrypted) == plaintext


def test_capture_rejects_relative_and_repository_paths(monkeypatch):
    monkeypatch.setenv("GEMINI_CREDENTIAL_FILE", "cookies.dpapi.json")
    with pytest.raises(RuntimeError, match="absolute path"):
        capture._credential_path()

    monkeypatch.setenv(
        "GEMINI_CREDENTIAL_FILE",
        str(ROOT / "cookies.dpapi.json"),
    )
    with pytest.raises(RuntimeError, match="outside the Git repository"):
        capture._credential_path()


def test_launcher_accepts_only_external_absolute_state_paths(tmp_path):
    external = launcher._external_path(str(tmp_path / "bound-chat.json"), "TEST")
    assert external == (tmp_path / "bound-chat.json").resolve()

    with pytest.raises(RuntimeError, match="absolute path"):
        launcher._external_path("bound-chat.json", "TEST")
    with pytest.raises(RuntimeError, match="outside the Git repository"):
        launcher._external_path(str(ROOT / "bound-chat.json"), "TEST")
