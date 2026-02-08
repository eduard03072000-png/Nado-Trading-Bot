"""
Multi-User Dashboard Manager
Creates isolated dashboard instances for each registered user
"""
from trading_dashboard_v2 import PRODUCTS
from nado_protocol.client import create_nado_client, NadoClientMode
from decimal import Decimal
import config

class UserDashboard:
    """
    User-specific trading dashboard
    Each user gets isolated instance with their own Linked Signer
    """
    
    def __init__(self, user_data: dict):
        """
        Initialize dashboard for specific user
        
        Args:
            user_data: User data from UserManager
        """
        self.telegram_id = user_data['telegram_id']
        self.account_name = user_data['account_name']
        self.wallet_address = user_data['wallet_address']
        self.subaccount_id = user_data['subaccount_id']
        self.bot_private_key = user_data['bot_private_key']
        self.bot_address = user_data['bot_address']
        self.leverage = Decimal(str(user_data.get('leverage', 10)))
        
        # Create NADO client with user's bot key (Linked Signer)
        network = config.get_network()
        self.network = network
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        self.client = create_nado_client(mode=mode, signer=self.bot_private_key)
        
        # Addresses for display
        self.user_address = self.wallet_address
        self.user_subaccount = self.subaccount_id
    
    def get_market_price(self, product_id: int):
        """Get current market price"""
        try:
            price_data = self.client.market.get_latest_market_price(product_id)
            if not price_data or not hasattr(price_data, 'bid_x18'):
                return None
            
            bid = Decimal(str(price_data.bid_x18)) / Decimal(10**18)
            ask = Decimal(str(price_data.ask_x18)) / Decimal(10**18)
            return float((bid + ask) / 2)
        except Exception as e:
            print(f"Error getting price: {e}")
        return None
    
    def normalize_size(self, product_id: int, size: Decimal) -> Decimal:
        """Round size to step"""
        SIZE_INCREMENTS = {
            8: Decimal("0.01"),  # SOL
            9: Decimal("0.001"), # BTC
            10: Decimal("0.01"), # ETH
        }
        from decimal import ROUND_DOWN
        step = SIZE_INCREMENTS.get(product_id, Decimal("0.01"))
        return size.quantize(step, rounding=ROUND_DOWN)
    
    def place_order(self, product_id: int, size, is_long: bool, custom_price=None):
        """Place order"""
        try:
            from nado_protocol.engine_client.types.execute import PlaceOrderParams
            from nado_protocol.utils.execute import OrderParams
            from nado_protocol.utils.order import build_appendix, OrderType
            import time
            
            PRICE_INCREMENTS_X18 = {
                8: 10000000000000000,   # SOL: 0.01
                9: 1000000000000000,    # BTC: 0.001
                10: 10000000000000000,  # ETH: 0.01
            }
            
            size = Decimal(size)
            size = self.normalize_size(product_id, size)
            
            size_with_leverage = size * self.leverage
            size_with_leverage = self.normalize_size(product_id, size_with_leverage)
            
            amount_x18 = int((size_with_leverage * Decimal(10**18)).to_integral_value())
            
            if not is_long:
                amount_x18 = -amount_x18
            
            # Get price
            if custom_price is not None:
                price = custom_price
            else:
                price = self.get_market_price(product_id)
                if not price:
                    raise ValueError("Failed to get market price")
            
            price_decimal = Decimal(str(price))
            
            # Round to price increment
            price_increment = PRICE_INCREMENTS_X18.get(product_id, 10000000000000000)
            price_x18_raw = int((price_decimal * Decimal(10**18)).to_integral_value())
            price_x18 = (price_x18_raw // price_increment) * price_increment
            
            appendix = build_appendix(
                order_type=OrderType.DEFAULT,
                isolated=False,
                reduce_only=False
            )
            
            expiration = int(time.time()) + 60
            
            # Place on user's subaccount
            order = OrderParams(
                sender=self.user_subaccount,
                amount=amount_x18,
                priceX18=price_x18,
                expiration=expiration,
                appendix=appendix
            )
            
            params = PlaceOrderParams(
                product_id=product_id,
                order=order
            )
            
            result = self.client.market.place_order(params)
            
            return result if result and hasattr(result, 'status') else None
                
        except Exception as e:
            print(f"Error placing order: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_positions(self):
        """Get user positions"""
        try:
            summary = self.client.subaccount.get_engine_subaccount_summary(self.user_subaccount)
            positions = []
            
            if hasattr(summary, 'perp_balances') and summary.perp_balances:
                for balance in summary.perp_balances:
                    product_id = balance.product_id
                    amount = float(balance.balance.amount) / 1e18
                    
                    if abs(amount) < 0.0001:
                        continue
                    
                    symbol = PRODUCTS.get(product_id, f"UNKNOWN-{product_id}")
                    price = self.get_market_price(product_id)
                    
                    positions.append({
                        "product_id": product_id,
                        "symbol": symbol,
                        "amount": amount,
                        "side": "LONG" if amount > 0 else "SHORT",
                        "price": price,
                        "notional": price * abs(amount) if price else None
                    })
            
            return positions
        except Exception as e:
            print(f"Error getting positions: {e}")
            return []
    
    def close_position(self, product_id: int):
        """Close position"""
        try:
            positions = self.get_positions()
            pos = next((p for p in positions if p['product_id'] == product_id), None)
            
            if not pos:
                return None
            
            is_long = pos['amount'] < 0
            size = abs(pos['amount']) / float(self.leverage)
            
            return self.place_order(product_id, size, is_long)
            
        except Exception as e:
            print(f"Error closing position: {e}")
            return None
    
    def get_balance(self):
        """Get user balance"""
        try:
            summary = self.client.subaccount.get_engine_subaccount_summary(self.user_subaccount)
            
            if hasattr(summary, 'healths') and summary.healths and len(summary.healths) > 0:
                health = summary.healths[0]
                return {
                    "assets": float(health.assets) / 1e18,
                    "liabilities": float(health.liabilities) / 1e18,
                    "equity": (float(health.assets) - float(health.liabilities)) / 1e18,
                    "health": float(health.health) / 1e18
                }
        except Exception as e:
            print(f"Error getting balance: {e}")
        
        return None


# Dashboard cache - one instance per user
_dashboard_cache = {}

def get_user_dashboard(user_data: dict) -> UserDashboard:
    """Get or create dashboard for user"""
    telegram_id = user_data['telegram_id']
    
    # Update leverage if changed
    if telegram_id in _dashboard_cache:
        dashboard = _dashboard_cache[telegram_id]
        new_leverage = Decimal(str(user_data.get('leverage', 10)))
        if dashboard.leverage != new_leverage:
            dashboard.leverage = new_leverage
    else:
        _dashboard_cache[telegram_id] = UserDashboard(user_data)
    
    return _dashboard_cache[telegram_id]

def clear_user_dashboard(telegram_id: int):
    """Clear cached dashboard for user"""
    if telegram_id in _dashboard_cache:
        del _dashboard_cache[telegram_id]
