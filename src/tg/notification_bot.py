"""
Telegram бот для уведомлений И обработки команд.
Уведомления шлём через Bot, команды слушаем через Application + polling.
"""
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Уведомления + обработка команд из Telegram"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token  = bot_token
        self.chat_id    = chat_id
        self.bot        = Bot(token=bot_token)
        self.app        = None          # Application (polling)
        self.trading_bot = None         # ссылка на TradingBot (ставится извне)

    # ─── отправка сообщения ───────────────────────────────────

    async def send_message(self, text: str):
        try:
            await self.bot.send_message(
                chat_id=self.chat_id, text=text, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    # ─── запуск polling в фоне ────────────────────────────────

    async def start_polling(self):
        """Создаём Application и стартуем polling в фоновой задаче"""
        self.app = (
            Application.builder()
            .token(self.bot_token)
            .build()
        )
        # регистрация команд
        self.app.add_handler(CommandHandler("start",    self._cmd_start))
        self.app.add_handler(CommandHandler("stop",     self._cmd_stop))
        self.app.add_handler(CommandHandler("status",   self._cmd_status))
        self.app.add_handler(CommandHandler("positions",self._cmd_positions))
        self.app.add_handler(CommandHandler("open_long", self._cmd_open_long))
        self.app.add_handler(CommandHandler("open_short",self._cmd_open_short))
        self.app.add_handler(CommandHandler("close_all",self._cmd_close_all))
        self.app.add_handler(CommandHandler("settings", self._cmd_settings))
        self.app.add_handler(CommandHandler("report",   self._cmd_report))
        self.app.add_handler(CommandHandler("help",     self._cmd_help))

        # стартуем polling в фоновой задаче (не блокируем цикл бота)
        import asyncio
        asyncio.create_task(self._run_polling())
        logger.info("✅ Telegram polling запущен")

    async def _run_polling(self):
        await self.app.initialize()
        await self.app.start()
        # drop_pending_updates сбрасывает старый offset (после перезапуска)
        await self.app.updater.start_polling(drop_pending_updates=True)
        import asyncio
        try:
            # Ждем пока updater работает
            while self.app.updater.running:
                await asyncio.sleep(1)
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Получен сигнал остановки polling")
        finally:
            if self.app.updater.running:
                await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    async def stop_polling(self):
        if self.app and self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    # ─── guard: только наш чат ───────────────────────────────

    def _is_allowed(self, update: Update) -> bool:
        user_chat_id = str(update.effective_chat.id)
        my_chat_id = str(self.chat_id)
        allowed = user_chat_id == my_chat_id
        logger.debug(f"🔍 _is_allowed: user={user_chat_id}, expected={my_chat_id}, allowed={allowed}")
        return allowed

    # ═══════════════════════════════════════════════════════════
    # ОБРАБОТЧИКИ КОМАНД
    # ═══════════════════════════════════════════════════════════

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        await update.message.reply_text(
            "📖 <b>КОМАНДЫ БОТА</b>\n\n"
            "/status — текущий статус и цена\n"
            "/positions — открытые позиции\n"
            "/open_long [сумма] — открыть лонг\n"
            "/open_short [сумма] — открыть шорт\n"
            "/close_all — закрыть все позиции\n"
            "/settings auto_trade true — настройки\n"
            "/report — сгенерировать отчёт\n"
            "/stop — остановить бот\n"
            "/help — эта справка",
            parse_mode="HTML"
        )

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        await update.message.reply_text("🟢 Бот уже работает. Используйте /status для статуса.")

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        await update.message.reply_text("🛑 Останавливаем бот...")
        if self.trading_bot:
            import asyncio
            asyncio.create_task(self.trading_bot.stop())

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"📨 Получена команда /status от {update.effective_chat.id}")
        if not self._is_allowed(update):
            logger.warning(f"⛔ Команда отклонена. Chat ID {update.effective_chat.id} != {self.chat_id}")
            return
        logger.info("✅ Команда разрешена, обрабатываем...")
        if not self.trading_bot:
            await update.message.reply_text("⚠️ TradingBot не инициализирован")
            return

        s = self.trading_bot.get_status()
        text = (
            "📊 <b>СТАТУС БОТА</b>\n\n"
            f"🟢 Работает: <b>{'Да' if s['running'] else 'Нет'}</b>\n"
            f"📈 Автотрейд: <b>{'Да' if s['auto_trade'] else 'Нет'}</b>\n"
            f"💹 Цена {s['symbol']}: <code>${s['current_price']:,.2f}</code>\n\n"
            f"📦 Позиций: <b>{s['active_positions']}</b>\n"
            f"📉 Unrealized PnL: <code>{s['unrealized_pnl']:+.4f}</code>\n"
            f"💰 Прибыль (закр.): <code>{s['total_profit']:+.4f}</code>\n"
            f"📊 Объём сегодня: <code>{s['daily_volume']:.2f}</code>\n\n"
            f"⚙️ Размер позиции: <code>{s['position_size']}</code> | "
            f"Плеч: <code>x{s['leverage']}</code> | "
            f"Max/сторону: <code>{s['max_per_side']}</code>\n\n"
            f"📈 История: сделок={s['history']['total']} | "
            f"wins={s['history']['wins']} | "
            f"winrate={s['history']['win_rate']:.1f}%"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        if not self.trading_bot:
            await update.message.reply_text("⚠️ TradingBot не инициализирован")
            return

        active = self.trading_bot.order_manager.get_active_orders()
        if not active:
            await update.message.reply_text("📦 Открытых позиций нет.")
            return

        price = self.trading_bot.current_price
        lines = ["📦 <b>ОТКРЫТЫЕ ПОЗИЦИИ</b>\n"]
        for o in active:
            pnl, pnl_pct = o.calculate_pnl(price)
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{emoji} <code>{o.order_id}</code> | "
                f"<b>{o.side.upper()}</b> | "
                f"size={o.size} | entry={o.entry_price} | "
                f"PnL={pnl:+.4f} ({pnl_pct:+.2f}%)"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_open_long(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        await self._open_pos(update, "long")

    async def _cmd_open_short(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        await self._open_pos(update, "short")

    async def _open_pos(self, update: Update, side: str):
        if not self.trading_bot:
            await update.message.reply_text("⚠️ TradingBot не инициализирован")
            return

        # парсим сумму из аргумента
        args = update.message.text.split()
        size = None
        if len(args) > 1:
            try:
                size = Decimal(args[1])
            except Exception:
                await update.message.reply_text("❌ Укажите сумму числом, например /open_long 100")
                return

        await update.message.reply_text(f"⏳ Открываем {side.upper()}...")
        result = await self.trading_bot.open_position(side, size)

        if result["ok"]:
            await update.message.reply_text(
                f"✅ <b>Позиция открыта</b>\n\n"
                f"Сторона: <b>{result['side'].upper()}</b>\n"
                f"Размер: <code>{result['size']}</code>\n"
                f"Вход: <code>{result['entry']}</code>\n"
                f"TP: <code>{result['tp']}</code>\n"
                f"SL: <code>{result['sl']}</code>",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Неизвестная ошибка')}")

    async def _cmd_close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        if not self.trading_bot:
            await update.message.reply_text("⚠️ TradingBot не инициализирован")
            return

        await update.message.reply_text("⏳ Закрываем все позиции...")
        result = await self.trading_bot.close_all()
        await update.message.reply_text(f"✅ {result.get('msg', 'Готово')}")

    async def _cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        if not self.trading_bot:
            await update.message.reply_text("⚠️ TradingBot не инициализирован")
            return

        args = update.message.text.split()
        # /settings без аргументов — показать текущие
        if len(args) < 3:
            s = self.trading_bot.get_status()
            await update.message.reply_text(
                f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
                f"position_size: <code>{s['position_size']}</code>\n"
                f"leverage: <code>{s['leverage']}</code>\n"
                f"auto_trade: <code>{s['auto_trade']}</code>\n"
                f"max_per_side: <code>{s['max_per_side']}</code>\n\n"
                f"Пример: /settings auto_trade true",
                parse_mode="HTML"
            )
            return

        key, value = args[1], args[2]
        # конвертация типов
        if value.lower() in ("true", "false"):
            value = value.lower() == "true"

        try:
            self.trading_bot.update_settings(**{key: value})
            await update.message.reply_text(f"✅ {key} = <code>{value}</code>", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        await update.message.reply_text("📊 Генерируем отчёт... (скоро)")

    # ═══════════════════════════════════════════════════════════
    # УВЕДОМЛЕНИЯ (без изменений — всё через send_message)
    # ═══════════════════════════════════════════════════════════

    async def notify_order_opened(self, side, size, entry_price, tp, sl):
        emoji = "🟢" if side == "long" else "🔴"
        await self.send_message(
            f"{emoji} <b>ПОЗИЦИЯ ОТКРЫТА</b>\n\n"
            f"📊 {side.upper()} | 💰 {size} | 📍 {entry_price}\n"
            f"🎯 TP: {tp} | 🛑 SL: {sl}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )

    async def notify_order_closed(self, side, size, entry_price, exit_price, profit, profit_percent):
        emoji = "✅" if profit > 0 else "❌"
        await self.send_message(
            f"{emoji} <b>ПОЗИЦИЯ ЗАКРЫТА</b>\n\n"
            f"📊 {side.upper()} | 💰 {size}\n"
            f"📍 Вход: {entry_price} → Выход: {exit_price}\n"
            f"💵 PnL: {profit:+.4f} ({profit_percent:+.2f}%)\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )

    async def notify_error(self, error_message: str):
        await self.send_message(
            f"⚠️ <b>ОШИБКА</b>\n\n❌ {error_message}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )

    async def notify_bot_started(self):
        await self.send_message(
            f"🚀 <b>БОТ ЗАПУЩЕН</b>\n\n"
            f"✅ Торговый бот успешно запущен\n"
            f"📖 Доступные команды: /help\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )

    async def notify_bot_stopped(self):
        await self.send_message(
            f"⛔ <b>БОТ ОСТАНОВЛЕН</b>\n\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )

    async def notify_tp_hit(self, side, size, entry_price, tp_price, profit):
        await self.send_message(
            f"🎯 <b>TAKE PROFIT</b>\n\n"
            f"📊 {side.upper()} | 💰 {size} | TP: {tp_price}\n"
            f"💵 +{profit:.4f}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )

    async def notify_sl_hit(self, side, size, entry_price, sl_price, loss):
        await self.send_message(
            f"🛑 <b>STOP LOSS</b>\n\n"
            f"📊 {side.upper()} | 💰 {size} | SL: {sl_price}\n"
            f"💸 {loss:.4f}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )

    async def send_daily_report(self, total_trades, profitable_trades, total_volume, total_profit, win_rate):
        await self.send_message(
            f"📊 <b>ДНЕВНОЙ ОТЧЁТ</b>\n\n"
            f"📈 Сделок: {total_trades} | ✅ Прибыльных: {profitable_trades}\n"
            f"💰 Объём: {total_volume:.2f} | PnL: {total_profit:+.4f}\n"
            f"🎯 Winrate: {win_rate:.1f}%\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
