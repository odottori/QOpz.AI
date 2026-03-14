
import threading

_counter = 0
_counter_lock = threading.Lock()

def generate_client_order_id(run_id: str) -> str:
    global _counter
    with _counter_lock:
        _counter += 1
        return f"{run_id}-ORD-{_counter}"
