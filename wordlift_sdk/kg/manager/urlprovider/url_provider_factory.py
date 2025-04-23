from dataclasses import dataclass
from typing import Optional, List, Union

from google.auth.credentials import Credentials
from gspread import Client

from .url_provider import UrlProvider
from .sitemap_url_provider import SitemapUrlProvider
from .google_sheets_url_provider import GoogleSheetsUrlProvider
from .list_url_provider import ListUrlProvider


@dataclass
class UrlProviderFactoryInput:
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


class UrlProviderFactory:
    """
    Factory for creating URL providers based on available input parameters.
    
    This factory creates the most appropriate URL provider based on the provided input parameters.
    The order of preference is:
    1. SitemapUrlProvider (if sitemap_url is provided)
    2. GoogleSheetsUrlProvider (if sheets_* parameters are provided)
    3. ListUrlProvider (if urls is provided)
    
    If none of the required parameters are provided, an error is raised.
    """
    
    @staticmethod
    def create(input_params: UrlProviderFactoryInput) -> UrlProvider:
        """
        Create the most appropriate URL provider based on the provided input parameters.
        
        Args:
            input_params: An instance of UrlProviderFactoryInput containing the parameters
                          for creating URL providers.
                          
        Returns:
            An instance of a class implementing the UrlProvider interface.
            
        Raises:
            ValueError: If none of the required parameters are provided to create any provider.
        """
        # Try to create a SitemapUrlProvider if sitemap_url is provided
        if input_params.sitemap_url:
            return SitemapUrlProvider(input_params.sitemap_url)
        
        # Try to create a GoogleSheetsUrlProvider if all required sheets parameters are provided
        if (input_params.sheets_url and 
            input_params.sheets_name and 
            input_params.sheets_creds_or_client):
            return GoogleSheetsUrlProvider(
                input_params.sheets_creds_or_client,
                input_params.sheets_url,
                input_params.sheets_name
            )
        
        # Try to create a ListUrlProvider if urls is provided
        if input_params.urls:
            return ListUrlProvider(input_params.urls)
        
        # If we get here, none of the required parameters were provided
        raise ValueError(
            "No valid parameters provided to create a URL provider. "
            "Please provide either sitemap_url, all sheets parameters "
            "(sheets_url, sheets_name, sheets_creds_or_client), or urls."
        )