"""Save Gemini Web cookies locally with Windows DPAPI encryption.

This fallback is intended for Chrome versions whose App-Bound Encryption blocks
browser-cookie3. Cookie values never leave this process and are never printed.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _credential_path() -> Path:
    raw = os.environ.get("GEMINI_CREDENTIAL_FILE") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not raw:
        raise RuntimeError(
            "Set GEMINI_CREDENTIAL_FILE to an absolute path outside this Git repository"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise RuntimeError("GEMINI_CREDENTIAL_FILE must be an absolute path")
    path = candidate.resolve()
    repository = Path(__file__).resolve().parents[2]
    if path == repository or repository in path.parents:
        raise RuntimeError("Credential file must be stored outside the Git repository")
    return path


def _protect(value: str) -> str:
    raw = value.encode("utf-8")
    source_buffer = ctypes.create_string_buffer(raw)
    source = DATA_BLOB(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "Gemini Web MCP", None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return base64.b64encode(
            ctypes.string_at(output.pbData, output.cbData)
        ).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def main() -> int:
    output_path = _credential_path()
    root = tk.Tk()
    root.title("Gemini Web MCP 本地认证")
    root.geometry("680x290")
    root.resizable(False, False)

    instructions = (
        "仅在 Chrome App-Bound Encryption 导致自动读取失败时使用。\n"
        "从当前已登录的 Gemini 页面按 F12 → Application → Cookies，\n"
        "找到下面两个 Cookie；内容只会在本机使用 Windows DPAPI 加密。"
    )
    tk.Label(root, text=instructions, justify="left", anchor="w").pack(
        fill="x", padx=18, pady=(16, 10)
    )
    tk.Label(root, text=f"保存位置：{output_path}", anchor="w").pack(
        fill="x", padx=18, pady=(0, 8)
    )

    form = tk.Frame(root)
    form.pack(fill="x", padx=18)
    tk.Label(form, text="__Secure-1PSID", width=20, anchor="w").grid(
        row=0, column=0, pady=6
    )
    psid_entry = tk.Entry(form, show="●", width=65)
    psid_entry.grid(row=0, column=1, pady=6)
    tk.Label(form, text="__Secure-1PSIDTS", width=20, anchor="w").grid(
        row=1, column=0, pady=6
    )
    psidts_entry = tk.Entry(form, show="●", width=65)
    psidts_entry.grid(row=1, column=1, pady=6)

    def save() -> None:
        psid = psid_entry.get().strip()
        psidts = psidts_entry.get().strip()
        if not psid or not psidts:
            messagebox.showerror("缺少内容", "两个 Cookie 都需要填写。")
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        payload = {
            "version": 1,
            "psid": _protect(psid),
            "psidts": _protect(psidts),
        }
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, output_path)
        psid_entry.delete(0, tk.END)
        psidts_entry.delete(0, tk.END)
        messagebox.showinfo("保存成功", "Cookie 已用当前 Windows 用户的 DPAPI 加密保存。")
        root.destroy()

    tk.Button(root, text="DPAPI 加密保存", command=save, width=24).pack(pady=18)
    psid_entry.focus_set()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
