"""
Обработчики истории торговли для Telegram бота
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime


PERIOD_NAMES = {
    'today': '📅 Сегодня',
    'yesterday': '📅 Вчера',
    'week': '📅 Эта неделя',
    'month': '📅 Этот месяц',
    'all': '📅 Всё время'
}


async def show_history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, history_manager):
    """Главное меню истории - выбор периода"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data='hist_period_today')],
        [InlineKeyboardButton("📅 Вчера", callback_data='hist_period_yesterday')],
        [InlineKeyboardButton("📅 Эта неделя", callback_data='hist_period_week')],
        [InlineKeyboardButton("📅 Этот месяц", callback_data='hist_period_month')],
        [InlineKeyboardButton("📅 Всё время", callback_data='hist_period_all')],
        [InlineKeyboardButton("« Назад", callback_data='back')]
    ]
    
    await query.edit_message_text(
        "📜 <b>ИСТОРИЯ ТОРГОВЛИ</b>\n\n"
        "Выберите период:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_period_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, history_manager, period: str):
    """Показать сводку по периоду"""
    query = update.callback_query
    await query.answer()
    
    # Получаем статистику
    stats = history_manager.get_statistics(period)
    
    period_name = PERIOD_NAMES.get(period, period)
    
    if stats['total_trades'] == 0:
        text = f"📜 <b>{period_name}</b>\n\nℹ️ Нет сделок за этот период"
        
        keyboard = [
            [InlineKeyboardButton("« К периодам", callback_data='history')]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Формируем текст
    pnl_emoji = "🟢" if stats['total_pnl'] >= 0 else "🔴"
    
    text = f"📜 <b>{period_name}</b>\n\n"
    
    # Основная статистика
    text += f"📊 <b>Всего сделок:</b> {stats['total_trades']}\n"
    text += f"🟢 <b>Прибыльных:</b> {stats['winning_trades']}\n"
    text += f"🔴 <b>Убыточных:</b> {stats['losing_trades']}\n"
    text += f"📈 <b>Win Rate:</b> {stats['win_rate']:.1f}%\n\n"
    
    # P&L
    text += f"{pnl_emoji} <b>Общий P&L:</b> ${stats['total_pnl']:+,.2f}\n"
    text += f"💰 <b>Средний P&L:</b> ${stats['avg_pnl']:+,.2f}\n"
    text += f"📊 <b>Средний ROI:</b> {stats['avg_roi']:+.2f}%\n\n"
    
    # Лучшая/худшая сделка
    best_emoji = "🏆"
    worst_emoji = "💀"
    text += f"{best_emoji} <b>Лучшая:</b> ${stats['best_trade']:+,.2f}\n"
    text += f"{worst_emoji} <b>Худшая:</b> ${stats['worst_trade']:+,.2f}\n\n"
    
    # Объём и комиссии
    text += f"📦 <b>Объём:</b> ${stats['total_volume']:,.2f}\n"
    text += f"💸 <b>Комиссии:</b> ${stats['total_fees']:,.2f}\n"
    
    # Кнопки
    keyboard = [
        [InlineKeyboardButton("📋 Детали", callback_data=f'hist_details_{period}')],
        [InlineKeyboardButton("🔄 Обновить", callback_data=f'hist_period_{period}')],
        [InlineKeyboardButton("« К периодам", callback_data='history')]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_period_details(update: Update, context: ContextTypes.DEFAULT_TYPE, history_manager, period: str, page: int = 0):
    """Показать детали сделок за период (с пагинацией)"""
    query = update.callback_query
    await query.answer()
    
    trades = history_manager.get_trades_by_period(period)
    
    if not trades:
        await show_period_summary(update, context, history_manager, period)
        return
    
    # Сортируем от новых к старым
    trades = sorted(trades, key=lambda x: x['timestamp'], reverse=True)
    
    # Пагинация: по 5 сделок на страницу
    per_page = 5
    total_pages = (len(trades) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(trades))
    page_trades = trades[start_idx:end_idx]
    
    period_name = PERIOD_NAMES.get(period, period)
    
    text = f"📜 <b>{period_name} - Детали</b>\n"
    text += f"Страница {page + 1}/{total_pages}\n\n"
    
    for i, trade in enumerate(page_trades, start=start_idx + 1):
        pnl_emoji = "🟢" if trade['net_pnl'] >= 0 else "🔴"
        side_emoji = "🟢" if trade['side'] == "LONG" else "🔴"
        
        # Время
        trade_time = datetime.fromisoformat(trade['timestamp'])
        time_str = trade_time.strftime("%d.%m %H:%M")
        
        text += f"<b>#{i}. {side_emoji} {trade['symbol']}</b> ({time_str})\n"
        text += f"  💰 Entry: ${trade['entry_price']:,.2f}\n"
        text += f"  💰 Exit: ${trade['exit_price']:,.2f}\n"
        text += f"  📊 Size: {trade['size']:.2f} (x{trade['leverage']})\n"
        text += f"  {pnl_emoji} P&L: ${trade['net_pnl']:+,.2f} ({trade['roi_percent']:+.2f}% ROI)\n"
        
        total_fees = trade['entry_fee'] + trade['exit_fee']
        if total_fees > 0:
            text += f"  💸 Fees: ${total_fees:.2f}\n"
        
        text += "\n"
    
    # Кнопки навигации
    keyboard = []
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'hist_details_{period}_{page-1}'))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f'hist_details_{period}_{page+1}'))
    
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("« К сводке", callback_data=f'hist_period_{period}')])
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
