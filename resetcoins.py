from datetime import datetime
from typing import Dict, List

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


class ResetCoins:
    def __init__(self):
        self.logger = Logger()
        self.logger.info("Starting")

        self.config = Config()
        self.db = Database(self.logger, self.config)
        self.manager = BinanceAPIManager(self.config, self.db, self.logger)
        strategy = get_strategy(self.config.STRATEGY)
        if strategy is None:
            self.logger.error("Invalid strategy name")
            exit()
        self.trader = strategy(self.manager, self.db, self.logger, self.config)
        self.logger.info(f"Chosen strategy: {self.config.STRATEGY}")

        self.auto_trader = AutoTrader(self.manager, self.db, self.logger, self.config)
        self.auto_trader.reset_coins()


        return



if __name__ == "__main__":
    razvan = ResetCoins()
