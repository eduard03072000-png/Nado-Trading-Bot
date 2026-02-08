"""
Конфигурация для Nado Trading Bot
Загружает переменные из .env файла
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузить .env файл
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)


def get_env_variable(name: str, default: str = None, required: bool = True) -> str:
    """
    Получить переменную окружения
    
    Args:
        name: Имя переменной
        default: Значение по умолчанию
        required: Обязательна ли переменная
    
    Returns:
        Значение переменной
    
    Raises:
        ValueError: Если обязательная переменная не найдена
    """
    value = os.getenv(name, default)
    
    if required and not value:
        raise ValueError(
            f"❌ Переменная {name} не найдена в .env файле!\n"
            f"   Скопируйте .env.example в .env и заполните своими данными."
        )
    
    return value


# ═══════════════════════════════════════════════════════
# WALLET
# ═══════════════════════════════════════════════════════

def get_nado_key() -> str:
    """Получить приватный ключ для Nado
    
    ПРИОРИТЕТ: BOT_PRIVATE_KEY (Linked Signer)
    Fallback: NADO_PRIVATE_KEY (только для setup_linked_signer.py)
    """
    # ПРИОРИТЕТ: BOT_PRIVATE_KEY (бот как Linked Signer)
    key = get_env_variable("BOT_PRIVATE_KEY", required=False)
    
    # Fallback: NADO_PRIVATE_KEY (только для setup)
    if not key:
        key = get_env_variable("NADO_PRIVATE_KEY", required=False)
    
    if not key:
        raise ValueError(
            "❌ Не найден BOT_PRIVATE_KEY в .env файле!\n"
            "   BOT_PRIVATE_KEY должен быть установлен как Linked Signer.\n"
            "   Запустите: python setup_linked_signer.py"
        )
    
    # Добавить 0x если отсутствует
    if not key.startswith("0x"):
        key = "0x" + key
    
    return key


def get_wallet_address() -> str:
    """Получить адрес кошелька"""
    return get_env_variable("NADO_WALLET_ADDRESS", required=False)


def get_subaccount_id() -> str:
    """Получить subaccount ID (для работы без приватного ключа)"""
    return get_env_variable("NADO_SUBACCOUNT_ID", required=False)


# ═══════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════

def get_telegram_token() -> str:
    return get_env_variable("TELEGRAM_BOT_TOKEN", required=False)

def get_telegram_chat_id() -> str:
    return get_env_variable("TELEGRAM_CHAT_ID", required=False)



# ═══════════════════════════════════════════════════════
# NETWORK
# ═══════════════════════════════════════════════════════

def get_network() -> str:
    """Получить network (mainnet/testnet)"""
    return get_env_variable("NADO_NETWORK", default="testnet", required=False)


def is_mainnet() -> bool:
    """Проверить что используется mainnet"""
    return get_network().lower() == "mainnet"


def get_rpc_url() -> str:
    """Получить RPC URL"""
    return get_env_variable(
        "NADO_RPC_URL",
        default="https://rpc-gel.inkonchain.com/",
        required=False
    )


# ═══════════════════════════════════════════════════════
# TRADING (опционально из .env)
# ═══════════════════════════════════════════════════════

def get_trading_symbol() -> str:
    """Получить торговый символ"""
    return get_env_variable("TRADING_SYMBOL", default="BTC-USDT", required=False)


def get_position_size() -> float:
    """Получить размер позиции"""
    return float(get_env_variable("TRADING_POSITION_SIZE", default="100", required=False))


def get_leverage() -> int:
    """Получить плечо"""
    return int(get_env_variable("TRADING_LEVERAGE", default="1", required=False))


def get_auto_trade() -> bool:
    """Получить режим авто-торговли"""
    value = get_env_variable("TRADING_AUTO_TRADE", default="false", required=False)
    return value.lower() in ("true", "1", "yes")


# ═══════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════

def validate_config():
    """Проверить что все обязательные переменные заданы"""
    errors = []

    # Проверка приватного ключа
    try:
        key = get_nado_key()
        if len(key) != 66:  # 0x + 64 hex chars
            errors.append(
                "❌ NADO_PRIVATE_KEY: неверный формат (должен быть 66 символов с 0x)"
            )
    except ValueError as e:
        errors.append(str(e))

    # Проверка Telegram
    try:
        get_telegram_token()
    except ValueError as e:
        errors.append(str(e))

    try:
        get_telegram_chat_id()
    except ValueError as e:
        errors.append(str(e))

    # Проверка network
    network = get_network()
    if network not in ("mainnet", "testnet"):
        errors.append(
            f"❌ NADO_NETWORK: должен быть 'mainnet' или 'testnet', получен '{network}'"
        )

    # ❗ ВАЖНО: этот блок тоже ВНУТРИ функции
    if errors:
        error_msg = "\n".join(errors)
        raise ValueError(
            f"\n\n{'=' * 60}\nCONFIG ERRORS:\n{'=' * 60}\n"
            f"{error_msg}\n{'=' * 60}\n"
        )

    print("OK Configuration validated successfully!")
    print(f"   Network: {network}")
    print(f"   Wallet: {get_wallet_address() or 'not specified'}")



if __name__ == "__main__":
    # Test configuration
    print("=" * 60)
    print("CONFIGURATION CHECK")
    print("=" * 60)

    try:
        validate_config()
        print("\nOK All variables configured correctly!")
        print(f"\nNetwork: {get_network()}")
        print(f"RPC URL: {get_rpc_url()}")

        if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
            print("Telegram: configured")
        else:
            print("Telegram: not configured")

    except ValueError as e:
        print(e)
        print("\nTip:")
        print("   1. Copy .env.example to .env")
        print("   2. Fill in .env with your data")
        print("   3. Run again: python config.py")
