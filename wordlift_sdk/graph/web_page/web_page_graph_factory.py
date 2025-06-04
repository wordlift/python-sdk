from typing import AsyncGenerator

from .web_page import WebPage
from ..graph_bag import GraphBag
from ..graph_provider import GraphProvider
from ...kg.manager.urlprovider import UrlProvider
from ...wordlift.sitemap_import.protocol import ProtocolContext, ParseHtmlProtocolInterface, DefaultParseHtmlProtocol
import wordlift_client


class WebPageGraphFactory(GraphProvider):
    context: ProtocolContext
    parse_html: ParseHtmlProtocolInterface
    url_provider: UrlProvider

    def __init__(self, context: ProtocolContext, url_provider: UrlProvider, parse_html: ParseHtmlProtocolInterface):
        self.context = context
        self.url_provider = url_provider
        self.parse_html = parse_html or DefaultParseHtmlProtocol(context=context)

    async def graphs(self) -> AsyncGenerator[GraphBag, None]:
        async with wordlift_client.ApiClient(configuration=self.context.configuration) as client:
            api_instance = wordlift_client.WebPagesApi(client)

            async for url in self.url_provider.urls():
                response = await api_instance.get_web_page(url)
                web_page = WebPage(html=response.html)
