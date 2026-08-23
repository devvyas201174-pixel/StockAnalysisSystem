import pandas as pd

from StockAnalysisSystem.core.Utility.common import *
from StockAnalysisSystem.core.Utility.time_utility import *
from StockAnalysisSystem.core.Utility.CollectorUtility import *


# ------------------------------------------------------- Fields -------------------------------------------------------

FIELDS = {
    'Finance.BalanceSheet.US': {
        'totalAssets':             'Total Assets',
        'totalCurrentAssets':      'Total Current Assets',
        'totalCurrentLiabilities': 'Total Current Liabilities',
        'totalLiab':               'Total Liabilities',
        'totalStockholderEquity':  'Total Stockholder Equity',
        'cash':                    'Cash And Cash Equivalents',
        'inventory':               'Inventory',
        'longTermDebt':            'Long Term Debt',
        'shortLongTermDebt':       'Short/Current Long Term Debt',
    },

    'Finance.IncomeStatement.US': {
        'totalRevenue':     'Total Revenue',
        'costOfRevenue':    'Cost Of Revenue',
        'operatingIncome':  'Operating Income',
        'ebit':             'EBIT',
        'incomeTaxExpense': 'Income Tax Expense',
        'netIncome':        'Net Income',
    },

    'Finance.CashFlowStatement.US': {
        'totalCashFromOperatingActivities': 'Operating Cash Flow',
        'capitalExpenditures':              'Capital Expenditures',
        'dividendsPaid':                    'Dividends Paid',
    },
}

# Maps our URI to the Yahoo quoteSummary module and the statement list key inside it.
URI_MODULE_TABLE = {
    'Finance.BalanceSheet.US':      ('balanceSheetHistory',      'balanceSheetStatements'),
    'Finance.IncomeStatement.US':   ('incomeStatementHistory',   'incomeStatementHistory'),
    'Finance.CashFlowStatement.US': ('cashflowStatementHistory', 'cashflowStatements'),
}


# -------------------------------------------------------- Prob --------------------------------------------------------

def plugin_prob() -> dict:
    return {
        'plugin_name': 'finance_data_yfinance',
        'plugin_version': '0.0.0.1',
        'tags': ['yfinance', 'us_market'],
    }


def plugin_adapt(uri: str) -> bool:
    return uri in FIELDS.keys()


def plugin_capacities() -> list:
    return list(FIELDS.keys())


# ----------------------------------------------------------------------------------------------------------------------

def __raw(value: any) -> any:
    return value.get('raw') if isinstance(value, dict) else value


# quoteSummary: https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}

def __fetch_finance_data(**kwargs) -> pd.DataFrame or None:
    uri = kwargs.get('uri')
    result = check_execute_test_flag(**kwargs)

    if result is None:
        stock_identity = kwargs.get('stock_identity', '')
        ticker = stock_identity_to_us_ticker(stock_identity)
        module, statement_key = URI_MODULE_TABLE.get(uri, (None, None))
        if not str_available(ticker) or module is None:
            return None

        data = yahoo_fetch_json(
            YAHOO_QUOTE_SUMMARY_URL.format(symbol=ticker),
            params={'modules': module}, use_crumb=True)
        if data is None:
            return None

        query_results = data.get('quoteSummary', {}).get('result') or []
        if len(query_results) == 0:
            return None

        statements = (query_results[0].get(module) or {}).get(statement_key) or []
        if len(statements) == 0:
            return None

        field_list = list(FIELDS[uri].keys())
        rows = []
        for statement in statements:
            end_date = __raw(statement.get('endDate'))
            row = {'period': pd.to_datetime(end_date, unit='s') if end_date is not None else None}
            for field in field_list:
                row[field] = __raw(statement.get(field))
            rows.append(row)

        result = pd.DataFrame(rows)
        result['stock_identity'] = stock_identity if str_available(stock_identity) else \
            us_ticker_to_stock_identity(ticker)

    check_execute_dump_flag(result, **kwargs)
    return result


# ----------------------------------------------------------------------------------------------------------------------

def query(**kwargs) -> pd.DataFrame or None:
    uri = kwargs.get('uri')
    if uri in FIELDS.keys():
        return __fetch_finance_data(**kwargs)
    else:
        return None


def validate(**kwargs) -> bool:
    nop(kwargs)
    return True


def fields() -> dict:
    return FIELDS
