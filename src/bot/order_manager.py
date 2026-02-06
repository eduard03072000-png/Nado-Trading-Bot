"""
Менеджер ордеров - управление открытыми позициями и историей сделок
"""
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Order:
    """Класс представляющий ордер/позицию"""

    def __init__(
        self,
        order_id: str,
        side: str,
        size: Decimal,
        entry_price: Decimal,
        take_profit: Decimal,
        stop_loss: Decimal,
        symbol: str = "BTC-USDT",
        leverage: int = 1,
        strategy: str = "grid"
    ):
        self.order_id = order_id
        self.side = side                        # "long" | "short"
        self.size = size                        # текущий размер
        self.original_size: Decimal = size      # начальный размер
        self.entry_price = entry_price
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.symbol = symbol
        self.leverage = leverage
        self.strategy = strategy
        self.created_at = datetime.now()
        self.status = "open"                    # open | closed | cancelled
        self.exit_price: Optional[Decimal] = None
        self.closed_at: Optional[datetime] = None
        self.partial_closed: bool = False

    def calculate_pnl(self, current_price: Decimal) -> Tuple[Decimal, Decimal]:
        """
        Рассчитать PnL
        Returns: (pnl_абсолютный, pnl_процент)
        """
        if self.entry_price == Decimal("0"):
            return Decimal("0"), Decimal("0")

        if self.side == "long":
            pnl_pct = (current_price - self.entry_price) / self.entry_price
        else:
            pnl_pct = (self.entry_price - current_price) / self.entry_price

        pnl_absolute    = self.size * pnl_pct * self.leverage
        pnl_pct_display = pnl_pct * Decimal("100") * self.leverage
        return pnl_absolute, pnl_pct_display

    def is_tp_hit(self, current_price: Decimal) -> bool:
        if self.side == "long":
            return current_price >= self.take_profit
        return current_price <= self.take_profit

    def is_sl_hit(self, current_price: Decimal) -> bool:
        if self.side == "long":
            return current_price <= self.stop_loss
        return current_price >= self.stop_loss

    def to_dict(self) -> Dict:
        return {
            "id":            self.order_id,
            "symbol":        self.symbol,
            "side":          self.side,
            "size":          float(self.size),
            "original_size": float(self.original_size),
            "entry_price":   float(self.entry_price),
            "exit_price":    float(self.exit_price) if self.exit_price else None,
            "take_profit":   float(self.take_profit),
            "stop_loss":     float(self.stop_loss),
            "leverage":      self.leverage,
            "strategy":      self.strategy,
            "status":        self.status,
            "partial_closed":self.partial_closed,
            "created_at":    self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "closed_at":     self.closed_at.strftime('%Y-%m-%d %H:%M:%S') if self.closed_at else None
        }


# ─────────────────────────────────────────────

class OrderManager:
    """Менеджер позиций — добавление, чтение, TP/SL, закрытие, статистика"""

    def __init__(self):
        self.active_orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        self._counter: int = 0

    # ── генерация ID ──

    def generate_order_id(self) -> str:
        self._counter += 1
        return f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._counter:04d}"

    # ── добавить ──

    def add_order(
        self,
        side: str,
        size: Decimal,
        entry_price: Decimal,
        take_profit: Decimal,
        stop_loss: Decimal,
        symbol: str = "BTC-USDT",
        leverage: int = 1,
        strategy: str = "grid",
        order_id: str = None
    ) -> Order:
        if not order_id:
            order_id = self.generate_order_id()

        order = Order(
            order_id=order_id, side=side, size=size,
            entry_price=entry_price, take_profit=take_profit,
            stop_loss=stop_loss, symbol=symbol,
            leverage=leverage, strategy=strategy
        )
        self.active_orders[order_id] = order
        logger.info(f"✅ Ордер добавлен: {order_id} | {side.upper()} {size} @ {entry_price}")
        return order

    # ── чтение ──

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.active_orders.get(order_id)

    def get_active_orders(self) -> List[Order]:
        return list(self.active_orders.values())

    def get_orders_by_side(self, side: str) -> List[Order]:
        return [o for o in self.active_orders.values() if o.side == side]

    def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        return [o for o in self.active_orders.values() if o.symbol == symbol]

    def get_orders_count_by_side(self, side: str) -> int:
        return len(self.get_orders_by_side(side))

    # ── обновить TP / SL ──

    def update_take_profit(self, order_id: str, new_tp: Decimal) -> bool:
        order = self.get_order(order_id)
        if not order:
            logger.warning(f"⚠️ Ордер {order_id} не найден")
            return False
        old = order.take_profit
        order.take_profit = new_tp
        logger.info(f"📈 TP: {order_id} | {old} → {new_tp}")
        return True

    def update_stop_loss(self, order_id: str, new_sl: Decimal) -> bool:
        order = self.get_order(order_id)
        if not order:
            logger.warning(f"⚠️ Ордер {order_id} не найден")
            return False
        old = order.stop_loss
        order.stop_loss = new_sl
        logger.info(f"📉 SL: {order_id} | {old} → {new_sl}")
        return True

    # ── полное закрытие ──

    def close_order(self, order_id: str, exit_price: Decimal) -> Optional[Order]:
        order = self.active_orders.pop(order_id, None)
        if not order:
            logger.warning(f"⚠️ Ордер {order_id} не найден")
            return None

        order.status     = "closed"
        order.exit_price = exit_price
        order.closed_at  = datetime.now()
        self.order_history.append(order)

        pnl, pnl_pct = order.calculate_pnl(exit_price)
        emoji = "💰" if pnl >= 0 else "💸"
        logger.info(f"{emoji} Закрыт: {order_id} | PnL {pnl:+.4f} ({pnl_pct:+.2f}%)")
        return order

    # ── частичное закрытие ──

    def close_order_partial(
        self,
        order_id: str,
        close_percent: Decimal = Decimal("0.5")   # 0.5 = 50%
    ) -> Optional[Tuple[Order, Decimal]]:
        order = self.get_order(order_id)
        if not order:
            logger.warning(f"⚠️ Ордер {order_id} не найден")
            return None

        close_size   = order.size * close_percent
        order.size  -= close_size
        order.partial_closed = True
        logger.info(f"➗ Частичное: {order_id} | -{close_size} | осталось {order.size}")
        return order, close_size

    # ── отмена ──

    def cancel_order(self, order_id: str) -> Optional[Order]:
        order = self.active_orders.pop(order_id, None)
        if not order:
            return None
        order.status   = "cancelled"
        order.closed_at = datetime.now()
        self.order_history.append(order)
        logger.info(f"🚫 Отменён: {order_id}")
        return order

    def cancel_all_orders(self) -> int:
        count = len(self.active_orders)
        for oid in list(self.active_orders.keys()):
            self.cancel_order(oid)
        logger.info(f"🚫 Отменено: {count}")
        return count

    # ── TP / SL проверка ──

    def check_tp_sl(self, current_price: Decimal) -> Dict[str, List[str]]:
        """Проверить все позиции. Вернуть {"tp_hit": [...], "sl_hit": [...]}"""
        tp_hit: List[str] = []
        sl_hit: List[str] = []

        for order_id, order in self.active_orders.items():
            if order.is_tp_hit(current_price):
                tp_hit.append(order_id)
                logger.info(f"🎯 TP: {order_id} @ {current_price}")
            elif order.is_sl_hit(current_price):
                sl_hit.append(order_id)
                logger.warning(f"🛑 SL: {order_id} @ {current_price}")

        return {"tp_hit": tp_hit, "sl_hit": sl_hit}

    # ── PnL ──

    def get_total_pnl(self, current_price: Decimal) -> Tuple[Decimal, Decimal]:
        """Суммарный нереализованный PnL всех позиций"""
        if not self.active_orders:
            return Decimal("0"), Decimal("0")

        total_pnl  = Decimal("0")
        total_size = Decimal("0")
        for order in self.active_orders.values():
            pnl, _ = order.calculate_pnl(current_price)
            total_pnl  += pnl
            total_size += order.size

        avg_pct = (total_pnl / total_size * Decimal("100")) if total_size > 0 else Decimal("0")
        return total_pnl, avg_pct

    # ── статистика ──

    def get_history_stats(self) -> Dict:
        """Полная статистика по истории сделок"""
        closed = [o for o in self.order_history if o.status == "closed" and o.exit_price]

        if not closed:
            return {
                "total": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": Decimal("0"),
                "avg_pnl": Decimal("0"), "best": Decimal("0"), "worst": Decimal("0")
            }

        pnls = []
        for o in closed:
            pnl, _ = o.calculate_pnl(o.exit_price)
            pnls.append(pnl)

        wins      = sum(1 for p in pnls if p > 0)
        total_pnl = sum(pnls)

        return {
            "total":     len(closed),
            "wins":      wins,
            "losses":    len(closed) - wins,
            "win_rate":  round(wins / len(closed) * 100, 1),
            "total_pnl": total_pnl,
            "avg_pnl":   total_pnl / len(closed),
            "best":      max(pnls),
            "worst":     min(pnls)
        }

    def get_positions_info(self, current_price: Decimal) -> List[Dict]:
        """Данные позиций для Telegram"""
        result = []
        for order in self.active_orders.values():
            pnl, pnl_pct = order.calculate_pnl(current_price)
            info = order.to_dict()
            info["pnl"]           = float(pnl)
            info["pnl_percent"]   = float(pnl_pct)
            info["current_price"] = float(current_price)
            result.append(info)
        return result
