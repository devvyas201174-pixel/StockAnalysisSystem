import pandas as pd

from StockAnalysisSystem.core.Utility.common import *
from StockAnalysisSystem.core.Utility.time_utility import *
from StockAnalysisSystem.core.Utility.CollectorUtility import *


# ------------------------------------------------------- Fields -------------------------------------------------------

FIELDS = {
    'Market.SecuritiesInfo.US': {
        'symbol':     'Ticker Symbol',
        'name':       'Company Name',
        'sector':     'Sector',
        'industry':   'Industry',
        'exchange':   'Exchange',
        'currency':   'Currency',
        'country':    'Country',
        'website':    'Website',
        'market_cap': 'Market Capitalization',
    },
}


# -------------------------------------------------------- Prob --------------------------------------------------------

def plugin_prob() -> dict:
    return {
        'plugin_name': 'market_data_yfinance',
        'plugin_version': '0.0.0.1',
        'tags': ['yfinance', 'us_market'],
    }


def plugin_adapt(uri: str) -> bool:
    return uri in FIELDS.keys()


def plugin_capacities() -> list:
    return list(FIELDS.keys())


# ----------------------------------------------------------------------------------------------------------------------

def __raw(value: any) -> any:
    return value.get('raw') if isinstance(value, dict) else value


def __fetch_securities_info(**kwargs) -> pd.DataFrame or None:
    result = check_execute_test_flag(**kwargs)
    if result is None:
        stock_identity = kwargs.get('stock_identity', '')
        ticker = stock_identity_to_us_ticker(stock_identity)
        if not str_available(ticker):
            return None

        data = yahoo_fetch_json(
            YAHOO_QUOTE_SUMMARY_URL.format(symbol=ticker),
            params={'modules': 'assetProfile,price'}, use_crumb=True)
        if data is None:
            return None

        query_results = data.get('quoteSummary', {}).get('result') or []
        if len(query_results) == 0:
            return None

        record = query_results[0]
        profile = record.get('assetProfile', {}) or {}
        price = record.get('price', {}) or {}

        exchange = yahoo_exchange_to_sas_exchange(price.get('exchange', ''))
        result = pd.DataFrame([{
            'symbol':     ticker,
            'name':       price.get('longName') or price.get('shortName') or ticker,
            'sector':     profile.get('sector', ''),
            'industry':   profile.get('industry', ''),
            'exchange':   exchange,
            'currency':   price.get('currency', 'USD'),
            'country':    profile.get('country', ''),
            'website':    profile.get('website', ''),
            'market_cap': __raw(price.get('marketCap')),
        }])
        result['stock_identity'] = result['symbol'] + '.' + result['exchange']

    check_execute_dump_flag(result, **kwargs)
    return result


# ----------------------------------------------------------------------------------------------------------------------

def query(**kwargs) -> pd.DataFrame or None:
    uri = kwargs.get('uri')
    if uri == 'Market.SecuritiesInfo.US':
        return __fetch_securities_info(**kwargs)
    else:
        return None


def validate(**kwargs) -> bool:
    nop(kwargs)
    return True


def fields() -> dict:
    return FIELDS
