import pytest

from wordlift_sdk.id_generator.id_generator import IdGenerator
from wordlift_sdk.id_generator.id_generator_interface import IdGeneratorInterface


@pytest.fixture
def id_generator() -> IdGeneratorInterface:
    return IdGenerator()


def test_id_generator(id_generator: IdGeneratorInterface):
    str = id_generator.create('http://example.org', 'ProfilePage', 'An Example Profile Page')

    assert str == 'http://example.org/profile-page/an-example-profile-page'
