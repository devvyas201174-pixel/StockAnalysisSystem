import pandas as pd

from StockAnalysisSystem.core.Utility.common import *
from StockAnalysisSystem.core.Utility.time_utility import *
from StockAnalysisSystem.core.Utility.CollectorUtility import *


# ------------------------------------------------------- Fields -------------------------------------------------------
#
# Raw field keys below are our own names, not SEC's XBRL tags directly - see TAG_TABLE for the mapping to XBRL
# tags (usually more than one candidate, since SEC's tag naming drifts across filing years/companies).

FIELDS = {
    'Finance.BalanceSheet.US': {
        'total_assets':             'Total Assets',
        'total_current_assets':     'Total Current Assets',
        'total_current_liabilities':'Total Current Liabilities',
        'total_liabilities':        'Total Liabilities',
        'total_stockholder_equity': 'Total Stockholder Equity',
        'cash':                     'Cash And Cash Equivalents',
        'inventory':                'Inventory',
        'long_term_debt':           'Long Term Debt',
    },

    'Finance.IncomeStatement.US': {
        'total_revenue':     'Total Revenue',
        'cost_of_revenue':   'Cost Of Revenue',
        'operating_income':  'Operating Income',
        'income_tax_expense':'Income Tax Expense',
        'net_income':        'Net Income',
    },

    'Finance.CashFlowStatement.US': {
        'operating_cash_flow':  'Operating Cash Flow',
        'capital_expenditures': 'Capital Expenditures',
        'dividends_paid':       'Dividends Paid',
    },
}

# Our field -> ordered list of candidate SEC us-gaap XBRL tags to try (first match wins).
TAG_TABLE = {
    'Finance.BalanceSheet.US': {
        'total_assets':              ['Assets'],
        'total_current_assets':      ['AssetsCurrent'],
        'total_current_liabilities': ['LiabilitiesCurrent'],
        'total_liabilities':         ['Liabilities'],
        'total_stockholder_equity':  ['StockholdersEquity',
                                       'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
        'cash':                      ['CashAndCashEquivalentsAtCarryingValue',
                                       'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'],
        'inventory':                 ['InventoryNet'],
        'long_term_debt':            ['LongTermDebtNoncurrent', 'LongTermDebt'],
    },

    'Finance.IncomeStatement.US': {
        'total_revenue':      ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax',
                                'RevenueFromContractWithCustomerIncludingAssessedTax'],
        'cost_of_revenue':    ['CostOfGoodsAndServicesSold', 'CostOfRevenue'],
        'operating_income':   ['OperatingIncomeLoss'],
        'income_tax_expense': ['IncomeTaxExpenseBenefit'],
        'net_income':         ['NetIncomeLoss', 'ProfitLoss'],
    },

    'Finance.CashFlowStatement.US': {
        'operating_cash_flow':  ['NetCashProvidedByUsedInOperatingActivities'],
        'capital_expenditures': ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsForCapitalImprovements'],
        'dividends_paid':       ['PaymentsOfDividends', 'PaymentsOfDividendsCommonStock'],
    },
}


# -------------------------------------------------------- Prob --------------------------------------------------------

def plugin_prob() -> dict:
    return {
        'plugin_name': 'finance_data_sec_edgar',
        'plugin_version': '0.0.0.1',
        'tags': ['sec_edgar', 'us_market'],
    }


def plugin_adapt(uri: str) -> bool:
    return uri in FIELDS.keys()


def plugin_capacities() -> list:
    return list(FIELDS.keys())


# ----------------------------------------------------------------------------------------------------------------------

# companyfacts: https://www.sec.gov/edgar/sec-api-documentation

def __fetch_finance_data(**kwargs) -> pd.DataFrame or None:
    uri = kwargs.get('uri')
    result = check_execute_test_flag(**kwargs)

    if result is None:
        stock_identity = kwargs.get('stock_identity', '')
        ticker = stock_identity_to_us_ticker(stock_identity)
        tag_table = TAG_TABLE.get(uri)
        if not str_available(ticker) or tag_table is None:
            return None

        cik = sec_ticker_to_cik(ticker)
        if cik is None:
            return None

        facts = sec_company_facts(cik)
        if facts is None:
            return None

        # period end date -> {field: fact_entry}; a field's latest-filed value wins if it appears more than once
        # for the same period (e.g. amendments/restatements).
        periods = {}
        for field, tag_candidates in tag_table.items():
            for entry in sec_extract_annual_facts(facts, tag_candidates):
                end = entry.get('end')
                field_values = periods.setdefault(end, {})
                existing = field_values.get(field)
                if existing is None or entry.get('filed', '') >= existing.get('filed', ''):
                    field_values[field] = entry

        rows = []
        for end, field_values in periods.items():
            row = {'period': pd.to_datetime(end)}
            for field in tag_table.keys():
                entry = field_values.get(field)
                row[field] = entry.get('val') if entry is not None else None
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
