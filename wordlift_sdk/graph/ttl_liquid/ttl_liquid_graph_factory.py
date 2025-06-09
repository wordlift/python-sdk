import logging
from pathlib import Path

from liquid import Environment, CachingFileSystemLoader
from rdflib import Graph

from ...protocol import Context

logger = logging.getLogger(__name__)


class TtlLiquidGraphFactory:
    path: Path
    context: Context

    def __init__(self, context: Context, path: Path):
        self.context = context
        self.path = path

    async def graphs(self) -> None:
        templates = list(self.path.rglob("*.ttl.liquid"))
        env = Environment(
            loader=CachingFileSystemLoader(self.path),
        )

        for template in templates:
            template = env.get_template(str(template.absolute()))
            turtle = template.render(account=self.context.account.__dict__)

            try:
                # Create a new RDF graph
                graph = Graph()

                # Parse the Turtle data into the graph
                graph.parse(data=turtle, format="turtle")

                logger.info(
                    f"Successfully loaded {template} graph with {len(graph)} triples"
                )

                await self.context.graph_queue.put(graph)
            except Exception as e:
                logger.error(f"Error loading contact points graph: {e}")
