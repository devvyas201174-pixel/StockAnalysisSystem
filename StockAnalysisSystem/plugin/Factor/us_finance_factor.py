import pandas as pd

from StockAnalysisSystem.core.Utility.FactorUtility import *
from StockAnalysisSystem.core.DataHubEntry import DataHubEntry
from StockAnalysisSystem.core.Database.DatabaseEntry import DatabaseEntry


def factor_current_ratio(identity: str or [str], time_serial: tuple, mapping: dict,
                         data_hub: DataHubEntry, database: DatabaseEntry, extra: dict) -> pd.DataFrame:
    fields = ['Total Current Assets', 'Total Current Liabilities']
    df = query_finance_pattern(data_hub, identity, time_serial, fields, mapping)

    df['Current Ratio (US)'] = df['Total Current Assets'] / df['Total Current Liabilities']

    return df[['Current Ratio (US)'] + ['stock_identity', 'period']]


def factor_quick_ratio(identity: str or [str], time_serial: tuple, mapping: dict,
                       data_hub: DataHubEntry, database: DatabaseEntry, extra: dict) -> pd.DataFrame:
    fields = ['Total Current Assets', 'Total Current Liabilities', 'Inventory']
    df = query_finance_pattern(data_hub, identity, time_serial, fields, mapping)

    df['Quick Ratio (US)'] = (df['Total Current Assets'] - df['Inventory']) / df['Total Current Liabilities']

    return df[['Quick Ratio (US)'] + ['stock_identity', 'period']]


def factor_roe(identity: str or [str], time_serial: tuple, mapping: dict,
               data_hub: DataHubEntry, database: DatabaseEntry, extra: dict) -> pd.DataFrame:
    fields = ['Net Income', 'Total Stockholder Equity']
    df = query_finance_pattern(data_hub, identity, time_serial, fields, mapping)

    df['Return on Equity (US)'] = df['Net Income'] / df['Total Stockholder Equity']

    return df[['Return on Equity (US)'] + ['stock_identity', 'period']]


def factor_roa(identity: str or [str], time_serial: tuple, mapping: dict,
               data_hub: DataHubEntry, database: DatabaseEntry, extra: dict) -> pd.DataFrame:
    fields = ['Net Income', 'Total Assets']
    df = query_finance_pattern(data_hub, identity, time_serial, fields, mapping)

    df['Return on Assets (US)'] = df['Net Income'] / df['Total Assets']

    return df[['Return on Assets (US)'] + ['stock_identity', 'period']]


def factor_debt_to_equity(identity: str or [str], time_serial: tuple, mapping: dict,
                          data_hub: DataHubEntry, database: DatabaseEntry, extra: dict) -> pd.DataFrame:
    fields = ['Total Liabilities', 'Total Stockholder Equity']
    df = query_finance_pattern(data_hub, identity, time_serial, fields, mapping)

    df['Debt to Equity (US)'] = df['Total Liabilities'] / df['Total Stockholder Equity']

    return df[['Debt to Equity (US)'] + ['stock_identity', 'period']]


# ----------------------------------------------------------------------------------------------------------------------

FACTOR_TABLE = {
    'e3f1c8a2-3b7d-4e2a-9c1e-1a2b3c4d5e6f': (
        'Current Ratio (US)',
        ('Total Current Assets', 'Total Current Liabilities'),
        'Current Ratio = Total Current Assets / Total Current Liabilities',
        factor_current_ratio, None, None, None
    ),

    'f4a2d9b3-4c8e-4f3b-ad2f-2b3c4d5e6f70': (
        'Quick Ratio (US)',
        ('Total Current Assets', 'Total Current Liabilities', 'Inventory'),
        'Quick Ratio = (Total Current Assets - Inventory) / Total Current Liabilities',
        factor_quick_ratio, None, None, None
    ),

    'a5b3eac4-5d9f-405a-be3a-3c4d5e6f7081': (
        'Return on Equity (US)',
        ('Net Income', 'Total Stockholder Equity'),
        'ROE = Net Income / Total Stockholder Equity',
        factor_roe, None, None, None
    ),

    'b6c4fbd5-6eaf-416b-cf4b-4d5e6f708192': (
        'Return on Assets (US)',
        ('Net Income', 'Total Assets'),
        'ROA = Net Income / Total Assets',
        factor_roa, None, None, None
    ),

    'c7d50ce6-7fba-427c-d05c-5e6f708192a3': (
        'Debt to Equity (US)',
        ('Total Liabilities', 'Total Stockholder Equity'),
        'Debt to Equity = Total Liabilities / Total Stockholder Equity',
        factor_debt_to_equity, None, None, None
    ),
}


# ----------------------------------------------------------------------------------------------------------------------

def plugin_prob() -> dict:
    return {
        'plugin_id': '',
        'plugin_name': 'US Finance Factor',
        'plugin_version': '0.0.0.1',
        'tags': ['us_market', 'finance'],
        'factor': FACTOR_TABLE,
    }


def plugin_capacities() -> list:
    return list(FACTOR_TABLE.keys())


# ----------------------------------------------------------------------------------------------------------------------

def calculate(factor: str, identity: str or [str], time_serial: tuple, mapping: dict,
              data_hub: DataHubEntry, database: DatabaseEntry, extra: dict) -> pd.DataFrame or None:
    return dispatch_calculation_pattern(factor, identity, time_serial, mapping, data_hub, database, extra, FACTOR_TABLE)
