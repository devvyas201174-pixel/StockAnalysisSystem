import requests
import pandas as pd
from os import path

from .common import *
from .time_utility import *


# Tushare access limit, as fetch times per minute.
# If fetch data from tushare gets error message like: "抱歉，您每分钟最多访问该接口x次"
# Fill the x to the corresponding entry of this table
# This config is for 5000 scores. The number in comments is for 2000 or less.
#
# You can put your delay config in config.json as:
#
#    "TS_DELAY": {
#        "daily_basic":          "0",
#        "fina_mainbz":          "0",
#        ......
#    }
#

DEFAULT_TS_DELAYER_TABLE = {
    'daily_basic':          DelayerMinuteLimit(500),          # 500
    'fina_mainbz':          DelayerMinuteLimit(60),          # 60

    'fina_audit':           DelayerMinuteLimit(50),          # 50
    'balancesheet':         DelayerMinuteLimit(50),          # 50
    'income':               DelayerMinuteLimit(50),          # 50
    'cashflow':             DelayerMinuteLimit(50),          # 50

    'index_daily':          DelayerMinuteLimit(500),          # 500
    'daily_index':          DelayerMinuteLimit(500),          # 500

    'concept_detail':       DelayerMinuteLimit(100),          # 100
    'namechange':           DelayerMinuteLimit(100),          # 100

    'pledge_stat':          DelayerMinuteLimit(1200),          # 1200
    'pledge_detail':        DelayerMinuteLimit(1200),          # 1200


    'stk_holdernumber':     DelayerMinuteLimit(10),          # 10
    'top10_holders':        DelayerMinuteLimit(10),          # 10
    'top10_floatholders':   DelayerMinuteLimit(10),          # 10
    'stk_holdertrade':      DelayerMinuteLimit(300),        # 300

    'daily':                DelayerMinuteLimit(1200),          # 1200
    'adj_factor':           DelayerMinuteLimit(1200),          # 1200

    'repurchase':           DelayerMinuteLimit(20),          # 20
    'share_float':          DelayerMinuteLimit(20),          # 20
}


delayer_table = DEFAULT_TS_DELAYER_TABLE


def set_delay_table(table: dict):
    global delayer_table
    try:
        for k, v in table.items():
            delayer_table[k] = DelayerMinuteLimit(int(v))
    except Exception as e:
        delayer_table = DEFAULT_TS_DELAYER_TABLE
        print('Set delay table fail: ' + str(e))
        print('Use default delay table.')
    finally:
        pass


def ts_delay(ts_interface: str):
    delayer = delayer_table.get(ts_interface)
    if delayer is not None:
        delayer.delay()


root_path = path.dirname(path.dirname(path.abspath(__file__)))


def param_as_date_str(kwargs: dict, param: str) -> str:
    dt = kwargs.get(param)
    if dt is None:
        return ''
    if not isinstance(dt, (datetime.datetime, datetime.date, str)):
        return ''
    if isinstance(dt, str):
        dt = text2date(dt)
    return dt.strftime('%Y%m%d')


def pickup_since_until_as_date(kwargs: dict) -> (str, str):
    since = kwargs.get('since', None)
    until = kwargs.get('until', None)
    return param_as_date_str(kwargs, since), param_as_date_str(kwargs, until)


# def ts_exchange_to_stock_exchange(exchange: str) -> str:
#     return {
#         'SH': 'SSE',
#         'SZ': 'SZSE',
#     }.get(exchange, exchange)
#
#
# def ts_code_to_stock_identity(ts_code: str) -> str:
#     parts = ts_code.split('.')
#     if len(parts) != 2:
#         # Error
#         return ts_code
#     return parts[0] + '.' + ts_exchange_to_stock_exchange(parts[1])


TS_SAS_IDENTITY_SUFFIX_TABLE = [
    ('SH',    'SSE'),
    ('SZ',    'SZSE'),
    ('CSI',   'CSI'),
    ('CIC',   'CICC'),
    ('SI',    'SW'),
    ('MI',    'MSCI'),
    # 'OTH' not a valid exchange
]


BAO_SAS_IDENTITY_SUFFIX_TABLE = [
    ('sh',    'SSE'),
    ('sz',    'SZSE'),
]


def stock_identity_to_ts_code(stock_identity: str) -> str:
    for ts_suffix, sas_suffix in TS_SAS_IDENTITY_SUFFIX_TABLE:
        if stock_identity.endswith(sas_suffix):
            return stock_identity.replace(sas_suffix, ts_suffix)
    return stock_identity


def ts_code_to_stock_identity(ts_code: str) -> str:
    for ts_suffix, sas_suffix in TS_SAS_IDENTITY_SUFFIX_TABLE:
        if ts_code.endswith(ts_suffix):
            return ts_code.replace(ts_suffix, sas_suffix)
    return ts_code


def bao_code_to_stock_identity(bao_code: str) -> str:
    for bao_prefix, sas_suffix in BAO_SAS_IDENTITY_SUFFIX_TABLE:
        if bao_code.startswith(bao_prefix):
            return bao_code.replace(bao_prefix + '.', '') + '.' + sas_suffix
    return bao_code


def code_exchange_to_ts_code(code: str, exchange: str) -> str:
    for ts_suffix, sas_suffix in TS_SAS_IDENTITY_SUFFIX_TABLE:
        if exchange == sas_suffix:
            return code + '.' + ts_suffix
    return code + '.' + exchange


def code_exchange_to_bao_code(code: str, exchange: str) -> str:
    for bao_prefix, sas_suffix in BAO_SAS_IDENTITY_SUFFIX_TABLE:
        if exchange == sas_suffix:
            return bao_prefix + '.' + code
    return exchange + '.' + code


def pickup_ts_code(kwargs: dict) -> str:
    stock_identity = kwargs.get('stock_identity')
    if stock_identity is not None:
        return stock_identity_to_ts_code(stock_identity)
    code = kwargs.get('code')
    exchange = kwargs.get('exchange')
    if code is None or exchange is None:
        return ''
    if not isinstance(code, str) or not isinstance(exchange, str):
        return ''
    return code_exchange_to_ts_code(code, exchange)


def pickup_bao_code(kwargs: dict) -> str:
    stock_identity = kwargs.get('stock_identity')
    if stock_identity is not None:
        return stock_identity_to_ts_code(stock_identity)
    code = kwargs.get('code')
    exchange = kwargs.get('exchange')
    if code is None or exchange is None:
        return ''
    if not isinstance(code, str) or not isinstance(exchange, str):
        return ''
    return code_exchange_to_bao_code(code, exchange)


def path_from_plugin_param(**kwargs) -> str:
    uri = kwargs.get('uri')
    file = uri.replace('.', '_')
    return root_path + '/TestData/' + file + '.csv'


def check_execute_test_flag(**kwargs) -> pd.DataFrame or None:
    if kwargs.get('test_flag', False):
        uri = path_from_plugin_param(**kwargs)
        return pd.DataFrame.from_csv(uri)
    return None


def check_execute_dump_flag(result: pd.DataFrame, **kwargs):
    if kwargs.get('dump_flag', False):
        uri = path_from_plugin_param(**kwargs)
        result.to_csv(uri)


def is_slice_update(ts_code: str, since: datetime.datetime, until: datetime.datetime) -> bool:
    return not str_available(ts_code) and isinstance(since, datetime.datetime)


def convert_ts_code_field(df: pd.DataFrame, ts_field: str = 'ts_code',
                          sas_field: str = 'stock_identity') -> pd.DataFrame:
    df[sas_field] = df[ts_field].apply(ts_code_to_stock_identity)
    if sas_field != ts_field:
        del df[ts_field]
    return df


def convert_ts_date_field(df: pd.DataFrame, ts_field: str,
                          sas_field: str or None = None) -> pd.DataFrame:
    sas_field = ts_field if sas_field is None else sas_field
    df[sas_field] = pd.to_datetime(df[ts_field])
    if sas_field != ts_field:
        del df[ts_field]
    return df


# ------------------------------------------------------------------------------------------------------------------
# Yahoo Finance chart endpoint (US market prices).
#
# The yfinance package's bundled curl_cffi networking layer does not tolerate a TLS-terminating proxy, so the
# price collector talks to Yahoo's public chart JSON endpoint directly via `requests`. Unlike Yahoo's
# quoteSummary endpoint (see the SEC EDGAR helpers below, used instead for company info/financials), the chart
# endpoint needs no cookie/crumb handshake and has proven reliable.

YAHOO_CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
YAHOO_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

__yahoo_session = None


def yahoo_session() -> requests.Session:
    global __yahoo_session
    if __yahoo_session is None:
        __yahoo_session = requests.Session()
        __yahoo_session.headers.update({'User-Agent': YAHOO_USER_AGENT})
    return __yahoo_session


def yahoo_fetch_json(url: str, params: dict = None) -> dict or None:
    try:
        resp = yahoo_session().get(url, params=params, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        print('Yahoo finance fetch fail: HTTP %d for %s' % (resp.status_code, url))
    except Exception as e:
        print('Yahoo finance fetch fail: ' + str(e))
    return None


def us_ticker_to_stock_identity(ticker: str, exchange: str = 'NASDAQ') -> str:
    return ticker.upper() + '.' + exchange


def stock_identity_to_us_ticker(stock_identity: str) -> str:
    return stock_identity.split('.')[0] if str_available(stock_identity) else stock_identity


# ------------------------------------------------------------------------------------------------------------------
# SEC EDGAR helpers (US market company info + financial statements).
#
# Free, no API key, no cookie/crumb dance - just a descriptive User-Agent per SEC's fair-use policy
# (https://www.sec.gov/os/webmaster-faq#developers). Covers every US-listed filer's actual filed financials
# (10-K/10-Q), sourced straight from XBRL.

SEC_TICKER_CIK_URL = 'https://www.sec.gov/files/company_tickers.json'
SEC_SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK{cik}.json'
SEC_COMPANY_FACTS_URL = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
SEC_USER_AGENT = 'StockAnalysisSystem-US-market-plugin research@example.com'

__sec_session = None
__sec_ticker_cik_map = None


def sec_session() -> requests.Session:
    global __sec_session
    if __sec_session is None:
        __sec_session = requests.Session()
        __sec_session.headers.update({'User-Agent': SEC_USER_AGENT})
    return __sec_session


def sec_fetch_json(url: str) -> dict or None:
    try:
        resp = sec_session().get(url, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        print('SEC EDGAR fetch fail: HTTP %d for %s' % (resp.status_code, url))
    except Exception as e:
        print('SEC EDGAR fetch fail: ' + str(e))
    return None


def sec_ticker_to_cik(ticker: str) -> str or None:
    global __sec_ticker_cik_map
    if __sec_ticker_cik_map is None:
        data = sec_fetch_json(SEC_TICKER_CIK_URL) or {}
        __sec_ticker_cik_map = {v['ticker'].upper(): str(v['cik_str']).zfill(10) for v in data.values()}
    return __sec_ticker_cik_map.get(ticker.upper())


def sec_company_submission(cik: str) -> dict or None:
    return sec_fetch_json(SEC_SUBMISSIONS_URL.format(cik=cik))


def sec_company_facts(cik: str) -> dict or None:
    return sec_fetch_json(SEC_COMPANY_FACTS_URL.format(cik=cik))


def sec_extract_annual_facts(company_facts: dict, tag_candidates: [str], taxonomy: str = 'us-gaap') -> list:
    """
    SEC's XBRL tag naming drifts across filing years and companies (e.g. a company may report revenue under
    'Revenues' in older filings and 'RevenueFromContractWithCustomerExcludingAssessedTax' in newer ones), so
    this tries each candidate tag in order and returns the annual (10-K, full-year) USD datapoints of the
    first one that has any.
    """
    gaap = (company_facts.get('facts') or {}).get(taxonomy) or {}
    for tag in tag_candidates:
        concept = gaap.get(tag)
        if concept is None:
            continue
        usd = (concept.get('units') or {}).get('USD') or []
        annuals = [d for d in usd if d.get('form') == '10-K' and d.get('fp') == 'FY']
        if annuals:
            return annuals
    return []



