
from dataclasses import dataclass
from typing import Literal

OrderSide = Literal["BUY", "SELL"]

@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: int

    def validate(self):
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("quantity must be > 0")
