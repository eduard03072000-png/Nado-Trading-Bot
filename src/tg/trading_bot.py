"""
Расширенный Telegram бот для полного управления торговлей
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
import logging
from decimal import Decimal
from typing import Dict, Any
import json

logger = logging.getLogger(__name__)


class TradingTelegramBot:
    """
    Полнофункциональный Telegram бот для управления торговлей
    """
    
    def __init__(self, bot_token: str, trading_bot_instance=None):
        self.bot_token = bot_token
        self.trading_bot = trading_bot_instance
        self.application = None
        
        # Настройки фильтров (хранятся для каждого пользователя)
        self.user_settings: Dict[int, Dict[str, Any]] = {}
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        keyboard = [
            [
                InlineKeyboardButton("📊 Статус", callback_data="status"),
                InlineKeyboardButton("💰 Баланс", callback_data="balance")
            ],
            [
                InlineKeyboardButton("📈 Позиции", callback_data="positions"),
                InlineKeyboardButton("📋 Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
🤖 <b>NADO DEX Trading Bot</b>

Добро пожаловать! Этот бот позволяет управлять торговлей на NADO DEX.

Выберите действие:
"""
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню настроек"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        settings = self.user_settings.get(user_id, self._default_settings())
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Стратегия", callback_data="setting_strategy"),
                InlineKeyboardButton("💰 Размер позиции", callback_data="setting_size")
            ],
            [
                InlineKeyboardButton("🎯 Take Profit", callback_data="setting_tp"),
                InlineKeyboardButton("🛑 Stop Loss", callback_data="setting_sl")
            ],
            [
                InlineKeyboardButton("📈 Плечо", callback_data="setting_leverage"),
                InlineKeyboardButton("🔢 Макс. позиций", callback_data="setting_max_positions")
            ],
            [
                InlineKeyboardButton("⚡ Авто-торговля", callback_data="setting_auto_trade"),
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"""
⚙️ <b>НАСТРОЙКИ БОТА</b>

📊 Стратегия: <code>{settings['strategy']}</code>
💰 Размер позиции: <code>{settings['position_size']} USDT</code>
🎯 Take Profit: <code>{settings['take_profit']}%</code>
🛑 Stop Loss: <code>{settings['stop_loss']}%</code>
📈 Плечо: <code>{settings['leverage']}x</code>
🔢 Макс. позиций: <code>{settings['max_positions']}</code>
⚡ Авто-торговля: <code>{'ВКЛ' if settings['auto_trade'] else 'ВЫКЛ'}</code>
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def positions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню активных позиций"""
        query = update.callback_query
        await query.answer()
        
        # Получаем активные позиции от торгового бота
        if self.trading_bot:
            positions = await self.trading_bot.get_active_positions()
        else:
            positions = []
        
        if not positions:
            text = "📊 <b>АКТИВНЫЕ ПОЗИЦИИ</b>\n\n⚠️ Нет открытых позиций"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        else:
            text = "📊 <b>АКТИВНЫЕ ПОЗИЦИИ</b>\n\n"
            keyboard = []
            
            for idx, pos in enumerate(positions, 1):
                side_emoji = "🟢" if pos['side'] == 'long' else "🔴"
                text += f"{side_emoji} <b>#{idx} {pos['side'].upper()}</b>\n"
                text += f"💰 Размер: <code>{pos['size']}</code>\n"
                text += f"📍 Вход: <code>{pos['entry_price']}</code>\n"
                text += f"💵 PnL: <code>{pos['pnl']:+.2f} ({pos['pnl_percent']:+.2f}%)</code>\n\n"
                
                # Кнопки для управления позицией
                keyboard.append([
                    InlineKeyboardButton(f"🔧 Управление #{idx}", callback_data=f"manage_pos_{pos['id']}")
                ])
            
            keyboard.append([
                InlineKeyboardButton("❌ Закрыть все", callback_data="close_all_positions"),
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def manage_position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление конкретной позицией"""
        query = update.callback_query
        await query.answer()
        
        position_id = query.data.split('_')[-1]
        
        keyboard = [
            [
                InlineKeyboardButton("📈 Изменить TP", callback_data=f"change_tp_{position_id}"),
                InlineKeyboardButton("📉 Изменить SL", callback_data=f"change_sl_{position_id}")
            ],
            [
                InlineKeyboardButton("➗ Закрыть 50%", callback_data=f"close_half_{position_id}"),
                InlineKeyboardButton("❌ Закрыть всю", callback_data=f"close_full_{position_id}")
            ],
            [
                InlineKeyboardButton("🔙 К позициям", callback_data="positions")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"""
🔧 <b>УПРАВЛЕНИЕ ПОЗИЦИЕЙ #{position_id}</b>

Выберите действие:
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def open_position_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню открытия новой позиции"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [
                InlineKeyboardButton("🟢 Открыть LONG", callback_data="open_long"),
                InlineKeyboardButton("🔴 Открыть SHORT", callback_data="open_short")
            ],
            [
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
📊 <b>ОТКРЫТЬ НОВУЮ ПОЗИЦИЮ</b>

Выберите направление:
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    def _default_settings(self) -> Dict[str, Any]:
        """Настройки по умолчанию"""
        return {
            'strategy': 'Grid Trading',
            'position_size': 100,
            'take_profit': 1.0,
            'stop_loss': 0.5,
            'leverage': 1,
            'max_positions': 6,
            'auto_trade': False
        }
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий кнопок"""
        query = update.callback_query
        
        handlers = {
            'status':            self.status_handler,
            'balance':           self.balance_handler,
            'positions':         self.positions_menu,
            'stats':             self.stats_handler,
            'settings':          self.settings_menu,
            'help':              self.help_handler,
            'main_menu':         self.main_menu,
            'open_position':     self.open_position_menu,
            'open_long':         self.open_long_handler,
            'open_short':        self.open_short_handler,
            'close_all_positions': self.close_all_handler,
            'setting_auto_trade':  self.toggle_auto_trade
        }
        
        # сложные callback_data с суффиксом
        if query.data.startswith('manage_pos_'):
            await self.manage_position(update, context)
        elif query.data.startswith('close_full_'):
            await self.close_full_handler(update, context)
        elif query.data.startswith('close_half_'):
            await self.close_half_handler(update, context)
        elif query.data in handlers:
            await handlers[query.data](update, context)
        else:
            await query.answer("⚠️ Неизвестная команда")
    
    async def status_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статус бота"""
        query = update.callback_query
        await query.answer()

        if self.trading_bot:
            s = self.trading_bot.get_status()
            status_str = "🟢 Активен" if s["running"] else "🔴 Остановлен"
            auto_str   = "ВКЛ" if s["auto_trade"] else "ВЫКЛ"
            text = f"""
📊 <b>СТАТУС БОТА</b>

{status_str} | Авто-торговля: <code>{auto_str}</code>
📈 Позиций: <code>{s["active_positions"]}</code>
💹 Цена: <code>{s["current_price"]}</code>
💰 Прибыль сегодня: <code>{s["total_profit"]:+.4f} USDT</code>
📊 Объём сегодня: <code>{s["daily_volume"]:.2f} USDT</code>
📉 Нереализ. PnL: <code>{s["unrealized_pnl"]:+.4f} USDT</code>"""
        else:
            text = "📊 <b>СТАТУС</b>\n\n⚠️ Торговой ссылки нет"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def balance_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать баланс"""
        query = update.callback_query
        await query.answer()

        available = Decimal("0")
        in_positions = Decimal("0")

        if self.trading_bot and self.trading_bot.nado_api:
            try:
                balance_data = await self.trading_bot.nado_api.get_account_balance()
                if isinstance(balance_data, dict):
                    available    = Decimal(str(balance_data.get("available", 0)))
                    in_positions = Decimal(str(balance_data.get("in_positions", 0)))
            except Exception:
                pass

        total = available + in_positions
        text = f"""
💰 <b>БАЛАНС</b>

💵 Доступно: <code>{available:.4f} USDT</code>
🔒 В позициях: <code>{in_positions:.4f} USDT</code>
📊 Всего: <code>{total:.4f} USDT</code>"""

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def stats_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику"""
        query = update.callback_query
        await query.answer()

        h = {}
        if self.trading_bot:
            h = self.trading_bot.order_manager.get_history_stats()

        text = f"""
📋 <b>СТАТИСТИКА (за сессию)</b>

📊 Всего сделок: <code>{h.get("total", 0)}</code>
✅ Прибыльных: <code>{h.get("wins", 0)}</code>
❌ Убыточных: <code>{h.get("losses", 0)}</code>
🎯 Винрейт: <code>{h.get("win_rate", 0)}%</code>

💰 Общая прибыль: <code>{float(h.get("total_pnl", 0)):+.4f} USDT</code>
📈 Лучшая сделка: <code>{float(h.get("best", 0)):+.4f}</code>
📉 Худшая сделка: <code>{float(h.get("worst", 0)):+.4f}</code>

📄 Полный отчёт: /report"""

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать помощь"""
        query = update.callback_query
        await query.answer()
        
        text = """
❓ <b>СПРАВКА</b>

<b>Команды:</b>
/start - Главное меню
/status - Статус бота
/positions - Активные позиции
/balance - Баланс
/stats - Статистика
/settings - Настройки
/report - Полный отчет (Word)
/open_long - Открыть LONG
/open_short - Открыть SHORT
/close_all - Закрыть все позиции

<b>Управление позициями:</b>
• Через меню "Позиции"
• Изменение TP/SL
• Частичное закрытие
• Полное закрытие
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Статус", callback_data="status"),
                InlineKeyboardButton("💰 Баланс", callback_data="balance")
            ],
            [
                InlineKeyboardButton("📈 Позиции", callback_data="positions"),
                InlineKeyboardButton("📋 Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton("➕ Открыть позицию", callback_data="open_position"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "🤖 <b>ГЛАВНОЕ МЕНЮ</b>\n\nВыберите действие:"
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    # ── открыть позицию ──

    async def open_long_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Однокнопочное открытие LONG"""
        query = update.callback_query
        await query.answer()
        if self.trading_bot:
            ok = await self.trading_bot.open_manual_position("long")
            text = "✅ <b>LONG открыт</b>" if ok else "❌ <b>Не удалось открыть LONG</b>"
        else:
            text = "⚠️ Торговой ссылки нет"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def open_short_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Однокнопочное открытие SHORT"""
        query = update.callback_query
        await query.answer()
        if self.trading_bot:
            ok = await self.trading_bot.open_manual_position("short")
            text = "✅ <b>SHORT открыт</b>" if ok else "❌ <b>Не удалось открыть SHORT</b>"
        else:
            text = "⚠️ Торговой ссылки нет"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # ── закрыть позиции ──

    async def close_all_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Закрыть все позиции"""
        query = update.callback_query
        await query.answer()
        if self.trading_bot:
            await self.trading_bot.close_all_positions()
            text = "✅ <b>Все позиции закрыты</b>"
        else:
            text = "⚠️ Торговой ссылки нет"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def close_full_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """100% закрытие одной позиции"""
        query = update.callback_query
        await query.answer()
        order_id = query.data.split("close_full_")[1]
        if self.trading_bot:
            await self.trading_bot.close_position_by_id(order_id, Decimal("1"))
            text = f"✅ <b>Позиция {order_id} закрыта</b>"
        else:
            text = "⚠️ Торговой ссылки нет"
        keyboard = [[InlineKeyboardButton("🔙 К позициям", callback_data="positions")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    async def close_half_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """50% закрытие"""
        query = update.callback_query
        await query.answer()
        order_id = query.data.split("close_half_")[1]
        if self.trading_bot:
            await self.trading_bot.close_position_by_id(order_id, Decimal("0.5"))
            text = f"✅ <b>Позиция {order_id}: закрыто 50%</b>"
        else:
            text = "⚠️ Торговой ссылки нет"
        keyboard = [[InlineKeyboardButton("🔙 К позициям", callback_data="positions")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # ── toggle авто-торговля ──

    async def toggle_auto_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Вкл/выкл авто-торговли"""
        query = update.callback_query
        await query.answer()
        if self.trading_bot:
            current = self.trading_bot.auto_trade
            self.trading_bot.update_settings(auto_trade=not current)
            state = "ВКЛ" if not current else "ВЫКЛ"
            text = f"✅ <b>Авто-торговля: {state}</b>"
        else:
            text = "⚠️ Торговой ссылки нет"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings")]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # ── запуск ──

    def run(self):
        """Запустить бота"""
        self.application = Application.builder().token(self.bot_token).build()
        
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        logger.info("🤖 Telegram бот запущен")
        self.application.run_polling()
