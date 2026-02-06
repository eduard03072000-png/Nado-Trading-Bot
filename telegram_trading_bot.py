"""
Telegram Trading Bot - Full NADO DEX Integration
"""
import logging
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler
import config
from trading_dashboard import TradingDashboard, PRODUCTS
from tp_sl_calculator import TPSLCalculator
from decimal import Decimal
import asyncio

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global dashboard instance
dashboard = None

# TP/SL calculator
calc = None

# Active auto-traders
active_traders = {
    'grid': None,
    'ml': None
}

# Auto-traders status file
TRADERS_STATUS_FILE = os.path.join(os.path.dirname(__file__), "traders_status.json")

def save_traders_status():
    """Save traders status to file"""
    status = {
        'grid': active_traders['grid'] is not None and active_traders['grid'].running if active_traders['grid'] else False,
        'ml': active_traders['ml'] is not None and active_traders['ml'].running if active_traders['ml'] else False
    }
    with open(TRADERS_STATUS_FILE, 'w') as f:
        json.dump(status, f)

def load_traders_status():
    """Load traders status from file"""
    try:
        if os.path.exists(TRADERS_STATUS_FILE):
            with open(TRADERS_STATUS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'grid': False, 'ml': False}

# Conversation states
WAITING_PRODUCT, WAITING_SIZE, WAITING_LEVERAGE, WAITING_GRID_PRODUCT, WAITING_GRID_MODE, WAITING_GRID_SIZE, WAITING_GRID_OFFSET = range(7)
WAITING_AUTO_PRODUCT, WAITING_AUTO_SIZE, WAITING_AUTO_TP_SL, WAITING_AUTO_GRID_OFFSET = range(7, 11)
WAITING_ML_PRODUCT, WAITING_ML_SIZE, WAITING_AUTO_ML_CONFIDENCE, WAITING_ML_TP_SL = range(11, 15)
WAITING_TPSL_PRODUCT = 15  # Separate state for calculator

# Temporary user data storage
user_data_storage = {}

# Allowed users
ALLOWED_USERS = [677623236, 476105926]  # Add your ID here


def check_access(update: Update) -> bool:
    """Check user access"""
    user_id = update.effective_user.id
    return user_id in ALLOWED_USERS


def get_main_keyboard():
    """Main menu"""
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
            InlineKeyboardButton("📈📉 Grid Strategy", callback_data='grid_strategy')
        ],
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
    ]
    return InlineKeyboardMarkup(keyboard)


def get_products_keyboard():
    """Pair selection keyboard"""
    keyboard = []
    for product_id, symbol in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(symbol, callback_data=f'product_{product_id}')])
    keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command"""
    if not check_access(update):
        await update.message.reply_text("❌ You don't have access to this bot")
        return
    
    global dashboard, calc
    
    if dashboard is None:
        dashboard = TradingDashboard()
    
    # Reload data
    dashboard.entry_prices = dashboard.load_positions_data()
    
    if calc is None:
        calc = TPSLCalculator(leverage=dashboard.leverage)
    
    # Load traders status from file
    traders_status = load_traders_status()
    
    # Check auto-traders status
    grid_status = "🟢 Active" if traders_status.get('grid', False) else "⚪ Off"
    ml_status = "🟢 Active" if traders_status.get('ml', False) else "⚪ Off"
    
    # Get ML prediction if ML Auto is running
    ml_prediction_text = ""
    if active_traders['ml'] and active_traders['ml'].running:
        pred = active_traders['ml'].last_prediction
        direction = pred.get('direction', 'unknown').upper()
        confidence = pred.get('confidence', 0)
        
        if direction != 'UNKNOWN' and confidence > 0:
            emoji = "🟢" if direction == "UP" else "🔴" if direction == "DOWN" else "⏸️"
            ml_prediction_text = f"\n   └ Prediction: {emoji} {direction} ({confidence:.0%})"
    
    welcome_text = (
        "🤖 <b>NADO DEX Trading Bot</b>\n\n"
        f"🌐 Network: <b>{dashboard.network.upper()}</b>\n"
        f"👛 Wallet: <code>{dashboard.wallet[:10]}...{dashboard.wallet[-8:]}</code>\n"
        f"⚙️ Leverage: <b>{dashboard.leverage}x</b>\n\n"
        f"🤖 Auto Grid: {grid_status}\n"
        f"🧠 ML Auto: {ml_status}{ml_prediction_text}\n\n"
        "Select action:"
    )
    
    if update.message:
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )
    else:
        await update.callback_query.message.edit_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )


async def refresh_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh status"""
    query = update.callback_query
    await query.answer()
    
    balance = dashboard.get_balance()
    positions = dashboard.get_positions()
    
    # Get ML prediction if ML Auto is running
    ml_prediction_text = ""
    if active_traders['ml'] and active_traders['ml'].running:
        pred = active_traders['ml'].last_prediction
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
    """Show positions"""
    query = update.callback_query
    await query.answer()
    
    positions = dashboard.get_positions()
    
    if not positions:
        await query.edit_message_text(
            "📊 <b>ПОЗИЦИИ</b>\n\n✅ No open positions",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data='positions')],
                [InlineKeyboardButton("« Back", callback_data='back')]
            ])
        )
        return
    
    text = "📊 <b>OPEN POSITIONS</b>\n\n"
    total_pnl = 0
    
    keyboard = []
    
    for i, pos in enumerate(positions, 1):
        side_emoji = "🟢" if pos["side"] == "LONG" else "🔴"
        product_id = pos['product_id']
        current_price = pos['price']
        
        # Получаем данные о цене входа
        entry_data = dashboard.entry_prices.get(product_id)
        entry_price = entry_data.get('entry_price') if entry_data else None
        
        # Рассчитываем P&L
        pnl = None
        pnl_percent = None
        pnl_str = ""
        
        if current_price and entry_price:
            pnl = dashboard.calculate_pnl(product_id, current_price, pos['amount'])
            if pnl is not None:
                # Расчет процента P&L
                entry_value = abs(pos['amount']) * entry_price
                pnl_percent = (pnl / entry_value * 100) if entry_value > 0 else 0
                
                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                pnl_str = f"\nP&L: {pnl_emoji} ${pnl:+,.2f} ({pnl_percent:+.2f}%)"
                total_pnl += pnl
        
        # Формирование текста позиции
        pos_text = f"{side_emoji} <b>{pos['symbol']}</b>\n"
        pos_text += f"Size: {abs(pos['amount']):.4f}\n"
        
        # Добавляем цены
        if entry_price:
            pos_text += f"Entry: ${entry_price:,.2f}\n"
        pos_text += f"Price: ${current_price:,.2f}\n"
        pos_text += f"Value: ${pos['notional']:,.2f}"
        
        # Добавляем TP/SL если есть
        if entry_data:
            tp_price = entry_data.get('tp_price')
            sl_price = entry_data.get('sl_price')
            if tp_price:
                pos_text += f"\n🎯 TP: ${tp_price:,.2f}"
            if sl_price:
                pos_text += f"\n🛑 SL: ${sl_price:,.2f}"
        
        pos_text += pnl_str + "\n\n"
        text += pos_text
        
        keyboard.append([InlineKeyboardButton(
            f"❌ Close {pos['symbol']}",
            callback_data=f'close_{pos["product_id"]}'
        )])
    
    if total_pnl != 0:
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        text += f"\n{pnl_emoji} <b>Total P&L: ${total_pnl:+,.2f}</b>"
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='positions')])
    keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show history"""
    query = update.callback_query
    await query.answer()
    
    # Перезагружаем историю на случай обновлений
    dashboard.trade_history = dashboard.load_trade_history()
    
    if not dashboard.trade_history:
        await query.edit_message_text(
            "📜 <b>TRADING HISTORY</b>\n\nℹ️ History пуста",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data='history')],
                [InlineKeyboardButton("« Back", callback_data='back')]
            ])
        )
        return
    
    # Статистика
    total_trades = len(dashboard.trade_history)
    winning_trades = sum(1 for t in dashboard.trade_history if t['pnl'] > 0)
    losing_trades = sum(1 for t in dashboard.trade_history if t['pnl'] < 0)
    total_pnl = sum(t['pnl'] for t in dashboard.trade_history)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    text = (
        "📜 <b>TRADING HISTORY</b>\n\n"
        f"📊 Total trades: {total_trades}\n"
        f"🟢 Winning: {winning_trades}\n"
        f"🔴 Losing: {losing_trades}\n"
        f"📈 Win rate: {win_rate:.1f}%\n"
    )
    
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    text += f"{pnl_emoji} <b>Total P&L: ${total_pnl:+,.2f}</b>\n\n"
    
    text += "<b>Last 5 trades:</b>\n\n"
    
    for trade in reversed(dashboard.trade_history[-5:]):
        pnl_emoji = "🟢" if trade['pnl'] >= 0 else "🔴"
        side_emoji = "🟢" if trade['side'] == "LONG" else "🔴"
        
        text += (
            f"{side_emoji} {trade['symbol']}\n"
            f"  Entry: ${trade['entry_price']:,.2f} → Exit: ${trade['exit_price']:,.2f}\n"
            f"  {pnl_emoji} P&L: ${trade['pnl']:+,.2f} ({trade['pnl_percent']:+.2f}%)\n\n"
        )
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data='history')],
            [InlineKeyboardButton("« Back", callback_data='back')]
        ])
    )


async def open_position_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Position opening menu"""
    query = update.callback_query
    await query.answer()
    
    is_long = query.data == 'open_long'
    context.user_data['is_long'] = is_long
    
    direction = "LONG 🟢" if is_long else "SHORT 🔴"
    
    text = (
        f"<b>{direction}</b>\n\n"
        f"⚙️ Leverage: <b>{dashboard.leverage}x</b>\n\n"
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
        size = Decimal(update.message.text)
        if size <= 0:
            raise ValueError
        
        product_id = context.user_data['product_id']
        is_long = context.user_data['is_long']
        symbol = PRODUCTS[product_id]
        
        size = dashboard.normalize_size(product_id, size)
        
        if size <= 0:
            await update.message.reply_text("❌ Size below minimum шага")
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
            "Open position?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f'confirm_order_{size}'),
                InlineKeyboardButton("❌ No", callback_data='back')
            ]
        ]
        
        await update.message.reply_text(
            confirm_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nВведите размер заново:")
        return WAITING_SIZE


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation и размещение ордера"""
    query = update.callback_query
    await query.answer()
    
    size = Decimal(query.data.split('_')[2])
    product_id = context.user_data['product_id']
    is_long = context.user_data['is_long']
    symbol = PRODUCTS[product_id]
    
    await query.edit_message_text("🔄 Placing order...")
    
    result = dashboard.place_order(product_id, size, is_long)
    
    if result:
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


async def close_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close позицию"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split('_')[1])
    symbol = PRODUCTS[product_id]
    
    await query.edit_message_text(f"🔄 Closing position {symbol}...")
    
    result = dashboard.close_position(product_id)
    
    if result:
        await query.edit_message_text(
            f"✅ Позиция {symbol} закрыта!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« To menu", callback_data='back')]])
        )
    else:
        await query.edit_message_text(
            f"❌ Position close error {symbol}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
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
    context.user_data['grid_product_id'] = product_id
    
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
        
        context.user_data['grid_mode'] = 'standard'
        await query.edit_message_text(text, parse_mode='HTML')
        return WAITING_GRID_SIZE


async def handle_grid_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid size handling"""
    try:
        size = Decimal(update.message.text)
        if size <= 0:
            raise ValueError
        
        product_id = context.user_data['grid_product_id']
        size = dashboard.normalize_size(product_id, size)
        
        if size <= 0:
            await update.message.reply_text("❌ Size below minimum")
            return WAITING_GRID_SIZE
        
        context.user_data['grid_size'] = size
        
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
        
        product_id = context.user_data['grid_product_id']
        size = context.user_data['grid_size']
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
        
        context.user_data['grid_long_price'] = float(long_price)
        context.user_data['grid_short_price'] = float(short_price)
        
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
    
    product_id = context.user_data['grid_product_id']
    size = context.user_data['grid_size']
    long_price = context.user_data.get('grid_long_price')
    short_price = context.user_data.get('grid_short_price')
    mode = context.user_data.get('grid_mode', 'standard')
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
    
    context.user_data['grid_mode'] = mode
    context.user_data['grid_product_id'] = product_id
    
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

async def auto_grid_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grid Auto-Trader menu"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем статус
    is_running = active_traders['grid'] and active_traders['grid'].running
    
    if is_running:
        trader = active_traders['grid']
        product = PRODUCTS[trader.product_id]
        
        text = (
            "🤖 <b>GRID AUTO-TRADER</b>\n\n"
            f"Status: 🟢 <b>ACTIVE</b>\n\n"
            f"📊 Pair: <b>{product}</b>\n"
            f"💰 Size: <b>{trader.base_size}</b>\n"
            f"📏 Grid offset: <b>{trader.grid_offset}%</b>\n"
            f"🎯 TP: <b>{trader.tp_percent}%</b>\n"
            f"🛑 SL: <b>{trader.sl_percent}%</b>\n\n"
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
    context.user_data['auto_grid_product'] = product_id
    
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
        
        product_id = context.user_data['auto_grid_product']
        symbol = PRODUCTS[product_id]
        price = dashboard.get_market_price(product_id)
        
        # Проверка минимального размера
        # Notional = size * leverage * price должно быть >= $100
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
            return WAITING_AUTO_SIZE
        
        context.user_data['auto_grid_size'] = size
        
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
    """Grid offset handling"""
    try:
        offset = float(update.message.text)
        if offset <= 0 or offset > 5:
            raise ValueError
        
        product_id = context.user_data['auto_grid_product']
        size = context.user_data['auto_grid_size']
        context.user_data['auto_grid_offset'] = offset
        
        symbol = PRODUCTS[product_id]
        price = dashboard.get_market_price(product_id)
        
        # Показываем готовые сценарии TP/SL
        scenarios = calc.calculate_scenarios(
            product_symbol=symbol,
            entry_price=price,
            size=size,
            is_long=True
        )
        
        text = (
            f"🤖 <b>GRID AUTO: {symbol}</b>\n"
            f"💰 Size: <b>{size}</b>\n"
            f"📏 Grid: <b>±{offset}%</b>\n\n"
            "<b>Select TP/SL scenario:</b>\n\n"
        )
        
        keyboard = []
        for i, s in enumerate(scenarios):
            label = f"{s['name']} (TP:{s['tp_percent']}% SL:{s['sl_percent']}%)"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'auto_grid_tpsl_{i}')])
        
        keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
        
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Сохраняем сценарии
        context.user_data['auto_grid_scenarios'] = scenarios
        
        return WAITING_AUTO_TP_SL
        
    except:
        await update.message.reply_text("❌ Invalid format. Введите число от 0.1 до 5:")
        return WAITING_AUTO_GRID_OFFSET


async def auto_grid_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start Grid Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    # Парсим выбранный сценарий
    scenario_idx = int(query.data.split('_')[-1])
    scenarios = context.user_data['auto_grid_scenarios']
    selected = scenarios[scenario_idx]
    
    product_id = context.user_data['auto_grid_product']
    size = context.user_data['auto_grid_size']
    offset = context.user_data.get('auto_grid_offset', 0.5)  # По умолчанию 0.5%
    
    symbol = PRODUCTS[product_id]
    
    await query.edit_message_text("🔄 Starting Grid Auto-Trader...")
    
    try:
        # Импортируем и запускаем
        from grid_autotrader import GridAutoTrader
        
        # Логируем параметры
        logger.info(f"Start Grid Auto-Trader: product_id={product_id}, base_size={size}, grid_offset={offset}")
        
        trader = GridAutoTrader(
            dashboard=dashboard,
            product_id=product_id,
            base_size=size,
            grid_offset=offset,
            tp_percent=selected['tp_percent'],
            sl_percent=selected['sl_percent']
        )
        
        # Останавливаем старый трейдер если есть
        if active_traders['grid'] and active_traders['grid'].running:
            active_traders['grid'].stop()
            await asyncio.sleep(2)
        
        # Сохраняем в глобальную переменную
        active_traders['grid'] = trader
        
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


async def stop_grid_trader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop Grid Auto-Trader"""
    query = update.callback_query
    await query.answer()
    
    if active_traders['grid']:
        active_traders['grid'].stop()
        active_traders['grid'] = None
        
        # Save status to file
        save_traders_status()
        
        await query.edit_message_text(
            "✅ Grid Auto-Trader stopped",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
    else:
        await query.edit_message_text("⚠️ Auto-Trader was not started")


# ============ ML AUTO-TRADER ============

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
            f"🎲 Мин. уверенность: <b>{trader.min_confidence:.0%}</b>\n\n"
            "ML модель анализирует:\n"
            "• Скользящие средние\n"
            "• RSI индикатор\n"
            "• MACD\n"
            "• Волатильность\n\n"
            "Открывает позиции только при\n"
            "высокой уверенности прогноза"
        )
        
        keyboard = [
            [InlineKeyboardButton("🛑 Stop", callback_data='stop_ml')],
            [InlineKeyboardButton("« Back", callback_data='back')]
        ]
    else:
        text = (
            "🧠 <b>ML AUTO-TRADER</b>\n\n"
            "Status: ⚪ <b>OFF</b>\n\n"
            "Умная торговля на основе ML:\n"
            "• Прогноз движения цены\n"
            "• Только направленные сделки\n"
            "• Opening при уверенности >70%\n"
            "• Автоматический TP/SL\n\n"
            "Select pair for запуска:"
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
        
        # Сохраняем в глобальную переменную
        active_traders['ml'] = trader
        
        # Launchаем в фоне
        asyncio.create_task(trader.start())
        
        confidence_pct = min_confidence * 100
        
        text = (
            "✅ <b>ML AUTO-TRADER STARTED!</b>\n\n"
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
    
    if active_traders['ml']:
        active_traders['ml'].stop()
        active_traders['ml'] = None
        
        # Save status to file
        save_traders_status()
        
        await query.edit_message_text(
            "✅ ML Auto-Trader stopped",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='back')]])
        )
    else:
        await query.edit_message_text("⚠️ ML Auto-Trader was not started")


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


def main():
    """Start bot"""
    # Get token
    bot_token = config.get_telegram_token()
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Position opening handler
    open_position_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(open_position_menu, pattern='^open_(long|short)$')
        ],
        states={
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
            CallbackQueryHandler(grid_strategy_menu, pattern='^grid_strategy$')
        ],
        states={
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
            CallbackQueryHandler(auto_grid_menu, pattern='^auto_grid$')
        ],
        states={
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
            CallbackQueryHandler(auto_ml_menu, pattern='^auto_ml$')
        ],
        states={
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
    
    # Commands
    application.add_handler(CommandHandler("start", start))
    
    # ConversationHandlers
    application.add_handler(open_position_handler)
    application.add_handler(leverage_handler)
    application.add_handler(grid_handler)
    application.add_handler(auto_grid_handler)
    application.add_handler(auto_ml_handler)
    application.add_handler(tpsl_handler)
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(start, pattern='^back$'))
    application.add_handler(CallbackQueryHandler(refresh_status, pattern='^refresh$'))
    application.add_handler(CallbackQueryHandler(show_balance, pattern='^balance$'))
    application.add_handler(CallbackQueryHandler(show_prices, pattern='^prices$'))
    application.add_handler(CallbackQueryHandler(show_positions, pattern='^positions$'))
    application.add_handler(CallbackQueryHandler(show_history, pattern='^history$'))
    application.add_handler(CallbackQueryHandler(confirm_order, pattern='^confirm_order_'))
    application.add_handler(CallbackQueryHandler(close_position, pattern=r'^close_\d+$'))
    application.add_handler(CallbackQueryHandler(confirm_grid, pattern='^confirm_grid$'))
    application.add_handler(CallbackQueryHandler(grid_mode_selected, pattern=r'^grid_mode_(adaptive|standard)_\d+$'))
    application.add_handler(CallbackQueryHandler(stop_grid_trader, pattern='^stop_grid$'))
    application.add_handler(CallbackQueryHandler(stop_ml_trader, pattern='^stop_ml$'))
    
    # Launch
    logger.info("🤖 Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
