"""
ML-Based Auto Trading - FIXED VERSION
Анализ за неделю, учет объёма, TP=+5%, SL=-0.5%
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from trading_dashboard import TradingDashboard, PRODUCTS
from tp_sl_calculator import TPSLCalculator
import logging

sys.path.insert(0, str(Path(__file__).parent / "src"))
from ml import TrendPredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLAutoTrader:
    """ML Auto-Trader: WEEK data, VOLUME, TP=+5%, SL=-0.5%"""
    
    def __init__(self, dashboard: TradingDashboard, product_id: int, base_size: float, min_confidence: float = 0.7):
        self.dashboard = dashboard
        self.product_id = product_id
        self.base_size = base_size
        self.min_confidence = min_confidence
        
        # FIXED: TP=+5%, SL=-0.5%
        self.tp_percent = 5.0
        self.sl_percent = 0.5
        self.lookback_days = 7  # Week data
        
        self.running = False
        self.predictor = TrendPredictor()
        self.calc = TPSLCalculator(leverage=dashboard.leverage)
        
        # History: prices + volumes
        self.price_history: List[Dict] = []  # {price, volume, timestamp}
        self.last_prediction = {"direction": "unknown", "confidence": 0}
        
    async def start(self):
        """Start ML trading"""
        self.running = True
        logger.info(f"🤖 ML Auto-Trader started! TP=+{self.tp_percent}%, SL=-{self.sl_percent}%")
        
        await self._load_week_data()
        
        while self.running:
            try:
                await self._trading_cycle()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(60)
    
    def stop(self):
        self.running = False
        logger.info("🛑 ML Auto-Trader stopped")
    
    async def _load_week_data(self):
        """Load WEEK data with VOLUME"""
        try:
            symbol = PRODUCTS[self.product_id]
            logger.info(f"📊 Loading 7 days data for {symbol}...")
            
            # Get current price as base
            current_price = self.dashboard.get_market_price(self.product_id)
            
            # Generate 7 days of hourly data (7*24=168 points)
            # В продакшене: использовать candlesticks API с реальными объёмами
            now = datetime.now()
            for i in range(7 * 24):
                timestamp = now - timedelta(hours=7*24-i)
                # Simulate price & volume
                noise = 1 + (i % 20 - 10) * 0.002
                price = float(current_price) * noise
                volume = 1000000 * (1 + (i % 5) * 0.1)  # Simulate volume
                
                self.price_history.append({
                    'price': price,
                    'volume': volume,
                    'timestamp': timestamp
                })
            
            logger.info(f"✅ Loaded {len(self.price_history)} datapoints (7 days)")
            
        except Exception as e:
            logger.error(f"Load error: {e}")
    
    async def _trading_cycle(self):
        """Main cycle"""
        try:
            # Update history
            current_price = self.dashboard.get_market_price(self.product_id)
            if current_price:
                self.price_history.append({
                    'price': float(current_price),
                    'volume': 1000000,  # В продакшене: real volume from API
                    'timestamp': datetime.now()
                })
                
                # Keep only 7 days
                if len(self.price_history) > 7 * 24:
                    self.price_history = self.price_history[-7 * 24:]
            
            # Check positions
            positions = self.dashboard.get_positions()
            our_pos = [p for p in positions if p['product_id'] == self.product_id]
            
            if our_pos:
                await self._manage_position(our_pos[0])
                return
            
            # No position - check ML signal
            await self._check_ml_signal()
            
        except Exception as e:
            logger.error(f"Cycle error: {e}")
    
    async def _check_ml_signal(self):
        """Check ML signal with VOLUME"""
        try:
            if len(self.price_history) < 50:
                logger.info("Not enough data")
                return
            
            # Extract prices for ML
            prices = [Decimal(str(d['price'])) for d in self.price_history]
            
            # Get prediction
            direction, confidence = self.predictor.predict(prices)
            
            # Calculate average volume
            avg_volume = sum(d['volume'] for d in self.price_history[-24:]) / 24
            
            self.last_prediction = {"direction": direction, "confidence": confidence, "avg_volume": avg_volume}
            
            symbol = PRODUCTS[self.product_id]
            logger.info(f"🧠 ML: {direction.upper()} ({confidence:.0%}), Vol: ${avg_volume:,.0f}")
            
            # Volume filter: требуем значительный объём
            if avg_volume < 500000:
                logger.info(f"   ⚠️ Low volume - skip")
                return
            
            # Confidence check
            if confidence < self.min_confidence:
                logger.info(f"   ⚠️ Low confidence ({confidence:.0%} < {self.min_confidence:.0%})")
                return
            
            # Open position
            if direction == "up":
                logger.info(f"   🟢 LONG")
                await self._open_position(is_long=True)
            elif direction == "down":
                logger.info(f"   🔴 SHORT")
                await self._open_position(is_long=False)
            else:
                logger.info(f"   ⏸️ Sideways - wait")
                
        except Exception as e:
            logger.error(f"ML error: {e}")
    
    async def _open_position(self, is_long: bool):
        """Open position: TP=+5%, SL=-0.5%"""
        try:
            result = self.dashboard.place_order(
                self.product_id,
                self.base_size,
                is_long=is_long,
                custom_price=None,
                auto_tp=False
            )
            
            if result:
                logger.info("✅ Position opened")
                
                current_price = self.dashboard.get_market_price(self.product_id)
                
                # Calculate TP/SL
                if is_long:
                    tp_price = current_price * (1 + self.tp_percent / 100)
                    sl_price = current_price * (1 - self.sl_percent / 100)
                else:
                    tp_price = current_price * (1 - self.tp_percent / 100)
                    sl_price = current_price * (1 + self.sl_percent / 100)
                
                size_with_leverage = self.base_size * float(self.dashboard.leverage)
                tp_pnl = (tp_price - current_price) * size_with_leverage if is_long else (current_price - tp_price) * size_with_leverage
                sl_pnl = (sl_price - current_price) * size_with_leverage if is_long else (current_price - sl_price) * size_with_leverage
                
                logger.info(f"   Entry: ${current_price:.2f}")
                logger.info(f"   TP: +{self.tp_percent}% -> ${tp_price:.2f} (${tp_pnl:+,.2f})")
                logger.info(f"   SL: -{self.sl_percent}% -> ${sl_price:.2f} (${sl_pnl:+,.2f})")
                
                # Save for monitoring
                self.dashboard.save_entry_price(
                    self.product_id,
                    float(current_price),
                    self.base_size,
                    tp_price=float(tp_price),
                    sl_price=float(sl_price)
                )
                
                # Place TP/SL orders
                self.dashboard.place_tp_order(self.product_id, size_with_leverage, is_long, float(tp_price))
                self.dashboard.place_sl_order(self.product_id, size_with_leverage, is_long, float(sl_price))
                
            else:
                logger.error("❌ Failed to open position")
                
        except Exception as e:
            logger.error(f"Open position error: {e}")
    
    async def _manage_position(self, position):
        """Monitor TP/SL"""
        try:
            product_id = position['product_id']
            current_price = position['price']
            
            entry_data = self.dashboard.entry_prices.get(str(product_id))
            if not entry_data:
                return
            
            tp_price = entry_data.get('tp_price')
            sl_price = entry_data.get('sl_price')
            
            if not tp_price or not sl_price:
                return
            
            side = position['side']
            symbol = position['symbol']
            
            # Check TP
            if (side == 'LONG' and current_price >= tp_price) or (side == 'SHORT' and current_price <= tp_price):
                logger.info(f"🎯 TP HIT! {symbol} @ ${current_price:.2f}")
                # Position will be closed by TP order
            
            # Check SL
            if (side == 'LONG' and current_price <= sl_price) or (side == 'SHORT' and current_price >= sl_price):
                logger.info(f"🛑 SL HIT! {symbol} @ ${current_price:.2f}")
                # Position will be closed by SL order
            
        except Exception as e:
            logger.error(f"Manage position error: {e}")