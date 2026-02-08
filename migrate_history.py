"""
Скрипт миграции старой истории в новый формат
"""
import json
import os
from trade_history_manager import TradeHistoryManager


def migrate_old_history(old_file='trade_history_old.json', leverage=10):
    """
    Мигрировать старую историю в новый формат
    
    Args:
        old_file: путь к старому файлу истории
        leverage: плечо (по умолчанию 10x)
    """
    if not os.path.exists(old_file):
        print(f"❌ Файл {old_file} не найден")
        return
    
    # Загружаем старую историю
    with open(old_file, 'r') as f:
        old_trades = json.load(f)
    
    if not old_trades:
        print("ℹ️ Старая история пуста")
        return
    
    print(f"📦 Найдено {len(old_trades)} старых сделок")
    
    # Создаём новый менеджер
    new_manager = TradeHistoryManager('trade_history_new.json')
    
    migrated = 0
    errors = 0
    
    for trade in old_trades:
        try:
            # Извлекаем данные из старого формата
            symbol = trade.get('symbol', 'UNKNOWN')
            product_id = trade.get('product_id', 8)
            side = trade.get('side', 'LONG')
            entry_price = trade.get('entry_price', 0)
            exit_price = trade.get('exit_price', 0)
            
            # Старый формат: pnl уже рассчитан, size может быть с плечом или без
            # Пытаемся восстановить базовый size
            old_pnl = trade.get('pnl', 0)
            
            # Если есть size в старом формате, используем его
            if 'size' in trade:
                # Предполагаем что это БЕЗ плеча
                size = trade['size']
            else:
                # Пытаемся восстановить size из P&L
                price_diff = abs(exit_price - entry_price)
                if price_diff > 0:
                    position_size = abs(old_pnl) / price_diff
                    size = position_size / leverage
                else:
                    size = 1.0  # Fallback
            
            # Рассчитываем комиссии (приблизительно)
            position_size = size * leverage
            entry_notional = entry_price * position_size
            exit_notional = exit_price * position_size
            entry_fee = entry_notional * 0.0001
            exit_fee = exit_notional * 0.0001
            
            # Timestamp
            timestamp = trade.get('timestamp', trade.get('closed_at', None))
            
            # Добавляем в новую историю
            new_manager.add_trade(
                symbol=symbol,
                product_id=product_id,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                leverage=leverage,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                timestamp=timestamp
            )
            
            migrated += 1
            
        except Exception as e:
            print(f"⚠️ Ошибка при миграции сделки: {e}")
            errors += 1
    
    print(f"\n✅ Мигрировано: {migrated} сделок")
    if errors > 0:
        print(f"⚠️ Ошибок: {errors}")
    
    print(f"\n💾 Новая история сохранена в: trade_history_new.json")
    print(f"ℹ️ Переименуйте файл в trade_history.json для использования")


if __name__ == '__main__':
    # Пример использования
    print("🔄 Миграция истории торговли...\n")
    migrate_old_history('trade_history.json', leverage=10)
