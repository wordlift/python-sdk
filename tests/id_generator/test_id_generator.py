import pytest
from wordlift_client import AccountInfo

from wordlift_sdk.id_generator.id_generator import IdGenerator
from wordlift_sdk.id_generator.id_generator_interface import IdGeneratorInterface


@pytest.fixture
def account() -> AccountInfo:
    return AccountInfo(
        accountId=968840058500977,
        datasetId='dataset968840058500977',
        datasetUri='http://data.example.org/dataset968840058500977',
        networks=[],
        subscriptionId=287955110733495,
        url='http://example.org'
    )


@pytest.fixture
def id_generator(account: AccountInfo) -> IdGeneratorInterface:
    return IdGenerator(account=account)


def test_id_generator(id_generator: IdGeneratorInterface):
    str = id_generator.create('http://example.org', 'ProfilePage', 'An Example Profile Page')

    assert str == 'http://data.example.org/dataset968840058500977/httpexampleorg/profile-page/an-example-profile-page'
