from dataclasses import dataclass
from wordlift_client import AccountInfo, Configuration


@dataclass
class Context:
    account: AccountInfo
    client_configuration: Configuration
