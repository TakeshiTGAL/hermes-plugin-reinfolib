"""Profile secrets come from agent.secret_scope at call time. Skip when Hermes is absent."""
from __future__ import annotations

import importlib.util
import json
import socket
import urllib.request
from datetime import date
from pathlib import Path

import pytest

import client
import messages
import service

ROOT = Path(__file__).resolve().parents[1]
ARGS = {"city": "13102", "year": 2015, "quarter": 2}
TODAY = date(2026, 10, 12)
BODY = (ROOT / "tests" / "fixtures" / "xit001_ok.json").read_bytes()
ENV_KEY = "env-key-value"
SCOPE_KEY = "scope-key-value"
SCOPE_KEY_TWO = "scope-key-two"


def _release(scope, token):
    if token is not None:
        try:
            scope.reset_secret_scope(token)
        except ValueError:
            pass
    scope.set_secret_scope(None)
    scope.set_multiplex_active(False)


def _quiet_transport(monkeypatch):
    calls = []

    def transport(url, headers, timeout, cap):
        calls.append((url, dict(headers)))
        return 200, {"content-type": "application/json"}, BODY

    monkeypatch.setattr(client, "default_transport", transport)
    monkeypatch.setattr(
        client,
        "DEFAULT_GAP",
        client.Gap(now=lambda: 0.0, sleep=lambda _delay: None),
    )
    return calls


def _handler():
    spec = importlib.util.spec_from_file_location("reinfolib_scope_entry", ROOT / "__init__.py")
    spec.submodule_search_locations = None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    found = {}

    class Ctx:
        def register_tool(self, **kwargs):
            found[kwargs["name"]] = kwargs["handler"]

        def register_command(self, *_args, **_kwargs):
            return None

        def register_skill(self, *_args, **_kwargs):
            return None

    mod.register(Ctx())
    return found["reinfolib_quarter"]


def test_scope_value_is_used_when_environ_differs(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    monkeypatch.setenv("REINFOLIB_API_KEY", ENV_KEY)
    monkeypatch.setenv("REINFOLIB_BASE_URL", "http://127.0.0.1:8")
    calls = _quiet_transport(monkeypatch)
    handler = _handler()
    token = scope.set_secret_scope({
        "REINFOLIB_API_KEY": SCOPE_KEY,
        "REINFOLIB_BASE_URL": "http://127.0.0.1:9",
    })
    try:
        raw = handler(ARGS)
        assert isinstance(raw, str)
        assert calls[0][0].startswith("http://127.0.0.1:9/ex-api/external/XIT001?")
        assert calls[0][1][client.HEADER] == SCOPE_KEY
        assert ENV_KEY not in raw and "127.0.0.1:8" not in calls[0][0]
        scope.reset_secret_scope(token)
        token = scope.set_secret_scope({
            "REINFOLIB_API_KEY": SCOPE_KEY_TWO,
            "REINFOLIB_BASE_URL": "http://127.0.0.1:7",
        })
        handler(ARGS)
        assert calls[1][0].startswith("http://127.0.0.1:7/ex-api/external/XIT001?")
        assert calls[1][1][client.HEADER] == SCOPE_KEY_TWO
    finally:
        _release(scope, token)


def test_multiplex_scope_miss_does_not_read_environ(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    monkeypatch.setenv("REINFOLIB_API_KEY", ENV_KEY)
    monkeypatch.setenv("REINFOLIB_BASE_URL", "http://127.0.0.1:8")
    calls = _quiet_transport(monkeypatch)
    handler = _handler()
    scope.set_multiplex_active(True)
    token = scope.set_secret_scope({"UNRELATED": "present"})
    try:
        raw = handler(ARGS)
    finally:
        _release(scope, token)
    assert isinstance(raw, str)
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert payload["error_type"] == "config"
    assert payload["detail"] == "missing_key"
    assert payload["message"] == messages.MISSING_KEY
    assert calls == []
    assert ENV_KEY not in raw
    assert "127.0.0.1:8" not in raw


def test_unscoped_multiplex_raises_and_does_not_call_upstream(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    monkeypatch.setenv("REINFOLIB_API_KEY", ENV_KEY)
    monkeypatch.setenv("REINFOLIB_BASE_URL", "http://127.0.0.1:8")
    calls = _quiet_transport(monkeypatch)
    handler = _handler()
    scope.set_multiplex_active(True)
    token = scope.set_secret_scope(None)
    try:
        with pytest.raises(scope.UnscopedSecretError):
            handler(ARGS)
    finally:
        _release(scope, token)
    assert calls == []


def test_unset_secret_returns_the_fixed_config_error(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    monkeypatch.delenv("REINFOLIB_API_KEY", raising=False)
    monkeypatch.delenv("REINFOLIB_BASE_URL", raising=False)
    calls = _quiet_transport(monkeypatch)
    scope.set_multiplex_active(False)
    token = scope.set_secret_scope(None)
    try:
        payload = service.quarter(ARGS, today=TODAY)
    finally:
        _release(scope, token)
    assert payload["ok"] is False
    assert payload["error_type"] == "config"
    assert payload["detail"] == "missing_key"
    assert payload["message"] == messages.MISSING_KEY
    assert calls == []


def test_opener_ignores_environment_proxy(monkeypatch):
    passed = []
    real_build = urllib.request.build_opener

    def spy(*handlers):
        passed.append(handlers)
        return real_build(*handlers)

    monkeypatch.setattr(client.urllib.request, "build_opener", spy)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.test:8443")
    monkeypatch.setenv("https_proxy", "http://proxy.test:8443")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.test:8443")
    monkeypatch.setenv("http_proxy", "http://proxy.test:8443")
    targets = []

    def blocked(address, *args, **kwargs):
        targets.append(address)
        raise OSError("blocked")

    monkeypatch.setattr(socket, "create_connection", blocked)
    try:
        client.default_transport(
            "http://127.0.0.1:9/ex-api/external/XIT001",
            {client.HEADER: ENV_KEY},
            1.0,
            64,
        )
    except client.CallError as error:
        assert error.error_type == "upstream" and error.detail == "network"
    else:
        raise AssertionError("transport connected")
    proxies = [handler for handler in passed[0] if isinstance(handler, urllib.request.ProxyHandler)]
    assert len(proxies) == 1 and proxies[0].proxies == {}
    hosts = [item[0] if isinstance(item, tuple) else item for item in targets]
    assert hosts and hosts[0] == "127.0.0.1"
    assert "proxy.test" not in hosts
