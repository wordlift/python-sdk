from rdflib import Graph, URIRef, Literal
import wordlift_client
from wordlift_client.models.entity_patch_request import EntityPatchRequest

def create_entity_patch_request(resource: URIRef, prop: URIRef, value: Literal) -> EntityPatchRequest:
    g = Graph()
    g.bind('schema', 'http://schema.org/')
    g.add((resource, prop, value))

    return wordlift_client.EntityPatchRequest(
        op='add',
        path='/' + str(prop),
        value=g.serialize(format='json-ld', auto_compact=True)
    )
