from __future__ import annotations

import importlib
import sys
import types

cfg = importlib.import_module("wordlift_sdk.configuration.get_config_value")


def test_load_config_py_missing_or_empty_path(tmp_path):
    assert cfg.load_config_py("") == {}
    assert cfg.load_config_py(None) == {}
    assert cfg.load_config_py(str(tmp_path / "missing.py")) == {}


def test_load_config_py_reads_public_symbols(tmp_path):
    config_path = tmp_path / "config.py"
    config_path.write_text("A = 1\n_B = 2\nNAME = 'x'\n")

    loaded = cfg.load_config_py(str(config_path))
    assert loaded["A"] == 1
    assert loaded["NAME"] == "x"
    assert "_B" not in loaded


def test_get_config_value_precedence_globals_config_env_default(tmp_path, monkeypatch):
    key = "WL_TEST_KEY"

    # global wins over all
    monkeypatch.setitem(cfg.__dict__, key, "from-global")
    monkeypatch.setenv(key, "from-env")
    config_path = tmp_path / "config.py"
    config_path.write_text(f"{key} = 'from-config'\n")
    assert (
        cfg.get_config_value(key, config_py_path=str(config_path), default="fallback")
        == "from-global"
    )

    # remove global: config wins over env
    cfg.__dict__.pop(key, None)
    assert (
        cfg.get_config_value(key, config_py_path=str(config_path), default="fallback")
        == "from-config"
    )

    # remove config: env wins
    config_path.write_text("OTHER = 1\n")
    assert (
        cfg.get_config_value(key, config_py_path=str(config_path), default="fallback")
        == "from-env"
    )

    # remove env: default is returned
    monkeypatch.delenv(key, raising=False)
    assert (
        cfg.get_config_value(key, config_py_path=str(config_path), default="fallback")
        == "fallback"
    )


def test_get_config_value_colab_secret(monkeypatch):
    key = "WL_COLAB_SECRET"

    class _UserData:
        @staticmethod
        def get(name):
            return "secret-value" if name == key else None

    colab_module = types.ModuleType("google.colab")
    colab_module.userdata = _UserData
    google_module = types.ModuleType("google")
    google_module.colab = colab_module

    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.colab", colab_module)

    assert cfg.get_config_value(key, config_py_path="", default=None) == "secret-value"


def test_get_config_value_colab_import_error(monkeypatch):
    key = "WL_COLAB_MISSING"

    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.delitem(sys.modules, "google.colab", raising=False)

    assert (
        cfg.get_config_value(key, config_py_path="", default="fallback") == "fallback"
    )


def test_load_config_py_spec_without_loader(monkeypatch):
    # Simulate importlib returning an unusable spec.
    monkeypatch.setattr(cfg.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(
        cfg.importlib.util, "spec_from_file_location", lambda *_a, **_k: None
    )
    assert cfg.load_config_py("config.py") == {}
