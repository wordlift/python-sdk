"""
This module provides a default implementation of the ParseHtmlProtocolInterface.

The DefaultParseHtmlProtocol class implements a basic HTML parsing protocol
that can be used as a fallback or starting point for more complex implementations.
"""

from wordlift_client import EntityPatchRequest
from ..parse_html_protocol_interface import ParseHtmlProtocolInterface, ParseHtmlInput


class DefaultParseHtmlProtocol(ParseHtmlProtocolInterface):
    """
    Default implementation of the ParseHtmlProtocolInterface.

    This class provides a minimal implementation of the HTML parsing protocol
    that returns an empty list of entity patch requests. It can be used as a
    base class for more complex implementations or as a fallback when no
    specific parsing logic is required.

    Attributes:
        context (ProtocolContext): The protocol context containing configuration
            and entity types information.
    """

    async def parse_html(self, parse_html_input: ParseHtmlInput) -> list[EntityPatchRequest]:
        """
        Parse HTML content and extract entity information.

        This default implementation returns an empty list. Override this method
        to implement custom HTML parsing logic.

        Args:
            parse_html_input (ParseHtmlInput): An object containing the HTML content to parse,
                along with entity ID, URL, and additional data.

        Returns:
            list[EntityPatchRequest]: A list of entity patch requests to update
                the knowledge graph. This implementation returns an empty list.
        """
        return list()
