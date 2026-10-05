"""
Unified Model v2.1 - the v2 scorecard with four accuracy fixes. v2 (unified_model_v2) is left unchanged so
the two can be compared on the same inputs.

What changes against v2:
  1. Sector-relative scoring. Inputs whose normal range depends on the industry (leverage, interest cover,
     volatility, cash conversion, SBC, gross profitability) are shifted by the gap between the stock's sector
     median and the market median before they hit v2's curves. `sector_strength` blends absolute (0) and fully
     sector-relative (1) scoring; default 0.5.
  2. Portfolio fit is out of the score. Phase 4 and the TFSA / position-size checks no longer change how good
     the stock is; they scale and cap the position size in the action instead.
  3. Smooth regime. Growth and inflation are continuous coordinates (optionally using 3-month changes), and the
     phase weights are blended between neighbouring regimes instead of jumping at ISM 52 or CPI 3.0.
     The expensive-market and credit-stress overlays also scale in gradually.
  4. Coverage shrinkage. When fewer than 75% of the scored inputs are filled, the score is pulled toward a
     neutral 5 in proportion, so thin data can't look confident.

The phase curves, kill-switch thresholds and verdict bands are v2's.
"""

import json
import os

from . import unified_model_v2 as v2


SCORED_PHASES = [p for p in v2.PHASES if p[0] != 'p4']
FIT_PHASE = 'p4'
COVERAGE_FULL = 0.75
DEFAULT_SECTOR_STRENGTH = 0.5

# Inputs whose normal range depends on the industry. Ratios that are always positive and skewed are scaled
# multiplicatively; the rest are shifted additively.
SECTOR_FIELDS = ['p2_nde', 'p2_cov', 'p2_vol', 'p3_fcfconv', 'p3_sbc', 'p7_gpa']
RATIO_FIELDS = ['p2_cov', 'p2_vol', 'p3_sbc', 'p7_gpa']

_MEDIANS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), 'res', 'unified_model_sector_medians.json')
_medians_cache = None


def sector_medians() -> dict:
    """Loads res/unified_model_sector_medians.json (rebuild with unified_model_data.build_sector_medians)."""
    global _medians_cache
    if _medians_cache is None:
        try:
            with open(_MEDIANS_PATH) as f:
                _medians_cache = json.load(f)
        except (OSError, ValueError):
            _medians_cache = {}
    return _medians_cache


# ----------------------------------------------------------------------------------------------------------------------
#                                                     Smooth regime
# ----------------------------------------------------------------------------------------------------------------------

# Grid of (growth, inflation) nodes -> v2 regime table. Coordinates run -1 .. +1.
_GRID = {
    (1, 1): 'Overheat',      (1, 0): 'Mid-cycle',             (1, -1): 'Goldilocks',
    (0, 1): 'Late cycle',    (0, 0): 'Mid-cycle',             (0, -1): 'Soft landing',
    (-1, 1): 'Stagflation',  (-1, 0): 'Deflationary slowdown', (-1, -1): 'Deflationary slowdown',
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def regime_coordinates(r: dict) -> (float, float):
    """Continuous growth (G) and inflation (I) in -1 .. +1. Optional 'ism_3m_ago' / 'cpi_3m_ago' add direction."""
    g = (r['ism'] - 50) / 2.5
    g += {'falling': 0.75, 'rising': -0.75}.get(r['unempTrend'], 0)
    g -= _clamp((r['oas'] - 400) / 200, 0, 1)
    if r.get('ism_3m_ago') is not None:
        g += 0.5 * (r['ism'] - r['ism_3m_ago']) / 2.5

    i = max((r['cpi'] - 2.65) / 0.5, (r['ismP'] - 60) / 7.5)
    if r.get('cpi_3m_ago') is not None:
        i += 0.5 * (r['cpi'] - r['cpi_3m_ago']) / 0.5
    return _clamp(g, -1, 1), _clamp(i, -1, 1)


def classify_regime(regime: dict = None) -> dict:
    r = dict(v2.REGIME_DEFAULT)
    if regime:
        r.update({k: val for k, val in regime.items() if val is not None})
    G, I = regime_coordinates(r)

    # Bilinear blend of the four surrounding grid nodes.
    g0, i0 = (-1 if G < 0 else 0), (-1 if I < 0 else 0)
    fg, fi = G - g0, I - i0
    mix = {}
    for dg, wg in ((0, 1 - fg), (1, fg)):
        for di, wi in ((0, 1 - fi), (1, fi)):
            w = wg * wi
            if w > 1e-9:
                name = _GRID[(g0 + dg, i0 + di)]
                mix[name] = mix.get(name, 0) + w
    w = [0.0] * 8
    for name, share in mix.items():
        for k in range(8):
            w[k] += share * v2.REGIME_WEIGHTS[name][k]

    policy = 'tightening' if r['fed'] == 'hiking' else ('easing' if r['fed'] == 'cutting' else 'neutral')
    erp = 100.0 / r['fwdpe'] - r['tenY']
    tighten = (1 - max(I, 0)) if policy == 'tightening' else 0.0
    expensive = max(_clamp((r['cape'] - 25) / 10, 0, 1), _clamp((2 - erp) / 2, 0, 1))
    credit = _clamp((r['oas'] - 400) / 200, 0, 1)

    def mv(to, frm, amt):
        take = min(amt, w[frm])
        w[frm] -= take
        w[to] += take

    notes = []
    if tighten > 0:
        mv(0, 4, tighten)
        mv(0, 6, tighten)
        notes.append('Tightening overlay: +%.1f valuation' % (2 * tighten))
    if expensive > 0:
        mv(0, 6, 2 * expensive)
        mv(1, 4, expensive)
        notes.append('Expensive-market overlay (%.0f%%): +%.1f valuation, +%.1f risk' %
                     (expensive * 100, 2 * expensive, expensive))
    if credit > 0:
        mv(1, 6, 2 * credit)
        notes.append('Credit-stress overlay: +%.1f risk' % (2 * credit))
    s = sum(w)
    w = [x * 100 / s for x in w]

    name = _GRID[(int(round(G)), int(round(I)))]
    growth = 'expanding' if G >= 0.5 else ('contracting' if G <= -0.5 else 'neutral')
    infl = 'hot' if I >= 0.5 else ('cool' if I <= -0.5 else 'neutral')
    return {
        'name': name, 'mix': {k: round(val, 3) for k, val in sorted(mix.items(), key=lambda x: -x[1])},
        'G': G, 'I': I, 'growth': growth, 'infl': infl, 'policy': policy,
        'erp': erp, 'expensive': expensive, 'credit': credit,
        'oil': r['wti'] >= 90, 'geo': r['geo'] == 'on',
        'weights': w, 'notes': notes, 'readings': r,
    }


# ----------------------------------------------------------------------------------------------------------------------
#                                                         Scoring
# ----------------------------------------------------------------------------------------------------------------------

def peer_group(sector, industry, medians):
    """The industry group if one is defined, else the sector, else None."""
    if industry and ('industry:' + industry) in medians:
        return 'industry:' + industry
    return sector if sector in medians else None


def sector_adjust(field_id, value, group, medians, strength):
    """Value as it is scored after moving it `strength` of the way from absolute to peer-relative."""
    if group is None or strength == 0 or field_id not in SECTOR_FIELDS:
        return value
    s = (medians.get(group) or {}).get(field_id)
    m = (medians.get('_market') or {}).get(field_id)
    if s is None or m is None:
        return value
    if field_id in RATIO_FIELDS:
        if value <= 0 or s <= 0 or m <= 0:
            return value
        return value * (m / s) ** strength
    return value - strength * (s - m)


def score_stock(inputs: dict, regime: dict = None, sector: str = None, industry: str = None,
                sector_strength: float = DEFAULT_SECTOR_STRENGTH, medians: dict = None) -> dict:
    """
    :param inputs: {field_id: value}, same ids as v2 (see unified_model_v2.FIELDS).
    :param regime: overrides of v2.REGIME_DEFAULT; may add 'ism_3m_ago' and 'cpi_3m_ago'.
    :param sector: Yahoo sector name (e.g. 'Financial Services'); None scores everything on the absolute scale.
    :param industry: Yahoo industry name; used instead of the sector when it has its own peer group.
    """
    inputs = dict(inputs or {})
    cl = classify_regime(regime)
    medians = sector_medians() if medians is None else medians

    group = peer_group(sector, industry, medians)
    adjusted, adjustments = dict(inputs), {}
    for fid in SECTOR_FIELDS:
        n = v2._num(inputs.get(fid))
        if n is None:
            continue
        a = sector_adjust(fid, n, group, medians, sector_strength)
        if a != n:
            adjusted[fid] = a
            adjustments[fid] = {'raw': n, 'scored_as': a, 'peer_median': medians[group][fid],
                                'market_median': medians['_market'][fid]}

    phases, subs = {}, []
    filled = total = 0
    for pid, _, _, _ in v2.PHASES:
        sw = ss = 0.0
        for f in v2.FIELDS:
            if f['ph'] != pid or f.get('chk'):
                continue
            if pid != FIT_PHASE:
                total += 1
            s = v2.score_field(f['id'], adjusted, cl)
            if s is not None:
                if pid != FIT_PHASE:
                    filled += 1
                sw += f['w']
                ss += f['w'] * s
                subs.append({'field': f['id'], 'label': f['l'], 'phase': pid, 'score': s})
        phases[pid] = ss / sw if sw > 0 else None

    idx = {p[0]: i for i, p in enumerate(v2.PHASES)}
    wsum = sum(cl['weights'][idx[p[0]]] for p in SCORED_PHASES)
    weights = {p[0]: cl['weights'][idx[p[0]]] * 100 / wsum for p in SCORED_PHASES}
    W = S = 0.0
    for pid, _, _, _ in SCORED_PHASES:
        if phases[pid] is not None:
            W += weights[pid]
            S += weights[pid] * phases[pid]
    raw = S / W if W > 0 else None
    coverage = filled / total if total else 0.0
    shrink = min(1.0, coverage / COVERAGE_FULL)
    score = None if raw is None else 5 + (raw - 5) * shrink

    # Kill switches about the stock (fit-related ones moved to sizing).
    impl = v2._num(inputs.get('p1_implied'))
    adj_impl = None if impl is None else impl - (5 if inputs.get('p1_small') else 0)
    nde, conv = v2._num(inputs.get('p2_nde')), v2._num(inputs.get('p3_fcfconv'))
    conc, moat = v2._num(inputs.get('p2_conc')), v2._num(inputs.get('p6_moat'))

    def st(na, hit):
        return 'na' if na else ('hit' if hit else 'ok')

    kills = [
        {'label': 'Written one-paragraph thesis', 'status': st(False, not inputs.get('g_thesis')),
         'cap': 5.99, 'why': 'No written thesis'},
        {'label': 'No accounting red flag', 'status': st(False, bool(inputs.get('g_red'))),
         'cap': 4.49, 'why': 'Accounting red flag'},
        {'label': 'Implied growth <= 30%/yr', 'status': st(adj_impl is None, adj_impl is not None and adj_impl > 30),
         'cap': 5.99, 'why': 'Price implies >30%/yr growth for a decade'},
        {'label': 'Not levered and cash-poor',
         'status': st(nde is None or conv is None, nde is not None and conv is not None and nde > 4 and conv < 50),
         'cap': 5.99, 'why': 'Net debt >4x EBITDA with <50% cash conversion'},
        {'label': 'Customer concentration vs moat',
         'status': st(conc is None or moat is None,
                      conc is not None and moat is not None and conc > 75 and moat < 5),
         'cap': 5.99, 'why': 'Top-3 customers >75% with a weak moat'},
    ]
    cap, cap_why = 10.0, []
    for k in kills:
        if k['status'] == 'hit':
            cap = min(cap, k['cap'])
            cap_why.append(k['why'])
    eff = None if score is None else min(score, cap)
    ranked = sorted([x for x in subs if x['phase'] != FIT_PHASE], key=lambda x: x['score'], reverse=True)

    result = {
        'model': 'v2.1',
        'raw_score': raw,
        'score': score,
        'effective': eff,
        'verdict': v2._verdict(eff, False),
        'phases': phases,
        'weights': weights,
        'coverage': coverage,
        'coverage_shrink': shrink,
        'filled': filled,
        'total': total,
        'kill_switches': kills,
        'caps': cap_why,
        'sector': sector,
        'peer_group': group,
        'sector_adjustments': adjustments,
        'strengths': ranked[:3],
        'weaknesses': list(reversed(ranked[-3:])),
        'sub_scores': subs,
        'regime': {k: val for k, val in cl.items() if k != 'weights'},
    }
    result['action'] = _action(result, inputs)
    return result


def _action(r: dict, inputs: dict) -> dict:
    base = v2._action(dict(r, blocked=False), inputs)
    notes = []
    if not inputs.get('g_tfsa'):
        return {'style': 'No entry', 'text': 'Not a TFSA-qualified investment.', 'max_weight': 0.0,
                'fit_multiplier': None, 'notes': ['Blocked: not TFSA-qualified']}
    fit = r['phases'].get(FIT_PHASE)
    mult = 1.0 if fit is None else 0.5 + 0.05 * fit     # fit 10 -> 1.0x, 6 -> 0.8x, 3 -> 0.65x
    max_w = base['max_weight'] * mult
    pw = v2._num(inputs.get('p4_weight'))
    if max_w > 15:
        max_w = 15.0
    if pw is not None and pw > max_w and max_w > 0:
        notes.append('Planned position (%.1f%%) is above the suggested max (%.1f%%): buy less.' % (pw, max_w))
    if fit is None:
        notes.append('Portfolio fit not entered: size not adjusted for overlap.')
    base.update({'max_weight': max_w, 'fit_multiplier': mult, 'notes': notes})
    return base


def format_report(result: dict, ticker: str = '') -> str:
    fmt = (lambda x: '-' if x is None else '%.2f' % x)
    cl = result['regime']
    mix = ', '.join('%s %d%%' % (k, round(v * 100)) for k, v in cl['mix'].items())
    lines = ['Unified Model v2.1%s' % (' - ' + ticker if ticker else ''),
             'Regime: %s [%s] (G %+.2f, I %+.2f, policy %s)' % (cl['name'], mix, cl['G'], cl['I'], cl['policy']),
             'Peer group: %s' % (result['peer_group'] or 'none (absolute scoring)'),
             'Score: %s / 10  ->  %s   (raw %s, coverage shrink x%.2f)' %
             (fmt(result['score']), result['verdict'] or '-', fmt(result['raw_score']), result['coverage_shrink'])]
    if result['caps']:
        lines.append('Capped: ' + '; '.join(result['caps']))
    lines.append('Coverage: %d of %d scored inputs (%d%%)' %
                 (result['filled'], result['total'], round(result['coverage'] * 100)))
    lines.append('Phases:')
    for pid, n, name, _ in v2.PHASES:
        w = result['weights'].get(pid)
        lines.append('  P%d %-26s %s  %s' % (n, name, '%5.1f%%' % w if w is not None else ' sizing',
                                             fmt(result['phases'][pid])))
    if result['sector_adjustments']:
        lines.append('Peer adjustments (raw -> scored as; peer / market median):')
        for fid, a in result['sector_adjustments'].items():
            lines.append('  %-11s %8.2f -> %8.2f   (%.2f / %.2f)' %
                         (fid, a['raw'], a['scored_as'], a['peer_median'], a['market_median']))
    lines.append('Kill switches:')
    for k in result['kill_switches']:
        lines.append('  [%s] %s' % ({'ok': 'PASS', 'hit': 'HIT', 'na': 'N/A'}[k['status']], k['label']))
    a = result['action']
    lines.append('Action: %s%s' % (a['style'] + '. ' if a['style'] else '', a['text']))
    lines.append('Suggested max weight in sleeve: %.1f%%%s' %
                 (a['max_weight'], '' if not a.get('fit_multiplier') else ' (fit x%.2f)' % a['fit_multiplier']))
    for n in a.get('notes', []):
        lines.append('  - ' + n)
    return '\n'.join(lines)
