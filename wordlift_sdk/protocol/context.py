from dataclasses import dataclass
from wordlift_client import AccountInfo, Configuration

from wordlift_sdk.id_generator import IdGenerator


@dataclass
class Context:
    account: AccountInfo
    client_configuration: Configuration
    id_generator: IdGenerator
