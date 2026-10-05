from os import sys, path
root_path = path.dirname(path.dirname(path.dirname(path.abspath(__file__))))
sys.path.append(root_path)

from StockAnalysisSystem.core.Utility.unified_model_v2 import *


def test_sample_matches_artifact():
    r = score_stock(sample_inputs())
    assert r['regime']['name'] == 'Overheat'
    assert abs(r['score'] - 6.69) < 0.01
    assert r['verdict'] == 'Buy'
    assert r['coverage'] == 1.0
    assert r['action']['style'] == 'Enter'
    assert abs(sum(r['weights'].values()) - 100) < 1e-9
    assert round(r['weights']['p1']) == 25


def test_blanks_are_skipped():
    r = score_stock({'p2_nde': 0, 'g_thesis': True, 'g_tfsa': True})
    assert r['filled'] == 1
    assert r['phases']['p1'] is None
    assert abs(r['score'] - 9.5) < 1e-9


def test_kill_switches():
    inputs = sample_inputs()
    inputs['g_thesis'] = False
    r = score_stock(inputs)
    assert r['effective'] <= 5.99 and r['verdict'] == 'Watch'

    inputs = sample_inputs()
    inputs['g_red'] = True
    assert score_stock(inputs)['verdict'] == 'Pass'

    inputs = sample_inputs()
    inputs['g_tfsa'] = False
    assert score_stock(inputs)['verdict'] == 'Blocked'


def test_regime_moves_weights():
    goldilocks = classify_regime({'cpi': 2.0, 'ismP': 50, 'fed': 'cutting', 'cape': 20, 'fwdpe': 15})
    assert goldilocks['name'] == 'Goldilocks'
    assert goldilocks['weights'] == [17, 12, 15, 10, 12, 12, 12, 10]
    assert classify_regime({'ism': 46, 'oas': 600})['name'] == 'Stagflation'


def test_entry():
    test_sample_matches_artifact()
    test_blanks_are_skipped()
    test_kill_switches()
    test_regime_moves_weights()


def main():
    test_entry()
    print('All Test Passed.')


if __name__ == '__main__':
    main()
