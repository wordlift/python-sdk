import logging
from pathlib import Path
from typing import AsyncGenerator
from rdflib import Graph
from liquid import Environment, CachingFileSystemLoader

from wordlift_sdk.wordlift.sitemap_import.protocol import ProtocolContext
from ..graph_provider import GraphProvider
from ..graph_bag import GraphBag

logger = logging.getLogger(__name__)


class TtlLiquidGraphFactory(GraphProvider):
    path: Path
    context: ProtocolContext

    def __init__(self, context: ProtocolContext, path: Path):
        self.context = context
        self.path = path

    async def graphs(self) -> AsyncGenerator[GraphBag, None]:
        templates = list(self.path.rglob("*.ttl.liquid"))
        env = Environment(
            loader=CachingFileSystemLoader(self.path),
        )

        for template in templates:
            template = env.get_template(str(template))
            turtle = template.render(account=self.context.account.__dict__)

            try:
                # Create a new RDF graph
                graph = Graph()

                # Parse the Turtle data into the graph
                graph.parse(data=turtle, format="turtle")

                logger.info(f"Successfully loaded {template} graph with {len(graph)} triples")

                yield GraphBag(graph)
            except Exception as e:
                logger.error(f"Error loading contact points graph: {e}")
