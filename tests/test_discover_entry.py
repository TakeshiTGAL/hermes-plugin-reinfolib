"""Register through Hermes discovery, then call the real tool entry."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

import client
import schema

ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-secret-key-xyz"


def _copy_plugin(dest: Path) -> None:
    dest.mkdir(parents=True)
    for path in ROOT.iterdir():
        if path.name in {".git", ".pytest_cache", "tests", "__pycache__"} or path.name.startswith("."):
            continue
        if path.is_file():
            shutil.copy2(path, dest / path.name)
        elif path.name == "skills":
            shutil.copytree(path, dest / "skills")


def _loaded_client(dest: Path):
    root = str(dest.resolve())
    for mod in sys.modules.values():
        file = getattr(mod, "__file__", None) or ""
        if file.endswith("client.py") and root in str(Path(file).resolve()):
            return mod
    raise AssertionError("discovered plugin did not load client.py")


def test_discover_plugins_then_handle_function_call(monkeypatch, tmp_path):
    plugins = pytest.importorskip("hermes_cli.plugins")
    model_tools = pytest.importorskip("model_tools")
    scope = pytest.importorskip("agent.secret_scope")
    constants = pytest.importorskip("hermes_constants")
    home = tmp_path / "hermes"
    dest = home / "plugins" / "jp-reinfolib"
    _copy_plugin(dest)
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - jp-reinfolib\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("REINFOLIB_API_KEY", KEY)
    monkeypatch.delenv("REINFOLIB_BASE_URL", raising=False)
    override = constants.set_hermes_home_override(str(home))
    scope.set_multiplex_active(False)
    token = scope.set_secret_scope(None)
    plugins._reset_plugin_managers_for_tests()
    calls = []

    def transport(url, headers, timeout, cap):
        calls.append(url)
        return 200, {"content-type": "application/json"}, _body()

    try:
        assert Path(constants.get_hermes_home()).resolve() == home.resolve()
        plugins.discover_plugins(force=True)
        loaded = _loaded_client(dest)
        loaded.default_transport = transport
        loaded.DEFAULT_GAP = client.Gap(now=lambda: 0.0, sleep=lambda _delay: None)
        refused = json.loads(model_tools.handle_function_call(
            "reinfolib_quarter", {"city": "新宿区", "year": 2025, "quarter": 2},
        ))
        assert refused["detail"] == "bad_city"
        assert "新宿区" not in json.dumps(refused, ensure_ascii=False)
        assert calls == []
        seen = json.loads(model_tools.handle_function_call(
            "reinfolib_quarter", {"city": "13104", "year": 2015, "quarter": 2},
        ))
        assert seen["ok"] is True and seen["count"] == 1 and seen["city"] == "13104"
        assert seen["fetched_at"].endswith("Z")
        assert calls and "city=13104" in calls[0]
    finally:
        scope.reset_secret_scope(token)
        scope.set_multiplex_active(False)
        constants.reset_hermes_home_override(override)
        plugins._reset_plugin_managers_for_tests()


def _body() -> bytes:
    row = {column["name"]: column["sample"] for column in schema.COLUMNS}
    row["MunicipalityCode"] = "13104"
    return json.dumps({"status": "OK", "data": [row]}, ensure_ascii=False).encode()
