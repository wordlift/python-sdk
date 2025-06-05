from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Union

import gspread
from google.auth.credentials import Credentials
from gspread import Client

from .google_sheets_url_source import GoogleSheetsUrlSource
from .list_url_source import ListUrlSource
from .sitemap_url_source import SitemapUrlSource
from .url_source import UrlSource
from ..config import get_config_value


@dataclass
class UrlSourceInput:
    """
    Input structure for the UrlProviderFactory.
    
    This class holds all possible parameters needed to create any of the supported URL providers.
    The factory will use these parameters to determine which provider to create based on availability.
    """
    sitemap_url: Optional[str] = None
    sheets_url: Optional[str] = None
    sheets_name: Optional[str] = None
    sheets_creds_or_client: Optional[Union[Credentials, Client]] = None
    urls: Optional[List[str]] = None


class UrlSourceProvider:
    """
    Factory for creating URL providers based on available input parameters.
    
    This factory creates the most appropriate URL provider based on the provided input parameters.
    The order of preference is:
    1. SitemapUrlProvider (if sitemap_url is provided)
    2. GoogleSheetsUrlProvider (if sheets_* parameters are provided)
    3. ListUrlProvider (if urls is provided)
    
    If none of the required parameters are provided, an error is raised.
    """

    def create(self) -> UrlSource:
        # Try to read the configuration from the `config/default.py` file.
        config_path = Path.cwd() / "config" / "default.py"
        WORDLIFT_KEY = get_config_value("WORDLIFT_KEY", config_path)
        SITEMAP_URL = get_config_value("SITEMAP_URL", config_path)
        OUTPUT_TYPES = {
            get_config_value("OUTPUT_TYPE", config_path, "http://schema.org/Article")
        }
        SHEETS_URL = get_config_value("SHEETS_URL", config_path)
        SHEETS_NAME = get_config_value("SHEETS_NAME", config_path)
        SHEETS_SERVICE_ACCOUNT = get_config_value("SHEETS_SERVICE_ACCOUNT", config_path)
        URLS = get_config_value("URLS", config_path)

        if WORDLIFT_KEY is None:
            raise ValueError("`WORDLIFT_KEY` is required.")

        if OUTPUT_TYPES is None:
            raise ValueError("`OUTPUT_TYPES` is required.")

        if (
                SITEMAP_URL is None
                and URLS is None
                and (SHEETS_URL is None or SHEETS_NAME is None or SHEETS_SERVICE_ACCOUNT is None)
        ):
            raise ValueError(
                "One of `SITEMAP_URL` or `SHEETS_URL`/`SHEETS_NAME`/`SHEETS_SERVICE_ACCOUNT` is required."
            )

        input_params = UrlSourceInput(
            sitemap_url=SITEMAP_URL,
            sheets_url=SHEETS_URL,
            sheets_name=SHEETS_NAME,
            sheets_creds_or_client=(
                gspread.service_account(filename=SHEETS_SERVICE_ACCOUNT)
                if SHEETS_SERVICE_ACCOUNT
                else None
            ),
            urls=URLS,
        )

        # Try to create a SitemapUrlProvider if sitemap_url is provided
        if input_params.sitemap_url:
            return SitemapUrlSource(input_params.sitemap_url)

        # Try to create a GoogleSheetsUrlProvider if all required sheets parameters are provided
        if (input_params.sheets_url and
                input_params.sheets_name and
                input_params.sheets_creds_or_client):
            return GoogleSheetsUrlSource(
                input_params.sheets_creds_or_client,
                input_params.sheets_url,
                input_params.sheets_name
            )

        # Try to create a ListUrlProvider if urls is provided
        if input_params.urls:
            return ListUrlSource(input_params.urls)

        # If we get here, none of the required parameters were provided
        raise ValueError(
            "No valid parameters provided to create a URL provider. "
            "Please provide either sitemap_url, all sheets parameters "
            "(sheets_url, sheets_name, sheets_creds_or_client), or urls."
        )
