
from datetime import datetime

_counter = 0

def generate_client_order_id(run_id: str) -> str:
    global _counter
    _counter += 1
    return f"{run_id}-ORD-{_counter}"
