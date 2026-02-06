"""
Основной торговый бот — Nado DEX
Инициализация, торговый цикл, интеграция всех модулей
"""
import asyncio
import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timedelta
import logging
import sys

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent))  # Для импорта config

import config  # Загрузка переменных из .env

from dex.nado_sdk_client import NadoSDKClient
from dex.web3_manager import Web3Manager
from bot.strategies            import GridStrategy, TrailingProfitStrategy, VolumeMakerStrategy
from bot.order_manager         import OrderManager
from tg.notification_bot import TelegramNotifier
from utils.database            import TradingDatabase
from utils.report_generator    import WordReportGenerator
from ml.trend_predictor        import TrendPredictor
from ml.data_manager           import HistoricalDataManager

logger = logging.getLogger(__name__)


class TradingBot:
    """Центральный координатор торгового бота"""

    LOOP_INTERVAL   = 5     # секунды между итерациями
    STATS_INTERVAL  = 60    # секунды между обновлениями статистики
    REPORT_INTERVAL = 3600  # секунды обновления отчёта

    def __init__(self, config_path: str = "config/config.json"):
        self.config  = self._load_config(config_path)
        self.running = False

        # ── настройки из конфига ──
        trading    = self.config.get("trading", {})
        grid_cfg   = trading.get("grid_strategy", {})

        self.symbol        = trading.get("symbol",        "BTC-USDT")
        self.position_size = Decimal(str(trading.get("position_size",  100)))
        self.max_per_side  = grid_cfg.get("max_orders_per_side", 3)
        self.leverage      = trading.get("leverage",      1)
        self.auto_trade    = trading.get("auto_trade",    False)

        # ── компоненты (None до _init_components) ──
        self.nado_client:     NadoSDKClient       = None
        self.web3_manager:    Web3Manager         = None
        self.order_manager    = OrderManager()
        self.telegram:        TelegramNotifier    = None
        self.database:        TradingDatabase     = None
        self.report_generator:WordReportGenerator = None
        self.ml_predictor:    TrendPredictor      = None
        self.hist_data:       HistoricalDataManager = None

        # ── стратегии ──
        self.strategy:          GridStrategy           = None
        self.trailing_strategy: TrailingProfitStrategy = None
        self.volume_strategy:   VolumeMakerStrategy    = None

        # ── состояние ──
        self.current_price:   Decimal  = Decimal("0")
        self.daily_volume:    Decimal  = Decimal("0")
        self.total_profit:    Decimal  = Decimal("0")
        self.last_stats_upd:  datetime = datetime.now()
        self.last_report_upd: datetime = datetime.now()
        self.day_start:       datetime = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)

        logger.info("📦 TradingBot создан")

    # ═══ ЗАГРУЗКА КОНФИГА ═══

    def _load_config(self, config_path: str) -> dict:
        path = Path(config_path)
        if not path.exists():
            logger.error(f"❌ Конфиг не найден: {config_path}")
            raise FileNotFoundError(f"Config not found: {config_path}")
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"✅ Конфиг загружен: {config_path}")
        return data

    def _get_product_id(self, symbol: str = None) -> int:
        """
        Получить product_id для символа
        
        Маппинг символов на product_id в Nado DEX:
        1 = BTC-PERP
        2 = ETH-PERP  
        4 = SOL-PERP
        """
        if symbol is None:
            symbol = self.symbol
        
        symbol_map = {
            "BTC-USDT": 1, "BTC-PERP": 1, "BTC": 1,
            "ETH-USDT": 2, "ETH-PERP": 2, "ETH": 2,
            "SOL-USDT": 4, "SOL-PERP": 4, "SOL": 4,
        }
        
        product_id = symbol_map.get(symbol.upper())
        if not product_id:
            logger.warning(f"⚠️ Неизвестный символ {symbol}, используем BTC (1)")
            return 1
        
        return product_id

    # ═══ ИНИЦИАЛИЗАЦИЯ ═══

    async def _init_components(self):
        """Инициализация всех модулей"""
        logger.info("Инициализация компонентов...")

        # 1. NadoSDKClient - OFFICIAL SDK!
        try:
            private_key = config.get_nado_key()
            network = config.get_network()
            
            self.nado_client = NadoSDKClient(
                private_key=private_key,
                network=network
            )
            logger.info(f"  OK NadoSDKClient -> {network}")
            logger.info(f"     Address: {self.nado_client.address}")
            logger.info(f"     Products: {len(self.nado_client.products)}")
        
        except Exception as e:
            logger.error(f"  ERROR NadoSDKClient: {e}")
            raise

        # 2. Web3Manager (опционально)
        try:
            rpc = config.get_rpc_url()
            self.web3_manager = Web3Manager(rpc_url=rpc, private_key=private_key)
            logger.info("  OK Web3Manager")
        except Exception as e:
            logger.warning(f"  WARNING Web3Manager: {e}")

        # 3. Telegram - использует .env через config.py
        try:
            bot_token = config.get_telegram_token()
            chat_id = config.get_telegram_chat_id()
            
            self.telegram = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
            self.telegram.trading_bot = self       # ссылка для обработки команд
            await self.telegram.start_polling()    # стартуем listening
            logger.info("  OK Telegram")
        except Exception as e:
            logger.warning(f"  WARNING Telegram: {e}")

        # 4. БД
        self.database = TradingDatabase(db_path="data/trading.db")
        logger.info("  ✅ Database")

        # 5. Отчёты
        self.report_generator = WordReportGenerator(reports_dir="data/reports")
        logger.info("  ✅ ReportGenerator")

        # 6. Исторические данные
        self.hist_data = HistoricalDataManager()
        logger.info("  ✅ HistoricalDataManager")

        # 7. ML
        self.ml_predictor = TrendPredictor(model_path="ml_model/trained_model.pkl")
        logger.info(f"  ✅ TrendPredictor")

        # 8. Стратегии
        grid_cfg = self.config.get("trading", {}).get("grid_strategy", {})
        self.strategy = GridStrategy(
            max_orders_per_side = grid_cfg.get("max_orders_per_side", 3),
            price_deviation     = Decimal(str(grid_cfg.get("price_deviation_percent", 0.7))) / Decimal("100"),
            take_profit         = Decimal(str(grid_cfg.get("take_profit_percent",  0.8))) / Decimal("100"),
            stop_loss           = Decimal(str(grid_cfg.get("stop_loss_percent",    0.5))) / Decimal("100")
        )
        self.trailing_strategy = TrailingProfitStrategy()
        self.volume_strategy   = VolumeMakerStrategy()
        logger.info("  ✅ Стратегии (Grid / Trailing / Volume)")

        logger.info("🟢 Все компоненты инициализированы")

    # ═══ СТАРТ / СТОП ═══

    async def start(self):
        """Запуск бота"""
        logger.info("=" * 50)
        logger.info("🚀 NADO DEX Trading Bot — старт")
        logger.info("=" * 50)

        await self._init_components()

        self.running    = True
        self.day_start  = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        self.database.add_event("bot_start", "Бот запущен")

        if self.telegram:
            await self.telegram.notify_bot_started()

        logger.info("🟢 Торговый цикл запущен")
        try:
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("⚠️ Цикл отменён")
        except Exception as e:
            logger.critical(f"💥 Критическая ошибка: {e}")
            if self.telegram:
                await self.telegram.notify_error(str(e))

    async def stop(self):
        """Остановка бота"""
        if not self.running:
            return
        self.running = False
        logger.info("🛑 Останавливаем бот…")

        self.database.add_event("bot_stop", "Бот остановлен")
        if self.telegram:
            await self.telegram.notify_bot_stopped()

        # финальный отчёт
        await self._generate_report()

        # останавливаем Telegram polling
        if self.telegram:
            try:
                await self.telegram.stop_polling()
            except Exception:
                pass

        logger.info("✅ Бот полностью остановлен")

    # ═══ ОСНОВНОЙ ЦИКЛ ═══

    async def _main_loop(self):
        """
        Цикл:
          1) обновить цену
          2) проверить позиции (TP / SL / trailing / volume-maker)
          3) размещать новые ордера (если auto_trade)
          4) периодические задачи
        """
        while self.running:
            try:
                await self._fetch_market_data()

                if self.current_price == Decimal("0"):
                    logger.warning("⚠️ Цена = 0, пропуск итерации")
                    await asyncio.sleep(self.LOOP_INTERVAL)
                    continue

                await self._check_positions()

                if self.auto_trade:
                    await self._place_grid_orders()

                await self._run_periodic_tasks()

            except Exception as e:
                logger.error(f"❌ Ошибка цикла: {e}")
                self.database.add_event("error", f"Цикл: {e}")

            await asyncio.sleep(self.LOOP_INTERVAL)

    # ═══ ЦЕНА ═══

    async def _fetch_market_data(self):
        """Получить текущую цену из Nado SDK"""
        try:
            price = await self.nado_client.get_market_price(self.symbol)
            
            if price and price > Decimal("0"):
                self.current_price = price
                logger.debug(f"Price {self.symbol} = {self.current_price}")
                if self.hist_data:
                    self.hist_data.append_price(self.symbol, price)
        except Exception as e:
            logger.error(f"Fetch market data error: {e}")

    # ═══ ПРОВЕРКА ПОЗИЦИЙ ═══

    async def _check_positions(self):
        """TP / SL / trailing / volume-maker для всех позиций"""
        if not self.order_manager.get_active_orders():
            return

        # 1) TP / SL
        hits = self.order_manager.check_tp_sl(self.current_price)
        for oid in hits["tp_hit"]:
            await self._close_position(oid, self.current_price, reason="tp")
        for oid in hits["sl_hit"]:
            await self._close_position(oid, self.current_price, reason="sl")

        # 2) Trailing profit — смещаем TP вверх
        if self.trailing_strategy:
            for order in self.order_manager.get_active_orders():
                should_update, new_tp = self.trailing_strategy.should_update_tp(
                    entry_price   = order.entry_price,
                    current_price = self.current_price,
                    current_tp    = order.take_profit,
                    side          = order.side
                )
                if should_update:
                    self.order_manager.update_take_profit(order.order_id, new_tp)
                    logger.info(f"🎯 Trailing TP обновлен: {order.order_id} -> {new_tp}")
                    # ПРИМЕЧАНИЕ: Nado Gateway не поддерживает динамическое обновление TP
                    # TP/SL проверяются локально через check_tp_sl()

        # 3) Volume-maker — быстрые закрытия
        if self.volume_strategy:
            for order in list(self.order_manager.get_active_orders()):
                should_close, close_type, close_pct = self.volume_strategy.should_close_position(
                    entry_price   = order.entry_price,
                    current_price = self.current_price,
                    side          = order.side
                )
                if should_close:
                    if close_type == "full":
                        await self._close_position(order.order_id, self.current_price, reason="volume_full")
                    elif close_type == "partial":
                        await self._close_partial(order.order_id, close_pct)

    # ═══ РАЗМЕЩЕНИЕ СЕТКИ ═══

    async def _place_grid_orders(self):
        """Grid стратегия: размещать лонги ниже цены, шорты выше"""
        long_count  = self.order_manager.get_orders_count_by_side("long")
        short_count = self.order_manager.get_orders_count_by_side("short")

        if long_count >= self.max_per_side and short_count >= self.max_per_side:
            return  # все слоты заняты

        # ML предсказание
        ml_dir, ml_conf = "sideways", 0.5
        if self.ml_predictor and self.hist_data:
            try:
                recent = self.hist_data.get_recent_prices(self.symbol, count=50)
                if len(recent) >= 20:
                    ml_dir, ml_conf = self.ml_predictor.predict(recent)
                    logger.info(f"🤖 ML: {ml_dir} ({ml_conf:.0%})")
            except Exception as e:
                logger.warning(f"⚠️ ML predict: {e}")

        # генерация сетки
        grid = self.strategy.generate_grid_orders(
            market_price=self.current_price,
            order_size=self.position_size
        )

        # лонги
        if long_count < self.max_per_side:
            if ml_dir == "down" and ml_conf > 0.7:
                logger.info("🤖 ML: пропускаем LONG (медвежий)")
            else:
                for entry in grid["longs"][:self.max_per_side - long_count]:
                    await self._place_single_order(entry)

        # шорты
        if short_count < self.max_per_side:
            if ml_dir == "up" and ml_conf > 0.7:
                logger.info("🤖 ML: пропускаем SHORT (бычий)")
            else:
                for entry in grid["shorts"][:self.max_per_side - short_count]:
                    await self._place_single_order(entry)

    # ═══ ОТКРЫТИЕ ОДНОГО ОРДЕРА ═══

    async def _place_single_order(self, order_data: dict) -> bool:
        """Разместить один ордер на DEX"""
        side = order_data["side"]
        entry_price = order_data["entry_price"]
        size = order_data["size"]
        tp = order_data["take_profit"]
        sl = order_data["stop_loss"]

        try:
            # Place order via SDK
            sdk_side = "buy" if side == "long" else "sell"
            result = await self.nado_client.place_order(
                symbol=self.symbol,
                side=sdk_side,
                size=size,
                price=entry_price
            )

            if not result:
                logger.error(f"Failed to place order {side}")
                return False

            order_id = result.get("digest") or f"local_{id(result)}"

            # OrderManager
            order = self.order_manager.add_order(
                order_id=order_id, side=side, size=size,
                entry_price=entry_price, take_profit=tp, stop_loss=sl,
                symbol=self.symbol, leverage=self.leverage, strategy="grid"
            )

            # Database
            self.database.add_trade(
                trade_id=order.order_id, symbol=self.symbol, side=side,
                entry_price=entry_price, size=size, leverage=self.leverage,
                take_profit=tp, stop_loss=sl, strategy="grid"
            )

            # Telegram
            if self.telegram:
                await self.telegram.notify_order_opened(side, size, entry_price, tp, sl)

            self.daily_volume += size * entry_price
            logger.info(f"Order opened: {order.order_id} | {side.upper()} @ {entry_price}")
            return True

        except Exception as e:
            logger.error(f"Place order error: {e}")
            return False

    # ═══ ЗАКРЫТИЕ ПОЗИЦИЙ ═══

    async def _close_position(self, order_id: str, exit_price: Decimal, reason: str = "manual"):
        """Полное закрытие позиции"""
        order = self.order_manager.get_order(order_id)
        if not order:
            return

        try:
            # Close via SDK
            success = await self.nado_client.close_position(self.symbol)
            
            if not success:
                logger.warning(f"Failed to close position {order_id}")
                # Continue with local close

            # 2) OrderManager
            closed = self.order_manager.close_order(order_id, exit_price)
            if not closed:
                return

            pnl, pnl_pct = closed.calculate_pnl(exit_price)

            # 3) статистика
            self.total_profit  += pnl
            self.daily_volume  += closed.original_size * exit_price

            # 4) БД
            self.database.close_trade(order_id, exit_price, pnl, pnl_pct)
            self.database.add_event("close", f"{reason}: {order_id} PnL={pnl:+.4f}")

            # 5) Telegram
            if self.telegram:
                if reason == "tp":
                    await self.telegram.notify_tp_hit(
                        closed.side, closed.original_size, closed.entry_price, exit_price, pnl)
                elif reason == "sl":
                    await self.telegram.notify_sl_hit(
                        closed.side, closed.original_size, closed.entry_price, exit_price, abs(pnl))
                else:
                    await self.telegram.notify_order_closed(
                        closed.side, closed.original_size, closed.entry_price, exit_price, pnl, pnl_pct)

            emoji = "💰" if pnl >= 0 else "💸"
            logger.info(f"{emoji} Закрыт [{reason}]: {order_id} | PnL {pnl:+.4f} ({pnl_pct:+.2f}%)")

        except Exception as e:
            logger.error(f"❌ _close_position {order_id}: {e}")

    async def _close_partial(self, order_id: str, close_pct: Decimal):
        """Частичное закрытие"""
        try:
            result = self.order_manager.close_order_partial(order_id, close_pct)
            if result:
                order, closed_size = result
                logger.info(f"➗ Частичное: {order_id} | -{closed_size} | осталось {order.size}")
        except Exception as e:
            logger.error(f"❌ _close_partial {order_id}: {e}")

    # ═══ ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ═══

    async def _run_periodic_tasks(self):
        """Обновления статистики, отчётов и сброса дня"""
        now = datetime.now()

        # ── сброс дня ──
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if today_start > self.day_start:
            logger.info("📅 Новый день — сброс счётчиков")
            # дневной отчёт за прошедший день
            await self._send_daily_report()
            self.daily_volume = Decimal("0")
            self.total_profit = Decimal("0")
            self.day_start    = today_start
            self.database.add_event("day_reset", "Сброс дневных счётчиков")

        # ── обновление статистики каждые STATS_INTERVAL сек ──
        if (now - self.last_stats_upd).total_seconds() >= self.STATS_INTERVAL:
            self.last_stats_upd = now
            self.database._update_daily_stats()

        # ── обновление отчёта каждые REPORT_INTERVAL сек ──
        if (now - self.last_report_upd).total_seconds() >= self.REPORT_INTERVAL:
            self.last_report_upd = now
            await self._generate_report()

    # ═══ ОТЧЁТЫ ═══

    async def _send_daily_report(self):
        """Отправить дневной отчёт в Telegram"""
        if not self.telegram or not self.database:
            return
        try:
            stats = self.database.get_today_stats()
            if not stats:
                return
            await self.telegram.send_daily_report(
                total_trades      = stats.get("total_trades", 0),
                profitable_trades = stats.get("profitable_trades", 0),
                total_volume      = Decimal(str(stats.get("total_volume", 0))),
                total_profit      = Decimal(str(stats.get("total_profit", 0))),
                win_rate          = stats.get("win_rate", 0.0)
            )
        except Exception as e:
            logger.error(f"❌ _send_daily_report: {e}")

    async def _generate_report(self):
        """Сгенерировать Word отчёт"""
        if not self.report_generator or not self.database:
            return
        try:
            path = self.report_generator.create_daily_report(self.database)
            logger.info(f"📄 Отчёт: {path}")
        except Exception as e:
            logger.error(f"❌ _generate_report: {e}")

    # ═══ ПУБЛИЧНЫЙ API (для Telegram бота) ═══

    async def get_active_positions(self) -> list:
        """Список активных позиций с текущим PnL"""
        return self.order_manager.get_positions_info(self.current_price)

    async def close_all_positions(self):
        """Закрыть все открытые позиции"""
        orders = list(self.order_manager.get_active_orders())
        if not orders:
            logger.info("ℹ️ Нет позиций для закрытия")
            return

        for order in orders:
            await self._close_position(order.order_id, self.current_price, reason="manual_close_all")

        logger.info(f"✅ Закрыто {len(orders)} позиций")

    async def close_position_by_id(self, order_id: str, percent: Decimal = Decimal("1")):
        """
        Закрыть позицию по ID.
        percent = 1.0 → полное, 0.5 → 50%
        """
        if percent >= Decimal("1"):
            await self._close_position(order_id, self.current_price, reason="manual")
        else:
            await self._close_partial(order_id, percent)

    async def open_manual_position(
        self,
        side:     str,
        size:     Decimal = None,
        tp_pct:   Decimal = None,
        sl_pct:   Decimal = None
    ) -> bool:
        """
        Открыть позицию вручную из Telegram.
        Если параметры не переданы — берутся из текущих настроек.
        """
        if self.current_price == Decimal("0"):
            logger.warning("⚠️ Цена неизвестна — невозможно открыть позицию")
            return False

        size   = size   or self.position_size
        tp_pct = tp_pct or Decimal(str(
            self.config.get("trading", {}).get("grid_strategy", {}).get("take_profit_percent", 0.8)
        )) / Decimal("100")
        sl_pct = sl_pct or Decimal(str(
            self.config.get("trading", {}).get("grid_strategy", {}).get("stop_loss_percent",    0.5)
        )) / Decimal("100")

        if side == "long":
            tp = self.current_price * (Decimal("1") + tp_pct)
            sl = self.current_price * (Decimal("1") - sl_pct)
        else:
            tp = self.current_price * (Decimal("1") - tp_pct)
            sl = self.current_price * (Decimal("1") + sl_pct)

        order_data = {
            "side":        side,
            "entry_price": self.current_price,
            "size":        size,
            "take_profit": tp,
            "stop_loss":   sl
        }
        return await self._place_single_order(order_data)

    def update_settings(self, **kwargs):
        """
        Обновить настройки на ходу (из Telegram).
        Поддержка ключей: position_size, leverage, auto_trade, max_per_side
        """
        if "position_size" in kwargs:
            self.position_size = Decimal(str(kwargs["position_size"]))
            logger.info(f"⚙️ position_size → {self.position_size}")

        if "leverage" in kwargs:
            self.leverage = int(kwargs["leverage"])
            logger.info(f"⚙️ leverage → {self.leverage}")

        if "auto_trade" in kwargs:
            self.auto_trade = bool(kwargs["auto_trade"])
            logger.info(f"⚙️ auto_trade → {self.auto_trade}")

        if "max_per_side" in kwargs:
            self.max_per_side = int(kwargs["max_per_side"])
            logger.info(f"⚙️ max_per_side → {self.max_per_side}")

    def get_status(self) -> dict:
        """Снимок состояния бота для Telegram /status"""
        active = self.order_manager.get_active_orders()
        total_pnl, avg_pnl_pct = self.order_manager.get_total_pnl(self.current_price)
        history_stats = self.order_manager.get_history_stats()

        return {
            "running":          self.running,
            "auto_trade":       self.auto_trade,
            "current_price":    float(self.current_price),
            "active_positions": len(active),
            "daily_volume":     float(self.daily_volume),
            "total_profit":     float(self.total_profit),
            "unrealized_pnl":   float(total_pnl),
            "position_size":    float(self.position_size),
            "leverage":         self.leverage,
            "max_per_side":     self.max_per_side,
            "symbol":           self.symbol,
            "history":          history_stats
        }

    # ═══ ПУБЛИЧНЫЕ КОМАНДЫ (вызываются из Telegram) ═══

    async def open_position(self, side: str, size: Decimal = None) -> dict:
        """Открыть позицию по текущей цене (manual)"""
        if self.current_price == 0:
            return {"ok": False, "error": "Цена ещё не загружена"}

        if size is None:
            size = self.position_size

        grid_cfg = self.config.get("trading", {}).get("grid_strategy", {})
        tp_pct   = Decimal(str(grid_cfg.get("take_profit_percent",  0.8))) / 100
        sl_pct   = Decimal(str(grid_cfg.get("stop_loss_percent",    0.5))) / 100

        if side == "long":
            tp = self.current_price * (1 + tp_pct)
            sl = self.current_price * (1 - sl_pct)
        else:
            tp = self.current_price * (1 - tp_pct)
            sl = self.current_price * (1 + sl_pct)

        order_data = {
            "side":        side,
            "size":        size,
            "entry_price": self.current_price,
            "take_profit": tp,
            "stop_loss":   sl,
        }
        success = await self._place_single_order(order_data)
        if success:
            return {"ok": True, "side": side, "size": str(size),
                    "entry": str(self.current_price), "tp": str(tp), "sl": str(sl)}
        return {"ok": False, "error": "Ошибка размещения ордера"}

    async def close_all(self) -> dict:
        """Закрыть все открытые позиции"""
        active = self.order_manager.get_active_orders()
        if not active:
            return {"ok": True, "closed": 0, "msg": "Позиций нет"}

        closed = 0
        for order in list(active):
            try:
                await self._close_position(order.order_id, self.current_price, reason="manual_close_all")
                closed += 1
            except Exception as e:
                logger.error(f"❌ close_all -> {order.order_id}: {e}")

        return {"ok": True, "closed": closed, "msg": f"Закрыто {closed}/{len(active)} позиций"}
