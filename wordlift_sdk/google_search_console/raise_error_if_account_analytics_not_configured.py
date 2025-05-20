from pycountry import countries
from wordlift_client import AccountInfo


async def raise_error_if_account_analytics_not_configured(account: AccountInfo) -> bool:
    if account.google_search_console_site_url is None:
        raise ValueError(
            "%s is not connected to Google Search Console, open https://my.wordlift.io to connect it." % account.dataset_uri)

    if account.country_code is None:
        raise ValueError(
            "%s country code not configured, open https://my.wordlift.io to configure it." % account.dataset_uri)

    # Get the country name
    country = countries.get(alpha_2=account.country_code.upper())
    if country is None:
        raise ValueError(
            "Country code %s is invalid, open https://my.wordlift.io to reconfigure it." % account.country_code.upper())

    return True
