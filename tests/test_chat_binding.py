import json

import pytest

from gemini_webapi_mcp.chat_binding import (
    ChatBindingStore,
    latest_chat_metadata_from_body,
    normalize_gemini_chat_id,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://gemini.google.com/app/abc123?hl=zh-CN", "c_abc123"),
        ("https://gemini.google.com/app/c_abc123", "c_abc123"),
        ("https://gemini.google.com/u/1/app/abc123/", "c_abc123"),
        ("abc123", "c_abc123"),
        ("c_abc123", "c_abc123"),
    ],
)
def test_normalize_gemini_chat_id(value, expected):
    assert normalize_gemini_chat_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://example.com/app/abc123",
        "https://gemini.google.com/",
        "https://gemini.google.com/app/abc123/extra",
        "../../cookies",
    ],
)
def test_normalize_gemini_chat_id_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        normalize_gemini_chat_id(value)


def test_binding_store_round_trip_and_remove(tmp_path):
    path = tmp_path / "bound-chat.json"
    store = ChatBindingStore(path)

    store.save("c_abc123", "gemini-3.0-flash")

    assert store.load() == {
        "cid": "c_abc123",
        "model": "gemini-3.0-flash",
    }
    assert json.loads(path.read_text(encoding="utf-8")) == store.load()

    store.remove()
    assert store.load() is None
    assert not path.exists()


def test_latest_chat_metadata_uses_newest_completed_turn():
    body = [
        [
            [["c_abc123", "r_latest"], None, [["latest user"]], [[["rc_latest"]]]],
            [["c_abc123", "r_old"], None, [["old user"]], [[["rc_old"]]]],
        ]
    ]

    assert latest_chat_metadata_from_body(body, "c_abc123") == [
        "c_abc123",
        "r_latest",
        "rc_latest",
    ]


def test_latest_chat_metadata_waits_for_incomplete_browser_turn():
    body = [
        [
            [["c_abc123", "r_pending"], None, [["pending user"]], []],
            [["c_abc123", "r_old"], None, [["old user"]], [[["rc_old"]]]],
        ]
    ]

    assert latest_chat_metadata_from_body(body, "c_abc123") is None


def test_latest_chat_metadata_waits_when_streaming_candidate_already_has_rcid():
    candidate = ["rc_pending"] + [None] * 11 + [[None] * 6 + [["working"]]]
    body = [[[ ["c_abc123", "r_pending"], None, [["pending user"]], [[candidate]] ]]]

    assert latest_chat_metadata_from_body(body, "c_abc123") is None
