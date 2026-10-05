"""
Auto-fill Unified Model inputs from Yahoo Finance.

Every input that can be measured is computed here instead of typed in, so scores are reproducible and the
price-based ones can be backtested without hindsight. Judgement inputs (moat source, defensible revenue,
capital allocation, customer concentration, guidance, insider activity, macro exposure, portfolio fit, gates,
and P/E vs its own history) are not fetched; pass them in yourself.

Talks to Yahoo's public JSON endpoints with requests only (same cookie + crumb handshake the collectors use),
so it works without the rest of the system's dependencies.
"""

import math
import time
import datetime

import requests


YAHOO_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
SUMMARY_URL = 'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}'
TIMESERIES_URL = 'https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}'
CRUMB_URL = 'https://query1.finance.yahoo.com/v1/test/getcrumb'

SUMMARY_MODULES = 'price,summaryDetail,defaultKeyStatistics,financialData,assetProfile,earningsTrend,calendarEvents'
TIMESERIES_TYPES = [
    'trailingTotalRevenue', 'trailingGrossProfit', 'trailingNetIncome', 'trailingFreeCashFlow', 'trailingEBITDA',
    'trailingEBIT', 'trailingInterestExpense', 'trailingStockBasedCompensation', 'trailingTaxRateForCalcs',
    'quarterlyTotalDebt', 'quarterlyCashAndCashEquivalents', 'quarterlyTotalAssets', 'quarterlyInvestedCapital',
    'annualTotalRevenue', 'annualGrossProfit',
]

# Cost of equity used for the reverse DCF and ROIC spread: 10-yr yield + this premium.
EQUITY_PREMIUM = 5.0
TERMINAL_GROWTH = 3.0
DCF_YEARS = 10


class YahooClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': YAHOO_USER_AGENT})
        self.crumb = None

    def _crumb(self, refresh=False):
        if self.crumb is None or refresh:
            try:
                self.session.get('https://fc.yahoo.com', timeout=20)
            except requests.RequestException:
                pass
            resp = self.session.get(CRUMB_URL, timeout=20)
            self.crumb = resp.text.strip() if resp.status_code == 200 else ''
        return self.crumb

    def get(self, url, params=None, crumb=False, retry=2):
        params = dict(params or {})
        for attempt in range(retry + 1):
            if crumb:
                params['crumb'] = self._crumb(refresh=attempt > 0)
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
            except (requests.RequestException, ValueError):
                pass
            time.sleep(1 + attempt)
        return None

    def prices(self, symbol, range_='2y'):
        """[(date, adjusted close)] daily."""
        d = self.get(CHART_URL.format(symbol=symbol), {'range': range_, 'interval': '1d'})
        try:
            r = d['chart']['result'][0]
            ts = r['timestamp']
            closes = (r['indicators'].get('adjclose') or [{}])[0].get('adjclose') or r['indicators']['quote'][0]['close']
        except (TypeError, KeyError, IndexError):
            return []
        return [(datetime.datetime.utcfromtimestamp(t).date(), c) for t, c in zip(ts, closes) if c is not None]

    def summary(self, symbol):
        d = self.get(SUMMARY_URL.format(symbol=symbol), {'modules': SUMMARY_MODULES}, crumb=True)
        try:
            return d['quoteSummary']['result'][0]
        except (TypeError, KeyError, IndexError):
            return {}

    def timeseries(self, symbol, types=None):
        """{type: [(asOfDate, value)] oldest first}."""
        d = self.get(TIMESERIES_URL.format(symbol=symbol),
                     {'type': ','.join(types or TIMESERIES_TYPES), 'period1': 1420070400,
                      'period2': int(time.time()) + 86400}, crumb=True)
        out = {}
        try:
            for x in d['timeseries']['result']:
                t = x['meta']['type'][0]
                out[t] = [(e['asOfDate'], e['reportedValue']['raw']) for e in (x.get(t) or []) if e]
        except (TypeError, KeyError):
            pass
        return out

    def ten_year_yield(self):
        d = self.get(CHART_URL.format(symbol='^TNX'), {'range': '5d', 'interval': '1d'})
        try:
            return float(d['chart']['result'][0]['meta']['regularMarketPrice'])
        except (TypeError, KeyError, IndexError, ValueError):
            return None


# ----------------------------------------------------------------------------------------------------------------------
#                                                Price-based indicators
# ----------------------------------------------------------------------------------------------------------------------
# Each takes a list of closes (oldest first) ending at the as-of date, so the backtest can call them on history.

def pct_vs_sma(closes, n=200):
    if len(closes) < n:
        return None
    return (closes[-1] / (sum(closes[-n:]) / n) - 1) * 100


def momentum_12_1(closes):
    """12-month return skipping the latest month (252 / 21 trading days)."""
    if len(closes) < 253:
        return None
    return (closes[-22] / closes[-253] - 1) * 100


def rsi(closes, n=14):
    if len(closes) < n * 3:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def relative_strength_6m(closes, bench_closes):
    if len(closes) < 127 or len(bench_closes) < 127:
        return None
    return ((closes[-1] / closes[-127]) - (bench_closes[-1] / bench_closes[-127])) * 100


def volatility(closes, n=252):
    if len(closes) < 60:
        return None
    c = closes[-(n + 1):]
    r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252) * 100


def price_inputs(closes, bench_closes):
    return {
        'p5_200': pct_vs_sma(closes),
        'p5_mom': momentum_12_1(closes),
        'p5_rsi': rsi(closes),
        'p5_rs': relative_strength_6m(closes, bench_closes),
        'p2_vol': volatility(closes),
    }


def post_earnings_move(prices, report_date):
    """Close the session before the report date to the close 3 sessions after it, in %."""
    if report_date is None:
        return None
    before = [c for d, c in prices if d < report_date]
    after = [c for d, c in prices if d >= report_date]
    if not before or len(after) < 4:
        return None
    return (after[3] / before[-1] - 1) * 100


def implied_growth(market_value, cash_flow, discount=10.0, terminal=TERMINAL_GROWTH, years=DCF_YEARS):
    """Reverse DCF: the constant growth (%/yr) for `years` years that makes the DCF equal market value."""
    if not market_value or not cash_flow or cash_flow <= 0 or discount <= terminal:
        return None
    r, tg = discount / 100, terminal / 100

    def value(g):
        v, cf = 0.0, cash_flow
        for t in range(1, years + 1):
            cf *= 1 + g
            v += cf / (1 + r) ** t
        return v + cf * (1 + tg) / (r - tg) / (1 + r) ** years

    lo, hi = -0.5, 1.5
    if value(lo) > market_value:
        return lo * 100
    if value(hi) < market_value:
        return hi * 100
    for _ in range(100):
        mid = (lo + hi) / 2
        if value(mid) < market_value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 * 100


# ----------------------------------------------------------------------------------------------------------------------
#                                                     Assemble inputs
# ----------------------------------------------------------------------------------------------------------------------

def _raw(x):
    return x.get('raw') if isinstance(x, dict) else x


def _last(series, key):
    v = series.get(key) or []
    return v[-1] if v else (None, None)


def _div(a, b):
    return None if a is None or b in (None, 0) else a / b


def fundamental_inputs(summary: dict, series: dict, ten_year: float) -> (dict, dict):
    """Returns (inputs, notes). Financial-sector lenders use net income in place of FCF (loan growth runs
    through investing cash flow, so FCF there is not owners' cash)."""
    sd = summary.get('summaryDetail', {})
    ks = summary.get('defaultKeyStatistics', {})
    pr = summary.get('price', {})
    sector = summary.get('assetProfile', {}).get('sector')
    financial = sector == 'Financial Services'
    notes, inputs = {}, {}

    mcap = _raw(pr.get('marketCap')) or _raw(sd.get('marketCap'))
    _, rev = _last(series, 'trailingTotalRevenue')
    _, gp = _last(series, 'trailingGrossProfit')
    _, ni = _last(series, 'trailingNetIncome')
    _, fcf = _last(series, 'trailingFreeCashFlow')
    _, ebitda = _last(series, 'trailingEBITDA')
    _, sbc = _last(series, 'trailingStockBasedCompensation')
    _, debt = _last(series, 'quarterlyTotalDebt')
    _, cash = _last(series, 'quarterlyCashAndCashEquivalents')
    _, assets = _last(series, 'quarterlyTotalAssets')
    _, ic = _last(series, 'quarterlyInvestedCapital')
    _, tax = _last(series, 'trailingTaxRateForCalcs')

    owner_cash = ni if financial else fcf
    if financial:
        notes['cash_flow_basis'] = 'net income (financial sector)'

    coe = ten_year + EQUITY_PREMIUM
    inputs['p1_implied'] = implied_growth(mcap, owner_cash, discount=coe)
    yld = _div(owner_cash, mcap)
    inputs['p1_fcf'] = None if yld is None else yld * 100

    fpe = _raw(sd.get('forwardPE')) or _raw(ks.get('forwardPE'))
    g1 = None
    for t in summary.get('earningsTrend', {}).get('trend', []):
        if t.get('period') == '+1y':
            g1 = _raw(t.get('growth'))
    inputs['p1_peg'] = fpe / (g1 * 100) if fpe and g1 and g1 > 0 else None

    inputs['p2_nde'] = _div(None if debt is None else debt - (cash or 0), ebitda) if ebitda and ebitda > 0 else None

    # Interest coverage: latest EBIT / interest pair reported for the same period.
    ebit_s = dict(series.get('trailingEBIT') or [])
    int_s = dict(series.get('trailingInterestExpense') or [])
    common = sorted(set(ebit_s) & set(int_s))
    if common and int_s[common[-1]]:
        inputs['p2_cov'] = ebit_s[common[-1]] / abs(int_s[common[-1]])
        notes['p2_cov_as_of'] = common[-1]

    inputs['p3_fcfconv'] = None if financial else (_div(fcf, ni) * 100 if fcf is not None and ni and ni > 0 else None)
    inputs['p3_sbc'] = None if _div(sbc, rev) is None else _div(sbc, rev) * 100

    revs = []
    for t in summary.get('earningsTrend', {}).get('trend', []):
        if t.get('period') in ('0y', '+1y'):
            et = t.get('epsTrend', {})
            cur, old = _raw(et.get('current')), _raw(et.get('90daysAgo'))
            if cur is not None and old:
                revs.append((cur / old - 1) * 100)
    inputs['p3_rev'] = sum(revs) / len(revs) if revs else None

    nopat = None
    _, ebit = _last(series, 'trailingEBIT')
    if ebit is not None:
        nopat = ebit * (1 - (tax if tax is not None else 0.21))
    roic = _div(nopat, ic)
    inputs['p6_roic'] = None if roic is None or (ic or 0) <= 0 else roic * 100 - coe

    ar, ag = series.get('annualTotalRevenue') or [], dict(series.get('annualGrossProfit') or [])
    margins = [(d, ag[d] / r) for d, r in ar if d in ag and r]
    if len(margins) >= 2:
        old = margins[-4] if len(margins) >= 4 else margins[0]
        inputs['p6_gm'] = (margins[-1][1] - old[1]) * 100
        notes['p6_gm_window'] = '%s to %s' % (old[0], margins[-1][0])

    inputs['p7_gpa'] = None if _div(gp, assets) is None else _div(gp, assets) * 100

    # Insider activity (p7_ins) stays manual: Yahoo's netSharePurchaseActivity counts stock awards as buys,
    # so it reports 'net buying' for companies whose insiders only ever sell in the open market.

    si = _raw(ks.get('shortPercentOfFloat'))
    inputs['p7_si'] = None if si is None else si * 100

    notes['sector'] = sector
    notes['industry'] = summary.get('assetProfile', {}).get('industry')
    notes['market_cap'] = mcap
    notes['cost_of_equity'] = coe
    return {k: v for k, v in inputs.items() if v is not None}, notes


def last_report_date(summary: dict):
    cal = summary.get('calendarEvents', {}).get('earnings', {})
    for key in ('earningsCallDate', 'earningsDate'):
        dates = [_raw(x) for x in cal.get(key) or []]
        past = [d for d in dates if d and d < time.time()]
        if past:
            return datetime.datetime.utcfromtimestamp(max(past)).date()
    return None


def auto_inputs(ticker: str, client: YahooClient = None, ten_year: float = None) -> dict:
    """
    Fetch and compute every measurable input for `ticker`.
    :return: {'inputs': {field_id: value}, 'notes': {...}, 'ten_year': float, 'price': float}
    """
    client = client or YahooClient()
    ten_year = ten_year if ten_year is not None else (client.ten_year_yield() or 4.5)
    summary = client.summary(ticker)
    series = client.timeseries(ticker)
    prices = client.prices(ticker)
    bench = client.prices('SPY')

    closes = [c for _, c in prices]
    inputs = {k: v for k, v in price_inputs(closes, [c for _, c in bench]).items() if v is not None}
    fin, notes = fundamental_inputs(summary, series, ten_year)
    inputs.update(fin)

    rd = last_report_date(summary)
    pead = post_earnings_move(prices, rd)
    if pead is not None:
        inputs['p7_pead'] = pead
        notes['last_report'] = rd.isoformat()

    return {'ticker': ticker.upper(), 'inputs': inputs, 'notes': notes, 'ten_year': ten_year,
            'price': closes[-1] if closes else None,
            'as_of': prices[-1][0].isoformat() if prices else None}


# ----------------------------------------------------------------------------------------------------------------------
#                                                     Sector medians
# ----------------------------------------------------------------------------------------------------------------------
# Inputs whose normal range depends on the industry. v2.1 scores them partly against the sector's median
# rather than one market-wide scale (a utility's leverage or a software firm's SBC is normal for its sector).

SECTOR_FIELDS = ['p2_nde', 'p2_cov', 'p2_vol', 'p3_fcfconv', 'p3_sbc', 'p7_gpa']

SECTOR_PEERS = {
    'Technology': ['MSFT', 'AAPL', 'NVDA', 'ORCL', 'ADBE', 'CSCO', 'TXN', 'IBM', 'INTU', 'QCOM', 'AMAT', 'CRM'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'EA', 'CHTR', 'OMC'],
    'Consumer Cyclical': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'LOW', 'SBUX', 'BKNG', 'TJX', 'GM', 'ORLY', 'CMG'],
    'Consumer Defensive': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'MDLZ', 'CL', 'KMB', 'GIS', 'MO', 'HSY', 'KR'],
    'Healthcare': ['JNJ', 'UNH', 'LLY', 'MRK', 'ABBV', 'PFE', 'TMO', 'ABT', 'DHR', 'MDT', 'AMGN', 'ISRG'],
    'Financial Services': ['JPM', 'BAC', 'V', 'MA', 'AXP', 'COF', 'SYF', 'GS', 'SPGI', 'SCHW', 'AFRM', 'ALLY'],
    'Industrials': ['GE', 'HON', 'UNP', 'CAT', 'DE', 'LMT', 'RTX', 'UPS', 'ITW', 'ETN', 'WM', 'EMR'],
    'Energy': ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PSX', 'MPC', 'OXY', 'VLO', 'WMB', 'KMI', 'HAL'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'PEG', 'ED', 'WEC', 'EIX'],
    'Real Estate': ['PLD', 'AMT', 'EQIX', 'PSA', 'O', 'SPG', 'WELL', 'DLR', 'CCI', 'AVB', 'EQR', 'REG'],
    'Basic Materials': ['LIN', 'SHW', 'APD', 'ECL', 'NEM', 'FCX', 'DOW', 'NUE', 'PPG', 'VMC', 'MLM', 'DD'],
}


# Industries too different from the rest of their Yahoo sector to share its median (Yahoo files Visa and
# Mastercard under 'Credit Services' too; the list here is lenders only). Keyed 'industry:<Yahoo industry>'.
INDUSTRY_PEERS = {
    'Credit Services': ['AFRM', 'SYF', 'COF', 'AXP', 'ALLY', 'SOFI', 'UPST', 'OMF', 'ENVA', 'BFH', 'SLM', 'NAVI'],
    'Banks - Diversified': ['JPM', 'BAC', 'C', 'WFC'],
    'Banks - Regional': ['USB', 'PNC', 'TFC', 'FITB', 'MTB', 'HBAN', 'RF', 'KEY', 'CFG', 'ZION'],
    'Software - Application': ['CRM', 'INTU', 'ADBE', 'NOW', 'WDAY', 'ADSK', 'TEAM', 'DDOG', 'HUBS', 'TYL'],
    'Software - Infrastructure': ['MSFT', 'ORCL', 'PANW', 'CRWD', 'FTNT', 'SNPS', 'CDNS', 'ZS', 'NET', 'AKAM'],
    'Semiconductors': ['NVDA', 'AVGO', 'AMD', 'QCOM', 'TXN', 'ADI', 'MU', 'INTC', 'MCHP', 'NXPI', 'ON', 'MRVL'],
    'Biotechnology': ['AMGN', 'GILD', 'VRTX', 'REGN', 'BIIB', 'ALNY', 'INCY', 'BMRN', 'NBIX', 'EXEL'],
}


def _median(values):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def build_sector_medians(peers: dict = None, industry_peers: dict = None, client: YahooClient = None,
                         log=print) -> dict:
    """Fetch every peer and return {sector or 'industry:<name>': {field: median},
    '_market': {field: median over the sector peers}, '_as_of', '_peers'}."""
    client = client or YahooClient()
    ten_year = client.ten_year_yield() or 4.5
    peers = peers or SECTOR_PEERS
    industry_peers = INDUSTRY_PEERS if industry_peers is None else industry_peers
    groups = dict(peers)
    groups.update({'industry:' + k: v for k, v in industry_peers.items()})
    rows = {}
    for sector, tickers in groups.items():
        rows[sector] = []
        for t in tickers:
            try:
                r = auto_inputs(t, client=client, ten_year=ten_year)
                rows[sector].append({f: r['inputs'].get(f) for f in SECTOR_FIELDS})
                log('  %-24s %-6s ok' % (sector, t))
            except Exception as e:
                log('  %-24s %-6s failed: %s' % (sector, t, e))
    out = {s: {f: _median([r[f] for r in rs]) for f in SECTOR_FIELDS} for s, rs in rows.items()}
    every = [r for s, rs in rows.items() if not s.startswith('industry:') for r in rs]
    out['_market'] = {f: _median([r[f] for r in every]) for f in SECTOR_FIELDS}
    out['_as_of'] = datetime.date.today().isoformat()
    out['_peers'] = groups
    return out
