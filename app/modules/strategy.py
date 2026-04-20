from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
import hashlib
import json

from app.database.connection import get_db
from app.database.settings_connection import get_settings_db
from app.database.models import Candle
from app.database.settings_models import StrategySettings

router = APIRouter(prefix="/api/strategy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash(params: dict) -> str:
    return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()

def check_open_long(pd, cd, pos):      return pd <= 0 and cd == 1 and not pos
def check_average_long(pd, cd, f, cnt, pos): return pos and pd == -1 and cd == 1 and f and cnt > 0
def check_close_long(cd, p, t, pos):   return pos and cd == -1 and t is not None and p > t
def check_open_short(pd, cd, pos):     return pd >= 0 and cd == -1 and not pos
def check_average_short(pd, cd, f, cnt, pos): return pos and pd == 1 and cd == -1 and f and cnt > 0
def check_close_short(cd, p, t, pos):  return pos and cd == 1 and t is not None and p < t


# ---------------------------------------------------------------------------
# In-memory cache (lives as long as the server process is running)
# ---------------------------------------------------------------------------

class StrategyCache:
    def __init__(self):
        self.reset()

    def reset(self):
        self.last_settings_hash = ""
        self.last_timestamp = 0
        self.total_processed = 0

        self.window = []
        self.S = 0.0
        self.curr_high = None
        self.curr_low = None
        self.direction = 0

        self.long_active = False
        self.long_entries = []
        self.long_min_price = None
        self.long_count = 0
        self.long_flag = False
        self.long_target = None

        self.short_active = False
        self.short_entries = []
        self.short_max_price = None
        self.short_count = 0
        self.short_flag = False
        self.short_target = None

        self.signals = []
        self.history_lines = []
        self.renko_bricks = []


mem_cache = StrategyCache()


# ---------------------------------------------------------------------------
# Core simulation engine (called by data collector OR the API endpoint)
# ---------------------------------------------------------------------------

def _load_settings(db_settings: Session) -> StrategySettings:
    """Read active settings from DB. Creates defaults if missing."""
    ss = db_settings.query(StrategySettings).filter(StrategySettings.id == 1).first()
    if not ss:
        ss = StrategySettings(id=1)
        db_settings.add(ss)
        db_settings.commit()
    return ss


def run_simulation(db_market: Session, db_settings: Session):
    """
    Incremental simulation engine.
    Reads strategy settings autonomously from StrategySettings table.
    Processes only candles newer than mem_cache.last_timestamp.
    Updates mem_cache in-place.
    """
    ss = _load_settings(db_settings)

    current_hash = _hash({
        "p": ss.period, "w": ss.weight_factor, "m": ss.multiplier,
        "mp": ss.min_profit_pct, "iq": ss.initial_qty, "cs": ss.contract_size
    })

    # Reset cache if settings have changed
    if mem_cache.last_settings_hash != current_hash:
        mem_cache.reset()
        mem_cache.last_settings_hash = current_hash

    import time
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - 60000  # Ignore candles from the last 60 seconds

    # Fetch only NEW candles
    if mem_cache.last_timestamp > 0:
        new_candles = (db_market.query(Candle)
                       .filter(Candle.timestamp > mem_cache.last_timestamp)
                       .filter(Candle.timestamp < cutoff)
                       .order_by(Candle.timestamp.asc()).all())
    else:
        new_candles = (db_market.query(Candle)
                       .filter(Candle.timestamp < cutoff)
                       .order_by(Candle.timestamp.asc()).all())

    if not new_candles:
        return  # Nothing to do

    w_p        = ss.weight_factor ** ss.period
    INITIAL_QTY = ss.initial_qty
    C_SIZE      = ss.contract_size

    for c in new_candles:
        diff = c.high - c.low
        mem_cache.window.append(diff)
        mem_cache.S = diff + ss.weight_factor * mem_cache.S
        if len(mem_cache.window) > ss.period:
            mem_cache.S -= mem_cache.window.pop(0) * w_p

        step_size = max(0.01, mem_cache.S * ss.multiplier)

        if mem_cache.curr_high is None:
            mem_cache.curr_high = c.close
            mem_cache.curr_low  = c.close
            mem_cache.last_timestamp = c.timestamp
            mem_cache.total_processed += 1
            continue

        # ---- Renko brick detection ----
        while True:
            brick_formed = False
            pd = mem_cache.direction

            if c.close >= mem_cache.curr_high + step_size:
                b_o, b_c = mem_cache.curr_high, mem_cache.curr_high + step_size
                mem_cache.curr_low, mem_cache.curr_high, mem_cache.direction = b_o, b_c, 1
                brick_formed = True
            elif c.close <= mem_cache.curr_low - step_size:
                b_o, b_c = mem_cache.curr_low, mem_cache.curr_low - step_size
                mem_cache.curr_high, mem_cache.curr_low, mem_cache.direction = b_o, b_c, -1
                brick_formed = True

            if brick_formed:
                t, cd = int(c.timestamp // 1000), mem_cache.direction

                # --- LONG ---
                if mem_cache.long_active:
                    if check_close_long(cd, c.close, mem_cache.long_target, mem_cache.long_active):
                        w_a = sum(p * q for p, q in mem_cache.long_entries) / sum(q for _, q in mem_cache.long_entries)
                        pnl = (c.close - w_a) * sum(q for _, q in mem_cache.long_entries) * C_SIZE
                        mem_cache.signals.append({"time": t, "signal": "close_long", "price": round(c.close, 4), "pnl": round(pnl, 4)})
                        mem_cache.long_active, mem_cache.long_entries, mem_cache.long_target, mem_cache.long_min_price, mem_cache.long_count, mem_cache.long_flag = False, [], None, None, 0, False
                    elif check_average_long(pd, cd, mem_cache.long_flag, mem_cache.long_count, mem_cache.long_active):
                        mem_cache.long_entries.append((c.close, INITIAL_QTY * mem_cache.long_count))
                        w_a = sum(p * q for p, q in mem_cache.long_entries) / sum(q for _, q in mem_cache.long_entries)
                        mem_cache.long_target = w_a * (1 + ss.min_profit_pct / 100)
                        mem_cache.signals.append({"time": t, "signal": "average_long", "price": round(c.close, 4), "counter": mem_cache.long_count, "avg_price": round(w_a, 4), "target": round(mem_cache.long_target, 4)})
                        mem_cache.long_flag = False
                elif check_open_long(pd, cd, mem_cache.long_active):
                    mem_cache.long_active, mem_cache.long_entries = True, [(c.close, INITIAL_QTY)]
                    mem_cache.long_min_price = mem_cache.curr_low
                    mem_cache.long_target = c.close * (1 + ss.min_profit_pct / 100)
                    mem_cache.signals.append({"time": t, "signal": "open_long", "price": round(c.close, 4), "min_price": round(mem_cache.long_min_price, 4), "target": round(mem_cache.long_target, 4)})

                # --- SHORT ---
                if mem_cache.short_active:
                    if check_close_short(cd, c.close, mem_cache.short_target, mem_cache.short_active):
                        w_a = sum(p * q for p, q in mem_cache.short_entries) / sum(q for _, q in mem_cache.short_entries)
                        pnl = (w_a - c.close) * sum(q for _, q in mem_cache.short_entries) * C_SIZE
                        mem_cache.signals.append({"time": t, "signal": "close_short", "price": round(c.close, 4), "pnl": round(pnl, 4)})
                        mem_cache.short_active, mem_cache.short_entries, mem_cache.short_target, mem_cache.short_max_price, mem_cache.short_count, mem_cache.short_flag = False, [], None, None, 0, False
                    elif check_average_short(pd, cd, mem_cache.short_flag, mem_cache.short_count, mem_cache.short_active):
                        mem_cache.short_entries.append((c.close, INITIAL_QTY * mem_cache.short_count))
                        w_a = sum(p * q for p, q in mem_cache.short_entries) / sum(q for _, q in mem_cache.short_entries)
                        mem_cache.short_target = w_a * (1 - ss.min_profit_pct / 100)
                        mem_cache.signals.append({"time": t, "signal": "average_short", "price": round(c.close, 4), "counter": mem_cache.short_count, "avg_price": round(w_a, 4), "target": round(mem_cache.short_target, 4)})
                        mem_cache.short_flag = False
                elif check_open_short(pd, cd, mem_cache.short_active):
                    mem_cache.short_active, mem_cache.short_entries = True, [(c.close, INITIAL_QTY)]
                    mem_cache.short_max_price = mem_cache.curr_high
                    mem_cache.short_target = c.close * (1 - ss.min_profit_pct / 100)
                    mem_cache.signals.append({"time": t, "signal": "open_short", "price": round(c.close, 4), "max_price": round(mem_cache.short_max_price, 4), "target": round(mem_cache.short_target, 4)})

                # --- Averaging counters ---
                if mem_cache.long_active and cd == -1:
                    if mem_cache.long_min_price is not None and b_o < mem_cache.long_min_price:
                        mem_cache.long_count += 1
                        mem_cache.long_min_price = b_c
                        mem_cache.long_flag = True
                if mem_cache.short_active and cd == 1:
                    if mem_cache.short_max_price is not None and b_o > mem_cache.short_max_price:
                        mem_cache.short_count += 1
                        mem_cache.short_max_price = b_c
                        mem_cache.short_flag = True
            else:
                break

        # ---- Continuous Renko + history lines (sampled) ----
        t_now = int(c.timestamp // 1000)
        is_recent = mem_cache.total_processed > 123000

        if is_recent or (mem_cache.total_processed % 15 == 0):
            if mem_cache.direction == 1:
                rb_o, rb_c = mem_cache.curr_low, mem_cache.curr_low + step_size
            elif mem_cache.direction == -1:
                rb_o, rb_c = mem_cache.curr_high, mem_cache.curr_high - step_size
            else:
                rb_o, rb_c = mem_cache.curr_low, mem_cache.curr_high

            mem_cache.renko_bricks.append({
                "time": t_now,
                "open":  round(rb_o, 2),
                "high":  round(max(rb_o, rb_c), 2),
                "low":   round(min(rb_o, rb_c), 2),
                "close": round(rb_c, 2)
            })

            if mem_cache.long_active:
                w_a = sum(p * q for p, q in mem_cache.long_entries) / sum(q for _, q in mem_cache.long_entries)
                mem_cache.history_lines.append({"time": t_now, "type": "long", "avg": round(w_a, 4), "target": round(mem_cache.long_target, 4)})
            if mem_cache.short_active:
                w_a = sum(p * q for p, q in mem_cache.short_entries) / sum(q for _, q in mem_cache.short_entries)
                mem_cache.history_lines.append({"time": t_now, "type": "short", "avg": round(w_a, 4), "target": round(mem_cache.short_target, 4)})

        mem_cache.last_timestamp = c.timestamp
        mem_cache.total_processed += 1


# ---------------------------------------------------------------------------
# Trend endpoint (unchanged – used by the modal in the dashboard)
# ---------------------------------------------------------------------------

@router.get("/trend")
def calculate_trend(db: Session = Depends(get_db), db_settings: Session = Depends(get_settings_db)):
    ss = _load_settings(db_settings)
    candles = db.query(Candle).order_by(desc(Candle.timestamp)).limit(ss.period).all()
    if not candles:
        return {"value": 0.0}
    total_sum, weight = 0.0, 1.0
    for c in candles:
        total_sum += (c.high - c.low) * weight
        weight *= ss.weight_factor
    return {"value": round(total_sum * ss.multiplier, 4)}


# ---------------------------------------------------------------------------
# Simulate endpoint – instant response from cache
# ---------------------------------------------------------------------------

@router.get("/simulate")
def simulate_strategy(db: Session = Depends(get_db), db_settings: Session = Depends(get_settings_db)):
    """
    Returns cached simulation results.
    If cache is empty (first call after server restart) runs full simulation first.
    Subsequent calls are instant – the data collector keeps the cache warm.
    """
    # First call or after settings change → compute now
    run_simulation(db, db_settings)

    t_q_l = sum(q for _, q in mem_cache.long_entries)  if mem_cache.long_entries  else 0
    t_q_s = sum(q for _, q in mem_cache.short_entries) if mem_cache.short_entries else 0
    l_avg  = (sum(p * q for p, q in mem_cache.long_entries)  / t_q_l) if t_q_l else None
    s_avg  = (sum(p * q for p, q in mem_cache.short_entries) / t_q_s) if t_q_s else None

    last_candle = db.query(Candle).order_by(desc(Candle.timestamp)).first()
    last_price  = last_candle.close if last_candle else 0
    C_SIZE      = _load_settings(db_settings).contract_size

    return {
        "signals":              mem_cache.signals,
        "history_lines":        mem_cache.history_lines,
        "renko":                mem_cache.renko_bricks,
        "current_long_active":  mem_cache.long_active,
        "current_short_active": mem_cache.short_active,
        "long_avg_price":       round(l_avg, 4) if l_avg else None,
        "short_avg_price":      round(s_avg, 4) if s_avg else None,
        "long_target":          round(mem_cache.long_target, 4)  if mem_cache.long_target  else None,
        "short_target":         round(mem_cache.short_target, 4) if mem_cache.short_target else None,
        "long_count":           mem_cache.long_count,
        "short_count":          mem_cache.short_count,
        "long_qty":             round(t_q_l, 4),
        "short_qty":            round(t_q_s, 4),
        "long_pnl":             round((last_price - l_avg) * t_q_l * C_SIZE if l_avg else 0, 4),
        "long_pnl_pct":         round((last_price / l_avg - 1) * 100 if l_avg else 0, 2),
        "short_pnl":            round((s_avg - last_price) * t_q_s * C_SIZE if s_avg else 0, 4),
        "short_pnl_pct":        round((s_avg / last_price - 1) * 100 if s_avg and last_price else 0, 2),
    }
