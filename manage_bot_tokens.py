"""
Управление Bot Tokens для NADO DEX
"""
import sys
import config
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import LinkBotTokenParams
import json


def check_bot_token(subaccount_id):
    """Проверить существует ли бот токен для субаккаунта"""
    try:
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        client = create_nado_client(mode=mode, signer=config.get_nado_key())
        
        # Проверяем существующие токены
        # Метод может называться get_bot_tokens, list_bot_tokens и т.д.
        # Нужно проверить документацию
        
        print(f"📊 Доступные методы subaccount:")
        methods = [m for m in dir(client.subaccount) if not m.startswith('_')]
        for m in methods:
            if 'token' in m.lower() or 'link' in m.lower():
                print(f"  - {m}")
        
        return None
        
    except Exception as e:
        print(f"❌ Ошибка проверки токена: {e}")
        return None


def create_bot_token(subaccount_id):
    """Создать бот токен для субаккаунта"""
    try:
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        client = create_nado_client(mode=mode, signer=config.get_nado_key())
        
        bot_address = client.context.signer.address
        
        print(f"🔗 Создание бот токена:")
        print(f"  Bot: {bot_address}")
        print(f"  Subaccount: {subaccount_id}")
        
        # Пытаемся создать токен через link_bot_token
        params = LinkBotTokenParams(
            sender=subaccount_id,
            bot=bot_address
        )
        
        result = client.subaccount.link_bot_token(params)
        
        print(f"✅ Бот токен создан!")
        print(f"  Status: {result.status if hasattr(result, 'status') else 'OK'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания токена: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: python manage_bot_tokens.py <command> <subaccount_id>")
        print("Commands:")
        print("  check  - проверить токен")
        print("  create - создать токен")
        print("\nExample:")
        print("  python manage_bot_tokens.py create 0xb6da54b9cd60832d33d1a401933d48dee774dcfa64656661756c740000000000")
        return
    
    command = sys.argv[1]
    subaccount_id = sys.argv[2]
    
    if command == "check":
        check_bot_token(subaccount_id)
    elif command == "create":
        create_bot_token(subaccount_id)
    else:
        print(f"❌ Неизвестная команда: {command}")


if __name__ == '__main__':
    main()
