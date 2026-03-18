"""Tests for Wheel persistence layer (wheel_storage.py)."""
import os
import uuid
import pytest

# Use an isolated in-memory or temp DuckDB for tests
import tempfile
from pathlib import Path


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point EXEC_DB_PATH to a temp file so tests don't pollute the real DB."""
    db_path = tmp_path / "test_wheel.duckdb"
    import execution.storage as _st
    import execution.wheel_storage as _ws
    monkeypatch.setattr(_st, "EXEC_DB_PATH", db_path)
    monkeypatch.setattr(_st, "_SCHEMA_READY", False)
    monkeypatch.setattr(_ws, "_WHEEL_SCHEMA_READY", False)
    yield


from execution.wheel_storage import (
    init_wheel_schema,
    save_wheel_position,
    load_wheel_position,
    list_wheel_positions,
)
from strategy.wheel import WheelPosition, WheelState


def _new_run() -> str:
    return str(uuid.uuid4())


def _new_pos_id() -> str:
    return str(uuid.uuid4())


# ── schema init ──────────────────────────────────────────────────────────────

class TestInitWheelSchema:
    def test_idempotent(self):
        init_wheel_schema()
        init_wheel_schema()  # second call must not raise

    def test_tables_exist(self, tmp_path, monkeypatch):
        import execution.storage as _st
        import duckdb
        init_wheel_schema()
        con = duckdb.connect(str(_st.EXEC_DB_PATH))
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        assert "wheel_positions" in tables
        assert "wheel_position_events" in tables
        con.close()


# ── save / load round-trip ────────────────────────────────────────────────────

class TestSaveLoadWheelPosition:
    def test_save_and_load_idle(self):
        pos = WheelPosition(symbol="IWM")
        pid = _new_pos_id()
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=_new_run())
        loaded = load_wheel_position(pid, profile="dev")
        assert loaded is not None
        assert loaded.symbol == "IWM"
        assert loaded.state == WheelState.IDLE

    def test_load_returns_none_for_unknown(self):
        result = load_wheel_position(str(uuid.uuid4()), profile="dev")
        assert result is None

    def test_save_open_csp_state(self):
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        pid = _new_pos_id()
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=_new_run(), event_type="open_csp")
        loaded = load_wheel_position(pid, profile="dev")
        assert loaded.state == WheelState.OPEN_CSP
        assert loaded.csp_strike == pytest.approx(190.0)
        assert loaded.csp_expiry == "20260417"
        assert loaded.csp_premium_received == pytest.approx(1.50)

    def test_save_assigned_state(self):
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        pos.assign()
        pid = _new_pos_id()
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=_new_run(), event_type="assign")
        loaded = load_wheel_position(pid, profile="dev")
        assert loaded.state == WheelState.ASSIGNED
        assert loaded.cost_basis == pytest.approx(190.0)
        assert loaded.total_premium_collected == pytest.approx(1.50)

    def test_save_open_cc_state(self):
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        pos.assign()
        pos.open_cc(strike=193.0, expiry="20260515", premium=1.20)
        pid = _new_pos_id()
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=_new_run(), event_type="open_cc")
        loaded = load_wheel_position(pid, profile="dev")
        assert loaded.state == WheelState.OPEN_CC
        assert loaded.cc_strike == pytest.approx(193.0)
        assert loaded.cycle_count == 1

    def test_save_closed_state(self):
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        pos.assign()
        pos.open_cc(strike=193.0, expiry="20260515", premium=1.20)
        pos.call_away()
        pid = _new_pos_id()
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=_new_run(), event_type="call_away")
        loaded = load_wheel_position(pid, profile="dev")
        assert loaded.state == WheelState.CLOSED
        assert loaded.total_premium_collected == pytest.approx(1.50 + 1.20)

    def test_upsert_overwrites_previous(self):
        pid = _new_pos_id()
        pos = WheelPosition(symbol="IWM")
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=_new_run())

        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=_new_run(), event_type="open_csp")

        loaded = load_wheel_position(pid, profile="dev")
        assert loaded.state == WheelState.OPEN_CSP  # updated, not duplicated

    def test_prev_state_recorded_in_events(self, tmp_path, monkeypatch):
        import execution.storage as _st
        import duckdb
        pid = _new_pos_id()
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        save_wheel_position(
            pos,
            position_id=pid,
            profile="dev",
            run_id=_new_run(),
            prev_state=WheelState.IDLE,
            event_type="open_csp",
        )
        con = duckdb.connect(str(_st.EXEC_DB_PATH))
        rows = con.execute(
            "SELECT prev_state, new_state, event_type FROM wheel_position_events WHERE position_id = ?",
            (pid,),
        ).fetchall()
        con.close()
        assert len(rows) == 1
        assert rows[0][0] == "IDLE"
        assert rows[0][1] == "OPEN_CSP"
        assert rows[0][2] == "open_csp"


# ── list_wheel_positions ──────────────────────────────────────────────────────

class TestListWheelPositions:
    def test_lists_active_positions(self):
        run = _new_run()
        for i in range(3):
            pos = WheelPosition(symbol=f"SYM{i}")
            pos.open_csp(strike=100.0 + i, expiry="20260417", premium=1.0)
            save_wheel_position(pos, position_id=_new_pos_id(), profile="dev", run_id=run)
        result = list_wheel_positions(profile="dev")
        assert len(result) == 3

    def test_excludes_closed_by_default(self):
        run = _new_run()
        pid_open = _new_pos_id()
        pos_open = WheelPosition(symbol="IWM")
        pos_open.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        save_wheel_position(pos_open, position_id=pid_open, profile="dev", run_id=run)

        pid_closed = _new_pos_id()
        pos_closed = WheelPosition(symbol="SPY")
        pos_closed.open_csp(strike=500.0, expiry="20260417", premium=2.0)
        pos_closed.assign()
        pos_closed.open_cc(strike=505.0, expiry="20260515", premium=1.5)
        pos_closed.call_away()
        save_wheel_position(pos_closed, position_id=pid_closed, profile="dev", run_id=run)

        result = list_wheel_positions(profile="dev")
        pids = {pid for pid, _ in result}
        assert pid_open in pids
        assert pid_closed not in pids

    def test_filter_by_symbol(self):
        run = _new_run()
        for sym in ["IWM", "SPY", "IWM"]:
            pos = WheelPosition(symbol=sym)
            save_wheel_position(pos, position_id=_new_pos_id(), profile="dev", run_id=run)
        result = list_wheel_positions(profile="dev", symbol="IWM")
        assert all(p.symbol == "IWM" for _, p in result)
        assert len(result) == 2

    def test_filter_by_state(self):
        run = _new_run()
        pid = _new_pos_id()
        pos = WheelPosition(symbol="IWM")
        pos.open_csp(strike=190.0, expiry="20260417", premium=1.50)
        save_wheel_position(pos, position_id=pid, profile="dev", run_id=run)

        # IDLE position
        pid2 = _new_pos_id()
        save_wheel_position(WheelPosition(symbol="SPY"), position_id=pid2, profile="dev", run_id=run)

        result = list_wheel_positions(profile="dev", state=WheelState.OPEN_CSP)
        assert len(result) == 1
        assert result[0][0] == pid

    def test_profile_isolation(self):
        run = _new_run()
        pos = WheelPosition(symbol="IWM")
        save_wheel_position(pos, position_id=_new_pos_id(), profile="dev", run_id=run)
        result = list_wheel_positions(profile="paper")
        assert result == []
