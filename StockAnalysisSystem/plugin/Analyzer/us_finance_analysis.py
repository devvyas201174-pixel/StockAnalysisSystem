import pandas as pd

from StockAnalysisSystem.core.Utility.common import *
from StockAnalysisSystem.core.Utility.time_utility import *
from StockAnalysisSystem.core.Utility.AnalyzerUtility import *
from StockAnalysisSystem.core.DataHubEntry import DataHubEntry
from StockAnalysisSystem.core.Database.DatabaseEntry import DatabaseEntry


def analysis_us_current_and_quick_ratio(securities: str, time_serial: tuple, data_hub: DataHubEntry,
                                        database: DatabaseEntry, context: AnalysisContext, **kwargs) -> [AnalysisResult]:
    nop(database, context, kwargs)

    df = data_hub.get_data_center().query_from_factor(
        'Factor.Finance', securities, time_serial, fields=['Current Ratio (US)', 'Quick Ratio (US)'], readable=True)
    if df is None or len(df) == 0:
        return [AnalysisResult(securities, None, AnalysisResult.SCORE_NOT_APPLIED, 'No data', 'No data')]

    # Annual report only
    df = df[df['period'].dt.month == 12]

    results = []
    for index, row in df.iterrows():
        score = 100
        brief = []
        reason = []
        period = row['period']

        if row['Current Ratio (US)'] < 1.5:
            score -= 50
            brief.append('Current ratio too low')
            reason.append('%s: Current ratio %.2f < 1.5' % (period.year, row['Current Ratio (US)']))
        else:
            reason.append('%s: Current ratio %.2f - OK' % (period.year, row['Current Ratio (US)']))

        if row['Quick Ratio (US)'] < 1.0:
            score -= 50
            brief.append('Quick ratio too low')
            reason.append('%s: Quick ratio %.2f < 1.0' % (period.year, row['Quick Ratio (US)']))
        else:
            reason.append('%s: Quick ratio %.2f - OK' % (period.year, row['Quick Ratio (US)']))

        brief = '; '.join(brief) if len(brief) > 0 else 'Normal'
        results.append(AnalysisResult(securities, period, score, reason, brief))
    return results


def analysis_us_roe_roa(securities: str, time_serial: tuple, data_hub: DataHubEntry,
                        database: DatabaseEntry, context: AnalysisContext, **kwargs) -> [AnalysisResult]:
    nop(database, context, kwargs)

    df = data_hub.get_data_center().query_from_factor(
        'Factor.Finance', securities, time_serial,
        fields=['Return on Equity (US)', 'Return on Assets (US)'], readable=True)
    if df is None or len(df) == 0:
        return [AnalysisResult(securities, None, AnalysisResult.SCORE_NOT_APPLIED, 'No data', 'No data')]

    # Annual report only
    df = df[df['period'].dt.month == 12]

    results = []
    for index, row in df.iterrows():
        score = 100
        brief = []
        reason = []
        period = row['period']

        if row['Return on Assets (US)'] < 0.05:
            score -= 50
            brief.append('ROA too low')
            reason.append('%s: ROA %.2f%% - too low' % (period.year, row['Return on Assets (US)'] * 100))
        else:
            reason.append('%s: ROA %.2f%% - OK' % (period.year, row['Return on Assets (US)'] * 100))

        if row['Return on Equity (US)'] < 0.10:
            score -= 50
            brief.append('ROE too low')
            reason.append('%s: ROE %.2f%% - too low' % (period.year, row['Return on Equity (US)'] * 100))
        elif row['Return on Equity (US)'] > 0.40:
            score -= 25
            brief.append('ROE unusually high')
            reason.append('%s: ROE %.2f%% - unusually high, verify quality of earnings' %
                          (period.year, row['Return on Equity (US)'] * 100))
        else:
            reason.append('%s: ROE %.2f%% - OK' % (period.year, row['Return on Equity (US)'] * 100))

        brief = '; '.join(brief) if len(brief) > 0 else 'Normal'
        results.append(AnalysisResult(securities, period, score, reason, brief))
    return results


# ----------------------------------------------------------------------------------------------------------------------

METHOD_LIST = [
    ('d1e2f3a4-1a2b-4c3d-8e9f-0a1b2c3d4e5f', 'US Current & Quick Ratio',
     'Flags companies failing current/quick liquidity ratio thresholds', analysis_us_current_and_quick_ratio),
    ('e2f3a4b5-2b3c-4d4e-9f0a-1b2c3d4e5f60', 'US ROE & ROA',
     'Analyzes return on equity and return on assets', analysis_us_roe_roa),
]


def plugin_prob() -> dict:
    return {
        'plugin_id': 'a1b2c3d4-5e6f-4708-9192-a3b4c5d6e7f8',
        'plugin_name': 'us_finance_analysis',
        'plugin_version': '0.0.0.1',
        'tags': ['us_market', 'finance', 'analyzer'],
        'methods': METHOD_LIST,
    }


def plugin_adapt(method: str) -> bool:
    return method in methods_from_prob(plugin_prob())


def plugin_capacities() -> list:
    return [
        'exclusive',
    ]


# ----------------------------------------------------------------------------------------------------------------------

def analysis(methods: [str], securities: [str], time_serial: tuple,
             data_hub: DataHubEntry, database: DatabaseEntry, **kwargs) -> [AnalysisResult]:
    return standard_dispatch_analysis(methods, securities, time_serial, data_hub, database, kwargs, METHOD_LIST)
