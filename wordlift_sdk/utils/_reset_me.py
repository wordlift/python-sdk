from typing import Optional

import wordlift_client
from wordlift_client import AccountApi, Configuration, ResetAccountRequest


async def reset_me(
    configuration: Configuration,
    keep_country: Optional[bool] = None,
    keep_language: Optional[bool] = None,
    keep_url: Optional[bool] = None,
) -> None:
    request = ResetAccountRequest(
        keep_country=keep_country,
        keep_language=keep_language,
        keep_url=keep_url,
    )
    async with wordlift_client.ApiClient(configuration) as api_client:
        api = AccountApi(api_client)
        await api.reset_me(reset_account_request=request)
