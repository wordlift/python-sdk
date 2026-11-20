"""What a URL handler does when the fetched page redirected elsewhere."""

from __future__ import annotations

import logging
from enum import Enum

from ...url_source import Url
from ...utils.url_normalization import is_same_url

logger = logging.getLogger(__name__)

FOLLOW_REDIRECTS_KEY = "FOLLOW_REDIRECTS"


class FollowRedirects(str, Enum):
    """Policy for pages whose final URL differs from the requested URL.

    ``SKIP`` (default) imports nothing. ``IMPORT_FINAL`` imports the final URL
    as a new page, without the requested URL's IRI or import hash.
    """

    SKIP = "skip"
    IMPORT_FINAL = "import_final"

    @classmethod
    def parse(cls, value: object) -> "FollowRedirects":
        if value is None or value == "":
            return cls.SKIP
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as error:
            allowed = ", ".join(policy.value for policy in cls)
            raise ValueError(
                f"Invalid {FOLLOW_REDIRECTS_KEY} value {value!r}; expected one of: {allowed}"
            ) from error


class ImportTarget:
    """The existing IRI and import hash to pass to the import callback."""

    __slots__ = ("existing_web_page_id", "existing_import_hash")

    def __init__(
        self, existing_web_page_id: str | None, existing_import_hash: str | None
    ) -> None:
        self.existing_web_page_id = existing_web_page_id
        self.existing_import_hash = existing_import_hash


def resolve_import_target(
    url: Url, final_url: object, policy: FollowRedirects
) -> ImportTarget | None:
    """Decide how to import a fetched page, or ``None`` to skip it.

    The requested URL's IRI is reused only when the final URL is the same page:
    an IRI is never reused across URLs.
    """
    if not isinstance(final_url, str) or not final_url:
        return ImportTarget(url.iri, url.import_hash)
    if is_same_url(url.value, final_url):
        return ImportTarget(url.iri, url.import_hash)

    logger.info("redirect %s -> %s", url.value, final_url)
    if policy is FollowRedirects.IMPORT_FINAL:
        return ImportTarget(None, None)
    return None
