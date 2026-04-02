import logging
from datetime import datetime, timezone

from ...url_source import Url
from ...workflow.url_handler.url_handler import UrlHandler

logger = logging.getLogger(__name__)


class DefaultUrlHandler(UrlHandler):
    _url_handler_list: list[UrlHandler]

    def __init__(self, url_handler_list: list[UrlHandler]):
        super().__init__()
        self._url_handler_list = url_handler_list
        self._failures: list[tuple[str, Url, str, str]] = []

    @property
    def failures(self) -> list[tuple[str, Url, str, str]]:
        return list(self._failures)

    async def __call__(self, url: Url) -> None:
        for url_handler in self._url_handler_list:
            try:
                await url_handler.__call__(url)
            except Exception as e:
                timestamp = datetime.now(timezone.utc).isoformat()
                self._failures.append(
                    (timestamp, url, type(url_handler).__name__, str(e))
                )
                logger.error(
                    f"Handler {type(url_handler).__name__} errored while handling url {url}: {e}"
                )
