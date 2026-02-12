"""
ML-Based Auto Trading - PRODUCTION VERSION
Real data from Binance API + Trained ML Model
"""
import asyncio
import pickle
import numpy as np
from pathlib import Path
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import datetime
import logging

from trading_dashboard_v2 import TradingDashboard, PRODUCTS
from historical_data_provider import HistoricalDataProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLAutoTrader:
    """ML Auto-Trader with Real Data & Trained Model"""
    
    def __init__(
        self,
        dashboard: TradingDashboard,
        product_id: int,
        base_size: float,
        tp_percent: float = 5.0,
        sl_percent: float = 0.5,
        min_confidence: float = 0.55,
        lookback_days: int = 7
    ):
        self.dashboard = dashboard
        self.product_id = product_id
        self.base_size = base_size
        self.tp_percent = tp_percent
        self.sl_percent = sl_percent
        self.min_confidence = min_confidence
        self.lookback_days = lookback_days
        
        # Load trained ML model
        model_path = Path("ml_model_trained.pkl")
        if model_path.exists():
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            logger.info(f"✅ ML model loaded from {model_path}")
        else:
            logger.error(f"❌ ML model not found: {model_path}")
            self.model = None
        
        self.running = False
        self.data_provider = HistoricalDataProvider()
        self.last_prediction = {"direction": "unknown", "confidence": 0}
    
    async def start(self):
        """Start ML trading"""
        if not self.model:
            logger.error("❌ Cannot start: ML model not loaded!")
            return
        
        self.running = True
        symbol = PRODUCTS[self.product_id]
        logger.info(f"🤖 ML Auto-Trader started for {symbol}!")
        logger.info(f"   TP: +{self.tp_percent}%, SL: -{self.sl_percent}%")
        logger.info(f"   Min confidence: {self.min_confidence:.0%}")
        
        # Initialize data provider
        await self.data_provider.__aenter__()
        
        try:
            while self.running:
                try:
                    await self._trading_cycle()
                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Cycle error: {e}")
                    import traceback
                    traceback.print_exc()
                    await asyncio.sleep(60)
        finally:
            await self.data_provider.__aexit__(None, None, None)
    
    def stop(self):
        self.running = False
        logger.info("🛑 ML Auto-Trader stopped")
    
    def _prepare_features(self, candles: List[Dict], lookback=24) -> Optional[np.ndarray]:
        """Prepare features from candles (same as training)"""
        try:
            if len(candles) < lookback:
                return None
            
            window = candles[-lookback:]
            closes = np.array([c['close'] for c in window])
            volumes = np.array([c['volume'] for c in window])
            highs = np.array([c['high'] for c in window])
            lows = np.array([c['low'] for c in window])
            
            features = []
            
            # 1. Price returns
            returns = np.diff(closes) / closes[:-1]
            features.extend([
                np.mean(returns),
                np.std(returns),
                np.max(returns),
                np.min(returns)
            ])
            
            # 2. Moving averages
            ma_5 = np.mean(closes[-5:])
            ma_10 = np.mean(closes[-10:])
            ma_20 = np.mean(closes)
            current_price = closes[-1]
            
            features.extend([
                (current_price - ma_5) / ma_5,
                (current_price - ma_10) / ma_10,
                (current_price - ma_20) / ma_20,
                (ma_5 - ma_10) / ma_10,
                (ma_10 - ma_20) / ma_20
            ])
            
            # 3. RSI
            gains = returns[returns > 0]
            losses = -returns[returns < 0]
            avg_gain = np.mean(gains) if len(gains) > 0 else 0
            avg_loss = np.mean(losses) if len(losses) > 0 else 0
            rs = avg_gain / avg_loss if avg_loss != 0 else 100
            rsi = 100 - (100 / (1 + rs))
            features.append(rsi / 100)
            
            # 4. Volatility
            volatility = np.std(returns)
            features.append(volatility)
            
            # 5. Volume
            avg_volume = np.mean(volumes)
            current_volume = volumes[-1]
            features.extend([
                (current_volume - avg_volume) / avg_volume,
                np.std(volumes) / avg_volume
            ])
            
            # 6. Price range
            avg_range = np.mean(highs - lows)
            current_range = highs[-1] - lows[-1]
            features.append((current_range - avg_range) / avg_range)
            
            return np.array(features).reshape(1, -1)
            
        except Exception as e:
            logger.error(f"Feature prep error: {e}")
            return None
    
    async def _trading_cycle(self):
        """Main trading cycle"""
        try:
            # Check current position
            positions = self.dashboard.get_positions()
            our_pos = next((p for p in positions if p['product_id'] == self.product_id), None)
            
            if our_pos:
                logger.info(f"📊 Position active: {our_pos['side']} {abs(our_pos['amount']):.4f}")
                return  # Position already open
            
            # No position - check ML signal
            await self._check_ml_signal()
            
        except Exception as e:
            logger.error(f"Trading cycle error: {e}")
    
    async def _check_ml_signal(self):
        """Check ML signal with real data"""
        try:
            # Load recent data
            candles = await self.data_provider.get_historical_klines(
                product_id=self.product_id,
                interval="1h",
                days=2  # Last 48 hours
            )
            
            if not candles or len(candles) < 24:
                logger.warning("Not enough data for prediction")
                return
            
            # Prepare features
            features = self._prepare_features(candles, lookback=24)
            if features is None:
                return
            
            # Get ML prediction
            prediction_proba = self.model.predict_proba(features)[0]
            prediction_class = self.model.predict(features)[0]
            
            # Class 0 = DOWN, Class 1 = UP
            direction = "UP" if prediction_class == 1 else "DOWN"
            confidence = prediction_proba[prediction_class]
            
            # Get volume
            avg_volume = np.mean([c['volume'] for c in candles[-24:]])
            current_volume = candles[-1]['volume']
            
            self.last_prediction = {
                "direction": direction,
                "confidence": confidence,
                "avg_volume": avg_volume
            }
            
            symbol = PRODUCTS[self.product_id]
            logger.info(f"🧠 ML: {direction} ({confidence:.0%}), Vol: ${avg_volume:,.0f}")
            
            # Volume filter
            if avg_volume < 100000:  # Lowered threshold for crypto
                logger.info(f"   ⚠️ Low volume - skip")
                return
            
            # Confidence check
            if confidence < self.min_confidence:
                logger.info(f"   ⚠️ Low confidence ({confidence:.0%} < {self.min_confidence:.0%})")
                return
            
            # Open position
            if direction == "UP":
                logger.info(f"   🟢 Opening LONG")
                await self._open_position(is_long=True)
            else:
                logger.info(f"   🔴 Opening SHORT")
                await self._open_position(is_long=False)
                
        except Exception as e:
            logger.error(f"ML signal error: {e}")
            import traceback
            traceback.print_exc()
    
    async def _open_position(self, is_long: bool):
        """Open position with TP/SL - LIMIT ORDER + SL ORDER"""
        try:
            # Get current price
            current_price = self.dashboard.get_market_price(self.product_id)
            if not current_price:
                logger.error("Cannot get current price!")
                return
            
            # Calculate entry price slightly better than market
            # For LONG: buy slightly below market
            # For SHORT: sell slightly above market
            entry_offset = 0.0005  # 0.05%
            if is_long:
                limit_price = current_price * (1 - entry_offset)
            else:
                limit_price = current_price * (1 + entry_offset)
            
            # Place LIMIT order
            result = self.dashboard.place_order(
                self.product_id,
                self.base_size,
                is_long=is_long,
                custom_price=float(limit_price),
                auto_tp=False
            )
            
            if result:
                logger.info(f"✅ LIMIT order placed @ ${limit_price:.2f}")
                
                # Wait a bit for order to fill
                await asyncio.sleep(3)
                
                # Check if position opened
                positions = self.dashboard.get_positions()
                our_pos = next((p for p in positions if p['product_id'] == self.product_id), None)
                
                if not our_pos:
                    logger.warning("Position not filled yet, waiting...")
                    return
                
                actual_entry = our_pos['price']
                logger.info(f"✅ Position FILLED @ ${actual_entry:.2f}")
                
                # Calculate TP/SL from actual entry
                if is_long:
                    tp_price = actual_entry * (1 + self.tp_percent / 100)
                    sl_price = actual_entry * (1 - self.sl_percent / 100)
                else:
                    tp_price = actual_entry * (1 - self.tp_percent / 100)
                    sl_price = actual_entry * (1 + self.sl_percent / 100)
                
                size_with_leverage = abs(our_pos['amount'])
                
                logger.info(f"   TP: ${tp_price:.2f} (+{self.tp_percent}%)")
                logger.info(f"   SL: ${sl_price:.2f} (-{self.sl_percent}%)")
                
                # Save entry data
                self.dashboard.save_entry_price(
                    self.product_id,
                    float(actual_entry),
                    self.base_size,
                    tp_price=float(tp_price),
                    sl_price=float(sl_price)
                )
                
                # Place LIMIT CLOSE order for TP
                tp_result = self.dashboard.place_limit_close_order(
                    product_id=self.product_id,
                    size=size_with_leverage,
                    is_long=is_long,
                    target_price=float(tp_price)
                )
                
                if tp_result:
                    logger.info(f"✅ TP order placed @ ${tp_price:.2f}")
                else:
                    logger.error("❌ Failed to place TP order")
                
                # Place LIMIT CLOSE order for SL
                sl_result = self.dashboard.place_limit_close_order(
                    product_id=self.product_id,
                    size=size_with_leverage,
                    is_long=is_long,
                    target_price=float(sl_price)
                )
                
                if sl_result:
                    logger.info(f"✅ SL order placed @ ${sl_price:.2f}")
                else:
                    logger.error("❌ Failed to place SL order")
                
            else:
                logger.error("❌ Failed to place order")
                
        except Exception as e:
            logger.error(f"Open position error: {e}")
            import traceback
            traceback.print_exc()
    
    async def _manage_position(self, position):
