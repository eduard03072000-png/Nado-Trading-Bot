"""
Telegram Bot для управления торговлей на Nado DEX
Команды для открытия/закрытия позиций
"""
import os
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
import logging
from decimal import Decimal
import asyncio

# Добавляем путь к модулям DEX
sys.path.append(os.path.join(os.path.dirname(__file__), 'dex'))

from nado_rest_client import NadoRESTClient

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальный клиент Nado
nado_client = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    welcome_text = """
🤖 *Nado DEX Trading Bot*

Доступные команды:

📊 *Информация:*
/nado\_balance - Баланс аккаунта
/nado\_positions - Открытые позиции

🟢 *Открыть позиции:*
/nado\_long <размер> - Long позиция
   Пример: `/nado_long 1.1`

🔴 *Открыть Short:*
/nado\_short <размер> - Short позиция
   Пример: `/nado_short 1.1`

⚪️ *Закрыть позиции:*
/nado\_close <product\_id> - Закрыть позицию
   Пример: `/nado_close 1` (1=SOL)

⚠️ *Все ордера выполняются немедленно!*
    """
    await update.message.reply_text(
        welcome_text,
        parse_mode='MarkdownV2'
    )


async def nado_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /nado_balance - показать баланс"""
    
    if nado_client is None:
        await update.message.reply_text(
            "❌ Nado клиент не инициализирован!\n"
            "Проверьте переменную NADO_PRIVATE_KEY"
        )
        return
    
    await update.message.reply_text("⏳ Получаю баланс...")
    
    try:
        balance = nado_client.get_balance()
        
        if "error" in balance:
            await update.message.reply_text(
                f"❌ Ошибка: {balance['error']}"
            )
            return
        
        # Форматируем ответ
        text = f"""
💰 *БАЛАНС NADO DEX*

Available Margin: `${balance['available_margin']:.2f}`
Total Equity: `${balance['total_equity']:.2f}`
Margin Usage: `{balance['margin_usage']:.2%}`

Wallet: `{nado_client.address[:10]}...{nado_client.address[-8:]}`
        """
        
        await update.message.reply_text(text, parse_mode='MarkdownV2')
        
    except Exception as e:
        logger.error(f"Error in nado_balance: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def nado_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /nado_positions - показать позиции"""
    
    if nado_client is None:
        await update.message.reply_text("❌ Nado клиент не инициализирован!")
        return
    
    await update.message.reply_text("⏳ Получаю позиции...")
    
    try:
        positions = nado_client.get_positions()
        
        if "error" in positions:
            await update.message.reply_text(f"❌ Ошибка: {positions['error']}")
            return
        
        count = positions.get("count", 0)
        
        if count == 0:
            await update.message.reply_text("📊 Нет открытых позиций")
            return
        
        # Форматируем позиции
        text = f"📊 *ОТКРЫТЫЕ ПОЗИЦИИ* \\({count}\\)\n\n"
        
        for i, pos in enumerate(positions["positions"], 1):
            side = "LONG 🟢" if pos["size"] > 0 else "SHORT 🔴"
            size = abs(pos["size"])
            pnl_emoji = "📈" if pos["unrealized_pnl"] > 0 else "📉"
            
            text += f"*Позиция {i}:* {side}\n"
            text += f"Product ID: `{pos['product_id']}`\n"
            text += f"Размер: `{size:.4f}`\n"
            text += f"Вход: `${pos['entry_price']:.2f}`\n"
            text += f"PnL: `${pos['unrealized_pnl']:.2f}` {pnl_emoji}\n"
            text += "\n"
        
        await update.message.reply_text(text, parse_mode='MarkdownV2')
        
    except Exception as e:
        logger.error(f"Error in nado_positions: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def nado_long(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /nado_long <размер> - открыть LONG"""
    
    if nado_client is None:
        await update.message.reply_text("❌ Nado клиент не инициализирован!")
        return
    
    # Проверяем аргументы
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Использование: /nado_long <размер>\n"
            "Пример: /nado_long 1.1"
        )
        return
    
    try:
        size = float(context.args[0])
        
        if size <= 0:
            await update.message.reply_text("❌ Размер должен быть положительным!")
            return
        
        # Подтверждение
        await update.message.reply_text(
            f"⚠️ Открываю LONG позицию {size} SOL...\n"
            f"⏳ Размещаю market ордер..."
        )
        
        # Размещаем ордер
        result = nado_client.place_market_order(
            product_id=1,  # SOL
            side="buy",
            size=size,
            reduce_only=False
        )
        
        if "error" in result:
            await update.message.reply_text(f"❌ Ошибка: {result['error']}")
        else:
            await update.message.reply_text(
                f"✅ LONG позиция открыта!\n"
                f"Размер: {size} SOL\n"
                f"Используйте /nado_positions для проверки"
            )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат размера!")
    except Exception as e:
        logger.error(f"Error in nado_long: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def nado_short(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /nado_short <размер> - открыть SHORT"""
    
    if nado_client is None:
        await update.message.reply_text("❌ Nado клиент не инициализирован!")
        return
    
    # Проверяем аргументы
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Использование: /nado_short <размер>\n"
            "Пример: /nado_short 1.1"
        )
        return
    
    try:
        size = float(context.args[0])
        
        if size <= 0:
            await update.message.reply_text("❌ Размер должен быть положительным!")
            return
        
        # Подтверждение
        await update.message.reply_text(
            f"⚠️ Открываю SHORT позицию {size} SOL...\n"
            f"⏳ Размещаю market ордер..."
        )
        
        # Размещаем ордер
        result = nado_client.place_market_order(
            product_id=1,  # SOL
            side="sell",
            size=size,
            reduce_only=False
        )
        
        if "error" in result:
            await update.message.reply_text(f"❌ Ошибка: {result['error']}")
        else:
            await update.message.reply_text(
                f"✅ SHORT позиция открыта!\n"
                f"Размер: {size} SOL\n"
                f"Используйте /nado_positions для проверки"
            )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат размера!")
    except Exception as e:
        logger.error(f"Error in nado_short: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def nado_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /nado_close <product_id> - закрыть позицию"""
    
    if nado_client is None:
        await update.message.reply_text("❌ Nado клиент не инициализирован!")
        return
    
    # Проверяем аргументы
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Использование: /nado_close <product_id>\n"
            "Пример: /nado_close 1 (для SOL)\n"
            "Используйте /nado_positions чтобы узнать product_id"
        )
        return
    
    try:
        product_id = int(context.args[0])
        
        # Подтверждение
        await update.message.reply_text(
            f"⚠️ Закрываю позицию Product {product_id}...\n"
            f"⏳ Размещаю market ордер..."
        )
        
        # Закрываем позицию
        result = nado_client.close_position(product_id)
        
        if "error" in result:
            await update.message.reply_text(f"❌ Ошибка: {result['error']}")
        else:
            await update.message.reply_text(
                f"✅ Позиция закрыта!\n"
                f"Product ID: {product_id}\n"
                f"Используйте /nado_positions для проверки"
            )
        
    except ValueError:
        await update.message.reply_text("❌ Product ID должен быть числом!")
    except Exception as e:
        logger.error(f"Error in nado_close: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


def main():
    """Главная функция - запуск бота"""
    global nado_client
    
    # Получаем токен бота
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден!")
        print("Установите: set TELEGRAM_BOT_TOKEN=your_token")
        return
    
    # Получаем приватный ключ для Nado
    nado_key = os.environ.get("NADO_PRIVATE_KEY")
    if not nado_key:
        print("❌ Ошибка: NADO_PRIVATE_KEY не найден!")
        print("Установите: set NADO_PRIVATE_KEY=0x...")
        return
    
    # Инициализируем Nado клиент
    try:
        nado_client = NadoRESTClient(nado_key, mainnet=True)
        print("✅ Nado клиент инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации Nado: {e}")
        return
    
    # Создаем приложение
    application = Application.builder().token(bot_token).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("nado_balance", nado_balance))
    application.add_handler(CommandHandler("nado_positions", nado_positions))
    application.add_handler(CommandHandler("nado_long", nado_long))
    application.add_handler(CommandHandler("nado_short", nado_short))
    application.add_handler(CommandHandler("nado_close", nado_close))
    
    # Запускаем бота
    print("="*60)
    print("🤖 Telegram Bot для Nado DEX запущен!")
    print("="*60)
    print(f"Wallet: {nado_client.address}")
    print("Команды:")
    print("  /start - Помощь")
    print("  /nado_balance - Баланс")
    print("  /nado_positions - Позиции")
    print("  /nado_long <размер> - Открыть Long")
    print("  /nado_short <размер> - Открыть Short")
    print("  /nado_close <product_id> - Закрыть позицию")
    print("="*60)
    
    application.run_polling()


if __name__ == "__main__":
    main()
