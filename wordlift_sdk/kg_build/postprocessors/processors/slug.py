"""Language-aware ASCII slugs and stable identity suffixes."""

from __future__ import annotations

import functools
import hashlib
import re
import unicodedata

import regex
from anyascii import __version__ as ANYASCII_VERSION, anyascii

# Slugs are part of canonical IRIs, so the transliteration backend is pinned:
# a different anyascii release can romanize differently and mint new IRIs.
# Upgrading it is an ID migration (impact check and cleanup), not a bump.
_EXPECTED_ANYASCII_VERSION = "0.3.3"

# Scripts transliterated only for the languages below, as Unicode script
# properties; elsewhere they are dropped rather than given a guessed reading.
_SCRIPTS = {
    "ru": r"\p{Cyrillic}",
    "uk": r"\p{Cyrillic}",
    "el": r"\p{Greek}",
    "ar": r"\p{Arabic}",
    "he": r"\p{Hebrew}",
    # Kana only, not kanji; the prolonged sound mark (ー, ｰ) is Common script.
    "ja": r"\p{Hiragana}\p{Katakana}\u30fc\uff70",
    "ko": r"\p{Hangul}",
    "hi": r"\p{Devanagari}",
}
_HAN = r"\p{Han}"
_HAN_CHAR = regex.compile(_HAN)
_GERMAN_REPLACEMENTS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
)


def _language_parts(language: str | None) -> list[str]:
    return (language or "").strip().lower().replace("_", "-").split("-")


def _script(language: str | None) -> str:
    parts = _language_parts(language)
    primary = parts[0]
    # Han readings are Mandarin only. Do not apply them to Cantonese (including
    # zh-yue), other Chinese extlangs, Japanese kanji, or an unknown language.
    mandarin = primary in {"zh", "cmn"}
    for part in parts[1:]:
        # Extlangs precede script/region/extension/private-use subtags.
        if len(part) != 3 or not part.isalpha():
            break
        if part != "cmn":
            mandarin = False
            break
    return _HAN if mandarin else _SCRIPTS.get(primary, "")


def _letters(char: str) -> str:
    # anyascii spells some letters with punctuation (Arabic ain as a backtick,
    # the Cyrillic soft sign as an apostrophe); keep a letter within its word.
    return re.sub(r"[^A-Za-z0-9]", "", anyascii(char))


@functools.lru_cache(maxsize=None)
def _transliterable(script: str) -> regex.Pattern[str]:
    # Latin letters in every language, the language's own script (letters and
    # its own signs, such as Devanagari vowel signs), and digits.
    return regex.compile(
        rf"[[\p{{Latin}}{script}]&&[\p{{L}}\p{{Mn}}\p{{Mc}}]]|\p{{Nd}}", regex.V1
    )


def _transliterate(value: str, language: str | None) -> str:
    script = _script(language)
    transliterable = _transliterable(script)
    parts = []
    for char in value:
        if char.isascii():
            parts.append(char)
        elif regex.match(r"\p{Inherited}", char):
            # Combining accents are removed without splitting the word.
            continue
        elif transliterable.match(char):
            # One syllable per Han character: keep syllables apart.
            text = _letters(char)
            parts.append(f" {text} " if _HAN_CHAR.match(char) else text)
        else:
            # Symbols, emoji and unsupported scripts become separators.
            parts.append(" ")
    return "".join(parts)


def normalize_slug(value: str, language: str | None = None) -> str:
    """Return a readable ASCII slug; unsupported script text is omitted.

    Use ``identity_slug`` when the result identifies an entity: transliteration
    is lossy, and unsupported text alone yields the readable fallback ``thing``.
    """
    value = unicodedata.normalize("NFC", value)
    if not value.isascii() and ANYASCII_VERSION != _EXPECTED_ANYASCII_VERSION:
        raise RuntimeError(
            "Canonical ID transliteration requires anyascii "
            f"{_EXPECTED_ANYASCII_VERSION} for stable output; found "
            f"{ANYASCII_VERSION}. Install "
            f'"anyascii=={_EXPECTED_ANYASCII_VERSION}" (the kg-build extra pins it).'
        )
    if _language_parts(language)[0] == "de":
        value = value.translate(_GERMAN_REPLACEMENTS)
    if not value.isascii():
        value = _transliterate(value, language)
    lowered = value.strip().lower()
    lowered = re.sub(r"[^\w\s-]", " ", lowered, flags=re.ASCII)
    lowered = re.sub(r"[_\s]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "thing"


def identity_slug(
    value: str, language: str | None = None, *, has_url: bool = False
) -> str:
    """Disambiguate non-ASCII input unless the caller supplies a URL hash."""
    slug = normalize_slug(value, language)
    digest = source_digest(value) if not has_url else None
    if digest is not None:
        return f"{slug}-{digest}"
    return slug


def source_digest(value: str) -> str | None:
    """Stable identity for non-ASCII source text, independent of romanization."""
    normalized = unicodedata.normalize("NFC", value.strip())
    if normalized.isascii():
        return None
    original = unicodedata.normalize("NFC", normalized.strip().lower())
    return hashlib.sha256(original.encode("utf-8")).hexdigest()
