"""
Test: проверяем что новый юзер может читать свои данные по subaccount
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import config
from trading_dashboard import TradingDashboard

# Новый юзер 677623236
subaccount = "0xb6da54b9cd60832d33d1a401933d48dee774dcfa64656661756c740000000000"
user_id = "677623236"

print(f"=== Testing new user {user_id} ===")
print(f"Subaccount: {subaccount}")

try:
    dash = TradingDashboard(subaccount, user_id=user_id)
    print(f"✅ Dashboard created")
    print(f"   Network: {dash.network}")
    print(f"   Wallet: {dash.wallet}")
    print(f"   Sender: {dash.sender_hex}")
except Exception as e:
    print(f"❌ Failed to create dashboard: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Тест READ операций
print(f"\n=== Balance ===")
try:
    balance = dash.get_balance()
    if balance:
        print(f"✅ Balance: equity=${balance['equity']:.2f}, assets=${balance['assets']:.2f}")
    else:
        print(f"⚠️ Balance returned None (user may not have deposits)")
except Exception as e:
    print(f"❌ Error: {e}")

print(f"\n=== Positions ===")
try:
    positions = dash.get_positions()
    if positions:
        for p in positions:
            print(f"  {p['symbol']} {p['side']} amount={p['amount']} price={p['price']}")
    else:
        print(f"  No open positions")
except Exception as e:
    print(f"❌ Error: {e}")

print(f"\n=== Open Orders ===")
try:
    orders = dash.get_open_orders(8)  # SOL
    print(f"  SOL orders: {len(orders) if orders else 0}")
except Exception as e:
    print(f"❌ Error: {e}")

print(f"\n✅ All READ operations completed")
