import pandas as pd

from StockAnalysisSystem.core.Utility.common import *
from StockAnalysisSystem.core.Utility.time_utility import *
from StockAnalysisSystem.core.Utility.CollectorUtility import *


# ------------------------------------------------------- Fields -------------------------------------------------------

FIELDS = {
    'TradeData.Stock.Daily.US': {
        'open':         'Open Price',
        'high':         'High Price',
        'low':          'Low Price',
        'close':        'Close Price',
        'volume':       'Trading Volume',
        'dividends':    'Dividends',
        'stock_splits': 'Stock Splits',
    },
}


# -------------------------------------------------------- Prob --------------------------------------------------------

def plugin_prob() -> dict:
    return {
        'plugin_name': 'trade_data_yfinance',
        'plugin_version': '0.0.0.1',
        'tags': ['yfinance', 'us_market'],
    }


def plugin_adapt(uri: str) -> bool:
    return uri in FIELDS.keys()


def plugin_capacities() -> list:
    return list(FIELDS.keys())


# ----------------------------------------------------------------------------------------------------------------------

# chart: https://query1.finance.yahoo.com/v8/finance/chart/{symbol}

def __fetch_trade_data_daily(**kwargs) -> pd.DataFrame or None:
    result = check_execute_test_flag(**kwargs)
    if result is None:
        stock_identity = kwargs.get('stock_identity', '')
        ticker = stock_identity_to_us_ticker(stock_identity)
        if not str_available(ticker):
            return None

        period = kwargs.get('trade_date')
        since, until = normalize_time_serial(period, default_since(), today())

        data = yahoo_fetch_json(
            YAHOO_CHART_URL.format(symbol=ticker),
            params={
                'period1': int(since.timestamp()),
                'period2': int(until.timestamp()),
                'interval': '1d',
                'events': 'div,split',
            })
        if data is None:
            return None

        chart_result = (data.get('chart', {}).get('result') or [None])[0]
        if chart_result is None:
            return None

        timestamps = chart_result.get('timestamp') or []
        if len(timestamps) == 0:
            return None

        quote = (chart_result.get('indicators', {}).get('quote') or [{}])[0]
        events = chart_result.get('events', {}) or {}

        result = pd.DataFrame({
            'trade_date': pd.to_datetime(timestamps, unit='s').normalize(),
            'open':       quote.get('open'),
            'high':       quote.get('high'),
            'low':        quote.get('low'),
            'close':      quote.get('close'),
            'volume':     quote.get('volume'),
        })
        result['dividends'] = 0.0
        result['stock_splits'] = 0.0

        for _, div in (events.get('dividends') or {}).items():
            div_date = pd.to_datetime(int(div.get('date')), unit='s').normalize()
            result.loc[result['trade_date'] == div_date, 'dividends'] = div.get('amount', 0.0)

        for _, split in (events.get('splits') or {}).items():
            split_date = pd.to_datetime(int(split.get('date')), unit='s').normalize()
            denominator = split.get('denominator') or 0
            ratio = (split.get('numerator', 1) / denominator) if denominator else 0.0
            result.loc[result['trade_date'] == split_date, 'stock_splits'] = ratio

        result['stock_identity'] = stock_identity if str_available(stock_identity) else \
            us_ticker_to_stock_identity(ticker)

    check_execute_dump_flag(result, **kwargs)
    return result


# ----------------------------------------------------------------------------------------------------------------------

def query(**kwargs) -> pd.DataFrame or None:
    uri = kwargs.get('uri')
    if uri == 'TradeData.Stock.Daily.US':
        return __fetch_trade_data_daily(**kwargs)
    else:
        return None


def validate(**kwargs) -> bool:
    nop(kwargs)
    return True


def fields() -> dict:
    return FIELDS
