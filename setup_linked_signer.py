"""
Setup Linked Signer - Bot trades without main key access
"""
import sys
sys.path.insert(0, r"C:\Project\Trading_bot")

from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import LinkSignerParams
from nado_protocol.utils.bytes32 import subaccount_to_bytes32
import config

def setup():
    user_key = config.get_env_variable("NADO_PRIVATE_KEY")
    bot_addr = "0xc4d55282Ab2dD5793820cadCD3c6e8472AF13964"
    user_sub = config.get_subaccount_id()
    
    if not user_key.startswith("0x"):
        user_key = "0x" + user_key
    
    print("="*80)
    print("SETUP LINKED SIGNER")
    print("="*80)
    print(f"User subaccount: {user_sub}")
    print(f"Bot address: {bot_addr}")
    print()
    
    client = create_nado_client(NadoClientMode.MAINNET, user_key)
    print(f"Client wallet: {client.context.signer.address}")
    print()
    
    signer_bytes32 = subaccount_to_bytes32(bot_addr, "default")
    
    params = LinkSignerParams(
        sender=user_sub,
        signer=signer_bytes32
    )
    
    print("Linking bot as signer...")
    print(f"  Sender: {user_sub}")
    print(f"  Signer: {bot_addr}")
    print()
    
    try:
        result = client.context.engine_client.link_signer(params)
        
        if result and hasattr(result, 'status'):
            print(f"SUCCESS! Status: {result.status}")
            print()
            print("="*80)
            print("BOT NOW AUTHORIZED!")
            print("="*80)
            print()
            print("Bot can now:")
            print("  - Trade on your subaccount")
            print("  - Use ONLY BOT_PRIVATE_KEY")
            print("  - NO access to NADO_PRIVATE_KEY needed")
            print()
            print("You can safely remove NADO_PRIVATE_KEY from bot .env!")
            return True
        else:
            print(f"FAILED: {result}")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print()
    print("WARNING: This will authorize bot to trade on your subaccount.")
    print("Run this ONCE, then remove NADO_PRIVATE_KEY from bot .env")
    print()
    
    confirm = input("Continue? (yes/no): ")
    if confirm.lower() in ("yes", "y"):
        setup()
    else:
        print("Cancelled")
