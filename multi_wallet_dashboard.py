"""
Multi-Wallet Trading Dashboard
Управление торговлей с нескольких кошельков
"""
import config
from trading_dashboard_v2 import TradingDashboard, PRODUCTS
from nado_protocol.client import create_nado_client, NadoClientMode
import logging

logger = logging.getLogger(__name__)

class MultiWalletDashboard:
    """Управление несколькими кошельками"""
    
    def __init__(self, leverage=10):
        """Инициализация с несколькими кошельками"""
        self.wallets = {}
        self.active_wallet = 1
        
        # Инициализируем первый кошелек
        try:
            self.wallets[1] = self._create_dashboard(wallet_num=1, leverage=leverage)
            logger.info(f"✅ Wallet 1 initialized: {self.wallets[1].wallet}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Wallet 1: {e}")
            raise
        
        # Пытаемся инициализировать второй кошелек
        try:
            key2 = config.get_nado_key(wallet_num=2)
            if key2:
                self.wallets[2] = self._create_dashboard(wallet_num=2, leverage=leverage)
                logger.info(f"✅ Wallet 2 initialized: {self.wallets[2].wallet}")
        except Exception as e:
            logger.warning(f"⚠️ Wallet 2 not configured: {e}")
    
    def _create_dashboard(self, wallet_num: int, leverage: int):
        """Создать dashboard для конкретного кошелька"""
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        
        # Создаем клиент
        private_key = config.get_nado_key(wallet_num)
        client = create_nado_client(mode=mode, signer=private_key)
        
        # Создаем dashboard
        dashboard = TradingDashboard.__new__(TradingDashboard)
        dashboard.network = network
        dashboard.client = client
        dashboard.wallet = client.context.signer.address
        
        # ✅ Проверяем наличие subaccount
        subaccount_id = config.get_subaccount_id(wallet_num)
        
        if subaccount_id:
            # ЕСТЬ SUBACCOUNT - используем его (как Wallet 2)
            dashboard.sender_hex = subaccount_id
            dashboard.subaccount_hex = subaccount_id
            logger.info(f"✅ Wallet {wallet_num} using SUBACCOUNT: {subaccount_id}")
        else:
            # НЕТ SUBACCOUNT - торгуем НАПРЯМУЮ с кошелька
            # Создаём sender_hex: адрес + padding нулями до 32 байт
            from nado_protocol.utils import SubaccountParams, subaccount_to_hex
            params = SubaccountParams(
                subaccount_owner=dashboard.wallet,
                subaccount_name=""  # Пустая строка = торговля напрямую
            )
            dashboard.sender_hex = subaccount_to_hex(params)
            dashboard.subaccount_hex = dashboard.sender_hex
            logger.info(f"✅ Wallet {wallet_num} using DIRECT TRADING (no subaccount): {dashboard.sender_hex}")
        
        # Настройки
        dashboard.leverage = leverage
        dashboard.margin_mode = "AUTO"
        
        # Хранилище для entry prices (разные файлы для каждого кошелька)
        import os
        dashboard.positions_file = os.path.join(
            os.path.dirname(__file__), 
            f"positions_data_wallet{wallet_num}.json"
        )
        dashboard.entry_prices = dashboard.load_positions_data()
        
        # История торговли
        dashboard.history_file = os.path.join(
            os.path.dirname(__file__), 
            f"trade_history_wallet{wallet_num}.json"
        )
        dashboard.trade_history = dashboard.load_trade_history()
        
        return dashboard
    
    def get_isolated_dashboard(self, wallet_num):
        """Получить изолированный dashboard для автономной работы (для автогрида)"""
        return self.wallets[wallet_num]
    
    def switch_wallet(self, wallet_num: int):
        """Переключиться на другой кошелек"""
        if wallet_num not in self.wallets:
            raise ValueError(f"Кошелек {wallet_num} не инициализирован")
        self.active_wallet = wallet_num
        logger.info(f"🔄 Переключено на Wallet {wallet_num}")
    
    def get_current_dashboard(self) -> TradingDashboard:
        """Получить текущий активный dashboard"""
        return self.wallets[self.active_wallet]
    
    def get_all_balances(self):
        """Получить балансы всех кошельков"""
        balances = {}
        for wallet_num, dashboard in self.wallets.items():
            try:
                balance = dashboard.get_balance()
                balances[wallet_num] = {
                    'address': dashboard.wallet,
                    'balance': balance
                }
            except Exception as e:
                logger.error(f"Ошибка получения баланса кошелька {wallet_num}: {e}")
                balances[wallet_num] = None
        return balances
    
    def get_all_positions(self):
        """Получить позиции со всех кошельков"""
        all_positions = {}
        for wallet_num, dashboard in self.wallets.items():
            try:
                positions = dashboard.get_positions()
                all_positions[wallet_num] = {
                    'address': dashboard.wallet,
                    'positions': positions
                }
            except Exception as e:
                logger.error(f"Ошибка получения позиций кошелька {wallet_num}: {e}")
                all_positions[wallet_num] = None
        return all_positions
    
    # Proxy методы для текущего активного кошелька
    @property
    def leverage(self):
        return self.get_current_dashboard().leverage
    
    @leverage.setter
    def leverage(self, value):
        self.get_current_dashboard().leverage = value
    
    @property
    def network(self):
        return self.get_current_dashboard().network
    
    @property
    def wallet(self):
        return self.get_current_dashboard().wallet
    
    @property
    def sender_hex(self):
        return self.get_current_dashboard().sender_hex
    
    @property
    def client(self):
        return self.get_current_dashboard().client
    
    @property
    def entry_prices(self):
        return self.get_current_dashboard().entry_prices
    
    @property  
    def positions_file(self):
        return self.get_current_dashboard().positions_file
    
    def get_balance(self):
        return self.get_current_dashboard().get_balance()
    
    def get_positions(self):
        return self.get_current_dashboard().get_positions()
    
    def place_order(self, *args, **kwargs):
        return self.get_current_dashboard().place_order(*args, **kwargs)
    
    def close_position(self, *args, **kwargs):
        return self.get_current_dashboard().close_position(*args, **kwargs)
    
    def get_market_price(self, *args, **kwargs):
        return self.get_current_dashboard().get_market_price(*args, **kwargs)
    
    def set_leverage(self, *args, **kwargs):
        return self.get_current_dashboard().set_leverage(*args, **kwargs)
    
    def get_open_orders(self, *args, **kwargs):
        return self.get_current_dashboard().get_open_orders(*args, **kwargs)
    
    def cancel_all_orders(self, *args, **kwargs):
        return self.get_current_dashboard().cancel_all_orders(*args, **kwargs)
    
    def cancel_product_orders(self, *args, **kwargs):
        """Прокси для отмены ордеров по продуктам (для автогрида)"""
        return self.get_current_dashboard().client.market.cancel_product_orders(*args, **kwargs)
    
    def place_tp_order(self, *args, **kwargs):
        return self.get_current_dashboard().place_tp_order(*args, **kwargs)
    
    def place_limit_close_order(self, *args, **kwargs):
        return self.get_current_dashboard().place_limit_close_order(*args, **kwargs)
