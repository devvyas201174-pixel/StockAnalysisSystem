"""
Score a stock with Unified Model v2 and v2.1 side by side, or run the price-signal backtest.

    python example/unified_model_score.py SEZL [--judgement example/unified_model_inputs/SEZL.json]
    python example/unified_model_score.py --backtest

Measurable inputs come from Yahoo Finance; judgement inputs come from the JSON file (keys are field ids from
StockAnalysisSystem/core/Utility/unified_model_v2.py). The regime uses v2's saved readings with the live 10-yr yield.
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from StockAnalysisSystem.core.Utility import unified_model_v2 as v2
from StockAnalysisSystem.core.Utility import unified_model_v21 as v21
from StockAnalysisSystem.core.Utility.unified_model_data import auto_inputs
from StockAnalysisSystem.core.Utility import unified_model_backtest as bt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker', nargs='?')
    ap.add_argument('--judgement', help='JSON file of judgement inputs')
    ap.add_argument('--backtest', action='store_true', help='Run the 10-year price-signal backtest')
    args = ap.parse_args()

    if args.backtest:
        print(bt.format_backtest(bt.run_backtest(bt.load_prices(bt.default_universe()))))
        return
    if not args.ticker:
        ap.error('ticker required')

    data = auto_inputs(args.ticker)
    inputs = dict(data['inputs'])
    path = args.judgement or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unified_model_inputs',
                                          args.ticker.upper() + '.json')
    if os.path.exists(path):
        with open(path) as f:
            inputs.update({k: v for k, v in json.load(f).items() if not k.startswith('_')})
    regime = {'tenY': data['ten_year'], 'asOf': 'saved readings, live 10-yr'}

    print('%s  price %.2f as of %s  |  %s / %s  |  10-yr %.2f%%' % (
        data['ticker'], data['price'], data['as_of'], data['notes'].get('sector'), data['notes'].get('industry'),
        data['ten_year']))
    print('Fetched inputs:')
    for k, v in sorted(data['inputs'].items()):
        print('  %-11s %s' % (k, '%.2f' % v if isinstance(v, float) else v))
    for k, v in data['notes'].items():
        print('  note: %s = %s' % (k, v))
    print()
    print(v2.format_report(v2.score_stock(inputs, regime), data['ticker']))
    print()
    print(v21.format_report(v21.score_stock(inputs, regime, sector=data['notes'].get('sector'),
                                                industry=data['notes'].get('industry')), data['ticker']))


if __name__ == '__main__':
    main()
