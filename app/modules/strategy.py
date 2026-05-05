from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
import hashlib
import json
import threading

from app.database.connection import get_db
from app.database.settings_connection import get_settings_db
from app.database.models import Candle
from app.database.settings_models import AppSetting, StrategySettings

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
        self.long_avg_events = 0
        self.long_flag = False
        self.long_target = None

        self.short_active = False
        self.short_entries = []
        self.short_max_price = None
        self.short_count = 0
        self.short_avg_events = 0
        self.short_flag = False
        self.short_target = None

        self.signals = []
        self.history_lines = []
        self.renko_bricks = []
        self.probabilities = {}
        self.analytics_stats = {"total_pnl": 0, "avg_pnl": 0, "max_pnl": 0, "min_pnl": 0, "total_positions": 0}
        self.max_underwater_pnl = 0.0
        self.l2_max_underwater_pnl = 0.0
        self.trigger_history = []

        # Strategy L2 State
        self.l2_signals = []
        self.l2_history_lines = []
        self.l2_long_active = False
        self.l2_long_entries = []
        self.l2_long_target = None
        self.l2_long_waiting_room = 0.0
        self.l2_long_pending_trigger = None
        self.l2_short_active = False
        self.l2_short_entries = []
        self.l2_short_target = None
        self.l2_short_waiting_room = 0.0
        self.l2_short_pending_trigger = None


mem_cache = StrategyCache()
simulate_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Core simulation engine (called by data collector OR the API endpoint)
# ---------------------------------------------------------------------------

def _calculate_stats():
    """
    Calculates conditional probabilities and PnL statistics from signals.
    Ported from frontend logic to backend.
    """
    signals = mem_cache.signals
    if not signals:
        return

    avg_counts = {}
    pnl_list = []
    long_avgs = 0
    short_avgs = 0
    
    for s in signals:
        sig = s.get("signal")
        if sig == 'open_long':
            long_avgs = 0
        elif sig == 'average_long':
            long_avgs += 1
        elif sig == 'close_long':
            avg_counts[long_avgs] = avg_counts.get(long_avgs, 0) + 1
            if "pnl" in s: pnl_list.append(s["pnl"])
            
        if sig == 'open_short':
            short_avgs = 0
        elif sig == 'average_short':
            short_avgs += 1
        elif sig == 'close_short':
            avg_counts[short_avgs] = avg_counts.get(short_avgs, 0) + 1
            if "pnl" in s: pnl_list.append(s["pnl"])

    # PnL Stats
    if pnl_list:
        mem_cache.analytics_stats = {
            "total_pnl": round(sum(pnl_list), 2),
            "avg_pnl": round(sum(pnl_list) / len(pnl_list), 2),
            "max_pnl": round(max(pnl_list), 2),
            "min_pnl": round(min(pnl_list), 2),
            "total_positions": len(pnl_list)
        }

    # Probabilities
    if avg_counts:
        max_c = max(avg_counts.keys()) if avg_counts else 0
        probs = {}
        for i in range(max_c + 1):
            freq = avg_counts.get(i, 0)
            total_reached = sum(avg_counts.get(k, 0) for k in range(i, max_c + 1))
            prob = (freq / total_reached * 100) if total_reached > 0 else 0
            probs[i] = {"prob": round(prob, 1), "count": freq}
        mem_cache.probabilities = probs


def _load_settings(db_settings: Session) -> StrategySettings:
    """Read active settings from DB. Creates defaults if missing."""
    ss = db_settings.query(StrategySettings).filter(StrategySettings.id == 1).first()
    if not ss:
        ss = StrategySettings(id=1)
        db_settings.add(ss)
        db_settings.commit()
    return ss


def _load_float_app_setting(db_settings: Session, key: str, default: float) -> float:
    rec = db_settings.query(AppSetting).filter(AppSetting.key == key).first()
    if not rec or rec.value is None:
        return default
    try:
        return float(rec.value)
    except Exception:
        return default


def run_strategy_l2(
    c: Candle,
    t: int,
    l1_sig: str = None,
    l1_data: dict = None,
    ss: StrategySettings = None,
    avg_base_multiplier: float = 1.0,
    avg_step_multiplier: float = 1.0,
    record_history: bool = False,
):
    """
    Strategy L2 logic.
    Filters L1 averaging signals based on trigger levels.
    """
    if ss is None: return
    if l1_data is None: l1_data = {}
    
    C_SIZE = ss.contract_size
    INITIAL_QTY = ss.initial_qty

    base_mult = max(0.01, float(avg_base_multiplier))
    step_mult = max(0.01, float(avg_step_multiplier))

    def _try_fire_long_average():
        if (
            mem_cache.l2_long_active
            and mem_cache.l2_long_pending_trigger is not None
            and mem_cache.l2_long_waiting_room > 0
            and c.close >= mem_cache.l2_long_pending_trigger
        ):
            total_weight = mem_cache.l2_long_waiting_room
            avg_index = max(1, len(mem_cache.l2_long_entries))  # 1 for first L2 average, 2 for second...
            qty_mult = base_mult * (step_mult ** (avg_index - 1))
            mem_cache.l2_long_entries.append((c.close, INITIAL_QTY * total_weight * qty_mult))
            mem_cache.l2_long_waiting_room = 0.0
            mem_cache.l2_long_pending_trigger = None

            w_a = sum(p * q for p, q in mem_cache.l2_long_entries) / sum(q for _, q in mem_cache.l2_long_entries)
            mem_cache.l2_long_target = w_a * (1 + ss.min_profit_pct / 100)
            mem_cache.l2_signals.append(
                {"time": t, "signal": "average_long", "price": round(c.close, 4), "weight": total_weight, "multiplier": round(qty_mult, 6)}
            )

    def _try_fire_short_average():
        if (
            mem_cache.l2_short_active
            and mem_cache.l2_short_pending_trigger is not None
            and mem_cache.l2_short_waiting_room > 0
            and c.close <= mem_cache.l2_short_pending_trigger
        ):
            total_weight = mem_cache.l2_short_waiting_room
            avg_index = max(1, len(mem_cache.l2_short_entries))  # 1 for first L2 average, 2 for second...
            qty_mult = base_mult * (step_mult ** (avg_index - 1))
            mem_cache.l2_short_entries.append((c.close, INITIAL_QTY * total_weight * qty_mult))
            mem_cache.l2_short_waiting_room = 0.0
            mem_cache.l2_short_pending_trigger = None

            w_a = sum(p * q for p, q in mem_cache.l2_short_entries) / sum(q for _, q in mem_cache.l2_short_entries)
            mem_cache.l2_short_target = w_a * (1 - ss.min_profit_pct / 100)
            mem_cache.l2_signals.append(
                {"time": t, "signal": "average_short", "price": round(c.close, 4), "weight": total_weight, "multiplier": round(qty_mult, 6)}
            )

    # --- LONG L2 ---
    if l1_sig == 'open_long':
        mem_cache.l2_long_active = True
        mem_cache.l2_long_entries = [(c.close, INITIAL_QTY)]
        mem_cache.l2_long_target = c.close * (1 + ss.min_profit_pct / 100)
        mem_cache.l2_long_waiting_room = 0.0
        mem_cache.l2_long_pending_trigger = None
        mem_cache.l2_signals.append({"time": t, "signal": "open_long", "price": round(c.close, 4)})
    
    elif l1_sig == 'average_long' and mem_cache.l2_long_active:
        l1_weight = l1_data.get("weight", 0)
        trigger_level = l1_data.get("long_trigger")

        if l1_weight > 0:
            mem_cache.l2_long_waiting_room += l1_weight
        if trigger_level is not None:
            # Keep the latest trigger snapshot from the newest L1 averaging signal.
            mem_cache.l2_long_pending_trigger = trigger_level

        # Allow immediate fill on the same candle if trigger is already crossed.
        _try_fire_long_average()

    elif l1_sig == 'close_long' and mem_cache.l2_long_active:
        w_a = sum(p * q for p, q in mem_cache.l2_long_entries) / sum(q for _, q in mem_cache.l2_long_entries)
        pnl = (c.close - w_a) * sum(q for _, q in mem_cache.l2_long_entries) * C_SIZE
        mem_cache.l2_signals.append({"time": t, "signal": "close_long", "price": round(c.close, 4), "pnl": round(pnl, 4)})
        mem_cache.l2_long_active, mem_cache.l2_long_entries, mem_cache.l2_long_target, mem_cache.l2_long_waiting_room, mem_cache.l2_long_pending_trigger = False, [], None, 0.0, None

    # --- SHORT L2 ---
    if l1_sig == 'open_short':
        mem_cache.l2_short_active = True
        mem_cache.l2_short_entries = [(c.close, INITIAL_QTY)]
        mem_cache.l2_short_target = c.close * (1 - ss.min_profit_pct / 100)
        mem_cache.l2_short_waiting_room = 0.0
        mem_cache.l2_short_pending_trigger = None
        mem_cache.l2_signals.append({"time": t, "signal": "open_short", "price": round(c.close, 4)})

    elif l1_sig == 'average_short' and mem_cache.l2_short_active:
        l1_weight = l1_data.get("weight", 0)
        trigger_level = l1_data.get("short_trigger")

        if l1_weight > 0:
            mem_cache.l2_short_waiting_room += l1_weight
        if trigger_level is not None:
            # Keep the latest trigger snapshot from the newest L1 averaging signal.
            mem_cache.l2_short_pending_trigger = trigger_level

        # Allow immediate fill on the same candle if trigger is already crossed.
        _try_fire_short_average()

    elif l1_sig == 'close_short' and mem_cache.l2_short_active:
        w_a = sum(p * q for p, q in mem_cache.l2_short_entries) / sum(q for _, q in mem_cache.l2_short_entries)
        pnl = (w_a - c.close) * sum(q for _, q in mem_cache.l2_short_entries) * C_SIZE
        mem_cache.l2_signals.append({"time": t, "signal": "close_short", "price": round(c.close, 4), "pnl": round(pnl, 4)})
        mem_cache.l2_short_active, mem_cache.l2_short_entries, mem_cache.l2_short_target, mem_cache.l2_short_waiting_room, mem_cache.l2_short_pending_trigger = False, [], None, 0.0, None

    # If we are waiting for a trigger, keep checking it on every next candle.
    if l1_sig is None:
        _try_fire_long_average()
        _try_fire_short_average()

    # Record L2 History Lines
    if record_history and mem_cache.l2_long_active:
        w_a = sum(p * q for p, q in mem_cache.l2_long_entries) / sum(q for _, q in mem_cache.l2_long_entries)
        mem_cache.l2_history_lines.append({"time": t, "type": "long", "avg": round(w_a, 4), "target": round(mem_cache.l2_long_target, 4)})
    if record_history and mem_cache.l2_short_active:
        w_a = sum(p * q for p, q in mem_cache.l2_short_entries) / sum(q for _, q in mem_cache.l2_short_entries)
        mem_cache.l2_history_lines.append({"time": t, "type": "short", "avg": round(w_a, 4), "target": round(mem_cache.l2_short_target, 4)})


def run_simulation(db_market: Session, db_settings: Session):
    """
    Incremental simulation engine.
    Reads strategy settings autonomously from StrategySettings table.
    Processes only candles newer than mem_cache.last_timestamp.
    Updates mem_cache in-place.
    """
    ss = _load_settings(db_settings)
    L2_AVG_MULT = _load_float_app_setting(db_settings, "l2_avg_multiplier", 1.0)
    L2_AVG_STEP_MULT = _load_float_app_setting(db_settings, "l2_avg_step_multiplier", 1.0)
    L2_SL_ENABLED = _load_float_app_setting(db_settings, "l2_sl_enabled", 0.0) >= 0.5
    L2_SL_VALUE = abs(_load_float_app_setting(db_settings, "l2_sl_value", 100.0))

    current_hash = _hash({
        "p": ss.period, "w": ss.weight_factor, "m": ss.multiplier,
        "mp": ss.min_profit_pct, "iq": ss.initial_qty, "cs": ss.contract_size,
        "mlpr": ss.mult_long_prob, "mspr": ss.mult_short_prob,
        "mlpn": ss.mult_long_pnl, "mspn": ss.mult_short_pnl,
        "mrl": ss.mult_res_long, "mrs": ss.mult_res_short,
        "l2am": round(L2_AVG_MULT, 6),
        "l2asm": round(L2_AVG_STEP_MULT, 6),
        "l2sl_en": int(L2_SL_ENABLED),
        "l2sl_v": round(L2_SL_VALUE, 6),
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
                        run_strategy_l2(c, t, "close_long", {}, ss, L2_AVG_MULT, L2_AVG_STEP_MULT)
                        mem_cache.long_active, mem_cache.long_entries, mem_cache.long_target, mem_cache.long_min_price, mem_cache.long_count, mem_cache.long_avg_events, mem_cache.long_flag = False, [], None, None, 0, 0, False
                    elif check_average_long(pd, cd, mem_cache.long_flag, mem_cache.long_count, mem_cache.long_active):
                        mem_cache.long_avg_events += 1
                        mem_cache.long_entries.append((c.close, INITIAL_QTY * mem_cache.long_count))
                        w_a = sum(p * q for p, q in mem_cache.long_entries) / sum(q for _, q in mem_cache.long_entries)
                        mem_cache.long_target = w_a * (1 + ss.min_profit_pct / 100)
                        l1_sig_data = {"time": t, "signal": "average_long", "price": round(c.close, 4), "counter": mem_cache.long_avg_events, "avg_price": round(w_a, 4), "target": round(mem_cache.long_target, 4)}
                        mem_cache.signals.append(l1_sig_data)
                        mem_cache.long_flag = False
                        
                        # Trigger L2
                        l1_prob_val = mem_cache.probabilities.get(mem_cache.long_avg_events, {}).get("prob", 0)
                        l1_res_long = ((100 - l1_prob_val) * ss.mult_long_prob + abs(round((c.close / w_a - 1) * 100, 2)) * ss.mult_long_pnl) * ss.mult_res_long
                        l1_trigger_level = mem_cache.curr_high * (1 + l1_res_long / 100)
                        run_strategy_l2(c, t, "average_long", {"weight": mem_cache.long_count, "long_trigger": l1_trigger_level}, ss, L2_AVG_MULT, L2_AVG_STEP_MULT)

                elif check_open_long(pd, cd, mem_cache.long_active):
                    mem_cache.long_active, mem_cache.long_entries = True, [(c.close, INITIAL_QTY)]
                    mem_cache.long_min_price = mem_cache.curr_low
                    mem_cache.long_target = c.close * (1 + ss.min_profit_pct / 100)
                    l1_sig_data = {"time": t, "signal": "open_long", "price": round(c.close, 4), "min_price": round(mem_cache.long_min_price, 4), "target": round(mem_cache.long_target, 4)}
                    mem_cache.signals.append(l1_sig_data)
                    run_strategy_l2(c, t, "open_long", {}, ss, L2_AVG_MULT, L2_AVG_STEP_MULT)

                # --- SHORT ---
                if mem_cache.short_active:
                    if check_close_short(cd, c.close, mem_cache.short_target, mem_cache.short_active):
                        w_a = sum(p * q for p, q in mem_cache.short_entries) / sum(q for _, q in mem_cache.short_entries)
                        pnl = (w_a - c.close) * sum(q for _, q in mem_cache.short_entries) * C_SIZE
                        mem_cache.signals.append({"time": t, "signal": "close_short", "price": round(c.close, 4), "pnl": round(pnl, 4)})
                        run_strategy_l2(c, t, "close_short", {}, ss, L2_AVG_MULT, L2_AVG_STEP_MULT)
                        mem_cache.short_active, mem_cache.short_entries, mem_cache.short_target, mem_cache.short_max_price, mem_cache.short_count, mem_cache.short_avg_events, mem_cache.short_flag = False, [], None, None, 0, 0, False
                    elif check_average_short(pd, cd, mem_cache.short_flag, mem_cache.short_count, mem_cache.short_active):
                        mem_cache.short_avg_events += 1
                        mem_cache.short_entries.append((c.close, INITIAL_QTY * mem_cache.short_count))
                        w_a = sum(p * q for p, q in mem_cache.short_entries) / sum(q for _, q in mem_cache.short_entries)
                        mem_cache.short_target = w_a * (1 - ss.min_profit_pct / 100)
                        l1_sig_data = {"time": t, "signal": "average_short", "price": round(c.close, 4), "counter": mem_cache.short_avg_events, "avg_price": round(w_a, 4), "target": round(mem_cache.short_target, 4)}
                        mem_cache.signals.append(l1_sig_data)
                        mem_cache.short_flag = False

                        # Trigger L2
                        l1_prob_val = mem_cache.probabilities.get(mem_cache.short_avg_events, {}).get("prob", 0)
                        l1_res_short = ((100 - l1_prob_val) * ss.mult_short_prob + abs(round((w_a / c.close - 1) * 100, 2)) * ss.mult_short_pnl) * ss.mult_res_short
                        l1_trigger_level = mem_cache.curr_low * (1 - l1_res_short / 100)
                        run_strategy_l2(c, t, "average_short", {"weight": mem_cache.short_count, "short_trigger": l1_trigger_level}, ss, L2_AVG_MULT, L2_AVG_STEP_MULT)

                elif check_open_short(pd, cd, mem_cache.short_active):
                    mem_cache.short_active, mem_cache.short_entries = True, [(c.close, INITIAL_QTY)]
                    mem_cache.short_max_price = mem_cache.curr_high
                    mem_cache.short_target = c.close * (1 - ss.min_profit_pct / 100)
                    l1_sig_data = {"time": t, "signal": "open_short", "price": round(c.close, 4), "max_price": round(mem_cache.short_max_price, 4), "target": round(mem_cache.short_target, 4)}
                    mem_cache.signals.append(l1_sig_data)
                    run_strategy_l2(c, t, "open_short", {}, ss, L2_AVG_MULT, L2_AVG_STEP_MULT)

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

        # Keep checking pending L2 triggers on every candle until hit or position close.
        run_strategy_l2(c, t_now, None, None, ss, L2_AVG_MULT, L2_AVG_STEP_MULT, record_history=False)

        # Track worst (most negative) floating PnL seen during any open position.
        if mem_cache.long_active and mem_cache.long_entries:
            long_qty = sum(q for _, q in mem_cache.long_entries)
            if long_qty > 0:
                long_avg = sum(p * q for p, q in mem_cache.long_entries) / long_qty
                long_pnl = (c.close - long_avg) * long_qty * C_SIZE
                mem_cache.max_underwater_pnl = min(mem_cache.max_underwater_pnl, long_pnl)
        if mem_cache.short_active and mem_cache.short_entries:
            short_qty = sum(q for _, q in mem_cache.short_entries)
            if short_qty > 0:
                short_avg = sum(p * q for p, q in mem_cache.short_entries) / short_qty
                short_pnl = (short_avg - c.close) * short_qty * C_SIZE
                mem_cache.max_underwater_pnl = min(mem_cache.max_underwater_pnl, short_pnl)

        l2_long_pnl = None
        l2_short_pnl = None
        if mem_cache.l2_long_active and mem_cache.l2_long_entries:
            l2_long_qty = sum(q for _, q in mem_cache.l2_long_entries)
            if l2_long_qty > 0:
                l2_long_avg = sum(p * q for p, q in mem_cache.l2_long_entries) / l2_long_qty
                l2_long_pnl = (c.close - l2_long_avg) * l2_long_qty * C_SIZE
                mem_cache.l2_max_underwater_pnl = min(mem_cache.l2_max_underwater_pnl, l2_long_pnl)
        if mem_cache.l2_short_active and mem_cache.l2_short_entries:
            l2_short_qty = sum(q for _, q in mem_cache.l2_short_entries)
            if l2_short_qty > 0:
                l2_short_avg = sum(p * q for p, q in mem_cache.l2_short_entries) / l2_short_qty
                l2_short_pnl = (l2_short_avg - c.close) * l2_short_qty * C_SIZE
                mem_cache.l2_max_underwater_pnl = min(mem_cache.l2_max_underwater_pnl, l2_short_pnl)

        # Optional L2 stop-loss: when hit, close both L1 and L2 for the same side.
        if L2_SL_ENABLED and L2_SL_VALUE > 0:
            if mem_cache.l2_long_active and l2_long_pnl is not None and l2_long_pnl <= -L2_SL_VALUE:
                if mem_cache.long_active and mem_cache.long_entries:
                    l1_qty = sum(q for _, q in mem_cache.long_entries)
                    if l1_qty > 0:
                        l1_avg = sum(p * q for p, q in mem_cache.long_entries) / l1_qty
                        l1_pnl = (c.close - l1_avg) * l1_qty * C_SIZE
                        mem_cache.signals.append({
                            "time": t_now,
                            "signal": "close_long",
                            "price": round(c.close, 4),
                            "pnl": round(l1_pnl, 4),
                            "sl_hit": True,
                            "sl_value": round(L2_SL_VALUE, 4),
                            "sl_source": "l2",
                        })
                mem_cache.l2_signals.append({
                    "time": t_now,
                    "signal": "close_long",
                    "price": round(c.close, 4),
                    "pnl": round(l2_long_pnl, 4),
                    "sl_hit": True,
                    "sl_value": round(L2_SL_VALUE, 4),
                })
                mem_cache.long_active, mem_cache.long_entries, mem_cache.long_target, mem_cache.long_min_price, mem_cache.long_count, mem_cache.long_avg_events, mem_cache.long_flag = False, [], None, None, 0, 0, False
                mem_cache.l2_long_active, mem_cache.l2_long_entries, mem_cache.l2_long_target, mem_cache.l2_long_waiting_room, mem_cache.l2_long_pending_trigger = False, [], None, 0.0, None

            if mem_cache.l2_short_active and l2_short_pnl is not None and l2_short_pnl <= -L2_SL_VALUE:
                if mem_cache.short_active and mem_cache.short_entries:
                    l1_qty = sum(q for _, q in mem_cache.short_entries)
                    if l1_qty > 0:
                        l1_avg = sum(p * q for p, q in mem_cache.short_entries) / l1_qty
                        l1_pnl = (l1_avg - c.close) * l1_qty * C_SIZE
                        mem_cache.signals.append({
                            "time": t_now,
                            "signal": "close_short",
                            "price": round(c.close, 4),
                            "pnl": round(l1_pnl, 4),
                            "sl_hit": True,
                            "sl_value": round(L2_SL_VALUE, 4),
                            "sl_source": "l2",
                        })
                mem_cache.l2_signals.append({
                    "time": t_now,
                    "signal": "close_short",
                    "price": round(c.close, 4),
                    "pnl": round(l2_short_pnl, 4),
                    "sl_hit": True,
                    "sl_value": round(L2_SL_VALUE, 4),
                })
                mem_cache.short_active, mem_cache.short_entries, mem_cache.short_target, mem_cache.short_max_price, mem_cache.short_count, mem_cache.short_avg_events, mem_cache.short_flag = False, [], None, None, 0, 0, False
                mem_cache.l2_short_active, mem_cache.l2_short_entries, mem_cache.l2_short_target, mem_cache.l2_short_waiting_room, mem_cache.l2_short_pending_trigger = False, [], None, 0.0, None

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

            # Record Trigger History (L1)
            l_prob_val = mem_cache.probabilities.get(mem_cache.long_avg_events, {}).get("prob", 0)
            s_prob_val = mem_cache.probabilities.get(mem_cache.short_avg_events, {}).get("prob", 0)
            l_prob_inv = 100 - l_prob_val
            s_prob_inv = 100 - s_prob_val

            l_avg_val = (sum(p * q for p, q in mem_cache.long_entries) / sum(q for _, q in mem_cache.long_entries)) if mem_cache.long_entries else None
            s_avg_val = (sum(p * q for p, q in mem_cache.short_entries) / sum(q for _, q in mem_cache.short_entries)) if mem_cache.short_entries else None
            
            l_pnl_pct = abs(round((c.close / l_avg_val - 1) * 100 if l_avg_val else 0, 2))
            s_pnl_pct = abs(round((s_avg_val / c.close - 1) * 100 if s_avg_val and c.close else 0, 2))

            res_long = (l_prob_inv * ss.mult_long_prob + l_pnl_pct * ss.mult_long_pnl) * ss.mult_res_long
            res_short = (s_prob_inv * ss.mult_short_prob + s_pnl_pct * ss.mult_short_pnl) * ss.mult_res_short

            mem_cache.trigger_history.append({
                "time": t_now,
                "long": round(res_long, 2),
                "short": round(res_short, 2)
            })

            # Record L2 History Lines only during sampling to avoid duplicates
            run_strategy_l2(c, t_now, None, None, ss, L2_AVG_MULT, L2_AVG_STEP_MULT, record_history=True)

        mem_cache.last_timestamp = c.timestamp
        mem_cache.total_processed += 1

    # Refresh stats after processing new candles
    _calculate_stats()


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
def simulate_strategy(
    db: Session = Depends(get_db),
    db_settings: Session = Depends(get_settings_db),
    m_l_prob: float = None, m_s_prob: float = None,
    m_l_pnl: float = None, m_s_pnl: float = None,
    m_res_l: float = None, m_res_s: float = None
):
    """
    Returns cached simulation results.
    If cache is empty (first call after server restart) runs full simulation first.
    Subsequent calls are instant – the data collector keeps the cache warm.
    """
    # First call or after settings change → compute now
    if simulate_lock.acquire(blocking=False):
        try:
            run_simulation(db, db_settings)
        finally:
            simulate_lock.release()

    t_q_l = sum(q for _, q in mem_cache.long_entries)  if mem_cache.long_entries  else 0
    t_q_s = sum(q for _, q in mem_cache.short_entries) if mem_cache.short_entries else 0
    l_avg  = (sum(p * q for p, q in mem_cache.long_entries)  / t_q_l) if t_q_l else None
    s_avg  = (sum(p * q for p, q in mem_cache.short_entries) / t_q_s) if t_q_s else None
    t_q_l2_l = sum(q for _, q in mem_cache.l2_long_entries) if mem_cache.l2_long_entries else 0
    t_q_l2_s = sum(q for _, q in mem_cache.l2_short_entries) if mem_cache.l2_short_entries else 0
    l2_l_avg = (sum(p * q for p, q in mem_cache.l2_long_entries) / t_q_l2_l) if t_q_l2_l else None
    l2_s_avg = (sum(p * q for p, q in mem_cache.l2_short_entries) / t_q_l2_s) if t_q_l2_s else None

    last_candle = db.query(Candle).order_by(desc(Candle.timestamp)).first()
    last_price  = last_candle.close if last_candle else 0
    ss = _load_settings(db_settings)
    C_SIZE = ss.contract_size

    # Calculate Renko boundaries for the next brick
    w_p = ss.weight_factor ** ss.period
    
    # We need to recalculate S for the very last state to get the current step_size
    # In a real scenario, mem_cache.S is already up to date
    step_size = max(0.01, mem_cache.S * ss.multiplier)
    
    renko_upper = mem_cache.curr_high + step_size
    renko_lower = mem_cache.curr_low - step_size

    # Calculate Trigger Results on Backend
    l_prob_val = mem_cache.probabilities.get(mem_cache.long_avg_events, {}).get("prob", 0)
    s_prob_val = mem_cache.probabilities.get(mem_cache.short_avg_events, {}).get("prob", 0)
    
    # Invert probability for trigger (100 - prob)
    l_prob_inv = 100 - l_prob_val
    s_prob_inv = 100 - s_prob_val
    
    l_pnl_pct = abs(round((last_price / l_avg - 1) * 100 if l_avg else 0, 2))
    s_pnl_pct = abs(round((s_avg / last_price - 1) * 100 if s_avg and last_price else 0, 2))
    
    # Use provided multipliers or fallback to DB values
    mlpr = m_l_prob if m_l_prob is not None else ss.mult_long_prob
    mspr = m_s_prob if m_s_prob is not None else ss.mult_short_prob
    mlpn = m_l_pnl  if m_l_pnl  is not None else ss.mult_long_pnl
    mspn = m_s_pnl  if m_s_pnl  is not None else ss.mult_short_pnl
    mrl  = m_res_l  if m_res_l  is not None else ss.mult_res_long
    mrs  = m_res_s  if m_res_s  is not None else ss.mult_res_short

    res_long = (l_prob_inv * mlpr + l_pnl_pct * mlpn) * mrl
    res_short = (s_prob_inv * mspr + s_pnl_pct * mspn) * mrs

    # Calculate Trigger Levels (Price levels)
    # Adding the percentage result to the Renko boundaries
    long_trigger_level = renko_upper * (1 + res_long / 100)
    short_trigger_level = renko_lower * (1 - res_short / 100)

    return {
        "signals":              mem_cache.signals,
        "history_lines":        mem_cache.history_lines,
        "renko":                mem_cache.renko_bricks,
        "renko_upper":          round(renko_upper, 4),
        "renko_lower":          round(renko_lower, 4),
        "long_trigger_level":   round(long_trigger_level, 4),
        "short_trigger_level":  round(short_trigger_level, 4),
        "probabilities":        mem_cache.probabilities, # Original for histogram
        "prob_long_inv":        round(l_prob_inv, 1),    # Inverted for display/trigger
        "prob_short_inv":       round(s_prob_inv, 1),   # Inverted for display/trigger
        "trigger_res_long":     round(res_long, 2),
        "trigger_res_short":    round(res_short, 2),
        "analytics_stats":      mem_cache.analytics_stats,
        "max_underwater_pnl":   round(mem_cache.max_underwater_pnl, 4),
        "l2_max_underwater_pnl": round(mem_cache.l2_max_underwater_pnl, 4),
        "current_long_active":  mem_cache.long_active,
        "current_short_active": mem_cache.short_active,
        "long_avg_price":       round(l_avg, 4) if l_avg else None,
        "short_avg_price":      round(s_avg, 4) if s_avg else None,
        "long_target":          round(mem_cache.long_target, 4)  if mem_cache.long_target  else None,
        "short_target":         round(mem_cache.short_target, 4) if mem_cache.short_target else None,
        "long_count":           mem_cache.long_avg_events,
        "short_count":          mem_cache.short_avg_events,
        "long_qty":             round(t_q_l, 4),
        "short_qty":            round(t_q_s, 4),
        "long_pnl":             round((last_price - l_avg) * t_q_l * C_SIZE if l_avg else 0, 4),
        "long_pnl_pct":         round((last_price / l_avg - 1) * 100 if l_avg else 0, 2),
        "short_pnl":            round((s_avg - last_price) * t_q_s * C_SIZE if s_avg else 0, 4),
        "short_pnl_pct":        round((s_avg / last_price - 1) * 100 if s_avg and last_price else 0, 2),
        "trigger_history":      mem_cache.trigger_history,
        "l2_signals":           mem_cache.l2_signals,
        "l2_history_lines":     mem_cache.l2_history_lines,
        "l2_current_long_active":  mem_cache.l2_long_active,
        "l2_current_short_active": mem_cache.l2_short_active,
        "l2_long_count":           max(0, len(mem_cache.l2_long_entries) - 1),
        "l2_short_count":          max(0, len(mem_cache.l2_short_entries) - 1),
        "l2_long_qty":             round(t_q_l2_l, 4),
        "l2_short_qty":            round(t_q_l2_s, 4),
        "l2_long_pnl":             round((last_price - l2_l_avg) * t_q_l2_l * C_SIZE if l2_l_avg else 0, 4),
        "l2_long_pnl_pct":         round((last_price / l2_l_avg - 1) * 100 if l2_l_avg else 0, 4),
        "l2_short_pnl":            round((l2_s_avg - last_price) * t_q_l2_s * C_SIZE if l2_s_avg else 0, 4),
        "l2_short_pnl_pct":        round((l2_s_avg / last_price - 1) * 100 if l2_s_avg and last_price else 0, 4),
    }
