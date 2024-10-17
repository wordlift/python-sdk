import gspread
import pandas as pd
from google.auth.credentials import Credentials
from gspread import Client


def create_dataframe_from_google_sheets(creds_or_client: Credentials | Client, url: str, sheet: str) -> pd.DataFrame:
    if isinstance(creds_or_client, Credentials):
        return create_dataframe_from_google_sheets_using_credentials(creds_or_client, url, sheet)
    elif isinstance(creds_or_client, Client):
        return create_dataframe_from_google_sheets_using_client(creds_or_client, url, sheet)
    else:
        raise TypeError("Expected creds_or_client to be of type Credentials or Client")


def create_dataframe_from_google_sheets_using_credentials(creds: Credentials, url: str, sheet: str) -> pd.DataFrame:
    gc = gspread.authorize(creds)

    return create_dataframe_from_google_sheets_using_client(gc, url, sheet)


def create_dataframe_from_google_sheets_using_client(gc: Client, url: str, sheet: str) -> pd.DataFrame:
    sheet = gc.open_by_url(url).worksheet(sheet)
    data = sheet.get_all_records()

    return pd.DataFrame([{k.strip(): v for k, v in row.items()} for row in data])
