"""
Test: get trigger orders - debug recvTime
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import config
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.trigger_client.types.query import (
    ListTriggerOrdersParams, ListTriggerOrdersTx
)
from nado_protocol.utils.expiration import get_expiration_timestamp

network = config.get_network()
mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
client = create_nado_client(mode=mode, signer=config.get_nado_key())

sender_hex = "0x45e293d6f82b6f94f8657a15dab479dcbe034b3964656661756c740000000000"

# Дебаг: что считает get_expiration_timestamp
print(f"Current time.time(): {int(time.time())}")
try:
    exp = get_expiration_timestamp(3600)
    print(f"get_expiration_timestamp(3600): {exp}")
except Exception as e:
    print(f"Error: {e}")

# Пробуем разные recvTime
for offset in [3600, 86400, int(time.time()) + 3600]:
    print(f"\n=== Trying recvTime={offset} ===")
    try:
        params = ListTriggerOrdersParams(
            tx=ListTriggerOrdersTx(
                sender=sender_hex,
                recvTime=offset,
                nonce=None
            ),
            product_ids=[8],
            limit=50
        )
        result = client.market.get_trigger_orders(params)
        print(f"SUCCESS! Status: {result.status}")
        if hasattr(result, 'orders'):
            print(f"Orders count: {len(result.orders)}")
            for i, order in enumerate(result.orders):
                print(f"\n--- Order {i+1} ---")
                for attr in dir(order):
                    if not attr.startswith('_'):
                        try:
                            val = getattr(order, attr)
                            if not callable(val):
                                print(f"  {attr}: {val}")
                        except:
                            pass
        break
    except Exception as e:
        err_msg = str(e)[:200]
        print(f"Error: {err_msg}")
