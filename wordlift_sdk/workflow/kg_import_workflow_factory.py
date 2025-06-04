from dataclasses import dataclass

import gspread
from wordlift_client import AccountInfo

from wordlift_sdk.graph import GraphQueue
from wordlift_sdk.graph.ttl_liquid import TtlLiquidGraphFactory
from wordlift_sdk.graphql.client import GraphQlClient, GraphQlClientFactory
from wordlift_sdk.id_generator import IdGenerator
from wordlift_sdk.kg.manager.urlprovider import UrlProvider, UrlProviderFactoryInput, UrlProviderFactory
from wordlift_sdk.utils import get_me
from wordlift_sdk.wordlift.sitemap_import.protocol import load_override_class, DefaultImportUrlProtocol, \
    DefaultParseHtmlProtocol
from wordlift_sdk.workflow.kg_import_workflow import KgImportWorkflowConfiguration, ProtocolContext, \
    ImportUrlProtocolInterface, ParseHtmlProtocolInterface, KgImportWorkflow


@dataclass
class KgImportWorkflowInitInput:
    account: AccountInfo
    configuration: KgImportWorkflowConfiguration
    context: ProtocolContext
    graphql_client: GraphQlClient
    import_url_protocol: ImportUrlProtocolInterface
    parse_html_protocol: ParseHtmlProtocolInterface
    ttl_liquid_graph_factory: TtlLiquidGraphFactory
    url_provider: UrlProvider


class KgImportWorkflowFactory:

    async def create(self, factory_input: KgImportWorkflowInitInput) -> KgImportWorkflow:
        client_configuration = factory_input.configuration.client_configuration
        factory_input.account = await get_me(configuration=client_configuration)

        # Define the context for protocol functions, it provides instances and data that those functions can use.
        factory_input.context = ProtocolContext(
            account=factory_input.account,
            configuration=client_configuration,
            id_generator=IdGenerator(account=factory_input.account),
            types=factory_input.configuration.output_types,
            graph_queue=GraphQueue(),
        )

        # Add templates from the data/templates folder.
        factory_input.ttl_liquid_graph_factory = TtlLiquidGraphFactory(context=factory_input.context)

        # Change the behavior of the import URL call.
        factory_input.import_url_protocol = load_override_class(
            name="import_url_protocol",
            class_name="ImportUrlProtocol",
            # Default class to use in case of missing override.
            default_class=DefaultImportUrlProtocol,
            context=factory_input.context,
        )

        # Change the behavior of the parse HTML call by parsing the web page html and sending patches to the graph.
        factory_input.parse_html_protocol = load_override_class(
            name="parse_html_protocol",
            class_name="ParseHtmlProtocol",
            # Default class to use in case of missing override.
            default_class=DefaultParseHtmlProtocol,
            context=factory_input.context,
        )

        # We can import for different sources: (1) sitemap or (2) Google Sheets or (3) list of URLs.
        # This will create the provider based on the configuration and the input parameters.
        factory_input.url_provider = UrlProviderFactory.create(
            input_params=UrlProviderFactoryInput(
                sitemap_url=factory_input.configuration.sitemap_url,
                sheets_url=factory_input.configuration.sheets_url,
                sheets_name=factory_input.configuration.sheets_name,
                sheets_creds_or_client=(
                    gspread.service_account(filename=factory_input.configuration.sheets_service_account)
                    if factory_input.configuration.sheets_service_account
                    else None
                ),
                urls=factory_input.configuration.urls,
            )
        )

        factory_input.graphql_client = GraphQlClientFactory(
            key=factory_input.configuration.key,
            api_url=factory_input.configuration.client_configuration.host + '/graphql'
        ).create()

        return KgImportWorkflow(**factory_input.__dict__)
