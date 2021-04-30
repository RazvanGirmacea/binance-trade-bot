from time import time
from .logger import Logger


def first(iterable, condition=lambda x: True):
    return next((x for x in iterable if condition(x)), None)


def get_market_ticker_price_from_list(all_tickers, ticker_symbol):
    """
    Get ticker price of a specific coin
    """
    ticker = first(all_tickers, condition=lambda x: x["symbol"] == ticker_symbol)
    return float(ticker["price"]) if ticker else None


########
### To prevent spam in Logs, print or log a message every X minutes (default 10)
#######
def print_or_log(message, minutes=10, logger=None):
    if 60 - time() % minutes and Logger:
        logger.info(message)
    else:
        print(message)
    pass
