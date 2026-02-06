"""
Комплексная проверка подключения к DEX и возможности торговли
"""
import sys
import os
if os.name == 'nt':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.utils import SubaccountParams, subaccount_to_hex
import config
from decimal import Decimal

def print_section(title):
    print("\n" + "="*70)
    print(f" {title}")
    print("="*70)

def check_connection():
    """Проверка базового подключения"""
    print_section("1. ПРОВЕРКА ПОДКЛЮЧЕНИЯ К DEX")
    
    try:
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        
        print(f"Network: {network}")
        print(f"Mode: {mode}")
        
        client = create_nado_client(mode=mode, signer=config.get_nado_key())
        wallet = client.context.signer.address
        
        print(f"✅ Подключение успешно")
        print(f"Wallet: {wallet}")
        
        return client, wallet
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return None, None

def check_products(client):
    """Проверка доступности продуктов"""
    print_section("2. ПРОВЕРКА ДОСТУПНЫХ ПРОДУКТОВ")
    
    try:
        products = client.market.get_all_product_symbols()
        print(f"✅ Найдено продуктов: {len(products)}")
        
        # Показываем первые 10
        print("\nОсновные продукты:")
        for p in products[:10]:
            print(f"  {p.symbol:<15} ID: {p.product_id}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка получения продуктов: {e}")
        return False

def check_balance(client, wallet):
    """Проверка баланса на DEX"""
    print_section("3. ПРОВЕРКА БАЛАНСА НА DEX")
    
    try:
        # Пробуем разные subaccounts
        subaccount_names = ["default", ""]
        
        for name in subaccount_names:
            try:
                params = SubaccountParams(
                    subaccount_owner=wallet,
                    subaccount_name=name
                )
                sender_hex = subaccount_to_hex(params)
                
                print(f"\nSubaccount '{name}':")
                print(f"  Sender hex: {sender_hex[:20]}...")
                
                summary = client.subaccount.get_engine_subaccount_summary(sender_hex)
                
                if hasattr(summary, 'healths') and summary.healths and len(summary.healths) > 0:
                    health = summary.healths[0]
                    assets = float(health.assets) / 1e18
                    liabilities = float(health.liabilities) / 1e18
                    equity = assets - liabilities
                    
                    print(f"  Assets: ${assets:.2f}")
                    print(f"  Liabilities: ${liabilities:.2f}")
                    print(f"  Equity: ${equity:.2f}")
                    
                    if equity > 0:
                        print(f"  ✅ Баланс найден!")
                        return True, sender_hex
                    else:
                        print(f"  ⚠️ Баланс нулевой")
                else:
                    print(f"  ⚠️ Нет данных о балансе")
                    
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
        
        return False, None
        
    except Exception as e:
        print(f"❌ Общая ошибка проверки баланса: {e}")
        return False, None

def check_price(client):
    """Проверка получения цены"""
    print_section("4. ПРОВЕРКА ПОЛУЧЕНИЯ ЦЕН")
    
    PRODUCT_ID = 8  # SOL-PERP
    
    try:
        price_data = client.market.get_latest_market_price(PRODUCT_ID)
        
        if isinstance(price_data, dict) and "bid_x18" in price_data:
            bid = float(Decimal(str(price_data["bid_x18"])) / Decimal(10**18))
            ask = float(Decimal(str(price_data["ask_x18"])) / Decimal(10**18))
            mid = (bid + ask) / 2
            
            print(f"SOL-PERP (ID {PRODUCT_ID}):")
            print(f"  Bid: ${bid:.2f}")
            print(f"  Ask: ${ask:.2f}")
            print(f"  Mid: ${mid:.2f}")
            print(f"  ✅ Цены получены успешно")
            
            return True, mid
        else:
            print(f"⚠️ Неожиданный формат цены: {price_data}")
            return False, None
            
    except Exception as e:
        print(f"❌ Ошибка получения цены: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_limit_order(client, sender_hex, current_price):
    """Тест размещения лимитного ордера"""
    print_section("5. ТЕСТ ЛИМИТНОГО ОРДЕРА")
    
    PRODUCT_ID = 8  # SOL-PERP
    AMOUNT = 0.1    # Маленькая тестовая позиция
    
    print(f"\nПараметры тестового ордера:")
    print(f"  Продукт: SOL-PERP (ID {PRODUCT_ID})")
    print(f"  Размер: {AMOUNT} SOL")
    print(f"  Текущая цена: ${current_price:.2f}")
    
    # Limit price чуть выше рынка для LONG
    limit_price = current_price * 1.002  # +0.2%
    print(f"  Limit price: ${limit_price:.2f}")
    
    confirm = input("\n⚠️ Попробовать разместить ТЕСТОВЫЙ лимитный ордер? (yes/no): ")
    if confirm.lower() not in ('yes', 'y', 'да'):
        print("❌ Пропущено")
        return False
    
    try:
        amount_x18 = int(AMOUNT * 10**18)
        price_x18 = int(limit_price * 10**18)
        
        print(f"\nРазмещение ордера...")
        print(f"  amount_x18: {amount_x18}")
        print(f"  price_x18: {price_x18}")
        
        # Используем client.perp.place_order для limit order
        result = client.perp.place_order(
            product_id=PRODUCT_ID,
            order_amount=amount_x18,
            price_x18=price_x18
        )
        
        print(f"\n✅ УСПЕХ! Лимитный ордер размещен!")
        print(f"Результат: {result}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ОШИБКА размещения ордера:")
        print(f"{e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*70)
    print(" "*15 + "КОМПЛЕКСНАЯ ПРОВЕРКА DEX")
    print("="*70)
    
    # 1. Подключение
    client, wallet = check_connection()
    if not client:
        print("\n❌ Не удалось подключиться к DEX")
        input("\nНажмите Enter...")
        return
    
    # 2. Продукты
    products_ok = check_products(client)
    if not products_ok:
        print("\n⚠️ Проблемы с получением продуктов, но продолжаем...")
    
    # 3. Баланс
    has_balance, sender_hex = check_balance(client, wallet)
    if not has_balance:
        print("\n⚠️ Баланс не найден или нулевой")
        print("Возможно нужно внести депозит на https://trade.nado.xyz")
        input("\nНажмите Enter...")
        return
    
    # 4. Цены
    price_ok, current_price = check_price(client)
    if not price_ok:
        print("\n❌ Не удалось получить цены")
        input("\nНажмите Enter...")
        return
    
    # 5. Тест ордера
    order_ok = test_limit_order(client, sender_hex, current_price)
    
    # Итоги
    print_section("ИТОГОВЫЙ РЕЗУЛЬТАТ")
    
    print(f"Подключение:      {'✅' if client else '❌'}")
    print(f"Продукты:         {'✅' if products_ok else '❌'}")
    print(f"Баланс:           {'✅' if has_balance else '❌'}")
    print(f"Цены:             {'✅' if price_ok else '❌'}")
    print(f"Тест ордера:      {'✅' if order_ok else '❌'}")
    
    if order_ok:
        print("\n🎉 ВСЁ РАБОТАЕТ! Можно торговать!")
    elif has_balance:
        print("\n⚠️ Подключение есть, но ордер не прошёл")
        print("Проверьте логи выше для деталей")
    else:
        print("\n⚠️ Нужно внести депозит на DEX")
    
    input("\nНажмите Enter...")

if __name__ == "__main__":
    main()
