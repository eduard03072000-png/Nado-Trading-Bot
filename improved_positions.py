"""
Улучшенное отображение позиций с установкой TP
Добавляется к telegram_trading_bot.py
"""

# ============ УЛУЧШЕННОЕ ОТОБРАЖЕНИЕ ПОЗИЦИЙ ============

async def show_positions_improved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенное отображение позиций с entry, current, P&L"""
    query = update.callback_query
    await query.answer()
    
    positions = dashboard.get_positions()
    
    if not positions:
        await query.edit_message_text(
            "📊 <b>POSITIONS</b>\n\n✅ No open positions",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data='positions')],
                [InlineKeyboardButton("« Back", callback_data='back')]
            ])
        )
        return
    
    text = "📊 <b>OPEN POSITIONS</b>\n\n"
    
    keyboard = []
    
    for i, pos in enumerate(positions, 1):
        side_emoji = "🟢" if pos["side"] == "LONG" else "🔴"
        product_id = pos['product_id']
        current_price = pos['price']
        symbol = pos['symbol']
        amount = abs(pos['amount'])
        
        # Получаем сохраненные данные о entry price
        entry_data = dashboard.entry_prices.get(product_id)
        
        if entry_data:
            entry_price = entry_data['entry_price']
            tp_price = entry_data.get('tp_price')
            sl_price = entry_data.get('sl_price')
        else:
            entry_price = current_price
            tp_price = None
            sl_price = None
        
        # Рассчитываем P&L
        pnl = dashboard.calculate_pnl(product_id, current_price, pos['amount'])
        if pnl is not None:
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            pnl_percent = (pnl / pos['notional'] * 100) if pos['notional'] else 0
            pnl_str = f"{pnl_emoji} ${pnl:+,.2f} ({pnl_percent:+.2f}%)"
        else:
            pnl_str = "N/A"
        
        # Формируем детальный текст позиции
        pos_text = (
            f"{side_emoji} <b>{symbol}</b>\n"
            f"├ Size: {amount:.4f}\n"
            f"├ Entry: ${entry_price:,.2f}\n"
            f"├ Current: ${current_price:,.2f}\n"
            f"├ Value: ${pos['notional']:,.2f}\n"
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
                f"🎯 Set TP {symbol}",
                callback_data=f'set_tp_{product_id}'
            ),
            InlineKeyboardButton(
                f"❌ Close {symbol}",
                callback_data=f'close_{product_id}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='positions')])
    keyboard.append([InlineKeyboardButton("« Back", callback_data='back')])
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============ УСТАНОВКА TP ============

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
            "❌ Position not found",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Back", callback_data='positions')
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
        f"🎯 <b>SET TAKE PROFIT</b>\n\n"
        f"📊 {symbol} {side}\n"
        f"💰 Entry: ${entry_price:,.2f}\n"
        f"💰 Current: ${current_price:,.2f}\n\n"
        f"Choose TP mode:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 By Price ($)", callback_data='tp_mode_price')],
        [InlineKeyboardButton("📊 By Percent (%)", callback_data='tp_mode_percent')],
        [InlineKeyboardButton("« Back", callback_data='positions')]
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
        await query.edit_message_text("❌ Position not found")
        return ConversationHandler.END
    
    symbol = position['symbol']
    current_price = position['price']
    side = position['side']
    
    # Получаем entry price
    entry_data = dashboard.entry_prices.get(product_id)
    entry_price = entry_data['entry_price'] if entry_data else current_price
    
    if mode == 'price':
        text = (
            f"🎯 <b>TP BY PRICE</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Entry: ${entry_price:,.2f}\n"
            f"💰 Current: ${current_price:,.2f}\n\n"
            f"Enter TP price in $:"
        )
    else:  # percent
        # Рассчитываем текущий P&L в процентах
        if side == 'LONG':
            current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            current_pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        text = (
            f"🎯 <b>TP BY PERCENT</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Entry: ${entry_price:,.2f}\n"
            f"💰 Current: ${current_price:,.2f}\n"
            f"📈 Current P&L: {current_pnl_pct:+.2f}%\n\n"
            f"Enter TP profit in %:\n"
            f"(Example: 5 for +5% profit)"
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
            await update.message.reply_text("❌ Position not found")
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
                f"❌ For LONG, TP must be > current price (${current_price:,.2f})\n"
                f"Enter new TP price:"
            )
            return WAITING_TP_PRICE
        
        if side == 'SHORT' and tp_price >= current_price:
            await update.message.reply_text(
                f"❌ For SHORT, TP must be < current price (${current_price:,.2f})\n"
                f"Enter new TP price:"
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
            f"🎯 <b>CONFIRM TAKE PROFIT</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Entry: ${entry_price:,.2f}\n"
            f"💰 Current: ${current_price:,.2f}\n"
            f"🎯 TP Price: ${tp_price:,.2f}\n\n"
            f"Expected profit:\n"
            f"📈 {tp_percent:+.2f}%\n"
            f"💵 ${tp_pnl:+,.2f}\n\n"
            f"Set TP order?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f'confirm_tp_{tp_price}'),
                InlineKeyboardButton("❌ No", callback_data='positions')
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
        await update.message.reply_text("❌ Invalid format. Enter price:")
        return WAITING_TP_PRICE


async def handle_tp_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода TP по проценту"""
    try:
        tp_percent = float(update.message.text)
        
        if tp_percent <= 0:
            await update.message.reply_text("❌ Percent must be > 0\nEnter TP percent:")
            return WAITING_TP_PERCENT
        
        product_id = context.user_data['tp_product_id']
        
        # Получаем позицию
        positions = dashboard.get_positions()
        position = next((p for p in positions if p['product_id'] == product_id), None)
        
        if not position:
            await update.message.reply_text("❌ Position not found")
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
            f"🎯 <b>CONFIRM TAKE PROFIT</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"💰 Entry: ${entry_price:,.2f}\n"
            f"💰 Current: ${current_price:,.2f}\n"
            f"🎯 TP Price: ${tp_price:,.2f}\n\n"
            f"Expected profit:\n"
            f"📈 +{tp_percent:.2f}%\n"
            f"💵 ${tp_pnl:+,.2f}\n\n"
            f"Set TP order?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f'confirm_tp_{tp_price}'),
                InlineKeyboardButton("❌ No", callback_data='positions')
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
        await update.message.reply_text("❌ Invalid format. Enter percent:")
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
            "❌ Position not found",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Back", callback_data='positions')
            ]])
        )
        return
    
    symbol = position['symbol']
    side = position['side']
    size = abs(position['amount'])
    is_long = side == 'LONG'
    
    await query.edit_message_text(f"🔄 Setting TP order for {symbol}...")
    
    # Размещаем TP ордер
    result = dashboard.place_tp_order(
        product_id=product_id,
        size=size / dashboard.leverage,  # Base size без плеча
        is_long=is_long,
        target_price=tp_price
    )
    
    if result:
        # Обновляем сохраненные данные
        entry_data = dashboard.entry_prices.get(product_id)
        if entry_data:
            dashboard.save_entry_price(
                product_id,
                entry_data['entry_price'],
                size,
                tp_price=tp_price,
                sl_price=entry_data.get('sl_price')
            )
        
        await query.edit_message_text(
            f"✅ <b>TP ORDER PLACED!</b>\n\n"
            f"📊 {symbol} {side}\n"
            f"🎯 TP: ${tp_price:,.2f}\n\n"
            f"Position will close automatically when price reaches TP",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« To Positions", callback_data='positions')
            ]])
        )
    else:
        await query.edit_message_text(
            f"❌ Failed to place TP order for {symbol}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Back", callback_data='positions')
            ]])
        )


# ============ HANDLERS ДЛЯ ДОБАВЛЕНИЯ В MAIN ============

def setup_tp_handler():
    """Создать ConversationHandler для установки TP"""
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
            CallbackQueryHandler(show_positions_improved, pattern='^positions$')
        ],
        per_message=False
    )
    return tp_handler
