import gspread
import pandas as pd


def create_dataframe_from_google_sheet(creds, url: str, sheet: str) -> pd.DataFrame:
    gc = gspread.authorize(creds)

    sheet = gc.open_by_url(url).worksheet(sheet)
    data = sheet.get_all_records()
    return pd.DataFrame([{k.strip(): v for k, v in row.items()} for row in data])
