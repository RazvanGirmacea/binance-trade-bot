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


class Razvan:
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

        #all_tickers = self.manager.get_all_market_tickers()
        last_trade: Trade = self.db.get_last_trade()
        print(last_trade.info())
        print(last_trade.crypto_starting_balance)

        return
        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.ratio.is_(None)).all():
                if not pair.from_coin.enabled or not pair.to_coin.enabled:
                    continue
                self.logger.info(f"Initializing {pair.from_coin} vs {pair.to_coin}")

                from_coin_price = all_tickers.get_price(pair.from_coin + self.config.BRIDGE)
                if from_coin_price is None:
                    self.logger.info(
                        "Skipping initializing {}, symbol not found".format(pair.from_coin + self.config.BRIDGE)
                    )
                    continue

                to_coin_price = all_tickers.get_price(pair.to_coin + self.config.BRIDGE)
                if to_coin_price is None:
                    self.logger.info(
                        "Skipping initializing {}, symbol not found".format(pair.to_coin + self.config.BRIDGE)
                    )
                    continue

                #pair.ratio = from_coin_price / to_coin_price
                ratio = from_coin_price / to_coin_price
                print(
                    f"{pair.from_coin/pair.to_coin}="
                    f"{ratio}"
                )


if __name__ == "__main__":
    razvan = Razvan()
