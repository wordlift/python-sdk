"""Language-aware ASCII slugs and stable identity suffixes."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from icu import ICU_VERSION, Transliterator


_TRANSFORMS = {
    "ru": "Russian-Latin/BGN",
    "uk": "Ukrainian-Latin/BGN",
    "el": "Greek-Latin",
    "ar": "Arabic-Latin",
    "he": "Hebrew-Latin",
    "ja": "Hiragana-Latin; Katakana-Latin",
    "ko": "Hangul-Latin",
    "hi": "Devanagari-Latin",
}
_GERMAN_REPLACEMENTS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
)


def _language_parts(language: str | None) -> list[str]:
    return (language or "").strip().lower().replace("_", "-").split("-")


def _transform(language: str | None) -> str:
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
    route = "Han-Latin" if mandarin else _TRANSFORMS.get(primary)
    return f"{route}; Latin-ASCII" if route else "Latin-ASCII"


def normalize_slug(value: str, language: str | None = None) -> str:
    """Return a readable ASCII slug; unsupported script text is omitted.

    Use ``identity_slug`` when the result identifies an entity: transliteration
    is lossy, and unsupported text alone yields the readable fallback ``thing``.
    """
    value = unicodedata.normalize("NFC", value)
    if not value.isascii() and ICU_VERSION != "74.2":
        raise RuntimeError(
            "Canonical ID transliteration requires ICU 74.2 for stable output; "
            f"found ICU {ICU_VERSION}. Install ICU 74.2 and rebuild PyICU against it."
        )
    if _language_parts(language)[0] == "de":
        value = value.translate(_GERMAN_REPLACEMENTS)
    if not value.isascii():
        # ICU objects are mutable: each call owns its transform, including when
        # ingestion workers normalize slugs concurrently.
        transform = Transliterator.createInstance(_transform(language))
        value = transform.transliterate(value)
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
