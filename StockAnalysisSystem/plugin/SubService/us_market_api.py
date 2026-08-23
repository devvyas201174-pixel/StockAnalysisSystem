from StockAnalysisSystem.core.Utility.CollectorUtility import us_ticker_to_stock_identity
from StockAnalysisSystem.core.SubServiceManager import SubServiceContext


# ----------------------------------------------------------------------------------------------------------------------
# Registers a couple of convenience sys-calls for the US market plugins, reachable both locally
# (sasApi.sys_call(...)) and over the existing generic REST endpoint (RestInterface -> /api),
# without adding any new server route.

def us_stock_identity(ticker: str, exchange: str = 'NASDAQ') -> str:
    return us_ticker_to_stock_identity(ticker, exchange)


# ----------------------------------------------------------------------------------------------------------------------

def plugin_prob() -> dict:
    return {
        'plugin_id': 'f1e2d3c4-b5a6-4988-9a7b-6c5d4e3f2a1b',
        'plugin_name': 'US Market API',
        'plugin_version': '0.0.0.1',
        'tags': ['us_market', 'Sleepy'],
    }


def plugin_adapt(method: str) -> bool:
    return method in ['f1e2d3c4-b5a6-4988-9a7b-6c5d4e3f2a1b']


def plugin_capacities() -> list:
    return ['api']


# ----------------------------------------------------------------------------------------------------------------------

subServiceContext: SubServiceContext = None


def init(sub_service_context: SubServiceContext) -> bool:
    global subServiceContext
    subServiceContext = sub_service_context
    subServiceContext.sas_api.register_sys_call(
        'sas_us_stock_identity', us_stock_identity, group='us_market')
    return True


def startup() -> bool:
    return True
