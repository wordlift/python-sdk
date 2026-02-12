from types import SimpleNamespace

import pandas as pd
import pytest

import importlib

sheets = importlib.import_module(
    "wordlift_sdk.utils.create_dataframe_from_google_sheets"
)


class _Creds:
    pass


class _Client:
    def __init__(self, records):
        self.records = records
        self.opened_url = None
        self.opened_sheet = None

    def open_by_url(self, url):
        self.opened_url = url

        class _Workbook:
            def __init__(self, outer):
                self.outer = outer

            def worksheet(self, name):
                self.outer.opened_sheet = name

                class _Sheet:
                    def __init__(self, records):
                        self._records = records

                    def get_all_records(self):
                        return self._records

                return _Sheet(self.outer.records)

        return _Workbook(self)


def test_create_dataframe_from_google_sheets_using_client(monkeypatch):
    monkeypatch.setattr(sheets, "Client", _Client)

    client = _Client([{" col ": "v"}])
    df = sheets.create_dataframe_from_google_sheets(client, "https://sheet", "Tab1")

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["col"]
    assert client.opened_url == "https://sheet"
    assert client.opened_sheet == "Tab1"


def test_create_dataframe_from_google_sheets_using_credentials(monkeypatch):
    monkeypatch.setattr(sheets, "Credentials", _Creds)
    monkeypatch.setattr(sheets, "Client", _Client)

    fake_client = _Client([{"a": 1}])
    monkeypatch.setattr(sheets.gspread, "authorize", lambda creds: fake_client)

    df = sheets.create_dataframe_from_google_sheets(_Creds(), "https://sheet", "Tab1")
    assert df.iloc[0].to_dict() == {"a": 1}


def test_create_dataframe_from_google_sheets_invalid_type():
    with pytest.raises(TypeError, match="Expected creds_or_client"):
        sheets.create_dataframe_from_google_sheets(SimpleNamespace(), "u", "s")
