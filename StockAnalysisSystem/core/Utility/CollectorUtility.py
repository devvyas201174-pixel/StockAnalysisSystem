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
# Yahoo Finance (US market) helpers.
#
# The yfinance package's bundled curl_cffi networking layer does not tolerate a TLS-terminating proxy, so these
# collectors talk to the same public Yahoo Finance JSON endpoints directly via `requests`, using a plain cookie +
# crumb handshake (the same one yfinance itself performs internally).

YAHOO_CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
YAHOO_QUOTE_SUMMARY_URL = 'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}'
YAHOO_CRUMB_URL = 'https://query1.finance.yahoo.com/v1/test/getcrumb'
YAHOO_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

__yahoo_session = None
__yahoo_crumb = None


def yahoo_session() -> requests.Session:
    global __yahoo_session
    if __yahoo_session is None:
        __yahoo_session = requests.Session()
        __yahoo_session.headers.update({'User-Agent': YAHOO_USER_AGENT})
    return __yahoo_session


def yahoo_crumb(force_refresh: bool = False) -> str:
    global __yahoo_crumb
    if __yahoo_crumb is None or force_refresh:
        try:
            resp = yahoo_session().get(YAHOO_CRUMB_URL, timeout=20)
            __yahoo_crumb = resp.text.strip() if resp.status_code == 200 else ''
        except Exception as e:
            print('Yahoo finance crumb fetch fail: ' + str(e))
            __yahoo_crumb = ''
    return __yahoo_crumb


def yahoo_fetch_json(url: str, params: dict = None, use_crumb: bool = False, retry: int = 2) -> dict or None:
    """
    GET a Yahoo Finance JSON endpoint. Yahoo's crumb tokens can be rejected under load (401/429); on such a
    response this refreshes the crumb and retries, up to `retry` times.
    """
    params = dict(params) if params is not None else {}
    for attempt in range(retry + 1):
        if use_crumb:
            params['crumb'] = yahoo_crumb(force_refresh=(attempt > 0))
        try:
            resp = yahoo_session().get(url, params=params, timeout=20)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (401, 429) and use_crumb and attempt < retry:
                continue
            print('Yahoo finance fetch fail: HTTP %d for %s' % (resp.status_code, url))
        except Exception as e:
            print('Yahoo finance fetch fail: ' + str(e))
        break
    return None


YAHOO_SAS_EXCHANGE_TABLE = [
    ('NMS', 'NASDAQ'),
    ('NGM', 'NASDAQ'),
    ('NCM', 'NASDAQ'),
    ('NYQ', 'NYSE'),
    ('ASE', 'AMEX'),
    ('PCX', 'ARCA'),
]


def yahoo_exchange_to_sas_exchange(yahoo_exchange: str) -> str:
    for yahoo_ex, sas_ex in YAHOO_SAS_EXCHANGE_TABLE:
        if yahoo_exchange == yahoo_ex:
            return sas_ex
    return yahoo_exchange if str_available(yahoo_exchange) else 'US'


def us_ticker_to_stock_identity(ticker: str, exchange: str = 'NASDAQ') -> str:
    return ticker.upper() + '.' + exchange


def stock_identity_to_us_ticker(stock_identity: str) -> str:
    return stock_identity.split('.')[0] if str_available(stock_identity) else stock_identity



