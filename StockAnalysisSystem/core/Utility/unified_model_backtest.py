"""
Point-in-time backtest of the Unified Model's price-based inputs.

At each rebalance date every stock is scored using only prices up to that date (Phase 5 technicals and the
Phase 2 volatility input, through v2's own curves), then compared with its next-12-month return minus SPY's.
No fundamentals are used: Yahoo only serves ~4 years of statements without as-reported dates, so a
fundamental backtest from it would leak later data.

Reports, per signal and for the Phase 5 composite:
  - mean rank IC (Spearman correlation of score vs forward excess return across stocks, per date)
  - t-stat of IC on non-overlapping 12-month dates (overlapping windows would overstate significance)
  - top-minus-bottom quintile forward excess return
  - share of top-quintile picks that beat SPY

Caveat: the default universe is today's large caps, so it carries survivorship bias (losers that were
delisted are missing). Treat absolute returns as flattering; the comparison between signals is the useful part.
"""

import math

from . import unified_model_v2 as v2
from .unified_model_data import YahooClient, price_inputs, SECTOR_PEERS


SIGNALS = ['p5_200', 'p5_mom', 'p5_rsi', 'p5_rs', 'p2_vol']
HORIZON = 252
STEP = 21


def _rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2.0
        i = j + 1
    return ranks


def spearman(x, y):
    if len(x) < 5:
        return None
    rx, ry = _rank(x), _rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return None if vx == 0 or vy == 0 else cov / (vx * vy)


def _field_score(fid, value):
    return v2.score_field(fid, {fid: value}, v2.classify_regime())


def _p5_score(inputs):
    sw = ss = 0.0
    for f in v2.FIELDS:
        if f['ph'] == 'p5':
            s = _field_score(f['id'], inputs.get(f['id']))
            if s is not None:
                sw += f['w']
                ss += f['w'] * s
    return ss / sw if sw else None


def load_prices(tickers, client=None, range_='10y', log=print):
    client = client or YahooClient()
    data = {}
    for t in list(tickers) + ['SPY']:
        p = client.prices(t, range_=range_)
        if len(p) > 260 + HORIZON or t == 'SPY':
            data[t] = p
        else:
            log('  skipped %s: %d price points' % (t, len(p)))
    return data


def run_backtest(prices: dict, horizon=HORIZON, step=STEP) -> dict:
    """prices: {ticker: [(date, close)]} including 'SPY'."""
    spy = prices['SPY']
    spy_idx = {d: i for i, (d, _) in enumerate(spy)}
    spy_closes = [c for _, c in spy]
    series = {t: ([d for d, _ in p], [c for _, c in p]) for t, p in prices.items() if t != 'SPY'}

    dates = [spy[i][0] for i in range(260, len(spy) - horizon, step)]
    names = SIGNALS + ['p5_composite']
    per_date = []
    for d in dates:
        si = spy_idx[d]
        spy_fwd = spy_closes[si + horizon] / spy_closes[si] - 1
        rows = []
        for t, (ds, cs) in series.items():
            # Position of d in this ticker's history (exact trading-day match only).
            try:
                i = ds.index(d)
            except ValueError:
                continue
            if i < 260 or i + horizon >= len(cs):
                continue
            inp = price_inputs(cs[:i + 1], spy_closes[:si + 1])
            sc = {f: _field_score(f, inp.get(f)) for f in SIGNALS}
            sc['p5_composite'] = _p5_score(inp)
            rows.append((sc, cs[i + horizon] / cs[i] - 1 - spy_fwd))
        if len(rows) >= 10:
            per_date.append((d, rows))

    out = {'dates': len(per_date), 'first': str(per_date[0][0]) if per_date else None,
           'last': str(per_date[-1][0]) if per_date else None,
           'stocks': len(series), 'signals': {}}
    for name in names:
        ics, spreads, top_hits, top_n = [], [], 0, 0
        for d, rows in per_date:
            pairs = [(r[0][name], r[1]) for r in rows if r[0][name] is not None]
            if len(pairs) < 10:
                ics.append(None)
                continue
            xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
            ics.append(spearman(xs, ys))
            ordered = sorted(pairs, key=lambda p: p[0])
            q = max(1, len(ordered) // 5)
            top, bot = ordered[-q:], ordered[:q]
            spreads.append(sum(p[1] for p in top) / q - sum(p[1] for p in bot) / q)
            top_hits += sum(1 for p in top if p[1] > 0)
            top_n += q
        valid = [x for x in ics if x is not None]
        # Non-overlapping sample: every (horizon/step)-th date.
        k = max(1, horizon // step)
        indep = [x for x in ics[::k] if x is not None]
        t_stat = None
        if len(indep) >= 5:
            m = sum(indep) / len(indep)
            sd = math.sqrt(sum((x - m) ** 2 for x in indep) / (len(indep) - 1))
            t_stat = m / (sd / math.sqrt(len(indep))) if sd > 0 else None
        out['signals'][name] = {
            'mean_ic': sum(valid) / len(valid) if valid else None,
            'ic_positive_share': sum(1 for x in valid if x > 0) / len(valid) if valid else None,
            'independent_periods': len(indep),
            't_stat': t_stat,
            'top_minus_bottom': sum(spreads) / len(spreads) if spreads else None,
            'top_quintile_hit_rate': top_hits / top_n if top_n else None,
        }
    return out


def format_backtest(r: dict) -> str:
    lines = ['Price-signal backtest: %d stocks, %d monthly dates (%s to %s), 12-month forward excess vs SPY' %
             (r['stocks'], r['dates'], r['first'], r['last']),
             '%-13s %8s %8s %8s %12s %10s' % ('signal', 'mean IC', 'IC>0', 't-stat', 'top-bottom', 'top hit')]
    def f(x, fmt):
        return '-' if x is None else fmt % x

    for name, s in r['signals'].items():
        lines.append('%-13s %8s %8s %8s %12s %10s' % (
            name, f(s['mean_ic'], '%.3f'), f(s['ic_positive_share'] and s['ic_positive_share'] * 100, '%.0f%%'),
            f(s['t_stat'], '%.2f'), f(s['top_minus_bottom'] and s['top_minus_bottom'] * 100, '%+.1f%%'),
            f(s['top_quintile_hit_rate'] and s['top_quintile_hit_rate'] * 100, '%.0f%%')))
    lines.append('Survivorship bias: the universe is today\'s large caps. Compare signals, not absolute returns.')
    return '\n'.join(lines)


def default_universe():
    return sorted({t for ts in SECTOR_PEERS.values() for t in ts})
