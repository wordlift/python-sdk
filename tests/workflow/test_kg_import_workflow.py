import pytest

import wordlift_client

from wordlift_client import AccountInfo

from wordlift_sdk.client import ClientConfigurationFactory
from wordlift_sdk.wordlift.sitemap_import.protocol import ProtocolContext
from wordlift_sdk.workflow.kg_import_workflow import KgImportWorkflow, KgImportWorkflowConfiguration
from wordlift_sdk.workflow.kg_import_workflow_factory import KgImportWorkflowFactory, KgImportWorkflowInitInput


@pytest.fixture
def test_wiremock_url(wiremock_url: str) -> str:
    return wiremock_url + '/test_kg_import_workflow'


@pytest.fixture
def client_configuration(test_wiremock_url: str) -> wordlift_client.Configuration:
    return ClientConfigurationFactory(key='key388966881976561', api_url=test_wiremock_url).create()


@pytest.fixture
def account_info() -> AccountInfo:
    return AccountInfo(
        accountId=950196419916214,
        country_code='IT',
        datasetId='dataset_950196419916214',
        datasetUri='https://data.example.org/dataset_950196419916214',
        networks=[],
        subscriptionId=757200920795189
    )


@pytest.fixture
def kg_import_workflow_configuration(
        client_configuration: wordlift_client.Configuration,
        test_wiremock_url: str
) -> KgImportWorkflowConfiguration:
    return KgImportWorkflowConfiguration(
        client_configuration=client_configuration,
        key=client_configuration.api_key['ApiKey'],
        urls=[test_wiremock_url + '/sitemap.xml']
    )

@pytest.fixture
def protocol_context() -> ProtocolContext:
    return ProtocolContext()

@pytest.fixture
def kg_import_workflow_input(
        account_info: AccountInfo,
        kg_import_workflow_configuration: KgImportWorkflowConfiguration
) -> KgImportWorkflowInitInput:
    return KgImportWorkflowInitInput(
        account=account_info,
        configuration=kg_import_workflow_configuration,

    )


@pytest.fixture
def kg_import_workflow_factory() -> KgImportWorkflowFactory:
    return KgImportWorkflowFactory()


@pytest.fixture
async def kg_import_workflow(kg_import_workflow_factory: KgImportWorkflowFactory) -> KgImportWorkflow:
    return await kg_import_workflow_factory.create(
        KgImportWorkflowInitInput(

        )
    )


@pytest.mark.asyncio
async def test(kg_import_workflow: KgImportWorkflow) -> None:
    await kg_import_workflow.start()
