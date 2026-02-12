"""
Telegram Trading Bot - Full NADO DEX Integration
"""
import logging
import os
import sys
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler
import config
# Import Multi-Wallet Dashboard
sys.path.insert(0, os.path.dirname(__file__))
from multi_wallet_dashboard import MultiWalletDashboard
from trading_dashboard_v2 import PRODUCTS
from tp_sl_calculator import TPSLCalculator
from trade_history_manager import TradeHistoryManager
from history_handlers import show_history_menu, show_period_summary, show_period_details
from decimal import Decimal
import asyncio
import time
from functools import wraps

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Rate limiting
user_cooldowns = {}

def rate_limit(seconds=2):
    """Rate limiting decorator для предотвращения спама"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            now = time.time()
            
            # Проверяем cooldown
            if user_id in user_cooldowns:
                if now - user_cooldowns[user_id] < seconds:
                    # Пользователь спамит
                    if update.callback_query:
                        await update.callback_query.answer(
                            "⏳ Подождите немного...", 
                            show_alert=False
                        )
                    return
            
            # Обновляем время последнего действия
            user_cooldowns[user_id] = now
            return await func(update, context)
        return wrapper
    return decorator

# Helper functions for wallet-specific data
def get_wallet_key(context, key_name):
    """Get wallet-specific key name"""
    wallet_num = context.user_data.get('active_wallet', 1)
    return f"{key_name}_w{wallet_num}"

def get_wallet_data(context, key_name, default=None):
    """Get wallet-specific data"""
    wallet_key = get_wallet_key(context, key_name)
    return context.user_data.get(wallet_key, default)

def set_wallet_data(context, key_name, value):
    """Set wallet-specific data"""
    wallet_key = get_wallet_key(context, key_name)
    context.user_data[wallet_key] = value

# Error recovery helper
async def send_error_with_retry(query, error_msg, retry_callback=None):
    """Отправить ошибку с кнопкой retry"""
    keyboard = []
    if retry_callback:
        keyboard.append([InlineKeyboardButton("🔄 Попробовать снова", callback_data=retry_callback)])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data='back')])
    
    await query.edit_message_text(
        f"❌ {error_msg}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Global dashboard instance
dashboard = None

# History manager
history_manager = None

# TP/SL calculator
calc = None

# Active auto-traders
# Active traders - теперь по кошелькам!
active_traders = {
    1: {'grid': None, 'ml': None},  # Wallet 1
    2: {'grid': None, 'ml': None}   # Wallet 2
}

def get_current_traders():
    """Получить traders для текущего кошелька"""
    wallet_num = dashboard.active_wallet if hasattr(dashboard, 'active_wallet') else 1
    return active_traders[wallet_num]

def set_current_trader(trader_type, trader_obj):
    """Установить trader для текущего кошелька"""
    wallet_num = dashboard.active_wallet if hasattr(dashboard, 'active_wallet') else 1
    active_traders[wallet_num][trader_type] = trader_obj

# Auto-traders status file
TRADERS_STATUS_FILE = os.path.join(os.path.dirname(__file__), "traders_status.json")

# User data file
USER_DATA_FILE = os.path.join(os.path.dirname(__file__), "user_data.json")

def load_user_data(user_id):
    """Load user's subaccount from file"""
    try:
        with open(USER_DATA_FILE, 'r') as f:
            data = json.load(f)
            return data.get(str(user_id))
    except FileNotFoundError:
        return None

def save_user_data(user_id, data):
    """Save user's subaccount to file"""
    try:
        with open(USER_DATA_FILE, 'r') as f:
            all_data = json.load(f)
    except FileNotFoundError:
        all_data = {}
    
    all_data[str(user_id)] = data
    
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(all_data, f, indent=2)

def save_traders_status():
    """Save traders status to file (multi-wallet)"""
    status = {}
    for wallet_num in [1, 2]:
        traders = active_traders[wallet_num]
        status[f'wallet_{wallet_num}'] = {
            'grid': traders['grid'] is not None and traders['grid'].running if traders['grid'] else False,
            'ml': traders['ml'] is not None and traders['ml'].running if traders['ml'] else False
        }
    with open(TRADERS_STATUS_FILE, 'w') as f:
        json.dump(status, f)

def load_traders_status():
    """Load traders status from file (multi-wallet)"""
    try:
        if os.path.exists(TRADERS_STATUS_FILE):
            with open(TRADERS_STATUS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except:
        return {}

# Conversation states
WAITING_WALLET, WAITING_PRODUCT, WAITING_SIZE, WAITING_LEVERAGE = range(4)
WAITING_GRID_WALLET, WAITING_GRID_PRODUCT, WAITING_GRID_MODE, WAITING_GRID_SIZE, WAITING_GRID_OFFSET = range(4, 9)
WAITING_AUTO_WALLET, WAITING_AUTO_PRODUCT, WAITING_AUTO_SIZE, WAITING_AUTO_TP_SL, WAITING_AUTO_GRID_OFFSET = range(9, 14)
WAITING_ML_WALLET, WAITING_ML_PRODUCT, WAITING_ML_SIZE, WAITING_AUTO_ML_CONFIDENCE, WAITING_ML_TP_SL = range(14, 19)
WAITING_TPSL_PRODUCT = 19  # Separate state for calculator
WAITING_TP_MODE, WAITING_TP_PRICE, WAITING_TP_PERCENT = range(20, 23)
WAITING_SL_MODE, WAITING_SL_PRICE, WAITING_SL_PERCENT = range(23, 26)  # For TP setup

# Temporary user data storage
user_data_storage = {}

# Allowed users - ПУСТОЙ список = доступ для ВСЕХ
ALLOWED_USERS = []

# Убрана логика субаккаунтов - подключение через NADO_PRIVATE_KEY из .env

def check_access(update: Update) -> bool:
    """Check user access"""
    if not ALLOWED_USERS:
        return True
    user_id = update.effective_user.id
    return user_id in ALLOWED_USERS


def get_main_keyboard():
    """Main menu with auto-grid control buttons"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 LONG", callback_data='open_long'),
            InlineKeyboardButton("🔴 SHORT", callback_data='open_short')
        ],
        [
            InlineKeyboardButton("📊 Positions", callback_data='positions'),
            InlineKeyboardButton("💰 Balance", callback_data='balance')
        ],
        [
            InlineKeyboardButton("📈 Prices", callback_data='prices'),
            InlineKeyboardButton("📜 History", callback_data='history')
        ],
        [
            InlineKeyboardButton("👛 Wallets", callback_data='wallets_menu')
        ],
        [
            InlineKeyboardButton("📈📉 Grid Strategy", callback_data='grid_strategy')
        ],
    ]
    
    # Добавляем кнопки управления автогридами для каждого кошелька
    grid_row = []
    
    # Wallet 1 Auto Grid
    w1_traders = active_traders[1]
    if w1_traders['grid'] and w1_traders['grid'].running:
        grid_row.append(InlineKeyboardButton("🛑 Grid W1", callback_data='stop_grid_w1'))
    else:
        grid_row.append(InlineKeyboardButton("▶️ Grid W1", callback_data='start_grid_w1'))
    
    # Wallet 2 Auto Grid
    w2_traders = active_traders[2]
    if w2_traders['grid'] and w2_traders['grid'].running:
        grid_row.append(InlineKeyboardButton("🛑 Grid W2", callback_data='stop_grid_w2'))
    else:
        grid_row.append(InlineKeyboardButton("▶️ Grid W2", callback_data='start_grid_w2'))
    
    keyboard.append(grid_row)
    
    # Старые кнопки Auto Grid / ML Auto для запуска через меню
    keyboard.extend([
        [
            InlineKeyboardButton("🤖 Auto Grid", callback_data='auto_grid'),
            InlineKeyboardButton("🧠 ML Auto", callback_data='auto_ml')
        ],
        [
            InlineKeyboardButton("🎯 TP/SL Calculator", callback_data='tpsl_calc')
        ],
        [
            InlineKeyboardButton("⚙️ Leverage", callback_data='leverage_settings'),
            InlineKeyboardButton("🔄 Refresh", callback_data='refresh')
        ]
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_products_keyboard():
    """Pair selection keyboard"""
    keyboard = []
    for product_id, symbol in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(symbol, callback_data=f'product_{product_id}')])
    keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
    return InlineKeyboardMarkup(keyboard)


def get_wallet_keyboard():
    """Клавиатура выбора кошелька"""
    # Показываем какой кошелек активен
    active = dashboard.active_wallet if dashboard else 1
    
    keyboard = []
    for wallet_num in sorted(dashboard.wallets.keys()) if dashboard else [1]:
        emoji = "✅" if wallet_num == active else "👛"
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} Wallet {wallet_num}", 
                callback_data=f'switch_wallet_{wallet_num}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command"""
    if not check_access(update):
        if update.message:
            await update.message.reply_text("❌ You don't have access to this bot")
        return
    
    user_id = update.effective_user.id
    
    # Создаём dashboard (Multi-Wallet Support)
    global dashboard, calc, history_manager
    
    # ВСЕГДА пересоздаем dashboard
    logger.info(f"🔗 Creating multi-wallet dashboard for user {user_id}")
    dashboard = MultiWalletDashboard(leverage=10)
    
    # ✅ СОХРАНЯЕМ dashboard в context сразу после создания!
    context.user_data['dashboard'] = dashboard.get_current_dashboard()
    
    # Инициализируем history manager если ещё не создан
    if history_manager is None:
        history_manager = TradeHistoryManager(f'trade_history_{user_id}.json')
    
    if calc is None:
        calc = TPSLCalculator(leverage=dashboard.leverage)
    
    # Load traders status (ВСЕГДА обновляем при заходе в главное меню)
    traders_status = load_traders_status()
    
    # Получаем traders для текущего кошелька
    current_traders = get_current_traders()
    
    # Проверяем реальный статус running из active_traders
    grid_running = current_traders.get('grid') and current_traders['grid'].running
    ml_running = current_traders.get('ml') and current_traders['ml'].running
    
    grid_status = "🟢 Active" if grid_running else "⚪ Off"
    ml_status = "🟢 Active" if ml_running else "⚪ Off"
    
    ml_prediction_text = ""
    if current_traders['ml'] and current_traders['ml'].running:
        pred = current_traders['ml'].last_prediction
        direction = pred.get('direction', 'unknown').upper()
        confidence = pred.get('confidence', 0)
        
        if direction != 'UNKNOWN' and confidence > 0:
            emoji = "🟢" if direction == "UP" else "🔴" if direction == "DOWN" else "⏸️"
            ml_prediction_text = f"\n   └ Prediction: {emoji} {direction} ({confidence:.0%})"
    
    welcome_text = (
        f"🤖 <b>NADO DEX Trading Bot</b>\n\n"
        f"🌐 Network: <code>{dashboard.network.upper()}</code>\n"
        f"👛 Wallet: <code>{dashboard.wallet[:10]}...{dashboard.wallet[-8:]}</code>\n"
        f"⚡ Leverage: <code>{dashboard.leverage}x</code>\n\n"
        f"🤖 Auto Grid: {grid_status}\n"
        f"🧠 ML Auto: {ml_status}{ml_prediction_text}\n\n"
        f"Выберите действие:"
    )
    
    if update.message:
        await update.message.reply_text(
            welcome_text,
            reply_markup=get_main_keyboard(),
            parse_mode='HTML'
        )
    else:
        await update.callback_query.message.edit_text(
            welcome_text,
            reply_markup=get_main_keyboard(),
            parse_mode='HTML'
        )


async def refresh_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh status"""
    query = update.callback_query
    await query.answer()
    
    balance = dashboard.get_balance()
    positions = dashboard.get_positions()
    
    # Get current traders
    current_traders = get_current_traders()
    
    # Get ML prediction if ML Auto is running
    ml_prediction_text = ""
    if current_traders['ml'] and current_traders['ml'].running:
        pred = current_traders['ml'].last_prediction
        direction = pred.get('direction', 'unknown').upper()
        confidence = pred.get('confidence', 0)
        
        if direction != 'UNKNOWN' and confidence > 0:
            emoji = "🟢" if direction == "UP" else "🔴" if direction == "DOWN" else "⏸️"
            ml_prediction_text = f"\n🧠 ML Prediction: {emoji} {direction} ({confidence:.0%})\n"
    
    status_text = (
        "📊 <b>STATUS</b>\n\n"
        f"🌐 Network: <b>{dashboard.network.upper()}</b>\n"
        f"⚙️ Leverage: <b>{dashboard.leverage}x</b>\n"
    )
    
    status_text += ml_prediction_text
    
    if balance:
        status_text += (
            f"\n💰 <b>Balance:</b>\n"
            f"  Equity: ${balance['equity']:,.2f}\n"
            f"  Health: {balance['health']:,.2f}\n\n"
        )
    
    if positions:
        status_text += f"📊 <b>Open positions:</b> {len(positions)}\n"
    else:
        status_text += "📊 <b>No positions</b>\n"
    
    await query.edit_message_text(
        status_text,
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )


async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance"""
    query = update.callback_query
    await query.answer()
    
    balance = dashboard.get_balance()
    
    if not balance:
        await query.edit_message_text(
            "❌ Failed to get balance",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
        return
    
    text = (
        "💰 <b>ACCOUNT BALANCE</b>\n\n"
        f"Assets: <b>${balance['assets']:,.2f}</b>\n"
        f"Liabilities: <b>${balance['liabilities']:,.2f}</b>\n"
        f"Equity: <b>${balance['equity']:,.2f}</b>\n"
        f"Health: <b>{balance['health']:,.2f}</b>\n"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
    )


async def show_wallets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню управления кошельками"""
    query = update.callback_query
    await query.answer()
    
    # Получаем информацию о всех кошельках
    all_balances = dashboard.get_all_balances()
    active_wallet = dashboard.active_wallet
    
    text = "👛 <b>WALLETS</b>\n\n"
    
    for wallet_num in sorted(all_balances.keys()):
        wallet_data = all_balances[wallet_num]
        is_active = "✅ " if wallet_num == active_wallet else ""
        
        if wallet_data and wallet_data['balance']:
            balance = wallet_data['balance']
            address = wallet_data['address']
            text += (
                f"{is_active}<b>Wallet {wallet_num}</b>\n"
                f"  Address: <code>{address[:10]}...{address[-8:]}</code>\n"
                f"  Equity: <b>${balance['equity']:,.2f}</b>\n"
                f"  Health: <b>{balance['health']:,.2f}</b>\n\n"
            )
        else:
            text += f"<b>Wallet {wallet_num}</b>: ❌ Error\n\n"
    
    text += "\nВыберите кошелек для переключения:"
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_wallet_keyboard()
    )


async def switch_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключить активный кошелек"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем номер кошелька и возвратную страницу из callback_data
    parts = query.data.split('_')
    wallet_num = int(parts[2])
    return_to = parts[3] if len(parts) > 3 else None
    
    try:
        dashboard.switch_wallet(wallet_num)
        
        # Если нужно вернуться на страницу позиций
        if return_to == 'positions':
            await show_positions(update, context)
            return
        
        # Иначе показываем подтверждение
        balance = dashboard.get_balance()
        text = (
            f"✅ <b>Переключено на Wallet {wallet_num}</b>\n\n"
            f"👛 Address: <code>{dashboard.get_current_dashboard().wallet}</code>\n"
        )
        
        if balance:
            text += (
                f"\n💰 <b>Balance:</b>\n"
                f"  Equity: ${balance['equity']:,.2f}\n"
                f"  Health: {balance['health']:,.2f}\n"
            )
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='wallets_menu')]])
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Ошибка переключения кошелька: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='wallets_menu')]])
        )


async def show_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show prices"""
    query = update.callback_query
    await query.answer()
    
    text = "📈 <b>CURRENT PRICES</b>\n\n"
    
    for product_id, symbol in PRODUCTS.items():
        price = dashboard.get_market_price(product_id)
        if price:
            text += f"{symbol}: <b>${price:,.2f}</b>\n"
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
    )


async def show_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенное отображение позиций с entry, current, P&L и Set TP"""
    query = update.callback_query
    await query.answer()
    
    positions = dashboard.get_positions()
    
    # Кнопки управления (всегда доступны)
    base_keyboard = []
    
    if not positions:
        text = "📊 <b>ПОЗИЦИИ</b>\n\n✅ Нет открытых позиций"
        # Добавляем кнопку отмены ордеров для каждого продукта
        for pid, symbol in PRODUCTS.items():
            base_keyboard.append([
                InlineKeyboardButton(
                    f"🚫 Отменить {symbol}",
                    callback_data=f'cancel_orders_{pid}'
                )
            ])
        base_keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data='positions')])
        base_keyboard.append([InlineKeyboardButton("« Назад", callback_data='back')])
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(base_keyboard)
        )
        return
    
    # Определяем активный кошелек
    if hasattr(dashboard, 'active_wallet'):
        wallet_info = f"👛 Wallet {dashboard.active_wallet}: <code>{dashboard.wallet[:10]}...{dashboard.wallet[-8:]}</code>\n\n"
    else:
        wallet_info = f"👛 <code>{dashboard.wallet[:10]}...{dashboard.wallet[-8:]}</code>\n\n"
    
    text = "📊 <b>ОТКРЫТЫЕ ПОЗИЦИИ</b>\n\n" + wallet_info
    keyboard = []
    
    for i, pos in enumerate(positions, 1):
        side_emoji = "🟢" if pos["side"] == "LONG" else "🔴"
        product_id = pos['product_id']
        current_price = pos['price']
        symbol = pos['symbol']
        amount = abs(pos['amount'])
        
        # Получаем entry price из сохраненных данных
        entry_data = dashboard.entry_prices.get(str(product_id))  # Ключ - строка!
        
        if entry_data:
            entry_price = entry_data['entry_price']
            tp_price = entry_data.get('tp_price')
            sl_price = entry_data.get('sl_price')
        else:
            entry_price = current_price
            tp_price = None
            sl_price = None
        
        # Рассчитываем P&L правильно
        # P&L = (current - entry) * amount для LONG
        # P&L = (entry - current) * amount для SHORT
        if pos['side'] == 'LONG':
            raw_pnl = (current_price - entry_price) * amount
        else:
            raw_pnl = (entry_price - current_price) * amount
        
        # Процент от вложенного капитала (entry * amount)
        invested = entry_price * amount
        pnl_percent = (raw_pnl / invested * 100) if invested > 0 else 0
        
        pnl_emoji = "🟢" if raw_pnl >= 0 else "🔴"
        pnl_str = f"{pnl_emoji} ${raw_pnl:+,.2f} ({pnl_percent:+.2f}%)"
        
        # Формируем детальный текст позиции
        pos_text = (
            f"{side_emoji} <b>{symbol}</b>\n"
            f"├ Размер: {amount:.4f}\n"
            f"├ Вход: ${entry_price:,.2f}\n"
            f"├ Сейчас: ${current_price:,.2f}\n"
            f"├ Объем: ${pos['notional']:,.2f}\n"
            f"└ P&L: {pnl_str}\n"
        )
        
        # Добавляем TP/SL если установлены
        if tp_price:
            pos_text += f"   🎯 TP: ${tp_price:,.2f}\n"
        if sl_price:
            pos_text += f"   🛑 SL: ${sl_price:,.2f}\n"
        
        text += pos_text + "\n"
        
        # Кнопки управления позицией
        keyboard.append([
            InlineKeyboardButton(
                f"🎯 TP {symbol}",
                callback_data=f'set_tp_{product_id}'
            ),
            InlineKeyboardButton(
                f"🛑 SL {symbol}",
                callback_data=f'set_sl_{product_id}'
            )
        ])
        keyboard.append([
            InlineKeyboardButton(
                f"🚫 Отменить {symbol}",
                callback_data=f'cancel_orders_{product_id}'
            ),
            InlineKeyboardButton(
                f"❌ Закрыть {symbol}",
                callback_data=f'close_{product_id}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data='positions')])
    
    # Добавляем кнопки переключения кошельков
    if hasattr(dashboard, 'active_wallet'):
        wallet_buttons = []
        for wallet_num in dashboard.wallets.keys():
            is_active = wallet_num == dashboard.active_wallet
            label = f"✅ Wallet {wallet_num}" if is_active else f"👛 Wallet {wallet_num}"
            wallet_buttons.append(
                InlineKeyboardButton(label, callback_data=f'switch_wallet_{wallet_num}_positions')
            )
        if len(wallet_buttons) > 0:
            keyboard.append(wallet_buttons)
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data='back')])
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show history menu"""
    await show_history_menu(update, context, history_manager)


@rate_limit(seconds=2)
async def select_wallet_for_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор кошелька для открытия позиции"""
    query = update.callback_query
    await query.answer()
    
    is_long = query.data == 'open_long'
    context.user_data['is_long'] = is_long
    
    direction = "LONG 🟢" if is_long else "SHORT 🔴"
    
    text = (
        f"<b>{direction}</b>\n\n"
        "Select wallet:"
    )
    
    try:
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=get_wallet_keyboard()
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=get_wallet_keyboard()
        )
    
    return WAITING_WALLET


async def wallet_selected_for_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора кошелька для позиции"""
    query = update.callback_query
    await query.answer()
    
    wallet_num = int(query.data.split('_')[2])
    context.user_data['wallet_num'] = wallet_num
    
    # Переключаемся на выбранный кошелек
    global dashboard
    dashboard.switch_wallet(wallet_num)
    
    # ✅ СОХРАНЯЕМ dashboard в context!
    context.user_data['dashboard'] = dashboard.get_current_dashboard()
    
    is_long = context.user_data.get('is_long', True)
    direction = "LONG 🟢" if is_long else "SHORT 🔴"
    
    current_dashboard = context.user_data['dashboard']
    
    text = (
        f"<b>{direction}</b>\n\n"
        f"👛 Wallet {wallet_num}: <code>{current_dashboard.wallet[:10]}...{current_dashboard.wallet[-8:]}</code>\n"
        f"⚙️ Leverage: <b>{current_dashboard.leverage}x</b>\n\n"
        "Select pair:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_products_keyboard()
    )
    
    return WAITING_PRODUCT


async def open_position_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Position opening menu"""
    query = update.callback_query
    await query.answer()
    
    is_long = query.data == 'open_long'
    context.user_data['is_long'] = is_long
    
    # Получаем глобальный dashboard для отображения leverage
    global dashboard
    
    direction = "LONG 🟢" if is_long else "SHORT 🔴"
    
    text = (
        f"<b>{direction}</b>\n\n"
        f"⚙️ Leverage: <b>{dashboard.get_current_dashboard().leverage}x</b>\n\n"
        "Select pair:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_products_keyboard()
    )
    
    return WAITING_PRODUCT


async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pair selection"""
    query = update.callback_query
    await query.answer()
    
    # Получаем dashboard
    if 'dashboard' in context.user_data:
        dashboard = context.user_data['dashboard']
    else:
        await query.edit_message_text("❌ Dashboard not initialized")
        return ConversationHandler.END
    
    product_id = int(query.data.split('_')[1])
    context.user_data['product_id'] = product_id
    
    symbol = PRODUCTS[product_id]
    price = dashboard.get_market_price(product_id)
    is_long = context.user_data.get('is_long', True)
    
    direction = "LONG 🟢" if is_long else "SHORT 🔴"
    
    text = (
        f"<b>{direction} {symbol}</b>\n\n"
        f"💰 Current price: <b>${price:,.2f}</b>\n"
        f"⚙️ Leverage: <b>{dashboard.leverage}x</b>\n\n"
        f"💡 При открытии автоматически разместится\n"
        f"   take-profit ордер (+0.03%)\n\n"
        "Enter base size:"
    )
    
    await query.edit_message_text(text, parse_mode='HTML')
    
    return WAITING_SIZE


async def handle_size_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Size input handling"""
    try:
        logger.info("📍 handle_size_input START")
        
        # Получаем dashboard
        if 'dashboard' in context.user_data:
            dashboard = context.user_data['dashboard']
            logger.info(f"✅ Dashboard found: {dashboard}")
        else:
            logger.error("❌ Dashboard NOT in context!")
            await update.message.reply_text("❌ Dashboard not initialized")
            return ConversationHandler.END
        
        # Поддержка и обычных сообщений, и callback query
        if update.message:
            size_text = update.message.text
            message = update.message
            logger.info(f"📝 Got message: {size_text}")
        elif update.callback_query:
            size_text = update.callback_query.data
            message = update.callback_query.message
            await update.callback_query.answer()
            logger.info(f"📝 Got callback: {size_text}")
        else:
            logger.error("❌ No message or callback!")
            return WAITING_SIZE
        
        logger.info("📍 Parsing size...")
        size = Decimal(size_text)
        if size <= 0:
            raise ValueError
        
        logger.info("📍 Getting product_id...")
        product_id = context.user_data['product_id']
        is_long = context.user_data['is_long']
        symbol = PRODUCTS[product_id]
        
        logger.info("📍 Getting balance...")
        # ❌ ВОТ ТУТ ПАДАЕТ!
        balance = dashboard.get_balance()
        logger.info(f"✅ Balance: {balance}")
        
        equity = Decimal(str(balance.get('equity', 0)))
        max_size = equity / 5  # Макс 20% депозита
        
        if size > max_size:
            reply_text = (
                f"⚠️ Размер слишком большой!\n\n"
                f"💰 Ваш баланс: ${equity:,.2f}\n"
                f"📊 Макс размер (20%): {max_size:.4f}\n\n"
                f"Введите размер заново:"
            )
            if update.message:
                await message.reply_text(reply_text, parse_mode='HTML')
            else:
                await message.edit_text(reply_text, parse_mode='HTML')
            return WAITING_SIZE
        
        size = dashboard.normalize_size(product_id, size)
        
        if size <= 0:
            error_text = "❌ Size below minimum шага"
            if update.message:
                await message.reply_text(error_text)
            else:
                await message.edit_text(error_text)
            return WAITING_SIZE
        
        # Получаем цену
        price = dashboard.get_market_price(product_id)
        size_with_leverage = size * dashboard.leverage
        notional = size_with_leverage * Decimal(str(price))
        
        # Расчет комиссий
        fee_rate = Decimal("0.0001")
        open_fee = notional * fee_rate
        close_fee = notional * fee_rate
        total_fee = open_fee + close_fee
        
        # РИСК КАЛЬКУЛЯТОР
        # Ликвидация при движении 1/leverage (например, 10% для 10x)
        liq_percent = 100 / float(dashboard.leverage)
        if is_long:
            liq_price = price * (1 - liq_percent / 100)
        else:
            liq_price = price * (1 + liq_percent / 100)
        
        # Risk/Reward с типичным TP 5% и SL 2%
        typical_tp = 5.0
        typical_sl = 2.0
        reward = float(notional) * typical_tp / 100
        risk = float(notional) * typical_sl / 100
        rr_ratio = reward / risk if risk > 0 else 0
        
        direction = "LONG 🟢" if is_long else "SHORT 🔴"
        
        confirm_text = (
            f"<b>Confirmation {direction}</b>\n\n"
            f"📊 {symbol}\n"
            f"💰 Цена: ${price:,.2f}\n"
            f"📦 Base size: {size}\n"
            f"⚡ Leverage: {dashboard.leverage}x\n"
            f"📈 Position size: {size_with_leverage}\n"
            f"💵 Notional: ${notional:,.2f}\n\n"
            f"💰 <b>Fees:</b>\n"
            f"  Opening: ${open_fee:,.4f}\n"
            f"  Closing: ${close_fee:,.4f}\n"
            f"  Total: ${total_fee:,.4f}\n\n"
            f"⚠️ <b>RISK:</b>\n"
            f"  🔻 Ликвидация: ${liq_price:,.2f} ({liq_percent:.1f}%)\n"
            f"  📊 Risk/Reward: 1:{rr_ratio:.1f} (TP {typical_tp}% / SL {typical_sl}%)\n\n"
            "Open position?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f'confirm_order_{size}'),
                InlineKeyboardButton("❌ No", callback_data='back')
            ]
        ]
        
        if update.message:
            await message.reply_text(
                confirm_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await message.edit_text(
                confirm_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return ConversationHandler.END
        
    except Exception as e:
        error_text = f"❌ Error: {e}\n\nВведите размер заново:"
        if update.message:
            await message.reply_text(error_text)
        elif update.callback_query:
            await message.edit_text(error_text)
        return WAITING_SIZE


@rate_limit(seconds=2)
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation и размещение ордера"""
    query = update.callback_query
    await query.answer()
    
    try:
        size = Decimal(query.data.split('_')[2])
        product_id = context.user_data['product_id']
        is_long = context.user_data['is_long']
        symbol = PRODUCTS[product_id]
        
        await query.edit_message_text("🔄 Placing order...")
        
        result = dashboard.place_order(product_id, size, is_long)
        
        if result:
            # ИСПРАВЛЕНИЕ: Сохраняем entry price СРАЗУ после открытия!
            current_price = dashboard.get_market_price(product_id)
            if current_price:
                dashboard.save_entry_price(
                    product_id=product_id,
                    entry_price=current_price,
                    size=float(size)
                )
            
            await query.edit_message_text(
                f"✅ Order placed!\n\n"
                f"{'🟢 LONG' if is_long else '🔴 SHORT'} {symbol}\n"
                f"Size: {size * dashboard.leverage}\n\n"
                f"Take-profit ордер активирован (+0.03%)",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« To menu", callback_data='back')]])
            )
        else:
            await query.edit_message_text(
                "❌ Order placement error",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
            )
    
    except Exception as e:
        logger.error(f"Error in confirm_order: {e}")
        keyboard = [
            [InlineKeyboardButton("🔄 Retry", callback_data=f'confirm_order_{size}')],
            [InlineKeyboardButton("« Cancel", callback_data='back')]
        ]
        await query.edit_message_text(
            f"❌ Ошибка размещения ордера:\n{str(e)}\n\nПопробовать еще раз?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


@rate_limit(seconds=3)
async def close_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать подтверждение закрытия позиции"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    symbol = PRODUCTS[product_id]
    
    # Получаем данные позиции
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text(
            f"❌ Позиция {symbol} не найдена",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='positions')]])
        )
        return
    
    # Получаем entry price и рассчитываем P&L
    entry_data = dashboard.entry_prices.get(str(product_id))
    entry_price = entry_data['entry_price'] if entry_data else position['price']
    current_price = position['price']
    amount = abs(position['amount'])
    side = position['side']
    
    # Расчет P&L
    if side == 'LONG':
        pnl = (current_price - entry_price) * amount
    else:
        pnl = (entry_price - current_price) * amount
    
    pnl_percent = (pnl / (entry_price * amount) * 100) if entry_price * amount > 0 else 0
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    
    # Подтверждение
    confirm_text = (
        f"⚠️ <b>ЗАКРЫТЬ ПОЗИЦИЮ?</b>\n\n"
        f"📊 {symbol} {side}\n"
        f"💰 Вход: ${entry_price:,.2f}\n"
        f"💰 Сейчас: ${current_price:,.2f}\n"
        f"📏 Размер: {amount:.4f}\n\n"
        f"{pnl_emoji} <b>P&L: ${pnl:+,.2f} ({pnl_percent:+.2f}%)</b>\n\n"
        f"Подтвердите закрытие:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Закрыть", callback_data=f'confirm_close_{product_id}'),
            InlineKeyboardButton("❌ Отмена", callback_data='positions')
        ]
    ]
    
    await query.edit_message_text(
        confirm_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@rate_limit(seconds=2)
async def confirm_close_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение - выполнить закрытие позиции"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[2])
    symbol = PRODUCTS[product_id]
    
    # Получаем данные позиции ДО закрытия
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text(
            f"❌ Позиция {symbol} не найдена",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='positions')]])
        )
        return
    
    # Получаем entry price
    entry_data = dashboard.entry_prices.get(str(product_id))
    entry_price = entry_data['entry_price'] if entry_data else position['price']
    
    # Текущая цена (exit price)
    exit_price = position['price']
    
    # Размер позиции
    position_size = abs(position['amount'])
    base_size = position_size / float(dashboard.leverage)
    
    await query.edit_message_text(f"🔄 Closing position {symbol}...")
    
    result = dashboard.close_position(product_id)
    
    if result:
        # Рассчитываем комиссии
        entry_notional = entry_price * position_size
        exit_notional = exit_price * position_size
        entry_fee = entry_notional * 0.0001
        exit_fee = exit_notional * 0.0001
        
        # Записываем в историю
        history_manager.add_trade(
            symbol=symbol,
            product_id=product_id,
            side=position['side'],
            entry_price=entry_price,
            exit_price=exit_price,
            size=base_size,
            leverage=dashboard.leverage,
            entry_fee=entry_fee,
            exit_fee=exit_fee
        )
        
        await query.edit_message_text(
            f"✅ Позиция {symbol} закрыта!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« To menu", callback_data='back')]])
        )
    else:
        await query.edit_message_text(
            f"❌ Position close error {symbol}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )


async def cancel_orders_for_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить все ордера для продукта"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[2])
    symbol = PRODUCTS[product_id]
    
    await query.edit_message_text(f"🔄 Отмена ордеров {symbol}...")
    
    try:
        from nado_protocol.engine_client.types.execute import CancelProductOrdersParams
        
        params = CancelProductOrdersParams(
            sender=dashboard.sender_hex,  # ИСПРАВЛЕНО: было user_subaccount
            productIds=[product_id]
        )
        
        result = dashboard.client.market.cancel_product_orders(params)
        
        await query.edit_message_text(
            f"✅ Ордера {symbol} отменены!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« К меню", callback_data='back')]])
        )
    except Exception as e:
        await query.edit_message_text(
            f"❌ Ошибка: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='back')]])
        )


async def leverage_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Leverage settings"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "⚙️ <b>НАСТРОЙКА ПЛЕЧА</b>\n\n"
        f"Текущее плечо: <b>{dashboard.leverage}x</b>\n\n"
        "💡 Isolated Margin:\n"
        "  • Каждая позиция имеет свою маржу\n"
        "  • Ликвидация одной не влияет на другие\n\n"
        "⚠️ Риски:\n"
        "  • 10x: движение 10% = 100% P&L\n"
        "  • 20x: движение 5% = 100% P&L\n"
        "  • 50x: движение 2% = 100% P&L\n\n"
        "Enter new leverage (1-100):"
    )
    
    await query.edit_message_text(text, parse_mode='HTML')
    return WAITING_LEVERAGE


async def handle_leverage_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Leverage input handling"""
    try:
        new_leverage = Decimal(update.message.text)
        if new_leverage < 1 or new_leverage > 100:
            raise ValueError
        
        old_leverage = dashboard.leverage
        dashboard.leverage = new_leverage
        
        text = (
            f"✅ <b>Leverage изменено</b>\n\n"
            f"Was: {old_leverage}x\n"
            f"Became: {new_leverage}x"
        )
        
        if new_leverage >= 20:
            text += f"\n\n🚨 <b>WARNING!</b>\nHigh leverage = high risk!"
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« To menu", callback_data='back')]])
        )
        
        return ConversationHandler.END
        
    except:
        await update.message.reply_text("❌ Invalid format. Введите число от 1 до 100:")
        return WAITING_LEVERAGE


async def select_wallet_for_grid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор кошелька для Grid Strategy"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "<b>📈📉 Grid Strategy</b>\n\n"
        "Select wallet:"
    )
    
    try:
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=get_wallet_keyboard()
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=get_wallet_keyboard()
        )
    
    return WAITING_GRID_WALLET


async def wallet_selected_for_grid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора кошелька для grid"""
    query = update.callback_query
    await query.answer()
    
    wallet_num = int(query.data.split('_')[2])
    context.user_data['wallet_num'] = wallet_num
    
    # Переключаемся на выбранный кошелек
    global dashboard
    dashboard.switch_wallet(wallet_num)
    
    text = (
        f"<b>📈📉 Grid Strategy</b>\n\n"
        f"👛 Wallet {wallet_num}: <code>{dashboard.wallet[:10]}...{dashboard.wallet[-8:]}</code>\n\n"
        "Select pair:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_products_keyboard()
    )
    
    return WAITING_GRID_PRODUCT


async def grid_strategy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid strategy menu"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "📈📉 <b>GRID СТРАТЕГИЯ</b>\n\n"
        "💡 Размещаются 2 ордера:\n"
        "  • 🟢 LONG ниже текущей цены\n"
        "  • 🔴 SHORT выше текущей цены\n\n"
        "При исполнении одного - автоматический TP\n\n"
        "Select pair:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_products_keyboard()
    )
    
    return WAITING_GRID_PRODUCT


async def grid_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pair selection for Grid"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    set_wallet_data(context, 'grid_product_id', product_id)
    
    symbol = PRODUCTS[product_id]
    price = dashboard.get_market_price(product_id)
    
    # Проверяем текущие позиции
    positions = dashboard.get_positions()
    current_pos = next((p for p in positions if p['product_id'] == product_id), None)
    
    if current_pos:
        # Есть открытая позиция
        pos_side = "LONG" if current_pos['amount'] > 0 else "SHORT"
        pos_size = abs(current_pos['amount'])
        
        text = (
            f"⚠️ <b>WARNING!</b>\n\n"
            f"У вас уже открыта {pos_side} позиция:\n"
            f"📊 {symbol}: {pos_size}\n\n"
            f"<b>Режимы Grid:</b>\n\n"
            f"1️⃣ <b>Адаптивный Grid</b> (рекомендуется)\n"
            f"   {'🟢 LONG ордер ниже' if pos_side == 'SHORT' else '🔴 SHORT ордер выше'}\n"
            f"   (противоположное направление)\n\n"
            f"2️⃣ <b>Стандартный Grid</b>\n"
            f"   🟢 LONG + 🔴 SHORT (оба ордера)\n"
            f"   ⚠️ Может увеличить позицию!\n\n"
            f"Выберите режим:"
        )
        
        keyboard = [
            [InlineKeyboardButton("1️⃣ Адаптивный (безопасно)", callback_data=f'grid_mode_adaptive_{product_id}')],
            [InlineKeyboardButton("2️⃣ Стандартный (риск)", callback_data=f'grid_mode_standard_{product_id}')],
            [InlineKeyboardButton("« Back", callback_data='back')]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Ждем выбор режима
        return WAITING_GRID_MODE
    else:
        # No позиций - standardный Grid
        text = (
            f"📈📉 <b>GRID: {symbol}</b>\n\n"
            f"💰 Current price: <b>${price:,.2f}</b>\n\n"
            f"✅ No positions - используем standardный Grid\n\n"
            "Enter base size:"
        )
        
        set_wallet_data(context, 'grid_mode', 'standard')
        await query.edit_message_text(text, parse_mode='HTML')
        return WAITING_GRID_SIZE


async def handle_grid_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid size handling"""
    try:
        size = Decimal(update.message.text)
        if size <= 0:
            raise ValueError
        
        product_id = get_wallet_data(context, 'grid_product_id')
        size = dashboard.normalize_size(product_id, size)
        
        if size <= 0:
            await update.message.reply_text("❌ Size below minimum")
            return WAITING_GRID_SIZE
        
        set_wallet_data(context, 'grid_size', size)
        
        await update.message.reply_text(
            "Введите процент отклонения\n(например, 0.5 for ±0.5%):"
        )
        
        return WAITING_GRID_OFFSET
        
    except:
        await update.message.reply_text("❌ Invalid format. Введите размер:")
        return WAITING_GRID_SIZE


async def handle_grid_offset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid offset handling"""
    try:
        offset_percent = Decimal(update.message.text) / 100
        if offset_percent <= 0 or offset_percent > 5:
            raise ValueError
        
        product_id = get_wallet_data(context, 'grid_product_id')
        size = get_wallet_data(context, 'grid_size')
        symbol = PRODUCTS[product_id]
        
        price = dashboard.get_market_price(product_id)
        price_decimal = Decimal(str(price))
        
        long_price = price_decimal * (Decimal("1") - offset_percent)
        short_price = price_decimal * (Decimal("1") + offset_percent)
        
        size_with_leverage = size * dashboard.leverage
        
        text = (
            f"<b>Confirmation GRID</b>\n\n"
            f"📊 {symbol}\n"
            f"💰 Current price: ${price:,.2f}\n"
            f"📦 Base size: {size}\n"
            f"⚡ Leverage: {dashboard.leverage}x\n"
            f"📈 Position size: {size_with_leverage}\n\n"
            f"🟢 LONG: ${long_price:,.2f} ({-offset_percent*100:.2f}%)\n"
            f"🔴 SHORT: ${short_price:,.2f} (+{offset_percent*100:.2f}%)\n\n"
            "Разместить оба ордера?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f'confirm_grid'),
                InlineKeyboardButton("❌ No", callback_data='back')
            ]
        ]
        
        set_wallet_data(context, 'grid_long_price', float(long_price))
        set_wallet_data(context, 'grid_short_price', float(short_price))
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ConversationHandler.END
        
    except:
        await update.message.reply_text("❌ Invalid format. Введите процент (0-5):")
        return WAITING_GRID_OFFSET


async def confirm_grid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation Grid стратегии"""
    query = update.callback_query
    await query.answer()
    
    product_id = get_wallet_data(context, 'grid_product_id')
    size = get_wallet_data(context, 'grid_size')
    long_price = get_wallet_data(context, 'grid_long_price')
    short_price = get_wallet_data(context, 'grid_short_price')
    mode = get_wallet_data(context, 'grid_mode', 'standard')
    symbol = PRODUCTS[product_id]
    
    await query.edit_message_text("🔄 Placing Grid orders...")
    
    size_with_leverage = size * dashboard.leverage
    
    # Адаптивный режим - проверяем текущую позицию
    if mode == 'adaptive':
        positions = dashboard.get_positions()
        current_pos = next((p for p in positions if p['product_id'] == product_id), None)
        
        if current_pos:
            is_long_pos = current_pos['amount'] > 0
            
            if is_long_pos:
                # LONG позиция - размещаем только SHORT выше
                result = dashboard.place_order(product_id, size, is_long=False, custom_price=short_price)
                
                if result:
                    await query.edit_message_text(
                        f"✅ <b>Adaptive Grid active!</b>\n\n"
                        f"📊 {symbol}\n"
                        f"🟢 У вас LONG позиция\n"
                        f"🔴 SHORT ордер: {size_with_leverage} @ ${short_price:,.2f}\n\n"
                        f"💡 Order waiting for execution",
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« To menu", callback_data='back')]])
                    )
                else:
                    await query.edit_message_text(
                        "❌ Error размещения SHORT ордера",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
                    )
                return
            else:
                # SHORT позиция - размещаем только LONG ниже
                result = dashboard.place_order(product_id, size, is_long=True, custom_price=long_price)
                
                if result:
                    await query.edit_message_text(
                        f"✅ <b>Adaptive Grid active!</b>\n\n"
                        f"📊 {symbol}\n"
                        f"🔴 У вас SHORT позиция\n"
                        f"🟢 LONG ордер: {size_with_leverage} @ ${long_price:,.2f}\n\n"
                        f"💡 Order waiting for execution",
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« To menu", callback_data='back')]])
                    )
                else:
                    await query.edit_message_text(
                        "❌ Error размещения LONG ордера",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
                    )
                return
    
    # Стандартный режим - оба ордера
    # Размещаем LONG
    long_result = dashboard.place_order(product_id, size, is_long=True, custom_price=long_price)
    
    if not long_result:
        await query.edit_message_text(
            "❌ Error размещения LONG ордера",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
        return
    
    # Размещаем SHORT
    short_result = dashboard.place_order(product_id, size, is_long=False, custom_price=short_price)
    
    if not short_result:
        await query.edit_message_text(
            "⚠️ LONG размещен, но SHORT не удалось",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
        return
    
    size_with_leverage = size * dashboard.leverage
    
    await query.edit_message_text(
        f"✅ <b>Grid Strategy активна!</b>\n\n"
        f"📊 {symbol}\n"
        f"🟢 LONG: {size_with_leverage} @ ${long_price:,.2f}\n"
        f"🔴 SHORT: {size_with_leverage} @ ${short_price:,.2f}\n\n"
        f"💡 Orders waiting for execution",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« To menu", callback_data='back')]])
    )


async def grid_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid mode selection handling"""
    query = update.callback_query
    await query.answer()
    
    # Парсим callback data: grid_mode_adaptive_8 или grid_mode_standard_8
    parts = query.data.split('_')
    mode = parts[2]  # adaptive или standard
    product_id = int(parts[3])
    
    set_wallet_data(context, 'grid_mode', mode)
    set_wallet_data(context, 'grid_product_id', product_id)
    
    symbol = PRODUCTS[product_id]
    price = dashboard.get_market_price(product_id)
    
    mode_text = "Адаптивный" if mode == "adaptive" else "Стандартный"
    
    text = (
        f"📈📉 <b>GRID: {symbol}</b>\n\n"
        f"💰 Current price: <b>${price:,.2f}</b>\n"
        f"🎯 Режим: <b>{mode_text}</b>\n\n"
        "Enter base size:"
    )
    
    await query.edit_message_text(text, parse_mode='HTML')
    return WAITING_GRID_SIZE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel"""
    await update.message.reply_text("❌ Cancelled")
    return ConversationHandler.END


# ============ TP/SL КАЛЬКУЛЯТОР ============

async def tpsl_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """TP/SL Calculator"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "🎯 <b>TP/SL КАЛЬКУЛЯТОР</b>\n\n"
        "Посмотрите сценарии прибыли/убытка\n"
        "for разных настроек TP/SL\n\n"
        "Select pair:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_products_keyboard()
    )
    
    return WAITING_TPSL_PRODUCT  # Separate state for calculator


# ============ GRID AUTO-TRADER ============

async def select_wallet_for_auto_grid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор кошелька для Auto Grid"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "<b>🤖 AUTO GRID TRADER</b>\n\n"
        "Select wallet:"
    )
    
    # Удаляем старое сообщение и отправляем новое
    try:
        await query.message.delete()
    except:
        pass
    
    await query.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=get_wallet_keyboard()
    )
    
    return WAITING_AUTO_WALLET


async def wallet_selected_for_auto_grid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора кошелька для auto grid"""
    query = update.callback_query
    await query.answer()
    
    wallet_num = int(query.data.split('_')[2])
    context.user_data['wallet_num'] = wallet_num
    
    # Переключаемся на выбранный кошелек
    global dashboard
    dashboard.switch_wallet(wallet_num)
    
    text = (
        f"<b>🤖 AUTO GRID TRADER</b>\n\n"
        f"👛 Wallet {wallet_num}: <code>{dashboard.wallet[:10]}...{dashboard.wallet[-8:]}</code>\n\n"
        "Select pair:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_products_keyboard()
    )
    
    return WAITING_AUTO_PRODUCT


async def auto_grid_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid Auto-Trader menu"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем статус для текущего кошелька
    current_traders = get_current_traders()
    is_running = current_traders['grid'] and current_traders['grid'].running
    
    if is_running:
        trader = current_traders['grid']
        product = PRODUCTS[trader.product_id]
        
        text = (
            "🤖 <b>GRID AUTO-TRADER</b>\n\n"
            f"Status: 🟢 <b>ACTIVE</b>\n\n"
            f"📊 Pair: <b>{product}</b>\n"
            f"💰 Size: <b>{trader.base_size}</b>\n"
            f"📏 Grid offset: <b>{trader.grid_offset}%</b>\n"
            "Бот автоматически:\n"
            "• Размещает Grid сетку\n"
            "• Мониторит позиции\n"
            "• Закрывает по TP/SL\n"
            "• Открывает новую Grid\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("🛑 Stop", callback_data='stop_grid')],
            [InlineKeyboardButton("« Back", callback_data='back')]
        ]
    else:
        text = (
            "🤖 <b>GRID AUTO-TRADER</b>\n\n"
            "Status: ⚪ <b>OFF</b>\n\n"
            "Grid Strategy с автоматическим TP/SL:\n"
            "• Размещает LONG и SHORT ордера\n"
            "• Автоматическое закрытие по TP/SL\n"
            "• Бесконечный цикл торговли\n\n"
            "Select pair for запуска:"
        )
        
        keyboard = get_products_keyboard().inline_keyboard
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_AUTO_PRODUCT if not is_running else ConversationHandler.END


async def auto_grid_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pair selection for Grid Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    set_wallet_data(context, 'auto_grid_product', product_id)
    
    symbol = PRODUCTS[product_id]
    price = dashboard.get_market_price(product_id)
    
    text = (
        f"🤖 <b>GRID AUTO: {symbol}</b>\n\n"
        f"💰 Цена: <b>${price:,.2f}</b>\n\n"
        "Enter base size позиции:"
    )
    
    await query.edit_message_text(text, parse_mode='HTML')
    return WAITING_AUTO_SIZE


async def auto_grid_handle_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid size handling Auto"""
    try:
        size = float(update.message.text)
        if size <= 0:
            raise ValueError
        
        product_id = get_wallet_data(context, 'auto_grid_product')
        symbol = PRODUCTS[product_id]
        price = dashboard.get_market_price(product_id)
        
        # Проверка минимального размера
        # Для лимитных ордеров Nado требует: abs(size * leverage * price) >= $100
        # Плечо УЖЕ учитывается в place_order, поэтому проверяем с плечом
        min_notional = 100
        current_notional = size * float(dashboard.leverage) * price
        
        if current_notional < min_notional:
            min_size = min_notional / (float(dashboard.leverage) * price)
            await update.message.reply_text(
                f"❌ <b>Size слишком мал!</b>\n\n"
                f"Текущий: {size} × {float(dashboard.leverage)}x × ${price:.2f} = ${current_notional:.2f}\n"
                f"Минимум: ${min_notional}\n\n"
                f"Минимальный размер: <b>{min_size:.2f} {symbol}</b>\n\n"
                f"Введите новый размер:",
                parse_mode='HTML'
            )
            return WAITING_AUTO_SIZE
        
        set_wallet_data(context, 'auto_grid_size', size)
        
        # Request Grid offset
        text = (
            f"🤖 <b>GRID AUTO: {symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n"
            f"💼 Notional: <b>${current_notional:.2f}</b> ✅\n\n"
            "<b>Enter Grid offset from price (%):</b>\n"
            "Example: 0.5 for ±0.5%\n\n"
            "💡 Recommendations:\n"
            "• 0.3% - tight grid\n"
            "• 0.5% - standard\n"
            "• 1.0% - wide grid"
        )
        
        await update.message.reply_text(text, parse_mode='HTML')
        
        return WAITING_AUTO_GRID_OFFSET
        
    except:
        await update.message.reply_text("❌ Invalid format. Введите число:")
        return WAITING_AUTO_SIZE


async def auto_grid_handle_offset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        offset_text = update.message.text
        logger.info(f"Parsing offset: '{offset_text}'")
        
        offset = float(offset_text)
        logger.info(f"Parsed offset: {offset}")
        
        if offset < 0.1 or offset > 5:
            logger.warning(f"Offset {offset} out of range (0.1-5)")
            raise ValueError

        product_id = get_wallet_data(context, 'auto_grid_product')
        size = get_wallet_data(context, 'auto_grid_size')
        symbol = PRODUCTS[product_id]

        await update.message.reply_text("🔄 Starting Grid Auto-Trader...")

        from grid_autotrader import GridAutoTrader

        # ВАЖНО: Используем wallet_num из context, а не dashboard.current_wallet
        # потому что dashboard.current_wallet может измениться!
        wallet_num = context.user_data.get('wallet_num', 1)
        isolated_dashboard = dashboard.get_isolated_dashboard(wallet_num)
        
        trader = GridAutoTrader(
            dashboard=isolated_dashboard,  # Изолированный dashboard!
            product_id=product_id,
            base_size=size,
            grid_offset=offset
        )

        # Используем новый API для выбранного кошелька
        current_traders = active_traders[wallet_num]
        if current_traders['grid'] and current_traders['grid'].running:
            current_traders['grid'].stop()
            await asyncio.sleep(2)

        active_traders[wallet_num]['grid'] = trader
        save_traders_status()
        asyncio.create_task(trader.start())

        # Кнопка "Назад в меню"
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ <b>GRID AUTO STARTED</b>\n\n"
            f"📊 Pair: <b>{symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n"
            f"📏 Grid: <b>±{offset}%</b>",
            parse_mode="HTML",
            reply_markup=reply_markup
        )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"ERROR in auto_grid_handle_offset: {e}", exc_info=True)
        await update.message.reply_text("❌ Введите число от 0.1 до 5:")
        return WAITING_AUTO_GRID_OFFSET



async def auto_grid_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start Grid Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    # Парсим выбранный сценарий
    scenario_idx = int(query.data.split('_')[-1])
    scenarios = get_wallet_data(context, 'auto_grid_scenarios')
    selected = scenarios[scenario_idx]
    
    product_id = get_wallet_data(context, 'auto_grid_product')
    size = get_wallet_data(context, 'auto_grid_size')
    offset = get_wallet_data(context, 'auto_grid_offset', 0.5)  # По умолчанию 0.5%
    
    symbol = PRODUCTS[product_id]
    
    await query.edit_message_text("🔄 Starting Grid Auto-Trader...")
    
    try:
        # Импортируем и запускаем
        from grid_autotrader import GridAutoTrader
        
        # Логируем параметры
        logger.info(f"Start Grid Auto-Trader: product_id={product_id}, base_size={size}, grid_offset={offset}")
        
        # ВАЖНО: Используем wallet_num из context
        wallet_num = context.user_data.get('wallet_num', 1)
        isolated_dashboard = dashboard.get_isolated_dashboard(wallet_num)
        
        trader = GridAutoTrader(
            dashboard=isolated_dashboard,  # Изолированный dashboard!
            product_id=product_id,
            base_size=size,
            grid_offset=offset
        )
        
        # Останавливаем старый трейдер если есть для этого кошелька
        current_traders = active_traders[wallet_num]
        if current_traders['grid'] and current_traders['grid'].running:
            current_traders['grid'].stop()
            await asyncio.sleep(2)
        
        # Сохраняем для выбранного кошелька
        active_traders[wallet_num]['grid'] = trader
        
        # Save status to file
        save_traders_status()
        
        # Launchаем в фоне
        asyncio.create_task(trader.start())
        
        text = (
            "✅ <b>GRID AUTO-TRADER STARTED!</b>\n\n"
            f"📊 Pair: <b>{symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n"
            f"📏 Grid: <b>±{offset}%</b>\n"
            f"🎯 TP: <b>{selected['tp_percent']}%</b> "
            f"(${selected['tp_pnl']:+,.2f})\n"
            f"🛑 SL: <b>{selected['sl_percent']}%</b> "
            f"(${selected['sl_pnl']:+,.2f})\n\n"
            "Bot runs in background 24/7\n"
            "Use /start for проверки статуса"
        )
        
        keyboard = [[InlineKeyboardButton("« Back", callback_data='back')]]
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Error запуска: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
    
    return ConversationHandler.END


# ============ БЫСТРОЕ УПРАВЛЕНИЕ АВТОГРИДАМИ ============

async def quick_stop_grid_w1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрая остановка Auto Grid на Wallet 1"""
    query = update.callback_query
    await query.answer()
    
    if active_traders[1]['grid']:
        active_traders[1]['grid'].stop()
        active_traders[1]['grid'] = None
        save_traders_status()
        await query.answer("✅ Grid W1 stopped!", show_alert=True)
    else:
        await query.answer("⚠️ Grid W1 not running", show_alert=True)
    
    # Обновляем главное меню
    await start(update, context)


async def quick_stop_grid_w2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрая остановка Auto Grid на Wallet 2"""
    query = update.callback_query
    await query.answer()
    
    if active_traders[2]['grid']:
        active_traders[2]['grid'].stop()
        active_traders[2]['grid'] = None
        save_traders_status()
        await query.answer("✅ Grid W2 stopped!", show_alert=True)
    else:
        await query.answer("⚠️ Grid W2 not running", show_alert=True)
    
    # Обновляем главное меню
    await start(update, context)


async def quick_start_grid_w1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрый запуск Auto Grid на Wallet 1"""
    query = update.callback_query
    await query.answer()
    
    # Переключаемся на Wallet 1 и открываем меню Auto Grid
    dashboard.switch_wallet(1)
    context.user_data['wallet_num'] = 1
    await select_wallet_for_auto_grid(update, context)


async def quick_start_grid_w2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрый запуск Auto Grid на Wallet 2"""
    query = update.callback_query
    await query.answer()
    
    # Переключаемся на Wallet 2 и открываем меню Auto Grid
    dashboard.switch_wallet(2)
    context.user_data['wallet_num'] = 2
    await select_wallet_for_auto_grid(update, context)


async def stop_grid_trader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop Grid Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    current_traders = get_current_traders()
    if current_traders['grid']:
        current_traders['grid'].stop()
        set_current_trader('grid', None)
        
        # Save status to file
        save_traders_status()
        
        await query.edit_message_text(
            "✅ Grid Auto-Trader stopped",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
    else:
        await query.edit_message_text("⚠️ Auto-Trader was not started")


# ============ ML AUTO-TRADER ============

async def select_wallet_for_ml(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор кошелька для ML Auto"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "<b>🧠 ML AUTO TRADER</b>\n\n"
        "Select wallet:"
    )
    
    try:
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=get_wallet_keyboard()
        )
    except Exception:
        await query.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=get_wallet_keyboard()
        )
    
    return WAITING_ML_WALLET


async def wallet_selected_for_ml(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора кошелька для ML"""
    query = update.callback_query
    await query.answer()
    
    wallet_num = int(query.data.split('_')[2])
    context.user_data['wallet_num'] = wallet_num
    
    # Переключаемся на выбранный кошелек
    global dashboard
    dashboard.switch_wallet(wallet_num)
    
    text = (
        f"<b>🧠 ML AUTO TRADER</b>\n\n"
        f"👛 Wallet {wallet_num}: <code>{dashboard.wallet[:10]}...{dashboard.wallet[-8:]}</code>\n\n"
        "Select pair:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=get_products_keyboard()
    )
    
    return WAITING_ML_PRODUCT


async def auto_ml_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ML Auto-Trader menu"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем статус
    is_running = active_traders['ml'] and active_traders['ml'].running
    
    if is_running:
        trader = active_traders['ml']
        product = PRODUCTS[trader.product_id]
        
        text = (
            "🧠 <b>ML AUTO-TRADER</b>\n\n"
            f"Status: 🟢 <b>ACTIVE</b>\n\n"
            f"📊 Pair: <b>{product}</b>\n"
            f"💰 Size: <b>{trader.base_size}</b>\n"
            f"🎯 TP: <b>{trader.tp_percent}%</b>\n"
            f"🛑 SL: <b>{trader.sl_percent}%</b>\n"
            f"🎲 Min. confidence: <b>{trader.min_confidence:.0%}</b>\n\n"
            "ML model analyzes:\n"
            "• Moving averages\n"
            "• RSI indicator\n"
            "• MACD\n"
            "• Volatility\n\n"
            "Opens positions only with\n"
            "high prediction confidence"
        )
        
        keyboard = [
            [InlineKeyboardButton("🛑 Stop", callback_data='stop_ml')],
            [InlineKeyboardButton("« Back", callback_data='back')]
        ]
    else:
        text = (
            "🧠 <b>ML AUTO-TRADER</b>\n\n"
            "Status: ⚪ <b>OFF</b>\n\n"
            "Smart trading based on ML:\n"
            "• Price movement prediction\n"
            "• Only directional trades\n"
            "• Opens at confidence >70%\n"
            "• Automatic TP/SL\n\n"
            "Select pair to launch:"
        )
        
        keyboard = get_products_keyboard().inline_keyboard
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_ML_PRODUCT if not is_running else ConversationHandler.END


async def auto_ml_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pair selection for ML Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    context.user_data['auto_ml_product'] = product_id
    
    symbol = PRODUCTS[product_id]
    price = dashboard.get_market_price(product_id)
    
    text = (
        f"🧠 <b>ML AUTO: {symbol}</b>\n\n"
        f"💰 Price: <b>${price:,.2f}</b>\n\n"
        "Enter base position size:"
    )
    
    await query.edit_message_text(text, parse_mode='HTML')
    return WAITING_ML_SIZE


async def auto_ml_handle_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ML Auto size handling"""
    try:
        size = float(update.message.text)
        if size <= 0:
            raise ValueError
        
        context.user_data['auto_ml_size'] = size
        
        # Запрашиваем минимальную уверенность ML
        product_id = context.user_data['auto_ml_product']
        symbol = PRODUCTS[product_id]
        
        text = (
            f"🧠 <b>ML AUTO: {symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n\n"
            "<b>Enter minimum ML confidence (%):</b>\n"
            "Example: 60 for 60%\n\n"
            "💡 Recommendations:\n"
            "• 50% - aggressive (more trades)\n"
            "• 60% - balanced\n"
            "• 70% - conservative (fewer trades)"
        )
        
        await update.message.reply_text(text, parse_mode='HTML')
        return WAITING_AUTO_ML_CONFIDENCE
        
        product_id = context.user_data['auto_ml_product']
        symbol = PRODUCTS[product_id]
        price = dashboard.get_market_price(product_id)
        
        # Проверка минимального размера
        min_notional = 100
        current_notional = size * float(dashboard.leverage) * price
        
        if current_notional < min_notional:
            min_size = min_notional / (float(dashboard.leverage) * price)
            await update.message.reply_text(
                f"❌ <b>Size слишком мал!</b>\n\n"
                f"Текущий: {size} × {float(dashboard.leverage)}x × ${price:.2f} = ${current_notional:.2f}\n"
                f"Минимум: ${min_notional}\n\n"
                f"Минимальный размер: <b>{min_size:.2f}</b>\n\n"
                f"Введите новый размер:",
                parse_mode='HTML'
            )
            return WAITING_ML_SIZE
        
        context.user_data['auto_ml_size'] = size
        
        # Показываем готовые сценарии TP/SL
        scenarios = calc.calculate_scenarios(
            product_symbol=symbol,
            entry_price=price,
            size=size,
            is_long=True
        )
        
        text = (
            f"🧠 <b>ML AUTO: {symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n"
            f"💼 Notional: <b>${current_notional:.2f}</b> ✅\n\n"
            "<b>Select TP/SL scenario:</b>\n\n"
        )
        
        keyboard = []
        for i, s in enumerate(scenarios):
            label = f"{s['name']} (TP:{s['tp_percent']}% SL:{s['sl_percent']}%)"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'auto_ml_tpsl_{i}')])
        
        keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Сохраняем сценарии
        context.user_data['auto_ml_scenarios'] = scenarios
        
        return WAITING_ML_TP_SL
        
    except:
        await update.message.reply_text("❌ Invalid format. Enter a number:")
        return WAITING_ML_SIZE


async def auto_ml_handle_confidence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ML Auto confidence handling"""
    try:
        confidence = float(update.message.text)
        if confidence < 0 or confidence > 100:
            raise ValueError
        
        context.user_data['auto_ml_confidence'] = confidence / 100  # Convert to 0-1
        
        size = context.user_data['auto_ml_size']
        product_id = context.user_data['auto_ml_product']
        symbol = PRODUCTS[product_id]
        price = dashboard.get_market_price(product_id)
        current_notional = size * float(dashboard.leverage) * price
        
        # Показываем готовые сценарии TP/SL
        scenarios = calc.calculate_scenarios(
            product_symbol=symbol,
            entry_price=price,
            size=size,
            is_long=True
        )
        
        text = (
            f"🧠 <b>ML AUTO: {symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n"
            f"💼 Notional: <b>${current_notional:.2f}</b> ✅\n"
            f"🎯 Min Confidence: <b>{confidence:.0f}%</b>\n\n"
            "<b>Select TP/SL scenario:</b>\n\n"
        )
        
        keyboard = []
        for i, s in enumerate(scenarios):
            label = f"{s['name']} (TP:{s['tp_percent']}% SL:{s['sl_percent']}%)"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'auto_ml_tpsl_{i}')])
        
        keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Сохраняем сценарии
        context.user_data['auto_ml_scenarios'] = scenarios
        
        return WAITING_ML_TP_SL
        
    except:
        await update.message.reply_text("❌ Invalid format. Enter a number 0-100:")
        return WAITING_AUTO_ML_CONFIDENCE
        return WAITING_ML_SIZE


async def auto_ml_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start ML Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    # Парсим выбранный сценарий
    scenario_idx = int(query.data.split('_')[-1])
    scenarios = context.user_data['auto_ml_scenarios']
    selected = scenarios[scenario_idx]
    
    product_id = context.user_data['auto_ml_product']
    size = context.user_data['auto_ml_size']
    
    symbol = PRODUCTS[product_id]
    
    await query.edit_message_text("🔄 Starting ML Auto-Trader...")
    
    try:
        # Импортируем и запускаем
        from ml_autotrader import MLAutoTrader
        
        wallet_num = context.user_data.get('wallet_num', 1)
        min_confidence = context.user_data.get('auto_ml_confidence', 0.5)
        
        trader = MLAutoTrader(
            dashboard=dashboard,
            product_id=product_id,
            base_size=size,
            tp_percent=selected['tp_percent'],
            sl_percent=selected['sl_percent'],
            min_confidence=min_confidence,
            lookback_days=7
        )
        
        # Сохраняем в глобальную переменную ПО КОШЕЛЬКУ!
        active_traders[wallet_num]['ml'] = trader
        
        # Launchаем в фоне
        asyncio.create_task(trader.start())
        
        confidence_pct = min_confidence * 100
        
        text = (
            "✅ <b>ML AUTO-TRADER STARTED!</b>\n\n"
            f"👛 Wallet {wallet_num}\n"
            f"📊 Pair: <b>{symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n"
            f"🎯 TP: <b>{selected['tp_percent']}%</b> "
            f"(${selected['tp_pnl']:+,.2f})\n"
            f"🛑 SL: <b>{selected['sl_percent']}%</b> "
            f"(${selected['sl_pnl']:+,.2f})\n"
            f"🎲 Min Confidence: <b>{confidence_pct:.0f}%</b>\n\n"
            "ML model will:\n"
            "• Analyze market every minute\n"
            "• Open positions on strong signals\n"
            "• Auto-close at TP/SL\n\n"
            "Use /start to check status"
        )
        
        keyboard = [[InlineKeyboardButton("« To menu", callback_data='back')]]
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Error запуска: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
    
    return ConversationHandler.END


async def stop_ml_trader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop ML Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    # Определяем текущий кошелек
    wallet_num = dashboard.active_wallet if hasattr(dashboard, 'active_wallet') else 1
    
    if active_traders[wallet_num]['ml']:
        active_traders[wallet_num]['ml'].stop()
        active_traders[wallet_num]['ml'] = None
        
        # Save status to file
        save_traders_status()
        
        await query.edit_message_text(
            f"✅ ML Auto-Trader stopped (Wallet {wallet_num})",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
    else:
        await query.edit_message_text(f"⚠️ ML Auto-Trader was not started (Wallet {wallet_num})")


# ============ TP/SL КАЛЬКУЛЯТОР ============ (оставляем старый код)

async def tpsl_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pair selection for калькулятора"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    symbol = PRODUCTS[product_id]
    price = dashboard.get_market_price(product_id)
    
    # Рассчитываем сценарии for примера
    scenarios = calc.calculate_scenarios(
        product_symbol=symbol,
        entry_price=price,
        size=0.5,  # Base size for примера
        is_long=True
    )
    
    text = (
        f"🎯 <b>TP/SL for {symbol}</b>\n\n"
        f"💰 Current price: <b>${price:,.2f}</b>\n"
        f"📊 Size: 0.5 (пример)\n"
        f"⚙️ Leverage: {float(dashboard.leverage)}x\n"
        f"💼 Позиция: {0.5 * float(dashboard.leverage)} {symbol.split('-')[0]}\n\n"
        f"<b>📊 СЦЕНАРИИ:</b>\n\n"
    )
    
    for scenario in scenarios:
        text += calc.format_scenario_text(scenario, symbol) + "\n"
    
    keyboard = [[InlineKeyboardButton("« Back", callback_data='back')]]
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ConversationHandler.END  # Завершаем conversation


# ============ УСТАНОВКА TAKE PROFIT ============

async def set_tp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора режима установки TP"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[2])
    context.user_data['tp_product_id'] = product_id
    
    # Получаем информацию о позиции
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text(
            "❌ Позиция не найдена",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data='positions')
            ]])
        )
        return ConversationHandler.END
    
    symbol = position['symbol']
    current_price = position['price']
    side = position['side']
    
    # Получаем entry price
    entry_data = dashboard.entry_prices.get(product_id)
    entry_price = entry_data['entry_price'] if entry_data else current_price
    
    text = (
        f"🎯 <b>УСТАНОВИТЬ TAKE PROFIT</b>\n\n"
        f"📊 {symbol} {side}\n"
        f"💰 Вход: ${entry_price:,.2f}\n"
        f"💰 Сейчас: ${current_price:,.2f}\n\n"
        f"Выберите режим:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 По цене ($)", callback_data='tp_mode_price')],
        [InlineKeyboardButton("📊 По проценту (%)", callback_data='tp_mode_percent')],
        [InlineKeyboardButton("« Назад", callback_data='positions')]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_TP_MODE


async def tp_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора режима TP"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.split('_')[2]  # 'price' или 'percent'
    context.user_data['tp_mode'] = mode
    
    product_id = context.user_data['tp_product_id']
    
    # Получаем позицию
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text("❌ Позиция не найдена")
        return ConversationHandler.END
    
    symbol = position['symbol']
    current_price = position['price']
    side = position['side']
    
    # Получаем entry price
    entry_data = dashboard.entry_prices.get(product_id)
    entry_price = entry_data['entry_price'] if entry_data else current_price
    
    if mode == 'price':
        text = (
            f"🎯 <b>TP ПО ЦЕНЕ</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n\n"
            f"Введите цену TP в $:"
        )
    else:  # percent
        # Рассчитываем текущий P&L в процентах
        if side == 'LONG':
            current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            current_pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        text = (
            f"🎯 <b>TP ПО ПРОЦЕНТУ</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n"
            f"📈 P&L сейчас: {current_pnl_pct:+.2f}%\n\n"
            f"Введите процент профита:\n"
            f"(Например: 5 для +5%)"
        )
    
    await query.edit_message_text(text, parse_mode='HTML')
    
    if mode == 'price':
        return WAITING_TP_PRICE
    else:
        return WAITING_TP_PERCENT


async def handle_tp_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода TP по цене"""
    try:
        tp_price = float(update.message.text)
        
        product_id = context.user_data['tp_product_id']
        
        # Получаем позицию
        positions = dashboard.get_positions()
        position = next((p for p in positions if p['product_id'] == product_id), None)
        
        if not position:
            await update.message.reply_text("❌ Позиция не найдена")
            return ConversationHandler.END
        
        symbol = position['symbol']
        side = position['side']
        current_price = position['price']
        
        # Получаем entry price
        entry_data = dashboard.entry_prices.get(product_id)
        entry_price = entry_data['entry_price'] if entry_data else current_price
        
        # Валидация
        if side == 'LONG' and tp_price <= current_price:
            await update.message.reply_text(
                f"❌ Для LONG, TP должен быть > текущей цены (${current_price:,.2f})\n"
                f"Введите новую цену:"
            )
            return WAITING_TP_PRICE
        
        if side == 'SHORT' and tp_price >= current_price:
            await update.message.reply_text(
                f"❌ Для SHORT, TP должен быть < текущей цены (${current_price:,.2f})\n"
                f"Введите новую цену:"
            )
            return WAITING_TP_PRICE
        
        # Рассчитываем P&L
        size = abs(position['amount'])
        if side == 'LONG':
            tp_pnl = (tp_price - entry_price) * size
            tp_percent = ((tp_price - entry_price) / entry_price) * 100
        else:
            tp_pnl = (entry_price - tp_price) * size
            tp_percent = ((entry_price - tp_price) / entry_price) * 100
        
        # Подтверждение
        confirm_text = (
            f"🎯 <b>ПОДТВЕРЖДЕНИЕ TP</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n"
            f"🎯 TP: ${tp_price:,.2f}\n\n"
            f"Ожидаемый профит:\n"
            f"📈 {tp_percent:+.2f}%\n"
            f"💵 ${tp_pnl:+,.2f}\n\n"
            f"Установить TP?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f'confirm_tp_{tp_price}'),
                InlineKeyboardButton("❌ Нет", callback_data='positions')
            ]
        ]
        
        await update.message.reply_text(
            confirm_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['tp_price'] = tp_price
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Введите цену:")
        return WAITING_TP_PRICE


async def handle_tp_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода TP по проценту"""
    try:
        tp_percent = float(update.message.text)
        
        if tp_percent <= 0:
            await update.message.reply_text("❌ Процент должен быть > 0\nВведите процент:")
            return WAITING_TP_PERCENT
        
        product_id = context.user_data['tp_product_id']
        
        # Получаем позицию
        positions = dashboard.get_positions()
        position = next((p for p in positions if p['product_id'] == product_id), None)
        
        if not position:
            await update.message.reply_text("❌ Позиция не найдена")
            return ConversationHandler.END
        
        symbol = position['symbol']
        side = position['side']
        current_price = position['price']
        
        # Получаем entry price
        entry_data = dashboard.entry_prices.get(product_id)
        entry_price = entry_data['entry_price'] if entry_data else current_price
        
        # Рассчитываем TP цену
        if side == 'LONG':
            tp_price = entry_price * (1 + tp_percent / 100)
        else:
            tp_price = entry_price * (1 - tp_percent / 100)
        
        # Рассчитываем P&L
        size = abs(position['amount'])
        tp_pnl = (tp_price - entry_price) * size if side == 'LONG' else (entry_price - tp_price) * size
        
        # Подтверждение
        confirm_text = (
            f"🎯 <b>ПОДТВЕРЖДЕНИЕ TP</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n"
            f"🎯 TP: ${tp_price:,.2f}\n\n"
            f"Ожидаемый профит:\n"
            f"📈 +{tp_percent:.2f}%\n"
            f"💵 ${tp_pnl:+,.2f}\n\n"
            f"Установить TP?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f'confirm_tp_{tp_price}'),
                InlineKeyboardButton("❌ Нет", callback_data='positions')
            ]
        ]
        
        await update.message.reply_text(
            confirm_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['tp_price'] = tp_price
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Введите процент:")
        return WAITING_TP_PERCENT


async def confirm_tp_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и размещение TP ордера"""
    query = update.callback_query
    await query.answer()
    
    tp_price = float(query.data.split('_')[2])
    product_id = context.user_data['tp_product_id']
    
    # Получаем позицию
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text(
            "❌ Позиция не найдена",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data='positions')
            ]])
        )
        return
    
    symbol = position['symbol']
    side = position['side']
    size = abs(position['amount'])
    is_long = side == 'LONG'
    
    await query.edit_message_text(f"🔄 Устанавливаю TP для {symbol}...")
    
    # Размещаем TP ордер
    result = dashboard.place_tp_order(
        product_id=product_id,
        size=float(size),  # ПОЛНЫЙ размер позиции (уже с плечом)
        is_long=is_long,
        target_price=tp_price
    )
    
    if result:
        # Обновляем сохраненные данные
        entry_data = dashboard.entry_prices.get(str(product_id))
        if entry_data:
            dashboard.save_entry_price(
                product_id,
                entry_data['entry_price'],
                size,
                tp_price=tp_price,
                sl_price=entry_data.get('sl_price')
            )
        
        await query.edit_message_text(
            f"✅ <b>TP УСТАНОВЛЕН!</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"🎯 TP: ${tp_price:,.2f}\n\n"
            f"Позиция закроется автоматически при достижении цены",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« К позициям", callback_data='positions')
            ]])
        )
    else:
        await query.edit_message_text(
            f"❌ Ошибка установки TP для {symbol}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data='positions')
            ]])
        )


# ============ УСТАНОВКА STOP LOSS ============

async def set_sl_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора режима установки SL"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[2])
    context.user_data['sl_product_id'] = product_id
    
    # Получаем информацию о позиции
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text(
            "❌ Позиция не найдена",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data='positions')
            ]])
        )
        return ConversationHandler.END
    
    symbol = position['symbol']
    current_price = position['price']
    side = position['side']
    
    # Получаем entry price
    entry_data = dashboard.entry_prices.get(str(product_id))
    entry_price = entry_data['entry_price'] if entry_data else current_price
    
    text = (
        f"🛑 <b>УСТАНОВИТЬ STOP LOSS</b>\n\n"
        f"📊 {symbol} {side}\n"
        f"💰 Вход: ${entry_price:,.2f}\n"
        f"💰 Сейчас: ${current_price:,.2f}\n\n"
        f"Выберите режим:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 По цене ($)", callback_data='sl_mode_price')],
        [InlineKeyboardButton("📊 По проценту (%)", callback_data='sl_mode_percent')],
        [InlineKeyboardButton("« Назад", callback_data='positions')]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_SL_MODE


async def sl_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора режима SL"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.split('_')[2]  # 'price' или 'percent'
    context.user_data['sl_mode'] = mode
    
    product_id = context.user_data['sl_product_id']
    
    # Получаем позицию
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text("❌ Позиция не найдена")
        return ConversationHandler.END
    
    symbol = position['symbol']
    current_price = position['price']
    side = position['side']
    
    # Получаем entry price
    entry_data = dashboard.entry_prices.get(str(product_id))
    entry_price = entry_data['entry_price'] if entry_data else current_price
    
    if mode == 'price':
        text = (
            f"🛑 <b>SL ПО ЦЕНЕ</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n\n"
            f"Введите цену SL в $:"
        )
    else:  # percent
        # Рассчитываем текущий P&L в процентах
        if side == 'LONG':
            current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            current_pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        text = (
            f"🛑 <b>SL ПО ПРОЦЕНТУ</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n"
            f"📈 P&L сейчас: {current_pnl_pct:+.2f}%\n\n"
            f"Введите процент убытка:\n"
            f"(Например: -5 для -5%)"
        )
    
    await query.edit_message_text(text, parse_mode='HTML')
    
    if mode == 'price':
        return WAITING_SL_PRICE
    else:
        return WAITING_SL_PERCENT


async def handle_sl_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода SL по цене"""
    try:
        sl_price = float(update.message.text)
        
        product_id = context.user_data['sl_product_id']
        
        # Получаем позицию
        positions = dashboard.get_positions()
        position = next((p for p in positions if p['product_id'] == product_id), None)
        
        if not position:
            await update.message.reply_text("❌ Позиция не найдена")
            return ConversationHandler.END
        
        symbol = position['symbol']
        side = position['side']
        current_price = position['price']
        
        # Получаем entry price
        entry_data = dashboard.entry_prices.get(str(product_id))
        entry_price = entry_data['entry_price'] if entry_data else current_price
        
        # Валидация
        if side == 'LONG' and sl_price >= current_price:
            await update.message.reply_text(
                f"❌ Для LONG, SL должен быть < текущей цены (${current_price:,.2f})\n"
                f"Введите новую цену:"
            )
            return WAITING_SL_PRICE
        
        if side == 'SHORT' and sl_price <= current_price:
            await update.message.reply_text(
                f"❌ Для SHORT, SL должен быть > текущей цены (${current_price:,.2f})\n"
                f"Введите новую цену:"
            )
            return WAITING_SL_PRICE
        
        # Рассчитываем P&L
        size = abs(position['amount'])
        sl_pnl = (sl_price - entry_price) * size if side == 'LONG' else (entry_price - sl_price) * size
        sl_percent = ((sl_price - entry_price) / entry_price * 100) if side == 'LONG' else ((entry_price - sl_price) / entry_price * 100)
        
        # Подтверждение
        confirm_text = (
            f"🛑 <b>ПОДТВЕРЖДЕНИЕ SL</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n"
            f"🛑 SL: ${sl_price:,.2f}\n\n"
            f"Ожидаемый убыток:\n"
            f"📉 {sl_percent:.2f}%\n"
            f"💵 ${sl_pnl:+,.2f}\n\n"
            f"Установить SL?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data='confirm_sl_order'),
                InlineKeyboardButton("❌ Нет", callback_data='positions')
            ]
        ]
        
        await update.message.reply_text(
            confirm_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['sl_price'] = sl_price
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число:")
        return WAITING_SL_PRICE


async def handle_sl_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода SL по проценту"""
    try:
        sl_percent = float(update.message.text)
        
        product_id = context.user_data['sl_product_id']
        
        # Получаем позицию
        positions = dashboard.get_positions()
        position = next((p for p in positions if p['product_id'] == product_id), None)
        
        if not position:
            await update.message.reply_text("❌ Позиция не найдена")
            return ConversationHandler.END
        
        symbol = position['symbol']
        side = position['side']
        current_price = position['price']
        
        # Получаем entry price
        entry_data = dashboard.entry_prices.get(str(product_id))
        entry_price = entry_data['entry_price'] if entry_data else current_price
        
        # Валидация
        if sl_percent >= 0:
            await update.message.reply_text(
                f"❌ SL должен быть отрицательным (убыток)\n"
                f"Введите отрицательный процент:"
            )
            return WAITING_SL_PERCENT
        
        # Рассчитываем цену
        if side == 'LONG':
            sl_price = entry_price * (1 + sl_percent / 100)
        else:
            sl_price = entry_price * (1 - sl_percent / 100)
        
        # Рассчитываем P&L
        size = abs(position['amount'])
        sl_pnl = (sl_price - entry_price) * size if side == 'LONG' else (entry_price - sl_price) * size
        
        # Подтверждение
        confirm_text = (
            f"🛑 <b>ПОДТВЕРЖДЕНИЕ SL</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Вход: ${entry_price:,.2f}\n"
            f"💰 Сейчас: ${current_price:,.2f}\n"
            f"🛑 SL: ${sl_price:,.2f}\n\n"
            f"Ожидаемый убыток:\n"
            f"📉 {sl_percent:.2f}%\n"
            f"💵 ${sl_pnl:+,.2f}\n\n"
            f"Установить SL?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data='confirm_sl_order'),
                InlineKeyboardButton("❌ Нет", callback_data='positions')
            ]
        ]
        
        await update.message.reply_text(
            confirm_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['sl_price'] = sl_price
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число:")
        return WAITING_SL_PERCENT


async def confirm_sl_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и размещение SL ордера"""
    query = update.callback_query
    await query.answer()
    
    sl_price = context.user_data['sl_price']  # ИСПРАВЛЕНО: берём из context
    product_id = context.user_data['sl_product_id']
    
    # Получаем позицию
    positions = dashboard.get_positions()
    position = next((p for p in positions if p['product_id'] == product_id), None)
    
    if not position:
        await query.edit_message_text("❌ Позиция не найдена")
        return
    
    symbol = position['symbol']
    side = position['side']
    size = abs(position['amount'])
    is_long = side == 'LONG'
    
    # Размещаем SL ЛИМИТНЫЙ ордер (reduce_only)
    result = dashboard.place_limit_close_order(  # ИСПРАВЛЕНО: лимитный ордер, не маркет!
        product_id=product_id,
        size=size,
        is_long=is_long,
        target_price=sl_price
    )
    
    if result:
        # Обновляем сохраненные данные
        entry_data = dashboard.entry_prices.get(str(product_id))
        if entry_data:
            dashboard.save_entry_price(
                product_id,
                entry_data['entry_price'],
                size,
                tp_price=entry_data.get('tp_price'),
                sl_price=sl_price
            )
        
        await query.edit_message_text(
            f"✅ <b>SL УСТАНОВЛЕН!</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"🛑 SL: ${sl_price:,.2f}\n\n"
            f"Позиция закроется автоматически при достижении цены",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« К позициям", callback_data='positions')
            ]])
        )
    else:
        await query.edit_message_text(
            f"❌ Ошибка установки SL для {symbol}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Назад", callback_data='positions')
            ]])
        )


def main():
    """Start bot"""
    # Get token
    bot_token = config.get_telegram_token()
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Убран subaccount_handler - больше не нужен!
    
    # Position opening handler
    open_position_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(select_wallet_for_position, pattern='^open_(long|short)$')
        ],
        states={
            WAITING_WALLET: [CallbackQueryHandler(wallet_selected_for_position, pattern=r'^switch_wallet_\d+$')],
            WAITING_PRODUCT: [CallbackQueryHandler(select_product, pattern=r'^product_\d+$')],
            WAITING_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_size_input)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(start, pattern='^back$')
        ],
        per_message=False
    )
    
    # Leverage settings handler
    leverage_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(leverage_settings, pattern='^leverage_settings$')
        ],
        states={
            WAITING_LEVERAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_leverage_input)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )
    
    # Grid strategy handler
    grid_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(select_wallet_for_grid, pattern='^grid_strategy$')
        ],
        states={
            WAITING_GRID_WALLET: [CallbackQueryHandler(wallet_selected_for_grid, pattern=r'^switch_wallet_\d+$')],
            WAITING_GRID_PRODUCT: [CallbackQueryHandler(grid_select_product, pattern=r'^product_\d+$')],
            WAITING_GRID_MODE: [CallbackQueryHandler(grid_mode_selected, pattern=r'^grid_mode_(adaptive|standard)_\d+$')],
            WAITING_GRID_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_grid_size)],
            WAITING_GRID_OFFSET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_grid_offset)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(start, pattern='^back$')
        ],
        per_message=False
    )
    
    # Grid Auto-Trader handler
    auto_grid_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(select_wallet_for_auto_grid, pattern='^auto_grid$')
        ],
        states={
            WAITING_AUTO_WALLET: [CallbackQueryHandler(wallet_selected_for_auto_grid, pattern=r'^switch_wallet_\d+$')],
            WAITING_AUTO_PRODUCT: [CallbackQueryHandler(auto_grid_select_product, pattern=r'^product_\d+$')],
            WAITING_AUTO_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, auto_grid_handle_size)],
            WAITING_AUTO_GRID_OFFSET: [MessageHandler(filters.TEXT & ~filters.COMMAND, auto_grid_handle_offset)],
            WAITING_AUTO_TP_SL: [CallbackQueryHandler(auto_grid_start, pattern=r'^auto_grid_tpsl_\d+$')]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(start, pattern='^back$')
        ],
        per_message=False
    )
    
    # ML Auto-Trader handler
    auto_ml_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(select_wallet_for_ml, pattern='^auto_ml$')
        ],
        states={
            WAITING_ML_WALLET: [CallbackQueryHandler(wallet_selected_for_ml, pattern=r'^switch_wallet_\d+$')],
            WAITING_ML_PRODUCT: [CallbackQueryHandler(auto_ml_select_product, pattern=r'^product_\d+$')],
            WAITING_ML_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, auto_ml_handle_size)],
            WAITING_AUTO_ML_CONFIDENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, auto_ml_handle_confidence)],
            WAITING_ML_TP_SL: [CallbackQueryHandler(auto_ml_start, pattern=r'^auto_ml_tpsl_\d+$')]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(start, pattern='^back$')
        ],
        per_message=False
    )
    
    # Обработчик TP/SL Calculatorа
    tpsl_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(tpsl_calculator, pattern='^tpsl_calc$')
        ],
        states={
            WAITING_TPSL_PRODUCT: [CallbackQueryHandler(tpsl_select_product, pattern=r'^product_\d+$')]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(start, pattern='^back$')
        ],
        per_message=False
    )
    
    # TP Setup Handler  
    tp_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_tp_menu, pattern=r'^set_tp_\d+$')
        ],
        states={
            WAITING_TP_MODE: [
                CallbackQueryHandler(tp_mode_selected, pattern=r'^tp_mode_(price|percent)$')
            ],
            WAITING_TP_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tp_price)
            ],
            WAITING_TP_PERCENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tp_percent)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(show_positions, pattern='^positions$')
        ],
        per_message=False
    )
    
    # SL Setup Handler
    sl_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_sl_menu, pattern=r'^set_sl_\d+$')
        ],
        states={
            WAITING_SL_MODE: [
                CallbackQueryHandler(sl_mode_selected, pattern=r'^sl_mode_(price|percent)$')
            ],
            WAITING_SL_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sl_price)
            ],
            WAITING_SL_PERCENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sl_percent)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(show_positions, pattern='^positions$')
        ],
        per_message=False
    )
    
    # Commands
    # Убрали add_handler(subaccount_handler) - больше не нужен!
    application.add_handler(CommandHandler('start', start))
    
    # ConversationHandlers
    application.add_handler(open_position_handler)
    application.add_handler(leverage_handler)
    application.add_handler(grid_handler)
    application.add_handler(auto_grid_handler)
    application.add_handler(auto_ml_handler)
    application.add_handler(tpsl_handler)
    application.add_handler(tp_handler)
    application.add_handler(sl_handler)
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(start, pattern='^back$'))
    application.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))
    application.add_handler(CallbackQueryHandler(refresh_status, pattern='^refresh$'))
    application.add_handler(CallbackQueryHandler(show_balance, pattern='^balance$'))
    application.add_handler(CallbackQueryHandler(show_prices, pattern='^prices$'))
    application.add_handler(CallbackQueryHandler(show_positions, pattern='^positions$'))
    application.add_handler(CallbackQueryHandler(show_history, pattern='^history$'))
    
    # Wallets handlers
    application.add_handler(CallbackQueryHandler(show_wallets_menu, pattern='^wallets_menu$'))
    application.add_handler(CallbackQueryHandler(switch_wallet, pattern=r'^switch_wallet_\d+(_\w+)?$'))
    
    # История - периоды
    async def history_period_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        period = update.callback_query.data.split('_')[2]
        await show_period_summary(update, context, history_manager, period)
    application.add_handler(CallbackQueryHandler(history_period_handler, pattern=r'^hist_period_'))
    
    # История - детали
    async def history_details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        parts = update.callback_query.data.split('_')
        period = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        await show_period_details(update, context, history_manager, period, page)
    application.add_handler(CallbackQueryHandler(history_details_handler, pattern=r'^hist_details_'))
    
    application.add_handler(CallbackQueryHandler(confirm_order, pattern='^confirm_order_'))
    application.add_handler(CallbackQueryHandler(close_position, pattern=r'^close_\d+$'))
    application.add_handler(CallbackQueryHandler(confirm_close_position, pattern=r'^confirm_close_\d+$'))
    application.add_handler(CallbackQueryHandler(cancel_orders_for_product, pattern=r'^cancel_orders_\d+$'))
    application.add_handler(CallbackQueryHandler(confirm_tp_order, pattern=r'^confirm_tp_'))
    application.add_handler(CallbackQueryHandler(confirm_sl_order, pattern='^confirm_sl_order$'))
    application.add_handler(CallbackQueryHandler(confirm_grid, pattern='^confirm_grid$'))
    application.add_handler(CallbackQueryHandler(grid_mode_selected, pattern=r'^grid_mode_(adaptive|standard)_\d+$'))
    application.add_handler(CallbackQueryHandler(stop_grid_trader, pattern='^stop_grid$'))
    application.add_handler(CallbackQueryHandler(stop_ml_trader, pattern='^stop_ml$'))
    
    # Быстрые кнопки управления автогридами
    application.add_handler(CallbackQueryHandler(quick_stop_grid_w1, pattern='^stop_grid_w1$'))
    application.add_handler(CallbackQueryHandler(quick_stop_grid_w2, pattern='^stop_grid_w2$'))
    application.add_handler(CallbackQueryHandler(quick_start_grid_w1, pattern='^start_grid_w1$'))
    application.add_handler(CallbackQueryHandler(quick_start_grid_w2, pattern='^start_grid_w2$'))
    
    # Запускаем фоновый мониторинг TP/SL
    async def monitor_tp_sl():
        """Мониторинг сработавших TP/SL"""
        previous_positions = {}
        
        while True:
            try:
                await asyncio.sleep(15)  # Проверка каждые 15 секунд
                
                # Получаем текущие позиции
                current_positions = dashboard.get_positions()
                current_ids = {p['product_id'] for p in current_positions}
                
                # Проверяем закрытые позиции
                for prev_id, prev_data in previous_positions.items():
                    if prev_id not in current_ids:
                        # Позиция закрылась!
                        entry_data = dashboard.entry_prices.get(str(prev_id))
                        
                        if entry_data:
                            entry_price = entry_data['entry_price']
                            tp_price = entry_data.get('tp_price')
                            sl_price = entry_data.get('sl_price')
                            
                            # Получаем последнюю цену
                            last_price = dashboard.get_market_price(prev_id)
                            
                            # Определяем что сработало
                            symbol = PRODUCTS[prev_id]
                            side = prev_data['side']
                            
                            if tp_price and last_price:
                                # Проверяем сработал ли TP
                                if (side == 'LONG' and last_price >= tp_price) or \
                                   (side == 'SHORT' and last_price <= tp_price):
                                    # TP сработал!
                                    pnl = (last_price - entry_price) * abs(prev_data['amount']) if side == 'LONG' else \
                                          (entry_price - last_price) * abs(prev_data['amount'])
                                    
                                    for user_id in ALLOWED_USERS:
                                        try:
                                            await application.bot.send_message(
                                                user_id,
                                                f"🎯 <b>TAKE PROFIT СРАБОТАЛ!</b>\n\n"
                                                f"📊 {symbol} {side}\n"
                                                f"💰 Вход: ${entry_price:,.2f}\n"
                                                f"💰 TP: ${tp_price:,.2f}\n"
                                                f"🟢 <b>Профит: ${pnl:+,.2f}</b>",
                                                parse_mode='HTML'
                                            )
                                        except Exception as e:
                                            logger.error(f"Error sending TP notification: {e}")
                            
                            if sl_price and last_price:
                                # Проверяем сработал ли SL
                                if (side == 'LONG' and last_price <= sl_price) or \
                                   (side == 'SHORT' and last_price >= sl_price):
                                    # SL сработал!
                                    pnl = (last_price - entry_price) * abs(prev_data['amount']) if side == 'LONG' else \
                                          (entry_price - last_price) * abs(prev_data['amount'])
                                    
                                    for user_id in ALLOWED_USERS:
                                        try:
                                            await application.bot.send_message(
                                                user_id,
                                                f"🛑 <b>STOP LOSS СРАБОТАЛ!</b>\n\n"
                                                f"📊 {symbol} {side}\n"
                                                f"💰 Вход: ${entry_price:,.2f}\n"
                                                f"💰 SL: ${sl_price:,.2f}\n"
                                                f"🔴 <b>Убыток: ${pnl:+,.2f}</b>",
                                                parse_mode='HTML'
                                            )
                                        except Exception as e:
                                            logger.error(f"Error sending SL notification: {e}")
                
                # Обновляем previous_positions
                previous_positions = {p['product_id']: p for p in current_positions}
                
            except Exception as e:
                logger.error(f"Error in monitor_tp_sl: {e}")
                await asyncio.sleep(30)
    
    # Запускаем мониторинг в фоне
    async def start_monitoring():
        """Запуск фонового мониторинга"""
        await asyncio.sleep(5)  # Ждем 5 секунд после старта
        asyncio.create_task(monitor_tp_sl())
    
    # Хук для запуска после старта
    async def post_init(application):
        await start_monitoring()
    
    application.post_init = post_init
    
    # Launch
    logger.info("🤖 Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


# Функция handle_subaccount_input удалена - больше не нужна!


if __name__ == '__main__':
    main()
