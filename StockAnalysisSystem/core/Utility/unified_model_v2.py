"""
Unified Model v2 - regime-aware, 9-phase stock scorecard.

A pure-Python port of the "Unified Model v2" scorecard engine (the Cowork artifact). Phases 1-8 are scored
from user-supplied inputs on piecewise-linear curves, weighted by a macro regime (Layer 0), then run through
kill switches to produce the Phase 9 decision: score, verdict, action and a volatility-adjusted position size.

Bands (unchanged from v1): >= 7.5 Strong Buy, 6 - 7.5 Buy, 4.5 - 6 Watch, < 4.5 Pass.

Usage:
    result = score_stock({'p1_implied': 12, 'p1_fcf': 3.2, ...}, regime=None)
    result['score'], result['verdict'], result['action']

Blank inputs (None / '' / missing) are left out rather than guessed; 'coverage' reports how much of the model ran.
"""

import copy


# ----------------------------------------------------------------------------------------------------------------------
#                                                     Regime (Layer 0)
# ----------------------------------------------------------------------------------------------------------------------

REGIME_DEFAULT = {
    'asOf': '22 Sep 2026',
    'tenY': 4.97,           # 10-yr Treasury, %
    'twoY': 4.75,           # 2-yr Treasury, %
    'fed': 'hiking',        # hiking / hold / cutting
    'cpi': 3.4,             # CPI YoY, %
    'core': 2.4,            # Core CPI YoY, %
    'ism': 54.6,            # ISM manufacturing
    'ismP': 71.1,           # ISM prices paid
    'unemp': 4.1,           # Unemployment, %
    'unempTrend': 'flat',   # falling / flat / rising
    'oas': 270,             # High-yield spread, bp
    'cape': 40.7,           # Shiller CAPE
    'fwdpe': 19.1,          # S&P 500 forward P/E
    'vix': 17,
    'wti': 103,             # WTI crude, $
    'geo': 'on',            # Geopolitical stress: on / off
}

PHASES = [
    ('p1', 1, 'Valuation & expectations', 'Valuation'),
    ('p2', 2, 'Risk', 'Risk'),
    ('p3', 3, 'Earnings quality', 'Earnings'),
    ('p4', 4, 'Portfolio fit', 'Fit'),
    ('p5', 5, 'Technical', 'Technical'),
    ('p6', 6, 'Competitive position', 'Competitive'),
    ('p7', 7, 'Quant signals', 'Quant'),
    ('p8', 8, 'Macro fit', 'Macro'),
]

V1_WEIGHTS = [20, 15, 15, 10, 10, 10, 10, 10]

REGIME_WEIGHTS = {
    'Mid-cycle':             [20, 15, 15, 10, 10, 10, 10, 10],
    'Goldilocks':            [17, 12, 15, 10, 12, 12, 12, 10],
    'Soft landing':          [19, 14, 15, 10, 11, 11, 10, 10],
    'Overheat':              [23, 16, 15, 10, 8, 10, 7, 11],
    'Late cycle':            [22, 18, 15, 10, 8, 11, 6, 10],
    'Stagflation':           [20, 20, 14, 10, 8, 12, 4, 12],
    'Deflationary slowdown': [18, 22, 14, 10, 10, 14, 4, 8],
}


def classify_regime(regime: dict = None) -> dict:
    """Classify growth x inflation x policy and derive the regime-adjusted phase weights (in %, summing to 100)."""
    r = dict(REGIME_DEFAULT)
    if regime:
        r.update({k: v for k, v in regime.items() if v is not None})

    g = 0
    if r['ism'] >= 52:
        g += 1
    elif r['ism'] <= 48:
        g -= 1
    if r['unempTrend'] == 'rising':
        g -= 1
    elif r['unempTrend'] == 'falling':
        g += 1
    if r['oas'] > 500:
        g -= 1
    growth = 'expanding' if g >= 1 else ('contracting' if g <= -1 else 'neutral')

    if r['cpi'] >= 3.0 or r['ismP'] >= 65:
        infl = 'hot'
    elif r['cpi'] <= 2.3 and r['ismP'] < 55:
        infl = 'cool'
    else:
        infl = 'neutral'

    policy = 'tightening' if r['fed'] == 'hiking' else ('easing' if r['fed'] == 'cutting' else 'neutral')

    if growth == 'expanding':
        name = 'Overheat' if infl == 'hot' else ('Goldilocks' if infl == 'cool' else 'Mid-cycle')
    elif growth == 'contracting':
        name = 'Stagflation' if infl == 'hot' else 'Deflationary slowdown'
    else:
        name = 'Late cycle' if infl == 'hot' else ('Soft landing' if infl == 'cool' else 'Mid-cycle')

    erp = 100.0 / r['fwdpe'] - r['tenY']
    expensive = r['cape'] > 30 or erp < 1
    credit = r['oas'] > 500

    w = list(REGIME_WEIGHTS[name])
    notes = []

    def mv(to, frm, amt):
        take = min(amt, w[frm])
        w[frm] -= take
        w[to] += take

    if policy == 'tightening' and name not in ('Overheat', 'Late cycle', 'Stagflation'):
        mv(0, 4, 1)
        mv(0, 6, 1)
        notes.append('Tightening overlay: +2 valuation')
    if expensive:
        mv(0, 6, 2)
        mv(1, 4, 1)
        notes.append('Expensive-market overlay: +2 valuation, +1 risk')
    if credit:
        mv(1, 6, 2)
        notes.append('Credit-stress overlay: +2 risk')

    s = float(sum(w))
    w = [x * 100.0 / s for x in w]

    return {
        'name': name, 'growth': growth, 'infl': infl, 'policy': policy,
        'erp': erp, 'expensive': expensive, 'credit': credit,
        'oil': r['wti'] >= 90, 'geo': r['geo'] == 'on',
        'curve': (r['tenY'] - r['twoY']) * 100, 'real': r['tenY'] - r['core'],
        'weights': w, 'base_weights': list(REGIME_WEIGHTS[name]), 'notes': notes,
        'readings': r,
    }


# ----------------------------------------------------------------------------------------------------------------------
#                                                     Fields (Phases 1-8)
# ----------------------------------------------------------------------------------------------------------------------
# Each field: phase, weight within phase, label, and either
#   'pts'  - piecewise-linear curve [(x, score), ...], optionally with an 'x' transform(value, inputs, regime)
#   'opts' - {option: score}, or 'sc' - function(option, regime_readings, classification) for regime-scored options
#   'chk'  - boolean gate / modifier (not scored directly)

def _x_implied(v, inputs, reg):
    return v - (5 if inputs.get('p1_small') else 0)


def _x_fcf(v, inputs, reg):
    return v - reg['tenY']


def _sc_dur(v, reg, cl):
    return {'hiking':  {'short': 9, 'medium': 6, 'long': 3},
            'hold':    {'short': 7, 'medium': 7, 'long': 6},
            'cutting': {'short': 5, 'medium': 7, 'long': 9}}[reg['fed']].get(v)


def _sc_price(v, reg, cl):
    return {'hot':     {'high': 9, 'medium': 6, 'low': 2},
            'neutral': {'high': 8, 'medium': 6, 'low': 4},
            'cool':    {'high': 7, 'medium': 6, 'low': 5}}[cl['infl']].get(v)


def _sc_cyc(v, reg, cl):
    return {'expanding':   {'defensive': 5, 'moderate': 7, 'high': 8},
            'neutral':     {'defensive': 7, 'moderate': 6, 'high': 5},
            'contracting': {'defensive': 9, 'moderate': 5, 'high': 2}}[cl['growth']].get(v)


def _sc_cmdty(v, reg, cl):
    o = reg['wti']
    if o >= 90:
        t = {'benefit': 9, 'neutral': 6, 'hurt': 3}
    elif o <= 65:
        t = {'benefit': 4, 'neutral': 6, 'hurt': 8}
    else:
        t = {'benefit': 6, 'neutral': 6, 'hurt': 5}
    return t.get(v)


def _sc_geo(v, reg, cl):
    t = {'low': 9, 'moderate': 5.5, 'high': 2} if reg['geo'] == 'on' else {'low': 8, 'moderate': 6, 'high': 4}
    return t.get(v)


FIELDS = [
    # P1 - Valuation & expectations
    {'id': 'p1_implied', 'ph': 'p1', 'w': 35, 'x': _x_implied,
     'l': 'Reverse-DCF implied 10-yr FCF growth (%/yr)',
     'pts': [(0, 10), (5, 9), (10, 7), (15, 4.5), (20, 2.5), (30, 0.5)], 's': 12},
    {'id': 'p1_small', 'ph': 'p1', 'chk': True,
     'l': 'Revenue under $1bn (small-company base rates are ~4x more forgiving)', 's': False},
    {'id': 'p1_fcf', 'ph': 'p1', 'w': 25, 'x': _x_fcf,
     'l': 'Free-cash-flow yield (%)', 'pts': [(-4, 1), (-2, 3.5), (0, 6), (2, 8), (4, 10)], 's': 3.2},
    {'id': 'p1_relpe', 'ph': 'p1', 'w': 20, 'l': 'Forward P/E vs own 5-yr average (% premium)',
     'pts': [(-30, 10), (-15, 8), (0, 6), (20, 4), (50, 1.5), (80, 0.5)], 's': 10},
    {'id': 'p1_peg', 'ph': 'p1', 'w': 20, 'l': 'PEG (forward P/E / EPS growth)',
     'pts': [(0.5, 10), (0.8, 9), (1, 8), (1.5, 6), (2, 4), (3, 2), (4, 1)], 's': 1.6},
    # P2 - Risk
    {'id': 'p2_nde', 'ph': 'p2', 'w': 30, 'l': 'Net debt / EBITDA (x)',
     'pts': [(-1, 10), (0, 9.5), (1, 8.5), (2, 7), (3, 5), (4, 3), (5, 1.5), (6, 0.5)], 's': 1.2},
    {'id': 'p2_cov', 'ph': 'p2', 'w': 15, 'l': 'Interest coverage (EBIT / interest, x)',
     'pts': [(1.5, 1), (3, 4), (5, 6), (10, 8), (20, 10)], 's': 14},
    {'id': 'p2_conc', 'ph': 'p2', 'w': 25, 'l': 'Top-3 customers, % of revenue',
     'pts': [(10, 10), (25, 7), (40, 5), (60, 3), (75, 1)], 's': 22},
    {'id': 'p2_vol', 'ph': 'p2', 'w': 30, 'l': 'Annualised volatility (%)',
     'pts': [(15, 10), (20, 9.5), (30, 7.5), (40, 5.5), (60, 3), (90, 1)], 's': 32},
    # P3 - Earnings quality
    {'id': 'p3_fcfconv', 'ph': 'p3', 'w': 35, 'l': 'FCF / net income (%)',
     'pts': [(20, 1), (50, 4), (70, 6), (90, 8), (110, 10)], 's': 95},
    {'id': 'p3_sbc', 'ph': 'p3', 'w': 20, 'l': 'Stock-based comp, % of revenue',
     'pts': [(1, 10), (3, 8), (6, 6), (10, 4), (15, 2), (20, 1)], 's': 4},
    {'id': 'p3_rev', 'ph': 'p3', 'w': 30, 'l': 'Next-12m EPS estimate change, last 90 days (%)',
     'pts': [(-10, 1), (-5, 4), (0, 6), (5, 8), (10, 10)], 's': 3},
    {'id': 'p3_guide', 'ph': 'p3', 'w': 15, 'l': 'Guidance direction, last 2 quarters',
     'opts': {'raised': 9, 'maintained': 6, 'none': 5, 'cut': 2}, 's': 'raised'},
    # P4 - Portfolio fit
    {'id': 'p4_overlap', 'ph': 'p4', 'w': 40, 'l': 'Overlap with your largest existing theme',
     'opts': {'orthogonal': 10, 'partial': 6, 'same': 3}, 's': 'partial'},
    {'id': 'p4_weight', 'ph': 'p4', 'w': 30, 'l': 'Position weight in sleeve after buying (%)',
     'pts': [(3, 10), (5, 8), (8, 6), (12, 3), (20, 1)], 's': 5},
    {'id': 'p4_theme', 'ph': 'p4', 'w': 30, 'l': "Largest theme's share of sleeve after buying (%)",
     'pts': [(30, 10), (40, 8), (50, 6), (60, 3), (70, 1)], 's': 45},
    # P5 - Technical
    {'id': 'p5_200', 'ph': 'p5', 'w': 30, 'l': 'Price vs 200-day moving average (%)',
     'pts': [(-30, 1.5), (-20, 2.5), (-10, 3.5), (0, 5.5), (10, 8), (20, 8.5), (35, 6), (50, 3), (80, 1.5)], 's': 6},
    {'id': 'p5_mom', 'ph': 'p5', 'w': 30, 'l': '12-month return, excluding last month (%)',
     'pts': [(-50, 1), (-20, 3), (0, 5), (20, 7), (50, 9), (100, 8), (150, 6)], 's': 18},
    {'id': 'p5_rsi', 'ph': 'p5', 'w': 15, 'l': 'RSI (14-day)',
     'pts': [(20, 8), (30, 7.5), (50, 6), (65, 5), (75, 3), (85, 1)], 's': 55},
    {'id': 'p5_rs', 'ph': 'p5', 'w': 25, 'l': "6-month return minus S&P 500's (pts)",
     'pts': [(-30, 1), (-10, 4), (0, 5.5), (10, 7), (30, 9), (60, 8)], 's': 4},
    # P6 - Competitive position
    {'id': 'p6_roic', 'ph': 'p6', 'w': 30, 'l': 'ROIC minus WACC (pts)',
     'pts': [(-5, 1), (0, 3.5), (5, 6), (10, 7.5), (20, 9), (30, 10)], 's': 11},
    {'id': 'p6_moat', 'ph': 'p6', 'w': 20, 'l': 'Moat source strength (0-10)', 'pts': [(0, 0), (10, 10)], 's': 7},
    {'id': 'p6_def', 'ph': 'p6', 'w': 20, 'l': 'Defensible share of revenue (%)',
     'pts': [(20, 1), (40, 4.5), (55, 6.5), (70, 8), (85, 10)], 's': 60},
    {'id': 'p6_gm', 'ph': 'p6', 'w': 15, 'l': 'Gross margin change over 3 years (pts)',
     'pts': [(-5, 1), (-2, 4), (0, 6), (2, 8), (5, 10)], 's': 1.5},
    {'id': 'p6_mgmt', 'ph': 'p6', 'w': 15, 'l': 'Capital allocation record (0-10)', 'pts': [(0, 0), (10, 10)], 's': 7},
    # P7 - Quant signals
    {'id': 'p7_gpa', 'ph': 'p7', 'w': 30, 'l': 'Gross profit / total assets (%)',
     'pts': [(10, 2), (20, 4), (33, 6.5), (50, 8.5), (70, 10)], 's': 38},
    {'id': 'p7_ins', 'ph': 'p7', 'w': 25, 'l': 'Insider activity, last 6 months',
     'opts': {'cluster': 9, 'buy': 7, 'routine': 5, 'heavy': 3}, 's': 'routine'},
    {'id': 'p7_si', 'ph': 'p7', 'w': 20, 'l': 'Short interest, % of float',
     'pts': [(1, 7), (3, 6.5), (5, 6), (10, 4), (20, 2), (30, 1)], 's': 2.5},
    {'id': 'p7_pead', 'ph': 'p7', 'w': 25, 'l': 'Stock move in 3 days after last earnings (%)',
     'pts': [(-15, 2), (-5, 4), (0, 5), (5, 7), (15, 9)], 's': 3},
    # P8 - Macro fit (scored against the live regime)
    {'id': 'p8_dur', 'ph': 'p8', 'w': 20, 'l': 'Cash-flow duration',
     'opts': ('short', 'medium', 'long'), 'sc': _sc_dur, 's': 'medium'},
    {'id': 'p8_price', 'ph': 'p8', 'w': 20, 'l': 'Pricing power (can pass on cost inflation)',
     'opts': ('high', 'medium', 'low'), 'sc': _sc_price, 's': 'medium'},
    {'id': 'p8_cyc', 'ph': 'p8', 'w': 15, 'l': 'Cyclicality',
     'opts': ('defensive', 'moderate', 'high'), 'sc': _sc_cyc, 's': 'moderate'},
    {'id': 'p8_cmdty', 'ph': 'p8', 'w': 10, 'l': 'Energy / commodity input exposure',
     'opts': ('benefit', 'neutral', 'hurt'), 'sc': _sc_cmdty, 's': 'neutral'},
    {'id': 'p8_geo', 'ph': 'p8', 'w': 15, 'l': 'Geopolitical & supply-chain exposure',
     'opts': ('low', 'moderate', 'high'), 'sc': _sc_geo, 's': 'moderate'},
    {'id': 'p8_sec', 'ph': 'p8', 'w': 20, 'l': 'Structural tailwind (0-10)', 'pts': [(0, 0), (10, 10)], 's': 7},
    # Gates
    {'id': 'g_thesis', 'ph': 'gate', 'chk': True, 'l': 'I have written a one-paragraph thesis for this stock', 's': True},
    {'id': 'g_tfsa', 'ph': 'gate', 'chk': True,
     'l': 'TFSA-qualified investment (listed on a designated exchange)', 's': True},
    {'id': 'g_red', 'ph': 'gate', 'chk': True,
     'l': 'Accounting red flag: restatement, auditor resignation or going-concern warning', 's': False},
]

FIELD_BY_ID = {f['id']: f for f in FIELDS}


def sample_inputs() -> dict:
    """The artifact's sample inputs: a hypothetical mid-quality compounder (not a real company)."""
    return {f['id']: f['s'] for f in FIELDS}


# ----------------------------------------------------------------------------------------------------------------------
#                                                         Scoring
# ----------------------------------------------------------------------------------------------------------------------

def _num(x):
    if x is None or x == '' or isinstance(x, bool):
        return None
    try:
        n = float(x)
    except (TypeError, ValueError):
        return None
    return n if n == n and n not in (float('inf'), float('-inf')) else None


def _interp(pts, x):
    if x <= pts[0][0]:
        return pts[0][1]
    for i in range(1, len(pts)):
        if x <= pts[i][0]:
            a, b = pts[i - 1], pts[i]
            return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
    return pts[-1][1]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def score_field(field_id: str, inputs: dict, cl: dict):
    """Sub-score 0-10 for one field, or None if blank / not scorable."""
    f = FIELD_BY_ID[field_id]
    if f.get('chk'):
        return None
    v = inputs.get(field_id)
    reg = cl['readings']
    if 'opts' in f:
        if not v:
            return None
        if 'sc' in f:
            return f['sc'](v, reg, cl)
        return f['opts'].get(v)
    n = _num(v)
    if n is None:
        return None
    x = f['x'](n, inputs, reg) if 'x' in f else n
    return _clamp(_interp(f['pts'], x), 0, 10)


def _verdict(eff, blocked):
    if blocked:
        return 'Blocked'
    if eff is None:
        return None
    if eff >= 7.5:
        return 'Strong Buy'
    if eff >= 6:
        return 'Buy'
    if eff >= 4.5:
        return 'Watch'
    return 'Pass'


def _avg(values):
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def _action(r: dict, inputs: dict) -> dict:
    if r['score'] is None:
        return {'style': None, 'text': 'No score yet.', 'max_weight': 0.0}
    if r['blocked']:
        return {'style': 'No entry', 'text': 'Resolve TFSA eligibility first.', 'max_weight': 0.0}
    eff = r['effective']
    vol = _num(inputs.get('p2_vol'))
    vol_adj = 30.0 / max(30.0 if vol is None else vol, 15.0)
    max_w = _clamp(((eff - 4.5) / 3) * 10 * vol_adj, 0, 12) if eff >= 6 else 0.0
    p1, p5 = r['phases']['p1'], r['phases']['p5']
    fund = _avg([r['phases']['p3'], r['phases']['p6']])

    if eff < 4.5:
        style, text = 'Pass', 'Nothing here justifies capital. Revisit only if the thesis inputs change, not the price.'
    elif eff < 6:
        if p1 is not None and p1 < 5 and fund is not None and fund >= 6.5:
            style = 'Right company, wrong price'
            text = ("The business scores well but valuation doesn't. "
                    "Set a price level where Phase 1 reaches 6 and wait for it.")
        else:
            style, text = 'Watchlist', 'Not buyable yet. Name the one input that would move it above 6 and track that.'
    elif p5 is not None and p5 < 5:
        style = 'Stage in'
        text = ("The fundamentals are ready but the price action isn't. Buy half now, and the rest when it "
                "reclaims the 200-day average or after the next clean earnings report.")
    else:
        style, text = 'Enter', 'Fundamentals and price action agree. Take the full planned size.'
    return {'style': style, 'text': text, 'max_weight': max_w, 'volatility_assumed': vol is None}


def score_stock(inputs: dict, regime: dict = None) -> dict:
    """
    Run the full Unified Model v2 scorecard.
    :param inputs: {field_id: value}. See FIELDS for ids; blanks are skipped. Gate checkboxes are booleans.
    :param regime: Optional overrides of REGIME_DEFAULT readings.
    :return: dict with score, effective, verdict, phases, weights, coverage, kill_switches, caps, action, ...
    """
    inputs = dict(inputs or {})
    cl = classify_regime(regime)

    phases, subs = {}, []
    filled = total = 0
    for pid, _, _, _ in PHASES:
        sw = ss = 0.0
        for f in FIELDS:
            if f['ph'] != pid or f.get('chk'):
                continue
            total += 1
            s = score_field(f['id'], inputs, cl)
            if s is not None:
                filled += 1
                sw += f['w']
                ss += f['w'] * s
                subs.append({'field': f['id'], 'label': f['l'], 'phase': pid, 'score': s})
        phases[pid] = ss / sw if sw > 0 else None

    W = S = 0.0
    for i, (pid, _, _, _) in enumerate(PHASES):
        if phases[pid] is not None:
            W += cl['weights'][i]
            S += cl['weights'][i] * phases[pid]
    score = S / W if W > 0 else None

    # Kill switches
    impl = _num(inputs.get('p1_implied'))
    adj_impl = None if impl is None else impl - (5 if inputs.get('p1_small') else 0)
    nde, conv = _num(inputs.get('p2_nde')), _num(inputs.get('p3_fcfconv'))
    pw, conc, moat = _num(inputs.get('p4_weight')), _num(inputs.get('p2_conc')), _num(inputs.get('p6_moat'))

    def st(na, hit):
        return 'na' if na else ('hit' if hit else 'ok')

    kills = [
        {'label': 'Written one-paragraph thesis', 'status': st(False, not inputs.get('g_thesis')),
         'cap': 5.99, 'why': 'No written thesis'},
        {'label': 'TFSA-qualified', 'status': st(False, not inputs.get('g_tfsa')),
         'cap': -1, 'why': 'Not TFSA-qualified'},
        {'label': 'No accounting red flag', 'status': st(False, bool(inputs.get('g_red'))),
         'cap': 4.49, 'why': 'Accounting red flag'},
        {'label': 'Implied growth <= 30%/yr', 'status': st(adj_impl is None, adj_impl is not None and adj_impl > 30),
         'cap': 5.99, 'why': 'Price implies >30%/yr growth for a decade'},
        {'label': 'Not levered and cash-poor',
         'status': st(nde is None or conv is None, nde is not None and conv is not None and nde > 4 and conv < 50),
         'cap': 5.99, 'why': 'Net debt >4x EBITDA with <50% cash conversion'},
        {'label': 'Position <= 15% of sleeve', 'status': st(pw is None, pw is not None and pw > 15),
         'cap': 5.99, 'why': 'Position would exceed 15% of sleeve'},
        {'label': 'Customer concentration vs moat',
         'status': st(conc is None or moat is None,
                      conc is not None and moat is not None and conc > 75 and moat < 5),
         'cap': 5.99, 'why': 'Top-3 customers >75% with a weak moat'},
    ]

    cap, cap_why, blocked = 10.0, [], False
    for k in kills:
        if k['status'] == 'hit':
            if k['cap'] < 0:
                blocked = True
            else:
                cap = min(cap, k['cap'])
                cap_why.append(k['why'])

    eff = None if score is None else min(score, cap)
    ranked = sorted(subs, key=lambda x: x['score'], reverse=True)

    result = {
        'model': 'v2',
        'score': score,
        'effective': eff,
        'verdict': _verdict(eff, blocked),
        'blocked': blocked,
        'phases': phases,
        'weights': {pid: cl['weights'][i] for i, (pid, _, _, _) in enumerate(PHASES)},
        'coverage': filled / total if total else 0.0,
        'filled': filled,
        'total': total,
        'kill_switches': kills,
        'caps': cap_why,
        'strengths': ranked[:3],
        'weaknesses': list(reversed(ranked[-3:])),
        'sub_scores': subs,
        'regime': {k: v for k, v in cl.items() if k != 'weights'},
    }
    result['action'] = _action(result, inputs)
    return result


def format_report(result: dict, ticker: str = '') -> str:
    """Plain-text summary of a score_stock() result."""
    fmt = (lambda x: '-' if x is None else '%.2f' % x)
    cl = result['regime']
    lines = ['Unified Model v2%s' % (' - ' + ticker if ticker else ''),
             'Regime: %s (growth %s, inflation %s, policy %s)%s' %
             (cl['name'], cl['growth'], cl['infl'], cl['policy'], ', expensive market' if cl['expensive'] else ''),
             'Score: %s / 10  ->  %s' % (fmt(result['score']), result['verdict'] or '-')]
    if result['caps']:
        lines.append('Capped: ' + '; '.join(result['caps']))
    lines.append('Coverage: %d of %d inputs (%d%%)%s' %
                 (result['filled'], result['total'], round(result['coverage'] * 100),
                  ' - provisional' if result['coverage'] < 0.6 else ''))
    lines.append('Phases:')
    for pid, n, name, _ in PHASES:
        lines.append('  P%d %-26s %5.1f%%  %s' % (n, name, result['weights'][pid], fmt(result['phases'][pid])))
    lines.append('Kill switches:')
    for k in result['kill_switches']:
        lines.append('  [%s] %s' % ({'ok': 'PASS', 'hit': 'HIT', 'na': 'N/A'}[k['status']], k['label']))
    a = result['action']
    lines.append('Action: %s%s' % (a['style'] + '. ' if a['style'] else '', a['text']))
    lines.append('Suggested max weight in sleeve: %.1f%%' % a['max_weight'])
    return '\n'.join(lines)
