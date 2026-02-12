"""
Nado DEX Client - OFFICIAL SDK VERSION
Uses official nado-protocol SDK for real trading
Based on working bot from: github.com/Furia-cell/nado_bot
"""
from decimal import Decimal
from typing import Optional, List, Dict
import logging
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.utils import SubaccountParams, subaccount_to_hex

logger = logging.getLogger(__name__)


class NadoSDKClient:
    """Wrapper around official Nado Protocol SDK"""
    
    def __init__(self, private_key: str, network: str = "testnet", subaccount_name: str = ""):
        """
        Initialize Nado SDK client
        
        Args:
            private_key: Private key (with or without 0x)
            network: "mainnet" or "testnet"
            subaccount_name: Subaccount name (empty string "" = trade directly from wallet)
        """
        self.network = network
        self.subaccount_name = subaccount_name
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        
        logger.info(f"Initializing Nado SDK client for {network}")
        self.client = create_nado_client(mode=mode, signer=private_key)
        
        self.address = self.client.context.signer.address
        
        # Получаем sender_hex
        # Пустая строка "" = торговля напрямую с кошелька (без субаккаунта)
        params = SubaccountParams(
            subaccount_owner=self.address, 
            subaccount_name=subaccount_name
        )
        self.sender_hex = subaccount_to_hex(params)
        
        self.products = self.client.market.get_all_product_symbols()
        
        logger.info(f"SDK Client ready: {self.address}")
        if subaccount_name:
            logger.info(f"Subaccount: {subaccount_name} ({self.sender_hex[:10]}...)")
        else:
            logger.info(f"Trading directly from wallet (no subaccount)")
        logger.info(f"Loaded {len(self.products)} products")
    
    def get_product_id(self, symbol: str) -> Optional[int]:
        """Get product ID by symbol (e.g. 'BTC-PERP' -> 2)"""
        for prod in self.products:
            if prod.symbol == symbol or prod.symbol.upper() == symbol.upper():
                return prod.product_id
        return None
    
    def get_market_price_sync(self, symbol: str, use_mark_price: bool = False) -> Optional[Decimal]:
        """
        Get market price for symbol
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTC-PERP')
            use_mark_price: Use mark price instead of orderbook mid (default: False)
        
        Returns:
            Mid price as Decimal or None
        """
        product_id = self.get_product_id(symbol)
        if not product_id:
            logger.warning(f"Product {symbol} not found")
            return None
        
        try:
            # Mark price (если запрошен)
            if use_mark_price:
                prices = self.client.perp.get_prices(product_id)
                if isinstance(prices, dict):
                    for key in ("mark", "mark_price", "index", "index_price"):
                        if key in prices and prices[key] is not None:
                            return Decimal(str(prices[key]))
                if isinstance(prices, (list, tuple)) and prices:
                    return Decimal(str(prices[0]))
            
            # Latest market price (bid/ask)
            price = self.client.market.get_latest_market_price(product_id)
            
            if isinstance(price, dict):
                if "bid_x18" in price and "ask_x18" in price:
                    bid = Decimal(str(price["bid_x18"])) / Decimal(10**18)
                    ask = Decimal(str(price["ask_x18"])) / Decimal(10**18)
                    mid = (bid + ask) / Decimal("2")
                    logger.debug(f"Price {symbol}: bid={bid}, ask={ask}, mid={mid}")
                    return mid
                if "mid" in price:
                    return Decimal(str(price["mid"]))
            
            if hasattr(price, "bid_x18") and hasattr(price, "ask_x18"):
                bid = Decimal(str(getattr(price, "bid_x18"))) / Decimal(10**18)
                ask = Decimal(str(getattr(price, "ask_x18"))) / Decimal(10**18)
                return (bid + ask) / Decimal("2")
            
            # Fallback
            return Decimal(str(price))
            
        except Exception as e:
            logger.error(f"Get price error for {symbol}: {e}")
            return None
    
    async def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        size: Decimal,
        price: Optional[Decimal] = None  # None = market order
    ) -> Optional[Dict]:
        """
        Place order
        
        Args:
            symbol: Trading pair (e.g. 'BTC-PERP')
            side: "buy" or "sell"
            size: Order size
            price: Limit price (None for market order)
        """
        product_id = self.get_product_id(symbol)
        if not product_id:
            logger.error(f"Product {symbol} not found")
            return None
        
        try:
            from nado_protocol.engine_client.types import OrderParams, PlaceOrderParams
            from nado_protocol.utils import get_expiration_timestamp, gen_order_nonce, to_x18
            from nado_protocol.utils.order import OrderType, build_appendix
            
            # Конвертируем amount в int (x18)
            amount_decimals = 18  # Nado использует 18 decimals
            amount_value = int(size * Decimal(10**amount_decimals))
            signed_amount = -amount_value if side.lower() == "sell" else amount_value
            
            # Market order: используем текущую цену с небольшим slippage
            if price is None:
                # Получаем текущую цену
                current_price = await self.get_market_price(symbol)
                if not current_price:
                    logger.error(f"Could not get price for {symbol}")
                    return None
                
                # Добавляем 0.5% slippage
                slippage = Decimal("0.005")
                if side.lower() == "buy":
                    price = current_price * (Decimal("1") + slippage)
                else:
                    price = current_price * (Decimal("1") - slippage)
                
                post_only = False  # Market order
                logger.info(f"Market order: {side} {size} {symbol} @ ~{price}")
            else:
                post_only = True  # Limit order
                logger.info(f"Limit order: {side} {size} {symbol} @ {price}")
            
            # Создаём ордер
            order_type = OrderType.POST_ONLY if post_only else OrderType.DEFAULT
            appendix = build_appendix(order_type, reduce_only=False)
            expiration = get_expiration_timestamp(60)  # 60 sec
            nonce = gen_order_nonce()
            
            order = OrderParams(
                priceX18=to_x18(float(price)),
                amount=signed_amount,
                nonce=nonce,
                expiration=expiration,
                sender=self.sender_hex,
                appendix=appendix,
            )
            
            params = PlaceOrderParams(product_id=product_id, order=order)
            resp = self.client.market.place_order(params)
            
            logger.info(f"Order placed successfully: {side} {size} {symbol}")
            return {"response": resp, "order": order}
        
        except Exception as e:
            logger.error(f"Place order error: {e}", exc_info=True)
            return None
    
    async def cancel_order(self, product_id: int, digest: str) -> bool:
        """Cancel order"""
        try:
            await self.client.perp.cancel_orders(
                product_id=product_id,
                digests=[digest]
            )
            logger.info(f"Order cancelled: {digest}")
            return True
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False
    
    async def get_balance(self) -> Optional[Dict]:
        """Get account balance"""
        try:
            # Используем sender_hex как в рабочем боте
            summary = self.client.subaccount.get_engine_subaccount_summary(self.sender_hex)
            
            result = {"raw": str(summary)}
            
            # Парсим health если есть
            if hasattr(summary, 'healths') and summary.healths and len(summary.healths) > 0:
                health = summary.healths[0]
                result["assets"] = float(health.assets) / 1e18
                result["liabilities"] = float(health.liabilities) / 1e18
                result["health_value"] = float(health.health) / 1e18
                result["equity"] = result["assets"] - result["liabilities"]
            
            return result
        except Exception as e:
            logger.error(f"Balance error: {e}", exc_info=True)
            return None
    
    async def get_positions(self) -> List[Dict]:
        """Get open positions"""
        try:
            summary = self.client.subaccount.get_engine_subaccount_summary(self.sender_hex)
            
            positions = []
            
            # Парсим perp_balances как в рабочем боте
            if hasattr(summary, 'perp_balances') and summary.perp_balances:
                for balance in summary.perp_balances:
                    product_id = balance.product_id
                    amount = float(balance.balance.amount) / 1e18
                    
                    # Пропускаем нулевые позиции
                    if amount == 0:
                        continue
                    
                    # Получаем символ
                    symbol = None
                    for prod in self.products:
                        if prod.product_id == product_id:
                            symbol = prod.symbol
                            break
                    
                    # Entry price
                    v_quote = float(balance.balance.v_quote_balance) / 1e18
                    entry_price = abs(v_quote / amount) if amount != 0 else 0
                    
                    positions.append({
                        "product_id": product_id,
                        "symbol": symbol or f"Product {product_id}",
                        "size": amount,
                        "entry_price": entry_price,
                        "side": "LONG" if amount > 0 else "SHORT"
                    })
            
            logger.info(f"Found {len(positions)} positions")
            return positions
            
        except Exception as e:
            logger.error(f"Positions error: {e}", exc_info=True)
            return []
    
    async def close_position(self, symbol: str) -> bool:
        """Close position"""
        try:
            # Получаем текущие позиции
            positions = await self.get_positions()
            
            # Находим позицию
            target_pos = None
            for pos in positions:
                if pos["symbol"] == symbol or pos["symbol"].upper() == symbol.upper():
                    target_pos = pos
                    break
            
            if not target_pos:
                logger.warning(f"Position {symbol} not found")
                return False
            
            # Закрываем обратным ордером
            close_side = "sell" if target_pos["side"] == "LONG" else "buy"
            close_size = abs(Decimal(str(target_pos["size"])))
            
            logger.info(f"Closing position: {close_side} {close_size} {symbol}")
            
            result = await self.place_order(
                symbol=symbol,
                side=close_side,
                size=close_size,
                price=None  # Market order
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Close position error: {e}", exc_info=True)
            return False


# Backward compatibility alias
NadoGatewayClient = NadoSDKClient
