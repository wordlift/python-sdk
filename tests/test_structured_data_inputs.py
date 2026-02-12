from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from wordlift_sdk.structured_data import inputs


def test_is_url():
    assert inputs.is_url("https://example.com")
    assert inputs.is_url("http://example.com")
    assert not inputs.is_url("ftp://example.com")
    assert not inputs.is_url("example.com")


def test_urls_from_sitemap_prefers_loc_then_url(monkeypatch):
    fake_adv = types.SimpleNamespace(
        sitemap_to_df=lambda _s: pd.DataFrame(
            {
                "loc": ["https://a.example", None, "https://b.example"],
                "url": ["https://ignored.example", None, None],
            }
        )
    )
    monkeypatch.setitem(sys.modules, "advertools", fake_adv)

    out = inputs.urls_from_sitemap("sitemap.xml")
    assert out == ["https://a.example", "https://b.example"]


def test_urls_from_sitemap_uses_url_column_when_loc_missing(monkeypatch):
    fake_adv = types.SimpleNamespace(
        sitemap_to_df=lambda _s: pd.DataFrame({"url": ["https://u.example", ""]})
    )
    monkeypatch.setitem(sys.modules, "advertools", fake_adv)

    out = inputs.urls_from_sitemap("sitemap.xml")
    assert out == ["https://u.example"]


def test_urls_from_sitemap_falls_back_to_first_column(monkeypatch):
    fake_adv = types.SimpleNamespace(
        sitemap_to_df=lambda _s: pd.DataFrame({"first": ["https://f.example", None]})
    )
    monkeypatch.setitem(sys.modules, "advertools", fake_adv)

    out = inputs.urls_from_sitemap("sitemap.xml")
    assert out == ["https://f.example"]


def test_urls_from_sitemap_empty(monkeypatch):
    fake_adv = types.SimpleNamespace(sitemap_to_df=lambda _s: pd.DataFrame())
    monkeypatch.setitem(sys.modules, "advertools", fake_adv)
    assert inputs.urls_from_sitemap("sitemap.xml") == []


def test_urls_from_sitemap_requires_advertools(monkeypatch):
    monkeypatch.delitem(sys.modules, "advertools", raising=False)

    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "advertools":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(RuntimeError, match="advertools is required"):
        inputs.urls_from_sitemap("sitemap.xml")


def test_resolve_input_urls_for_local_file(monkeypatch, tmp_path: Path):
    p = tmp_path / "in.xml"
    p.write_text("<xml/>")
    monkeypatch.setattr(inputs, "urls_from_sitemap", lambda _s: ["https://x.example"])
    assert inputs.resolve_input_urls(str(p)) == ["https://x.example"]


def test_resolve_input_urls_local_file_without_urls(monkeypatch, tmp_path: Path):
    p = tmp_path / "in.xml"
    p.write_text("<xml/>")
    monkeypatch.setattr(inputs, "urls_from_sitemap", lambda _s: [])
    with pytest.raises(RuntimeError, match="No URLs found"):
        inputs.resolve_input_urls(str(p))


def test_resolve_input_urls_remote_sitemap_then_fallback(monkeypatch):
    monkeypatch.setattr(inputs, "urls_from_sitemap", lambda _s: ["https://a.example"])
    assert inputs.resolve_input_urls("https://example.com/sitemap.xml") == [
        "https://a.example"
    ]

    def _raise(_s):
        raise RuntimeError("boom")

    monkeypatch.setattr(inputs, "urls_from_sitemap", _raise)
    assert inputs.resolve_input_urls("https://example.com/page") == [
        "https://example.com/page"
    ]


def test_resolve_input_urls_invalid_input():
    with pytest.raises(RuntimeError, match="INPUT must"):
        inputs.resolve_input_urls("not-a-url")


def test_filter_urls(monkeypatch):
    urls = ["https://a.example/p/1", "https://b.example/p/2", "https://a.example/p/3"]
    out = inputs.filter_urls(urls, r"a\.example", max_pages=1)
    assert out == ["https://a.example/p/1"]

    with pytest.raises(RuntimeError, match="No URLs matched"):
        inputs.filter_urls(urls, r"does-not-match", max_pages=None)
