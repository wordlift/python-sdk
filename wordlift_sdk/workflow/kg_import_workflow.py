import logging
from os import cpu_count
from pathlib import Path

from tqdm.asyncio import tqdm

from .url_handler.url_handler import UrlHandler
from ..graph.ttl_liquid import TtlLiquidGraphFactory
from ..protocol import (
    Context,
)
from ..url_source import UrlSource
from ..utils import create_delayed

logger = logging.getLogger(__name__)


class KgImportWorkflow:
    _concurrency: int
    _context: Context
    _url_handler: UrlHandler
    _url_source: UrlSource

    def __init__(
        self,
        context: Context,
        url_source: UrlSource,
        url_handler: UrlHandler,
        concurrency: int = min(cpu_count(), 4),
    ) -> None:
        self._context = context
        self._url_source = url_source
        self._url_handler = url_handler
        self._concurrency = concurrency

    async def run(self):
        await TtlLiquidGraphFactory(
            context=self._context, path=Path("data/templates")
        ).graphs()

        url_list = [url async for url in self._url_source.urls()]

        logger.info("Applying %d URL import request(s)" % len(url_list))

        delayed = create_delayed(self._url_handler, self._concurrency)
        await tqdm.gather(
            *[delayed(url) for url in list(url_list)],
            total=len(url_list),
        )
