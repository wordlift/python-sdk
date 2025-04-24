import wordlift_client
from wordlift_client import Configuration, AccountInfo, AccountApi


async def get_me(configuration: Configuration) -> AccountInfo:
    async with wordlift_client.ApiClient(configuration) as api_client:
        api = AccountApi(api_client)
        return await api.get_me()
