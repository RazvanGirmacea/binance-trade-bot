from datetime import datetime
from typing import Dict, List
from tabulate import tabulate

from sqlalchemy.orm import Session

from .binance_api_manager import AllTickers, BinanceAPIManager
from .config import Config
from .database import Database
from .logger import Logger
from .models import Coin, CoinValue, Pair, Trade, CurrentCoin


class AutoTrader:
    def __init__(self, binance_manager: BinanceAPIManager, database: Database, logger: Logger, config: Config):
        self.manager = binance_manager
        self.db = database
        self.logger = logger
        self.config = config

    def initialize(self):
        self.initialize_trade_thresholds()

    def reset_coins(self):
        self.logger.warning('Resetting pairs and coins ... ')

        session: Session
        with self.db.db_session() as session:
            session.query(Pair).delete()
            session.query(Coin).delete()
            session.query(CurrentCoin).delete()
            session.expunge_all()

        self.db.set_coins(self.config.SUPPORTED_COIN_LIST)
        self.initialize_trade_thresholds()
        return True

    """
    Useful to reset the Pairs table (reset all ratios)
    """

    def delete_pairs(self):
        self.logger.info('Resetting pairs and coins')
        session: Session
        with self.db.db_session() as session:
            session.query(Pair).delete()
            session.expunge_all()

        self.initialize_trade_thresholds()

    def transaction_through_bridge(self, pair: Pair, all_tickers: AllTickers):
        """
        Jump from the source coin to the destination coin through bridge coin
        """
        can_sell = False
        self.update_values() #update coin balance first

        balance = self.manager.get_currency_balance(pair.from_coin.symbol)
        from_coin_price = all_tickers.get_price(pair.from_coin + self.config.BRIDGE)

        if balance and balance * from_coin_price > self.manager.get_min_notional(pair.from_coin, self.config.BRIDGE):
            can_sell = True
        else:
            self.logger.info("Skipping sell")

        if can_sell and self.manager.sell_alt(pair.from_coin, self.config.BRIDGE, all_tickers) is None:
            self.logger.info("Couldn't sell, going back to scouting mode...")
            return None

        self.update_values() #update coin values before buying
        result = self.manager.buy_alt(pair.to_coin, self.config.BRIDGE, all_tickers)
        self.logger.info(f"RESULT = {result}  --- (to_coin {pair.to_coin.symbol})")

        self.update_values()  # update coin balance after selling

        if result and float(result["price"]) == 0:
            result["price"] = float(result["cummulativeQuoteQty"]) / float(result["origQty"])

        if result is not None:
            self.db.set_current_coin(pair.to_coin)
            self.update_trade_threshold(pair.to_coin, float(result["price"]), all_tickers)
            return result

        self.logger.info("Couldn't buy, going back to scouting mode...")
        return None

    def update_trade_threshold(self, coin: Coin, coin_price: float, all_tickers: AllTickers):
        """
        Update all the coins with the threshold of buying the current held coin
        """

        if coin_price is None:
            self.logger.info("Skipping update... current coin {} not found".format(coin + self.config.BRIDGE))
            return

        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.to_coin == coin):
                from_coin_price = all_tickers.get_price(pair.from_coin + self.config.BRIDGE)

                if from_coin_price is None:
                    self.logger.info(
                        "Skipping update for coin {} not found".format(pair.from_coin + self.config.BRIDGE)
                    )
                    continue

                if coin_price is None:
                    coin_price = all_tickers.get_price(pair.to_coin + self.config.BRIDGE)

                pair.ratio = from_coin_price / coin_price

            session.commit()


    def initialize_trade_thresholds(self):
        """
        Initialize the buying threshold of all the coins for trading between them
        """
        all_tickers = self.manager.get_all_market_tickers()

        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.ratio.is_(None)).all():
                if not pair.from_coin.enabled or not pair.to_coin.enabled:
                    continue
                print(f"Initializing {pair.from_coin} vs {pair.to_coin}")

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

                pair.ratio = from_coin_price / to_coin_price

    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        raise NotImplementedError()

    def _get_ratios(self, coin: Coin, coin_price: float, all_tickers: AllTickers):
        print_table = [["Time", "To Coin", "Result", "%", "To Price", "Possible Coins"]]
        is_lower_progress = 0

        """
         Get Balance info
         """
        balance_coin = self.manager.get_currency_balance(coin.symbol)
        balance_value = last_trade = profit = 0
        last_trade_symbol = None

        if balance_coin:
            balance_value = balance_coin * coin_price
            self.logger.info(
                f"--- {coin.symbol} price is ${coin_price:.4f}, balance is {balance_coin:.2f} valued at {balance_value:.0f}$",
            )

            """
            Get Last Trade info
            """
            last_trade: Trade = self.db.get_last_trade()
            if last_trade and last_trade.crypto_trade_amount:
                last_trade_value = last_trade.crypto_trade_amount
                last_trade_symbol = last_trade.alt_coin_id
                profit = balance_value / last_trade_value * 100 - 100;
                if last_trade_value:
                    self.logger.info(
                        f"Last trade value {last_trade_value:.0f}$. "
                        f"Current value is {profit:.1f}% "
                        f"({balance_value - last_trade_value:.0f}$)."
                    )

                    last_coin_trade: Trade = self.db.get_last_trade(last_trade)
                    if last_coin_trade:
                        profit_coins = last_trade.alt_trade_amount / last_coin_trade.alt_trade_amount * 100 - 100
                        profit_last_trade = last_trade.crypto_trade_amount / last_coin_trade.crypto_trade_amount * 100 - 100

                        last_coin_trade_price = last_coin_trade.crypto_trade_amount / last_coin_trade.alt_trade_amount
                        updown_string = 'increased' if last_coin_trade_price <= coin_price else 'decreased'
                        price_increase = coin_price / last_coin_trade_price * 100 - 100
                        self.db.logger.info("You had {:.2f} coins, now {:.1f}% more since last {} trade at {}"
                                            .format(last_coin_trade.alt_trade_amount,
                                                    profit_coins,
                                                    coin.symbol,
                                                    last_coin_trade.datetime.strftime("%d/%m/%Y %H:%M:%S")))
                        self.db.logger.info(f"Price {updown_string} by {price_increase:.1f}% "
                                            f"(From {last_coin_trade_price:.4f} to {coin_price:.4f})")
                        self.db.logger.info(f"Last {coin.symbol} trade balance "
                                            f"was {last_coin_trade.crypto_trade_amount:.0f}$ (now {profit_last_trade:.1f}%)")

        """
        Given a coin, get the current price ratio for every other enabled coin
        """
        ratio_dict: Dict[Pair, float] = {}

        for pair in self.db.get_pairs_from(coin):
            optional_coin_price = all_tickers.get_price(pair.to_coin + self.config.BRIDGE)

            if optional_coin_price is None:
                self.logger.info(
                    "Skipping scouting... optional coin {} not found".format(pair.to_coin + self.config.BRIDGE)
                )
                continue

            self.db.log_scout(pair, pair.ratio, coin_price, optional_coin_price)

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = coin_price / optional_coin_price

            transaction_fee = self.manager.get_fee(pair.from_coin, self.config.BRIDGE, True) + self.manager.get_fee(
                pair.to_coin, self.config.BRIDGE, False
            )

            ratio_dict[pair] = (coin_opt_coin_ratio -
                                transaction_fee * self.config.SCOUT_MULTIPLIER * coin_opt_coin_ratio
                                ) - pair.ratio

            # Output scout result for each selected pair
            progress = (
                    (coin_opt_coin_ratio - transaction_fee * self.config.SCOUT_MULTIPLIER * coin_opt_coin_ratio)
                    / pair.ratio
                    * 100
            )

            # mark at least one ratio is under 90% (or self.config.PROGRESS_PERCENTAGE_UNDER)
            if progress < self.config.PROGRESS_PERCENTAGE_UNDER:
                is_lower_progress = is_lower_progress + 1

            print_table.append([datetime.now().strftime("%H:%M:%S"),
                                "{:>6}".format(pair.to_coin.symbol),
                                "{:10.5f}".format(ratio_dict[pair]),
                                "{:.1f}%".format(progress),
                                "{:>10.4f}".format(optional_coin_price),
                                "{:10.3f}".format(balance_value / optional_coin_price * (1 - transaction_fee))])

            """
            Display progress for each coin
            """
            # print(
            #     f"[{datetime.now().strftime('%H:%M:%S')}]"
            #     f"{pair.to_coin.symbol:>6} result = {ratio_dict[pair]:10.5f} "
            #     f"[{progress:.1f}%] "
            #     f"({optional_coin_price:>10.4f}$) "
            #     f"Possible coins {balance_value / optional_coin_price:10.3f}, __last_trade_coins__",
            #     flush=True
            # )

        print(tabulate(print_table, headers="firstrow", tablefmt="github"))

        # if profit > 3% and at least one coin ratio is under 90%, reset to force jump and increase balance $
        if profit > self.config.PROFIT_TO_RESET and is_lower_progress and last_trade_symbol != coin.symbol:
            self.logger.warning(f"Profit > {self.config.PROFIT_TO_RESET}% "
                                f"and progress lower than {self.config.PROGRESS_PERCENTAGE_UNDER}%, "
                                f"maybe reset the pair values?")
            self.delete_pairs()
            self.logger.warning("Deleted pairs")

        # if profit > 0 and more coins are lower progress, reset coins to force jump
        if profit > 0 and is_lower_progress > self.config.NUMBER_OF_COINS_UNDER and last_trade_symbol != coin.symbol:
            self.logger.warning(f"Profit > 0% and {self.config.NUMBER_OF_COINS_UNDER} "
                                f"progress lower than {self.config.PROGRESS_PERCENTAGE_UNDER}%, "
                                f"maybe reset the pair values?")
            self.delete_pairs()
            self.logger.warning("Deleted pairs")

        # if all coins are lower progress, reset coins to force jump
        if is_lower_progress >= (len(self.db.get_coins())-1):
            self.logger.warning("Resetting pairs because all are low")
            self.delete_pairs()
            self.logger.warning("Deleted pairs")

        return ratio_dict

    def _jump_to_best_coin(self, coin: Coin, coin_price: float, all_tickers: AllTickers):
        """
        Given a coin, search for a coin to jump to
        """
        ratio_dict = self._get_ratios(coin, coin_price, all_tickers)

        # keep only ratios bigger than zero
        ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}

        # if we have any viable options, pick the one with the biggest ratio
        if ratio_dict:
            best_pair = max(ratio_dict, key=ratio_dict.get)
            self.logger.info(f"Will be jumping from {coin} to {best_pair.to_coin_id}")
            self.transaction_through_bridge(best_pair, all_tickers)

    def bridge_scout(self):
        """
        If we have any bridge coin leftover, buy a coin with it that we won't immediately trade out of
        """
        bridge_balance = self.manager.get_currency_balance(self.config.BRIDGE.symbol)
        all_tickers = self.manager.get_all_market_tickers()

        for coin in self.db.get_coins():
            current_coin_price = all_tickers.get_price(coin + self.config.BRIDGE)

            if current_coin_price is None:
                continue

            ratio_dict = self._get_ratios(coin, current_coin_price, all_tickers)
            if not any(v > 0 for v in ratio_dict.values()):
                # There will only be one coin where all the ratios are negative. When we find it, buy it if we can
                if bridge_balance > self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol):
                    self.logger.info(f"Will be purchasing {coin} using bridge coin")
                    self.manager.buy_alt(coin, self.config.BRIDGE, all_tickers)
                    return coin
        return None

    def update_values(self):
        """
        Log current value state of all altcoin balances against BTC and USDT in DB.
        """
        all_ticker_values = self.manager.get_all_market_tickers()

        now = datetime.now()

        session: Session
        with self.db.db_session() as session:
            coins: List[Coin] = session.query(Coin).all()
            for coin in coins:
                balance = self.manager.get_currency_balance(coin.symbol)
                if balance == 0:
                    continue
                usd_value = all_ticker_values.get_price(coin + "USDT")
                btc_value = all_ticker_values.get_price(coin + "BTC")
                cv = CoinValue(coin, balance, usd_value, btc_value, datetime=now)
                session.add(cv)
                self.db.send_update(cv)
