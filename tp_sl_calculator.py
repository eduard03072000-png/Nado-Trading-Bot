"""
TP/SL Калькулятор с примерами прибыли/убытков
"""
from decimal import Decimal
from typing import List, Dict


class TPSLCalculator:
    """Калькулятор Take-Profit и Stop-Loss с прогнозом P&L"""
    
    # Предустановленные варианты TP/SL (в процентах)
    CONSERVATIVE = {"tp": 0.5, "sl": 0.3}     # Консервативный
    MODERATE = {"tp": 1.0, "sl": 0.5}          # Умеренный  
    AGGRESSIVE = {"tp": 2.0, "sl": 1.0}        # Агрессивный
    SCALPING = {"tp": 0.3, "sl": 0.15}         # Скальпинг
    
    def __init__(self, leverage: int = 10, maker_fee: Decimal = Decimal("0.0001")):
        self.leverage = leverage
        self.maker_fee = maker_fee  # 0.01%
    
    def calculate_scenarios(
        self,
        product_symbol: str,
        entry_price: float,
        size: float,
        is_long: bool
    ) -> List[Dict]:
        """
        Рассчитать различные сценарии TP/SL
        
        Returns:
            Список сценариев с расчетами P&L
        """
        scenarios = []
        
        presets = [
            ("Скальпинг 🏃", self.SCALPING),
            ("Консервативный 🛡️", self.CONSERVATIVE),
            ("Умеренный ⚖️", self.MODERATE),
            ("Агрессивный 🚀", self.AGGRESSIVE),
        ]
        
        for name, params in presets:
            scenario = self._calculate_scenario(
                name=name,
                product_symbol=product_symbol,
                entry_price=entry_price,
                size=size,
                is_long=is_long,
                tp_percent=params["tp"],
                sl_percent=params["sl"]
            )
            scenarios.append(scenario)
        
        return scenarios
    
    def _calculate_scenario(
        self,
        name: str,
        product_symbol: str,
        entry_price: float,
        size: float,
        is_long: bool,
        tp_percent: float,
        sl_percent: float
    ) -> Dict:
        """Рассчитать один сценарий"""
        
        entry = Decimal(str(entry_price))
        base_size = Decimal(str(size))
        
        # Размер позиции с плечом
        position_size = base_size * self.leverage
        
        # Notional (стоимость позиции)
        notional = position_size * entry
        
        # TP/SL цены
        tp_price, sl_price = self._calculate_prices(
            entry, is_long, tp_percent, sl_percent
        )
        
        # P&L при TP
        tp_pnl = self._calculate_pnl(
            entry, tp_price, position_size, notional, is_long
        )
        
        # P&L при SL
        sl_pnl = self._calculate_pnl(
            entry, sl_price, position_size, notional, is_long
        )
        
        # Risk/Reward ratio
        rr_ratio = abs(tp_pnl / sl_pnl) if sl_pnl != 0 else 0
        
        return {
            "name": name,
            "tp_percent": tp_percent,
            "sl_percent": sl_percent,
            "tp_price": float(tp_price),
            "sl_price": float(sl_price),
            "tp_pnl": float(tp_pnl),
            "sl_pnl": float(sl_pnl),
            "rr_ratio": float(rr_ratio),
            "position_size": float(position_size),
            "notional": float(notional)
        }
    
    def _calculate_prices(
        self,
        entry: Decimal,
        is_long: bool,
        tp_percent: float,
        sl_percent: float
    ) -> tuple:
        """Рассчитать цены TP и SL"""
        
        tp_mult = Decimal(str(1 + tp_percent / 100))
        sl_mult = Decimal(str(1 - sl_percent / 100))
        
        if is_long:
            # LONG: TP выше, SL ниже
            tp_price = entry * tp_mult
            sl_price = entry * sl_mult
        else:
            # SHORT: TP ниже, SL выше
            tp_price = entry * sl_mult
            sl_price = entry * tp_mult
        
        return tp_price, sl_price
    
    def _calculate_pnl(
        self,
        entry: Decimal,
        exit: Decimal,
        position_size: Decimal,
        notional: Decimal,
        is_long: bool
    ) -> Decimal:
        """Рассчитать P&L с учетом комиссий"""
        
        # Изменение цены
        if is_long:
            price_change = exit - entry
        else:
            price_change = entry - exit
        
        # P&L без комиссий
        raw_pnl = price_change * position_size
        
        # Комиссии: открытие + закрытие
        open_fee = notional * self.maker_fee
        close_fee = (position_size * exit) * self.maker_fee
        total_fees = open_fee + close_fee
        
        # Итоговый P&L
        net_pnl = raw_pnl - total_fees
        
        return net_pnl
    
    def format_scenario_text(self, scenario: Dict, symbol: str) -> str:
        """Форматировать сценарий для отображения в Telegram"""
        
        tp_emoji = "🟢" if scenario["tp_pnl"] > 0 else "🔴"
        sl_emoji = "🔴" if scenario["sl_pnl"] < 0 else "🟢"
        
        text = (
            f"<b>{scenario['name']}</b>\n"
            f"├ TP: {scenario['tp_percent']}% → ${scenario['tp_price']:,.2f}\n"
            f"├ SL: {scenario['sl_percent']}% → ${scenario['sl_price']:,.2f}\n"
            f"│\n"
            f"├ {tp_emoji} Прибыль при TP: <b>${scenario['tp_pnl']:,.2f}</b>\n"
            f"├ {sl_emoji} Убыток при SL: <b>${scenario['sl_pnl']:,.2f}</b>\n"
            f"└ Risk/Reward: <b>{scenario['rr_ratio']:.2f}</b>\n"
        )
        
        return text


def test_calculator():
    """Тестирование калькулятора"""
    calc = TPSLCalculator(leverage=10)
    
    scenarios = calc.calculate_scenarios(
        product_symbol="SOL-PERP",
        entry_price=78.5,
        size=0.5,
        is_long=True
    )
    
    print("=" * 60)
    print("TP/SL СЦЕНАРИИ")
    print("=" * 60)
    print(f"Entry: $78.50 | Size: 0.5 SOL | Leverage: 10x")
    print(f"Position: 5 SOL ($392.50)")
    print("=" * 60)
    
    for s in scenarios:
        print(f"\n{calc.format_scenario_text(s, 'SOL-PERP')}")


if __name__ == "__main__":
    test_calculator()
