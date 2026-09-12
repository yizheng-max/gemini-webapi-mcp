"""Persistent binding to one Gemini Web conversation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse


_CHAT_ID_RE = re.compile(r"(?:c_)?[A-Za-z0-9_-]{6,}")


def normalize_gemini_chat_id(value: str) -> str:
    """Return Gemini's internal ``c_...`` ID from a URL or bare ID."""
    candidate = value.strip()
    if not candidate:
        raise ValueError("Gemini chat URL or ID is required")

    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or parsed.hostname != "gemini.google.com":
            raise ValueError("Expected an https://gemini.google.com/app/... URL")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0] == "app":
            candidate = parts[1]
        elif (
            len(parts) == 4
            and parts[0] == "u"
            and parts[1].isdigit()
            and parts[2] == "app"
        ):
            candidate = parts[3]
        else:
            raise ValueError("Expected a Gemini chat URL ending in /app/<chat-id>")

    if not _CHAT_ID_RE.fullmatch(candidate):
        raise ValueError("Invalid Gemini chat ID")
    return candidate if candidate.startswith("c_") else f"c_{candidate}"


class ChatBindingStore:
    """Store only the bound chat ID and preferred model in a local JSON file."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, str | None] | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        cid = normalize_gemini_chat_id(str(payload.get("cid", "")))
        model = payload.get("model")
        return {"cid": cid, "model": str(model) if model else None}

    def save(self, cid: str, model: str | None = None) -> None:
        payload = {"cid": normalize_gemini_chat_id(cid), "model": model or None}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)


def latest_chat_metadata_from_body(body: object, cid: str) -> list[str] | None:
    """Extract ``[cid, rid, rcid]`` from the newest completed Gemini turn."""
    if not isinstance(body, list) or not body or not isinstance(body[0], list):
        return None
    turns = body[0]
    if not turns:
        return None

    newest = turns[0]
    try:
        rid = newest[0][1]
        candidates = newest[3][0]
        candidate = candidates[0]
        rcid = candidate[0]
    except (IndexError, TypeError):
        return None

    if not isinstance(rid, str) or not rid or not isinstance(rcid, str) or not rcid:
        return None
    if _candidate_is_in_progress(candidate):
        return None
    return [normalize_gemini_chat_id(cid), rid, rcid]


def _candidate_is_in_progress(candidate: object) -> bool:
    """Recognize Gemini's current streaming/progress markers conservatively."""
    if not isinstance(candidate, list):
        return False

    try:
        completion_status = candidate[8][0]
    except (IndexError, TypeError):
        completion_status = None
    if completion_status == 1:
        return True

    try:
        rich_content = candidate[12]
    except IndexError:
        return False
    progress = _jspb_field(rich_content, 6)
    return isinstance(progress, list) and bool(progress) and progress[0] is not None


def _jspb_field(container: object, index: int) -> object | None:
    """Read a normal or sparse-bundle field from a Gemini JSPB list."""
    if not isinstance(container, list) or not container:
        return None
    value = container[index] if index < len(container) else None
    if value in (None, [], {}) or isinstance(value, dict):
        bundle = container[-1] if isinstance(container[-1], dict) else None
        value = bundle.get(str(index + 1)) if bundle else None
    return None if value in (None, [], {}) else value
