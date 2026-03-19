from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rdflib import Graph
from wordlift_client.models.web_page_scrape_response import WebPageScrapeResponse
from wordlift_sdk.protocol import Context

from .config import ProfileDefinition
from .id_allocator import IdAllocator
from .postprocessors import (
    PostprocessorContext,
    PostprocessorResult,
    close_loaded_postprocessors,
    load_postprocessors_for_profile,
)

logger = logging.getLogger(__name__)


def _clean_key(value: Any) -> str | None:
    if value is None:
        return None
    key = str(value).strip()
    return key or None


class PostprocessorService:
    def __init__(
        self,
        *,
        root_dir: Path,
        profile: ProfileDefinition,
        context: Context,
        pool_size: int,
        runtime: str,
    ) -> None:
        self._profile = profile
        self._context = context
        self._executor = ThreadPoolExecutor(
            max_workers=pool_size, thread_name_prefix="worai_pp"
        )
        self._queue: asyncio.Queue = asyncio.Queue()
        for _ in range(pool_size):
            self._queue.put_nowait(
                load_postprocessors_for_profile(
                    root_dir=root_dir,
                    profile_name=profile.name,
                    runtime=runtime,
                )
            )
        logger.info(
            "Created postprocessor pool for profile '%s' (pool_size=%d runtime=%s)",
            profile.name,
            pool_size,
            runtime,
        )

    async def apply(
        self,
        graph: Graph,
        url: str,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
        exports: dict[str, Any],
    ) -> PostprocessorResult:
        _t1 = time.perf_counter()
        postprocessors = await self._queue.get()
        queue_wait_ms = int((time.perf_counter() - _t1) * 1000)
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                self._executor,
                functools.partial(
                    self._run,
                    graph,
                    url,
                    response,
                    existing_web_page_id,
                    postprocessors,
                    queue_wait_ms,
                    exports,
                ),
            )
        finally:
            self._queue.put_nowait(postprocessors)

    def build_context(
        self,
        url: str,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
        exports: dict[str, Any],
    ) -> PostprocessorContext:
        dataset_uri = str(getattr(self._context.account, "dataset_uri", "")).rstrip("/")
        ids = IdAllocator(dataset_uri) if dataset_uri else None
        profile_payload = asdict(self._profile)
        profile_settings = dict(profile_payload.get("settings", {}) or {})
        profile_settings.setdefault("api_url", "https://api.wordlift.io")
        profile_payload["settings"] = profile_settings
        return PostprocessorContext(
            profile_name=self._profile.name,
            profile=profile_payload,
            url=url,
            account=self._context.account,
            account_key=self._resolve_account_key(),
            exports=exports,
            response=response,
            existing_web_page_id=existing_web_page_id,
            ids=ids,
        )

    def close(self) -> None:
        while not self._queue.empty():
            try:
                close_loaded_postprocessors(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        self._executor.shutdown(wait=False)

    def _run(
        self,
        graph: Graph,
        url: str,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
        postprocessors: list,
        queue_wait_ms: int,
        exports: dict[str, Any],
    ) -> PostprocessorResult:
        _t_start = time.perf_counter()
        if not postprocessors:
            return PostprocessorResult(
                graph=graph, queue_wait_ms=queue_wait_ms, postprocessors_ms=0
            )

        pp_context = self.build_context(url, response, existing_web_page_id, exports)
        if not pp_context.account_key:
            raise RuntimeError(
                "Postprocessor runtime requires an API key. Configure one via profile "
                "'api_key', WORDLIFT_KEY, or WORDLIFT_API_KEY."
            )

        for processor in postprocessors:
            _tp = time.perf_counter()
            graph = processor.run(graph, pp_context)
            logger.info(
                "Applied postprocessor '%s' for %s [%dms]",
                processor.name,
                url,
                int((time.perf_counter() - _tp) * 1000),
            )
        return PostprocessorResult(
            graph=graph,
            queue_wait_ms=queue_wait_ms,
            postprocessors_ms=int((time.perf_counter() - _t_start) * 1000),
        )

    def _resolve_account_key(self) -> str | None:
        profile_key = _clean_key(self._profile.api_key)
        if profile_key:
            return profile_key

        client_config = getattr(self._context, "client_configuration", None)
        if client_config is not None:
            api_key_map = getattr(client_config, "api_key", None)
            if isinstance(api_key_map, dict):
                runtime_key = _clean_key(api_key_map.get("ApiKey"))
                if runtime_key:
                    return runtime_key

        provider = getattr(self._context, "configuration_provider", None)
        if provider is not None:
            for name in ("WORDLIFT_KEY", "WORDLIFT_API_KEY"):
                try:
                    key = _clean_key(provider.get_value(name))
                except Exception:
                    key = None
                if key:
                    return key

        for name in ("WORDLIFT_KEY", "WORDLIFT_API_KEY"):
            key = _clean_key(os.getenv(name))
            if key:
                return key

        return None
