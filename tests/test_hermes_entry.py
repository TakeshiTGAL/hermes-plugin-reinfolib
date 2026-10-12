"""The model sees a JSON string. Hermes drops any other handler result."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

import client
import messages

ROOT = Path(__file__).resolve().parents[1]
ARGS = {"city": "13102", "year": 2015, "quarter": 2}
KEY = "unit-secret-key-xyz"
ROW = json.loads((ROOT / "tests" / "fixtures" / "xit001_ok.json").read_text(encoding="utf-8"))["data"][0]


def _plugin():
    spec = importlib.util.spec_from_file_location("reinfolib_entry", ROOT / "__init__.py")
    spec.submodule_search_locations = None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    found = {}

    class Ctx:
        def register_tool(self, **kwargs):
            found["tool"] = kwargs

        def register_command(self, name, handler, description=""):
            found["slash"] = handler

        def register_skill(self, *_args, **_kwargs):
            return None

    mod.register(Ctx())
    return found


def _quiet(monkeypatch, status, body):
    def transport(url, headers, timeout, cap):
        calls.append((url, dict(headers)))
        return status, {"content-type": "application/json"}, body

    calls = []
    monkeypatch.setattr(client, "default_transport", transport)
    monkeypatch.setattr(client, "DEFAULT_GAP", client.Gap(now=lambda: 0.0, sleep=lambda _delay: None))
    return calls


def _register(monkeypatch):
    registry_mod = pytest.importorskip("tools.registry")
    model_tools = pytest.importorskip("model_tools")
    scope = pytest.importorskip("agent.secret_scope")
    scope.set_multiplex_active(False)
    scope.set_secret_scope(None)
    plugin = _plugin()
    tool = plugin["tool"]
    registry_mod.registry.register(
        name=tool["name"],
        toolset=tool["toolset"],
        schema=tool["schema"],
        handler=tool["handler"],
        override=True,
    )
    return registry_mod.registry, model_tools, plugin["slash"]


def _seen(raw):
    assert isinstance(raw, str)
    payload = json.loads(raw)
    assert payload.get("error_type") != "tool_result_contract"
    assert "unsupported result type" not in raw
    return payload


def test_dispatch_and_handle_function_call_show_count_and_excerpt(monkeypatch):
    registry, model_tools, slash = _register(monkeypatch)
    monkeypatch.setenv("REINFOLIB_API_KEY", KEY)
    monkeypatch.delenv("REINFOLIB_BASE_URL", raising=False)
    body = json.dumps({"status": "OK", "data": [ROW] * 21}).encode()
    calls = _quiet(monkeypatch, 200, body)
    dispatched = _seen(registry.dispatch("reinfolib_quarter", ARGS))
    handled = _seen(model_tools.handle_function_call("reinfolib_quarter", ARGS))
    for payload in (dispatched, handled):
        assert payload["ok"] is True
        assert payload["count"] == 21
        assert payload["truncated"] is True
        assert len(payload["records"]) == 20
        assert payload["records"][0]["TradePrice"] == "0"
        assert KEY not in json.dumps(payload)
    text = asyncio.run(slash("13102 2015 2"))
    slash_payload = _seen(text)
    assert slash_payload["count"] == 21 and len(slash_payload["records"]) == 20
    assert calls and calls[0][1][client.HEADER] == KEY


def test_dispatch_shows_404_missing_key_and_bad_arguments(monkeypatch):
    registry, model_tools, slash = _register(monkeypatch)
    monkeypatch.setenv("REINFOLIB_API_KEY", KEY)
    calls = _quiet(monkeypatch, 404, b'{"message":"upstream text"}')
    for entry in (
        lambda args: registry.dispatch("reinfolib_quarter", args),
        lambda args: model_tools.handle_function_call("reinfolib_quarter", args),
    ):
        missing = _seen(entry({"year": 2015, "quarter": 2}))
        assert missing["error_type"] == "invalid_argument" and missing["detail"] == "missing_argument"
        assert missing["message"] == messages.ERRORS["invalid_argument"]
        not_found = _seen(entry(ARGS))
        assert not_found["error_type"] == "not_found" and not_found["status_code"] == 404
        assert not_found["message"] == messages.ERRORS["not_found"]
        assert "upstream text" not in json.dumps(not_found)
        assert "not separated" in not_found["message"]
    monkeypatch.delenv("REINFOLIB_API_KEY", raising=False)
    before = len(calls)
    for entry in (
        lambda args: registry.dispatch("reinfolib_quarter", args),
        lambda args: model_tools.handle_function_call("reinfolib_quarter", args),
    ):
        bare = _seen(entry(ARGS))
        assert bare["error_type"] == "config" and bare["detail"] == "missing_key"
        assert bare["message"] == messages.MISSING_KEY
        assert "REINFOLIB_API_KEY" in bare["message"]
    assert len(calls) == before
    slash_text = asyncio.run(slash("13102 2004 2"))
    refused = _seen(slash_text)
    assert refused["error_type"] == "invalid_argument" and refused["detail"] == "bad_year"
