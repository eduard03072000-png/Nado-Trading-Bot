"""
Test ML Auto-Trader - SIMPLE VERSION
"""
import asyncio
from ml_autotrader import MLAutoTrader

async def test_ml_prediction():
    print("=== ML AUTO-TRADER PREDICTION TEST ===\n")
    
    # Create fake dashboard for testing prediction
    class FakeDashboard:
        leverage = 10
        
        def get_market_price(self, product_id):
            return 100.0  # Fake price
        
        def place_order(self, *args, **kwargs):
            print("[FAKE] Order would be placed here")
            return True
        
        def save_entry_price(self, *args, **kwargs):
            print("[FAKE] Entry price would be saved here")
        
        def get_positions(self):
            return []  # No positions
    
    dashboard = FakeDashboard()
    
    # Create ML trader
    trader = MLAutoTrader(
        dashboard=dashboard,
        product_id=8,  # SOL-PERP
        base_size=0.1,
        tp_percent=5.0,
        sl_percent=0.5,
        min_confidence=0.55
    )
    
    if not trader.model:
        print("❌ ML Model not loaded!")
        return
    
    print("✅ ML Model loaded")
    print(f"✅ Dashboard initialized")
    print(f"✅ Min confidence: {trader.min_confidence:.0%}\n")
    
    print("Running prediction cycle...\n")
    
    # Run one prediction
    await trader._check_ml_signal()
    
    print(f"\n=== RESULT ===")
    print(f"Direction: {trader.last_prediction.get('direction', 'N/A')}")
    print(f"Confidence: {trader.last_prediction.get('confidence', 0):.2%}")
    print(f"Avg Volume: ${trader.last_prediction.get('avg_volume', 0):,.0f}")
    
    print("\n[OK] Test complete!")

if __name__ == "__main__":
    asyncio.run(test_ml_prediction())
