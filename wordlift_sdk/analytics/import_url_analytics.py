import wordlift_client
from pandas import Series
from tenacity import stop_after_attempt, retry, wait_fixed
from wordlift_client import Configuration, AnalyticsImportRequest


@retry(
    stop=stop_after_attempt(5),
    wait=wait_fixed(2)
)
async def import_url_analytics(configuration: Configuration, row: Series) -> None:
    url = row['url']
    async with wordlift_client.ApiClient(configuration) as api_client:
        api_instance = wordlift_client.AnalyticsImportsApi(api_client)
        request = AnalyticsImportRequest(urls=[url])
        await api_instance.create_analytics_import(request)
