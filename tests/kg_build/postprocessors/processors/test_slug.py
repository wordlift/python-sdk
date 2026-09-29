from __future__ import annotations

import hashlib
import random
import re
import string
import subprocess
import sys
import textwrap
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pytest

import wordlift_sdk.kg_build.postprocessors.processors.slug as slug_module
from wordlift_sdk.kg_build.postprocessors.processors.slug import (
    identity_slug,
    normalize_slug,
    source_digest,
)


def _released_normalize_slug(value: str) -> str:
    """``normalize_slug`` as released in 8.4.7, before transliteration."""
    lowered = value.strip().lower()
    lowered = re.sub(r"[^\w\s-]", " ", lowered)
    lowered = re.sub(r"[_\s]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "thing"


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
        ("Київ", "uk", "kiiv"),
        ("Αθήνα", "el", "athina"),
        ("مرحبا", "ar", "mrhb"),
        ("שלום", "he", "slvm"),
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


def test_concurrent_calls_agree_with_serial_calls() -> None:
    inputs = [
        ("Müller", "de"),
        ("Москва", "ru"),
        ("مرحبا", "ar"),
        ("서울", "ko"),
        ("カタカナ", "ja"),
        ("北京大学", "zh"),
        ("Nguyễn", "vi"),
        ("🎉 Party", None),
    ] * 16
    serial = [identity_slug(*args) for args in inputs]
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(lambda args: identity_slug(*args), inputs)) == serial


@pytest.mark.parametrize("language", ["de", "tr", "ja"])
def test_unpinned_backend_version_fails_before_transliteration(monkeypatch, language):
    monkeypatch.setattr(slug_module, "ANYASCII_VERSION", "0.4.0")
    with pytest.raises(RuntimeError, match=r'Install "anyascii==0\.3\.3"'):
        normalize_slug("Müller", language)
    assert normalize_slug("Hello World", language) == "hello-world"


def test_surrounding_unicode_whitespace_does_not_change_identity() -> None:
    assert identity_slug("\u00a0hello") == identity_slug("hello")


@pytest.mark.parametrize(
    "value",
    [
        "Hello World",
        "  Hello__World!! ",
        "MiXeD CaSe",
        "a--b__c  d",
        "--edge--",
        "tabs\tand\nnewlines",
        "dots.and/slashes\\back",
        "C++ & C#",
        "100% (approx.)",
        "snake_case_name",
        "",
        "   ",
        "!!!",
        "@#$%^&*()",
        "-_-",
    ],
)
@pytest.mark.parametrize("language", [None, "de", "zh", "ja", "ru"])
def test_ascii_slugs_match_the_released_sdk(value, language) -> None:
    assert normalize_slug(value, language) == _released_normalize_slug(value)
    assert identity_slug(value, language) == _released_normalize_slug(value)


def test_random_ascii_slugs_match_the_released_sdk() -> None:
    rng = random.Random(20260929)
    alphabet = string.printable + "____----    "
    for _ in range(5000):
        value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        language = rng.choice([None, "de", "zh-Hant-TW", "ja", "ar"])
        assert normalize_slug(value, language) == _released_normalize_slug(value)


@pytest.mark.parametrize(
    ("value", "language", "expected"),
    [
        ("São Paulo", "pt", "sao-paulo"),
        ("Açaí Coração", "pt-BR", "acai-coracao"),
        ("España Peña", "es", "espana-pena"),
        ("Crème brûlée", "fr", "creme-brulee"),
        ("Cœur Œuvre", "fr", "coeur-oeuvre"),
        ("Perché più", "it", "perche-piu"),
        ("Łódź Gdańsk Źrebię", "pl", "lodz-gdansk-zrebie"),
        ("Müller", "it", "muller"),
        ("Straße", None, "strasse"),
        ("Æsir Ærø", "da", "aesir-aero"),
        ("Đà Nẵng", "vi", "da-nang"),
        ("Nguyễn Thị Minh Khai", "vi", "nguyen-thi-minh-khai"),
        ("Şişli Ağaç İstanbul", "tr", "sisli-agac-istanbul"),
        ("Björk Guðmundsdóttir", "is", "bjork-gudmundsdottir"),
        ("Þór", "is", "thor"),
        ("Ǆemal", "hr", "dzemal"),
        ("ﬁnance", None, "finance"),
        ("Ｔｏｋｙｏ　２０２４", None, "tokyo-2024"),
        # Decomposed accents are removed without splitting the word.
        ("q\u0303x", None, "qx"),
        ("Mu\u0308ller", "tr", "muller"),
        ("Əliyev", "az", "eliyev"),
        # Latin-1 symbols are not letters.
        ("2×3÷4", None, "2-3-4"),
    ],
)
def test_latin_letters_fold_to_ascii_in_every_language(value, language, expected):
    assert normalize_slug(value, language) == expected


@pytest.mark.parametrize(
    ("value", "language", "expected"),
    [
        ("北京大学", "zh", "bei-jing-da-xue"),
        ("北京大学", "zh-Hans-CN", "bei-jing-da-xue"),
        ("北京大学", "cmn", "bei-jing-da-xue"),
        # One reading per character, even where context changes it.
        ("重庆", "zh-CN", "zhong-qing"),
        ("iPhone手机", "zh", "iphone-shou-ji"),
        # Only Han characters are split into syllables; other letters stay whole.
        ("Crème brûlée", "zh", "creme-brulee"),
        ("Hà Nội 北京", "zh", "ha-noi-bei-jing"),
        ("２０２４年", "zh", "2024-nian"),
        ("2024年", "zh", "2024-nian"),
        # Kanji are not given Mandarin readings; kana still transliterate.
        ("東京タワー", "ja", "tawa"),
        # The prolonged sound mark stays within the word.
        ("コーヒー", "ja", "kohi"),
        ("ｺｰﾋｰ", "ja", "kohi"),
        ("ジョン・スミス", "ja", "jiyon-sumisu"),  # middle dot separates words
        ("東京タワー", "zh", "dong-jing"),
        ("香港", "yue", "thing"),
        ("香港", "zh-yue", "thing"),
        ("香港", "zh-min-nan", "thing"),
        ("香港", "ko", "thing"),
        ("香港", None, "thing"),
    ],
)
def test_han_readings_are_mandarin_only(value, language, expected) -> None:
    assert normalize_slug(value, language) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Coca-Cola®", "coca-cola"),
        ("© 2024 ACME™", "2024-acme"),
        ("🍭 Candy", "candy"),
        ("Family 👨\u200d👩\u200d👧", "family"),
        ("½ price", "price"),
        ("Ⅻ Chapter", "chapter"),
        ("5㎏ bag", "5-bag"),
        ("m² price", "m-price"),
        ("€ 10", "10"),
        ("🎉🍭", "thing"),
    ],
)
@pytest.mark.parametrize("language", [None, "de", "ar", "zh"])
def test_symbols_and_emoji_are_dropped(value, language, expected) -> None:
    assert normalize_slug(value, language) == expected


@pytest.mark.parametrize(
    ("value", "language", "expected"),
    [
        ("١٢٣ مرحبا", "ar", "123-mrhb"),
        ("؋ ﷼ ﷽", "ar", "thing"),
        ("҂ ҈", "ru", "thing"),
        ("϶", "el", "thing"),
    ],
)
def test_script_signs_are_dropped_and_digits_kept(value, language, expected):
    assert normalize_slug(value, language) == expected


@pytest.mark.parametrize(
    ("value", "language", "expected"),
    [
        # anyascii spells these letters with punctuation; they stay in the word.
        ("سعيد", "ar", "syd"),
        ("Ильич", "ru", "ilich"),
        ("こゝろ", "ja", "koro"),
        ("ϗ", "el", "thing"),
        # Devanagari has no inherent vowel in anyascii: readable, not idiomatic.
        ("नमस्ते", "hi", "nmste"),
    ],
)
def test_script_letters_do_not_split_words(value, language, expected):
    assert normalize_slug(value, language) == expected


@pytest.mark.parametrize("value", ["Müller", "東京", "Москва", "🎉", "  Ärger "])
def test_source_digest_ignores_the_transliteration_backend(monkeypatch, value):
    expected = hashlib.sha256(
        unicodedata.normalize("NFC", value.strip().lower()).encode("utf-8")
    ).hexdigest()
    assert source_digest(value) == expected
    monkeypatch.setattr(slug_module, "anyascii", lambda text: "changed")
    assert source_digest(value) == expected
    assert identity_slug(value, "ru").endswith(f"-{expected}")


def test_repeated_calls_are_deterministic() -> None:
    inputs = [("Müller", "de"), ("北京大学", "zh"), ("Москва", "ru"), ("🎉", None)]
    first = [identity_slug(value, language) for value, language in inputs]
    for _ in range(3):
        assert [identity_slug(value, language) for value, language in inputs] == first


def test_missing_backend_fails_loudly_with_the_extra_hint() -> None:
    script = textwrap.dedent(
        """
        import sys

        sys.modules["anyascii"] = None
        import wordlift_sdk.kg_build as kg_build

        try:
            kg_build.IdAllocator
        except ModuleNotFoundError as exc:
            print(exc)
        else:
            raise SystemExit("IdAllocator resolved without anyascii")
        try:
            import wordlift_sdk.kg_build.postprocessors.processors.slug
        except ModuleNotFoundError as exc:
            print(exc.name)
        else:
            raise SystemExit("slug imported without anyascii")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    hint, missing = result.stdout.splitlines()
    assert "wordlift-sdk[kg-build]" in hint
    assert missing == "anyascii"
