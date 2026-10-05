from os import sys, path
root_path = path.dirname(path.dirname(path.dirname(path.abspath(__file__))))
sys.path.append(root_path)

from StockAnalysisSystem.core.Utility import unified_model_v2 as v2
from StockAnalysisSystem.core.Utility import unified_model_v21 as v21
from StockAnalysisSystem.core.Utility.unified_model_data import rsi, volatility, momentum_12_1, pct_vs_sma, \
    implied_growth
from StockAnalysisSystem.core.Utility.unified_model_backtest import spearman


MEDIANS = {'_market': {'p2_nde': 2.0, 'p2_cov': 8.0, 'p2_vol': 30.0, 'p3_fcfconv': 100.0, 'p3_sbc': 1.0,
                       'p7_gpa': 20.0},
           'Utilities': {'p2_nde': 5.0, 'p2_cov': 2.0, 'p2_vol': 20.0, 'p3_fcfconv': 100.0, 'p3_sbc': 1.0,
                         'p7_gpa': 10.0},
           'industry:Credit Services': {'p2_nde': 8.0, 'p2_cov': 2.0, 'p2_vol': 40.0, 'p3_fcfconv': None,
                                        'p3_sbc': 2.0, 'p7_gpa': 20.0}}


def test_matches_v2_without_fit_phase():
    inputs = v2.sample_inputs()
    a, b = v2.score_stock(inputs), v21.score_stock(inputs, medians={})
    # Same regime weights as v2 in a pure Overheat reading, with Phase 4 dropped and renormalised.
    w = {p: a['weights'][p] for p in a['weights'] if p != 'p4'}
    expect = sum(w[p] * a['phases'][p] for p in w) / sum(w.values())
    assert abs(b['score'] - expect) < 1e-9
    assert b['regime']['name'] == 'Overheat' and b['regime']['mix'] == {'Overheat': 1.0}


def test_regime_is_smooth():
    # CPI 2.9% -> 3.0% flips v2 from Mid-cycle to Overheat; v2.1 moves a fraction of the way.
    a, b = {'cpi': 2.9, 'ismP': 58, 'fed': 'hold'}, {'cpi': 3.0, 'ismP': 58, 'fed': 'hold'}
    assert (v2.classify_regime(a)['name'], v2.classify_regime(b)['name']) == ('Mid-cycle', 'Overheat')
    jump = max(abs(x - y) for x, y in zip(v2.classify_regime(a)['weights'], v2.classify_regime(b)['weights']))
    lo, hi = v21.classify_regime(a)['weights'], v21.classify_regime(b)['weights']
    assert max(abs(x - y) for x, y in zip(lo, hi)) < jump / 3
    assert abs(sum(lo) - 100) < 1e-9


def test_coverage_shrinks_toward_neutral():
    r = v21.score_stock({'p2_nde': 0, 'g_thesis': True, 'g_tfsa': True}, medians={})
    assert r['raw_score'] == 9.5
    assert 5 < r['score'] < 5.5


def test_peer_adjustment():
    # Utility leverage is scored half-way toward its sector norm; lender coverage scales by the ratio.
    assert abs(v21.sector_adjust('p2_nde', 5.0, 'Utilities', MEDIANS, 0.5) - 3.5) < 1e-9
    assert abs(v21.sector_adjust('p2_cov', 4.0, 'industry:Credit Services', MEDIANS, 0.5) - 8.0) < 1e-9
    assert v21.sector_adjust('p3_fcfconv', 80.0, 'industry:Credit Services', MEDIANS, 0.5) == 80.0
    assert v21.peer_group('Financial Services', 'Credit Services', MEDIANS) == 'industry:Credit Services'
    assert v21.peer_group('Utilities', 'Utilities - Regulated Electric', MEDIANS) == 'Utilities'
    assert v21.peer_group('Technology', None, MEDIANS) is None


def test_fit_and_tfsa_move_to_sizing():
    inputs = v2.sample_inputs()
    base = v21.score_stock(inputs, medians={})
    inputs['p4_overlap'], inputs['p4_theme'] = 'same', 70
    worse_fit = v21.score_stock(inputs, medians={})
    assert worse_fit['score'] == base['score']
    assert worse_fit['action']['max_weight'] < base['action']['max_weight']
    inputs['g_tfsa'] = False
    blocked = v21.score_stock(inputs, medians={})
    assert blocked['verdict'] == base['verdict'] and blocked['action']['max_weight'] == 0


def test_indicators():
    up = [100 * 1.001 ** i for i in range(300)]
    assert rsi(up) == 100.0
    assert volatility(up) < 1e-6
    assert abs(momentum_12_1(up) - (1.001 ** 231 - 1) * 100) < 1e-9
    assert pct_vs_sma(up) > 0
    g = implied_growth(1000.0, 50.0, discount=10.0)
    assert g is not None and abs(implied_growth(1000.0 * 1.0, 50.0, discount=10.0) - g) < 1e-9
    assert implied_growth(2000.0, 50.0, discount=10.0) > g
    assert abs(spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) - 1) < 1e-12


def test_entry():
    test_matches_v2_without_fit_phase()
    test_regime_is_smooth()
    test_coverage_shrinks_toward_neutral()
    test_peer_adjustment()
    test_fit_and_tfsa_move_to_sizing()
    test_indicators()


def main():
    test_entry()
    print('All Test Passed.')


if __name__ == '__main__':
    main()
