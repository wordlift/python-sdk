from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

import wordlift_sdk.kg_build.postprocessors.processors.slug as slug_module
from wordlift_sdk.kg_build.postprocessors.processors.slug import (
    identity_slug,
    normalize_slug,
)


@pytest.mark.parametrize(
    ("value", "language", "expected"),
    [
        ("  Hello__World!! ", None, "hello-world"),
        ("Müller Straße", "de-DE", "mueller-strasse"),
        ("MÜLLER", " DE_de ", "mueller"),
        ("Müller", "tr", "muller"),
        ("ışık", "tr", "isik"),
        ("Łódź smørrebrød", None, "lodz-smorrebrod"),
        ("Москва", "ru", "moskva"),
        ("Київ", "uk", "kyyiv"),
        ("Αθήνα", "el", "athena"),
        ("مرحبا", "ar", "mrhba"),
        ("שלום", "he", "slwm"),
        ("東京", "zh-Hant-TW", "dong-jing"),
        ("東京", "zh-Hant-x-foo", "dong-jing"),
        ("東京", "zh-u-co-pinyin", "dong-jing"),
        ("東京", "cmn-Hans-CN", "dong-jing"),
        ("東京", "ja", "thing"),
        ("東京", "yue", "thing"),
        ("東京", "zh-yue-Hant", "thing"),
        ("東京", "zh-min-nan", "thing"),
        ("東京", None, "thing"),
        ("Москва", "unknown", "thing"),
        ("ひらがな カタカナ ｶﾀｶﾅ", "ja", "hiragana-katakana-katakana"),
        ("서울", "ko", "seoul"),
        ("हिन्दी", "hi", "hindi"),
        ("", None, "thing"),
        ("! 🎉 !", None, "thing"),
    ],
)
def test_readable_transliteration(value, language, expected) -> None:
    assert normalize_slug(value, language) == expected


def test_identity_keeps_original_non_ascii_distinctions() -> None:
    digest = hashlib.sha256("müller".encode("utf-8")).hexdigest()
    assert identity_slug("Müller", "de") == f"mueller-{digest}"
    assert identity_slug("Mueller", "de") == "mueller"
    assert identity_slug("Müller", "de", has_url=True) == "mueller"
    assert identity_slug("東京", "ja") != identity_slug("大阪", "ja")
    assert identity_slug("Tokyo 東京", "ja") != identity_slug("Tokyo 大阪", "ja")
    assert identity_slug("Tokyo 東京", "ja").startswith("tokyo-")


def test_equivalent_unicode_case_and_whitespace_have_identical_ids() -> None:
    assert identity_slug("  MÜLLER ", "de") == identity_slug("Mu\u0308ller", "de")
    assert normalize_slug("Mu\u0308ller", "de") == "mueller"


def test_ascii_compatibility_and_empty_fallback() -> None:
    assert identity_slug(" Hello__World!! ") == "hello-world"
    assert identity_slug("!!!") == "thing"
    assert identity_slug("") == "thing"
    assert identity_slug("🎉").startswith("thing-")


def test_concurrent_languages_do_not_share_transform_state() -> None:
    inputs = [("Müller", "de"), ("Müller", "tr"), ("東京", "ja"), ("東京", "zh")] * 8
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda args: normalize_slug(*args), inputs))
    assert results == ["mueller", "muller", "thing", "dong-jing"] * 8


@pytest.mark.parametrize("language", ["de", "tr", "ja"])
def test_unsupported_icu_version_fails_before_transliteration(monkeypatch, language):
    monkeypatch.setattr(slug_module, "ICU_VERSION", "78.0")
    with pytest.raises(RuntimeError, match="Install ICU 74.2 and rebuild PyICU"):
        normalize_slug("Müller", language)
    assert normalize_slug("Hello World", language) == "hello-world"


def test_surrounding_unicode_whitespace_does_not_change_identity() -> None:
    assert identity_slug("\u00a0hello") == identity_slug("hello")
