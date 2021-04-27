from datetime import datetime
from typing import Dict, List
import sys

from sqlalchemy.orm import Session

from binance_trade_bot import BinanceAPIManager, database

from binance_trade_bot.config import Config
from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import Coin
from binance_trade_bot.strategies import get_strategy
from binance_trade_bot.models import Coin, CoinValue, Pair, Trade
from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.strategies import multiple_coins_strategy
from tabulate import tabulate


class SetCoin:
    def __init__(self, coin_symbol):
        self.logger = Logger()
        self.logger.info("Starting")

        self.config = Config()
        self.db = Database(self.logger, self.config)

        self.db.set_current_coin(coin_symbol)

        return


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print(f"run python setcoin.py COIN")
        pass

    if sys.argv[1]:
        setcoin = SetCoin(sys.argv[1])
