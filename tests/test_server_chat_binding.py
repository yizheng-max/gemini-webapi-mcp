import asyncio
import json
from types import SimpleNamespace

from gemini_webapi_mcp import server


class FakeChat:
    def __init__(self, response_text="ok"):
        self.response_text = response_text
        self.prompts = []

    async def send_message(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(text=self.response_text, thoughts=None)


class FakeClient:
    def __init__(self, read_body):
        self.read_body = read_body
        self.batch_payloads = []
        self.started_chats = []
        self.generated_prompts = []

    async def _batch_execute(self, payloads):
        self.batch_payloads.append(payloads)
        frame = [["wrb.fr", "hNvQHb", json.dumps(self.read_body)]]
        return SimpleNamespace(text=json.dumps(frame))

    def start_chat(self, *, model, metadata=None):
        chat = FakeChat()
        self.started_chats.append((model, metadata, chat))
        return chat

    async def generate_content(self, prompt, *, model):
        self.generated_prompts.append((prompt, model))
        return SimpleNamespace(text="stateless", thoughts=None)


class AckThenDataClient(FakeClient):
    async def _batch_execute(self, payloads):
        self.batch_payloads.append(payloads)
        frames = [
            ["wrb.fr", "hNvQHb", "null"],
            ["wrb.fr", "generic", json.dumps(self.read_body)],
        ]
        return SimpleNamespace(text=json.dumps(frames))


def make_context(client, sessions=None):
    state = {"gemini_client": client, "chat_sessions": sessions or {}}
    return SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=state)
    )


def completed_chat_body(cid="c_abc123", rid="r_latest", rcid="rc_latest"):
    return [[[[cid, rid], None, [["latest user"]], [[[rcid]]]]]]


def test_bind_chat_reads_conversation_and_persists_binding(tmp_path, monkeypatch):
    binding_file = tmp_path / "bound-chat.json"
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))
    client = FakeClient(completed_chat_body())

    result = asyncio.run(
        server.gemini_bind_chat(
            "https://gemini.google.com/app/abc123",
            make_context(client),
            model="gemini-3.0-pro",
        )
    )

    assert json.loads(result) == {
        "bound": True,
        "chat_id": "c_abc123",
        "model": "gemini-3.0-pro",
    }
    assert json.loads(binding_file.read_text(encoding="utf-8")) == {
        "cid": "c_abc123",
        "model": "gemini-3.0-pro",
    }
    assert len(client.batch_payloads) == 1


def test_chat_syncs_and_continues_the_bound_browser_conversation(tmp_path, monkeypatch):
    binding_file = tmp_path / "bound-chat.json"
    binding_file.write_text(
        json.dumps({"cid": "c_abc123", "model": "gemini-3.0-pro"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))
    client = FakeClient(completed_chat_body())

    result = asyncio.run(server.gemini_chat("continue here", make_context(client)))

    assert result == "ok"
    assert len(client.batch_payloads) == 1
    assert len(client.started_chats) == 1
    model, metadata, chat = client.started_chats[0]
    assert model == "gemini-3.0-pro"
    assert metadata == ["c_abc123", "r_latest", "rc_latest"]
    assert chat.prompts == ["continue here"]
    assert client.generated_prompts == []


def test_temporary_session_takes_precedence_over_bound_chat(tmp_path, monkeypatch):
    binding_file = tmp_path / "bound-chat.json"
    binding_file.write_text(
        json.dumps({"cid": "c_abc123", "model": "gemini-3.0-pro"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))
    temporary_chat = FakeChat("temporary")
    client = FakeClient(completed_chat_body())

    result = asyncio.run(
        server.gemini_chat(
            "temporary turn",
            make_context(client, {"temp123": temporary_chat}),
            session_id="temp123",
        )
    )

    assert result == "temporary"
    assert temporary_chat.prompts == ["temporary turn"]
    assert client.batch_payloads == []
    assert client.started_chats == []
    assert client.generated_prompts == []


def test_binding_status_reports_saved_chat_without_reading_conversation(tmp_path, monkeypatch):
    binding_file = tmp_path / "bound-chat.json"
    binding_file.write_text(
        json.dumps({"cid": "c_abc123", "model": "gemini-3.0-pro"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))

    result = asyncio.run(server.gemini_binding_status())

    assert json.loads(result) == {
        "bound": True,
        "chat_id": "c_abc123",
        "model": "gemini-3.0-pro",
    }


def test_unbind_removes_binding_and_restores_stateless_chat(tmp_path, monkeypatch):
    binding_file = tmp_path / "bound-chat.json"
    binding_file.write_text(
        json.dumps({"cid": "c_abc123", "model": "gemini-3.0-pro"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))
    client = FakeClient(completed_chat_body())

    unbind_result = asyncio.run(server.gemini_unbind_chat())
    chat_result = asyncio.run(server.gemini_chat("fresh", make_context(client)))

    assert json.loads(unbind_result) == {
        "bound": False,
        "removed_chat_id": "c_abc123",
    }
    assert not binding_file.exists()
    assert chat_result == "stateless"
    assert client.generated_prompts == [("fresh", server.DEFAULT_MODEL)]
    assert client.batch_payloads == []


def test_bind_does_not_persist_an_unreadable_or_incomplete_conversation(
    tmp_path, monkeypatch
):
    binding_file = tmp_path / "bound-chat.json"
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))
    incomplete = [[[["c_abc123", "r_pending"], None, [["user"]], []]]]
    client = FakeClient(incomplete)

    result = asyncio.run(
        server.gemini_bind_chat("abc123", make_context(client))
    )

    assert result.startswith("Error: RuntimeError — Gemini conversation could not be read")
    assert not binding_file.exists()


def test_bound_chat_waits_for_incomplete_browser_turn_without_falling_back(
    tmp_path, monkeypatch
):
    binding_file = tmp_path / "bound-chat.json"
    binding_file.write_text(
        json.dumps({"cid": "c_abc123", "model": None}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))
    incomplete = [[[["c_abc123", "r_pending"], None, [["user"]], []]]]
    client = FakeClient(incomplete)

    result = asyncio.run(server.gemini_chat("do not misroute", make_context(client)))

    assert "newest response is still incomplete" in result
    assert client.started_chats == []
    assert client.generated_prompts == []


def test_bind_skips_null_ack_frame_and_reads_following_data_frame(
    tmp_path, monkeypatch
):
    binding_file = tmp_path / "bound-chat.json"
    monkeypatch.setenv("GEMINI_BINDING_FILE", str(binding_file))
    client = AckThenDataClient(completed_chat_body())

    result = asyncio.run(
        server.gemini_bind_chat("abc123", make_context(client))
    )

    assert json.loads(result)["bound"] is True
