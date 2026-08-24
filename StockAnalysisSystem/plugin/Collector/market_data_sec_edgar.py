import pandas as pd

from StockAnalysisSystem.core.Utility.common import *
from StockAnalysisSystem.core.Utility.time_utility import *
from StockAnalysisSystem.core.Utility.CollectorUtility import *


# ------------------------------------------------------- Fields -------------------------------------------------------

FIELDS = {
    'Market.SecuritiesInfo.US': {
        'symbol':                 'Ticker Symbol',
        'name':                   'Company Name',
        'industry':               'Industry',
        'sic_code':               'SIC Code',
        'exchange':               'Exchange',
        'state_of_incorporation': 'State Of Incorporation',
        'category':               'Filer Category',
    },
}

# SEC's exchange labels aren't uniformly cased/named - normalize the common ones.
SEC_SAS_EXCHANGE_TABLE = {
    'NASDAQ': 'NASDAQ',
    'NYSE':   'NYSE',
    'CBOE':   'CBOE',
}


# -------------------------------------------------------- Prob --------------------------------------------------------

def plugin_prob() -> dict:
    return {
        'plugin_name': 'market_data_sec_edgar',
        'plugin_version': '0.0.0.1',
        'tags': ['sec_edgar', 'us_market'],
    }


def plugin_adapt(uri: str) -> bool:
    return uri in FIELDS.keys()


def plugin_capacities() -> list:
    return list(FIELDS.keys())


# ----------------------------------------------------------------------------------------------------------------------

# submissions: https://www.sec.gov/edgar/sec-api-documentation

def __fetch_securities_info(**kwargs) -> pd.DataFrame or None:
    result = check_execute_test_flag(**kwargs)
    if result is None:
        stock_identity = kwargs.get('stock_identity', '')
        ticker = stock_identity_to_us_ticker(stock_identity)
        if not str_available(ticker):
            return None

        cik = sec_ticker_to_cik(ticker)
        if cik is None:
            return None

        submission = sec_company_submission(cik)
        if submission is None:
            return None

        exchanges = submission.get('exchanges') or []
        exchange = SEC_SAS_EXCHANGE_TABLE.get(exchanges[0].upper(), exchanges[0].upper()) if exchanges else 'US'

        result = pd.DataFrame([{
            'symbol':                 ticker,
            'name':                   submission.get('name', ticker),
            'industry':               submission.get('sicDescription', ''),
            'sic_code':               submission.get('sic', ''),
            'exchange':               exchange,
            'state_of_incorporation': submission.get('stateOfIncorporation', ''),
            'category':               submission.get('category', ''),
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
