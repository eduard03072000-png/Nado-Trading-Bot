import re

# Read the original file
with open(r'C:\Project\Trading_bot\trading_dashboard.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Replace POST_ONLY with DEFAULT in place_sl_order
# Find the place_sl_order method and fix the order_type
old_sl_block = '''            print(f"   Placing trigger order: amount_x18={amount_x18}, priceX18={priceX18}, trigger={trigger_type}")
            result = self.client.market.place_price_trigger_order(
                product_id=product_id,
                price_x18=str(priceX18),
                amount_x18=str(amount_x18),
                trigger_price_x18=str(priceX18),
                trigger_type=trigger_type,
                reduce_only=True,
                order_type=OrderType.POST_ONLY
            )'''

new_sl_block = '''            # Execution price (цена исполнения) - со слиппажем для гарантии заполнения
            # Когда SL триггерится, цена уже прошла SL уровень,
            # лимитная цена должна быть ХУЖЕ триггера чтобы точно исполнилась
            slippage = Decimal("0.005")  # 0.5% слиппаж
            if is_long:
                # LONG SL: продаём → готовы продать ещё дешевле
                exec_price_decimal = price_decimal * (Decimal("1") - slippage)
            else:
                # SHORT SL: покупаем → готовы купить ещё дороже
                exec_price_decimal = price_decimal * (Decimal("1") + slippage)
            
            exec_price_decimal = self.normalize_price(product_id, exec_price_decimal)
            exec_priceX18 = int((exec_price_decimal * Decimal(10) ** 18).to_integral_value())
            exec_priceX18 = (exec_priceX18 // price_step_x18) * price_step_x18
            
            print(f"   Trigger price: ${price_decimal}, Exec price: ${exec_price_decimal}")
            print(f"   Placing trigger order: amount_x18={amount_x18}, exec_priceX18={exec_priceX18}, trigger_priceX18={priceX18}, trigger={trigger_type}")
            print(f"   Order type: DEFAULT (taker-compatible for guaranteed SL fill)")
            result = self.client.market.place_price_trigger_order(
                product_id=product_id,
                price_x18=str(exec_priceX18),
                amount_x18=str(amount_x18),
                trigger_price_x18=str(priceX18),
                trigger_type=trigger_type,
                reduce_only=True,
                order_type=OrderType.DEFAULT  # DEFAULT for SL - must execute as taker!
            )'''

if old_sl_block in content:
    content = content.replace(old_sl_block, new_sl_block)
    print("OK: Fixed place_sl_order - POST_ONLY -> DEFAULT + slippage")
else:
    print("ERROR: Could not find old_sl_block in file!")
    # Debug: show what's around place_sl_order
    idx = content.find('def place_sl_order')
    if idx >= 0:
        print(f"Found place_sl_order at index {idx}")
        print(repr(content[idx+500:idx+900]))

# Write the fixed file
with open(r'C:\Project\Trading_bot\trading_dashboard.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("File saved!")
