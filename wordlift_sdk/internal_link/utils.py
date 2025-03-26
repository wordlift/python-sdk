import logging
import re
from typing import Callable, Awaitable
from urllib.parse import quote

import wordlift_client
from pandas import Series
from rdflib import Graph, URIRef, RDF, Literal, XSD
from tenacity import retry, stop_after_attempt, wait_fixed
from wordlift_client import InternalLinkRequest, InternalLink, InternalLinksApi, AnchorText, Item, \
    VectorSearchQueryRequest, EntityPatchRequest, Configuration

from wordlift_sdk import entity

logger = logging.getLogger(__name__)


async def create_internal_link_request_default_filter(row: Series, request: InternalLinkRequest) -> InternalLinkRequest:
    return request


@retry(
    stop=stop_after_attempt(5),
    wait=wait_fixed(2)
)
async def create_internal_link(
        configuration: Configuration,
        row: Series,
        no_links: int = 10,
        internal_link_request_filter: Callable[
            [Series, InternalLinkRequest], Awaitable[
                InternalLinkRequest]] = create_internal_link_request_default_filter
) -> InternalLink | None:
    import wordlift_client
    entity_url = row['url']
    entity_id = row['iri']

    async with wordlift_client.ApiClient(configuration) as api_client:
        api = InternalLinksApi(api_client)
        request = await internal_link_request_filter(
            row,
            InternalLinkRequest(
                anchor_text=AnchorText(
                    enabled=True
                ),
                items=[
                    Item(
                        id=entity_id,
                        query=VectorSearchQueryRequest(
                            query_url=entity_url,
                            similarity_top_k=no_links
                        )
                    )
                ]
            )
        )

        try:
            results = await api.create_internal_link_suggestion(internal_link_request=request, _request_timeout=120)
            return results[0]
        except Exception as e:
            logger.error("Error creating Internal Links: %s", e)
            raise e


class InternalLinkData:
    source_id: str
    source_patch_request: EntityPatchRequest
    link_group_graph: Graph

    def __init__(self, source_id: str, source_patch_request: EntityPatchRequest, link_group_graph: Graph):
        self.source_id = source_id
        self.source_patch_request = source_patch_request
        self.link_group_graph = link_group_graph


async def create_internal_link_data(internal_link: InternalLink, group_id: str) -> InternalLinkData:
    """
    Create an RDFlib Graph from an InternalLink object using the SEO vocabulary.

    Args:
        internal_link: InternalLink object from wordlift_client

    Returns:
        RDFlib Graph containing the mapped data
        :param group_id:
    """

    # This is an example structure:
    #
    # InternalLink(
    #     destinations=[
    #         InternalLinkDestination(
    #             name='SEO Strategies',
    #             position=1,
    #             url='https://wordlift.io/blog/en/advanced-seo-natural-language-processing/'
    #         ),
    #         InternalLinkDestination(
    #             name='SERP Analysis',
    #             position=2,
    #             url='https://wordlift.io/blog/en/serp-analysis/'
    #         ),
    #         InternalLinkDestination(
    #             name='Semantic Search',
    #             position=3,
    #             url='https://wordlift.io/blog/en/semantic-search/'
    #         ),
    #         InternalLinkDestination(
    #             name='Text Summarize',
    #             position=4,
    #             url='https://wordlift.io/blog/en/text-summarization-in-seo/'
    #         ),
    #         InternalLinkDestination(
    #             name='RankBrain In SEO',
    #             position=5,
    #             url='https://wordlift.io/blog/en/rankbrain-will-make-blog-worthless-unless/'
    #         ),
    #         InternalLinkDestination(
    #             name='SEO and AI',
    #             position=6,
    #             url='https://wordlift.io/blog/en/how-expert-professional-seo-evolves-with-ai/'
    #         ),
    #         InternalLinkDestination(
    #             name='Content Optimize',
    #             position=7,
    #             url='https://wordlift.io/blog/en/seo-content-optimization/'
    #         ),
    #         InternalLinkDestination(
    #             name='Google Advances',
    #             position=8,
    #             url='https://wordlift.io/blog/en/advances-in-image-understanding/'
    #         ),
    #         InternalLinkDestination(
    #             name='Knowledge Graphs',
    #             position=9,
    #             url='https://wordlift.io/blog/en/finding-entities-knowledge-graphs/'
    #         )
    #     ],
    #     source=InternalLinkSource(
    #         id='https://data.wordlift.io/wl1505904/title-tag-seo-using-deep-learning-and-tensorflow-3e9202b7c7a6fde83605021a5820ab04',
    #         name=None,
    #         url='https://wordlift.io/blog/en/title-tag-seo-using-ai/'
    #     )
    # )

    # Validate group_id
    if not group_id or not isinstance(group_id, str):
        raise ValueError("group_id must be a non-empty string")

    # Check for valid characters (alphanumeric, hyphen, underscore)
    if not re.match(r'^[a-zA-Z0-9\-_]+$', group_id):
        raise ValueError("group_id must contain only alphanumeric characters, hyphens, or underscores")

    # URL encode the group_id for extra safety
    safe_group_id = quote(group_id)

    link_group_graph = Graph()
    source_graph = Graph()

    source_graph.bind("seovoc", "https://w3id.org/seovoc/")

    # Define namespaces
    link_group_graph.bind("seovoc", "https://w3id.org/seovoc/")
    link_group_graph.bind("xsd", "http://www.w3.org/2001/XMLSchema#")

    # Create source resource
    source = internal_link.source
    source_resource = URIRef(source.id)

    # Create a default link group for the destinations
    link_group_id = f"{source.id}/linkgroup_{safe_group_id}"
    link_group = URIRef(link_group_id)

    has_link_group = URIRef("https://w3id.org/seovoc/hasLinkGroup")
    source_graph.add((source_resource, has_link_group, link_group))

    link_group_graph.add((link_group, RDF.type, URIRef("https://w3id.org/seovoc/LinkGroup")))
    link_group_graph.add((link_group, URIRef("https://w3id.org/seovoc/identifier"), Literal(group_id)))
    link_group_graph.add((link_group, URIRef("https://w3id.org/seovoc/name"), Literal("Related Links")))
    link_group_graph.add((link_group, URIRef("https://w3id.org/seovoc/isLinkGroupOf"), source_resource))

    # Add destinations as links
    for dest in internal_link.destinations:
        # Create link resource
        link_id = f"{link_group_id}/link_{dest.position}"
        link_resource = URIRef(link_id)
        link_group_graph.add((link_resource, RDF.type, URIRef("https://w3id.org/seovoc/Link")))

        # Add link properties
        link_group_graph.add(
            (link_resource, URIRef("https://w3id.org/seovoc/position"), Literal(dest.position, datatype=XSD.integer)))
        link_group_graph.add((link_resource, URIRef("https://w3id.org/seovoc/name"), Literal(dest.name)))
        link_group_graph.add((link_resource, URIRef("https://w3id.org/seovoc/anchorText"), Literal(dest.name)))
        link_group_graph.add((link_resource, URIRef("https://w3id.org/seovoc/anchorValue"), URIRef(dest.url)))
        link_group_graph.add((link_resource, URIRef("https://w3id.org/seovoc/anchorResource"), URIRef(dest.id)))
        link_group_graph.add((link_resource, URIRef("https://w3id.org/seovoc/isLinkOf"), link_group))
        link_group_graph.add((link_group, URIRef("https://w3id.org/seovoc/hasLink"), link_resource))

    source_patch_request = EntityPatchRequest(
        op='add',
        path='/' + str(has_link_group),
        value=source_graph.serialize(format='json-ld', auto_compact=True)
    )

    return InternalLinkData(source.id, source_patch_request, link_group_graph)


def create_internal_link_handler(
        configuration: Configuration,
        link_group_id: str,
        no_links: int = 10,
        internal_link_request_filter: Callable[
            [Series, InternalLinkRequest], Awaitable[InternalLinkRequest]] = create_internal_link_request_default_filter
) -> Callable[[Series], Awaitable[None]]:
    async def handle(row: Series) -> None:
        response = await create_internal_link(configuration, row, no_links, internal_link_request_filter)

        if not response:
            return

        data = await create_internal_link_data(response, link_group_id)

        await entity.patch(configuration, data.source_id, [data.source_patch_request])

        async with wordlift_client.ApiClient(configuration) as api_client:
            # Create an instance of the API class
            api_instance = wordlift_client.EntitiesApi(api_client)
            body = data.link_group_graph.serialize(format="turtle")
            await api_instance.create_or_update_entities(body, _content_type="text/turtle")

    return handle
