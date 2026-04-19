from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database.connection import get_db
from app.database.models import Candle

router = APIRouter(prefix="/api/strategy")

@router.get("/trend")
def calculate_trend(
    period: int = Query(100, ge=1, le=1000),
    weight_factor: float = Query(0.87, ge=0.01, le=1.0),
    multiplier: float = Query(1.0, ge=0.001),
    db: Session = Depends(get_db)
):
    candles = db.query(Candle).order_by(desc(Candle.timestamp)).limit(period).all()
    if not candles: return {"value": 0.0}
    total_sum, current_weight = 0.0, 1.0
    for c in candles:
        total_sum += (c.high - c.low) * current_weight
        current_weight *= weight_factor
    return {"value": round(total_sum * multiplier, 4)}

@router.get("/renko")
def get_renko_indicator(
    period: int = Query(100, ge=1, le=1000),
    weight_factor: float = Query(0.87, ge=0.01, le=1.0),
    multiplier: float = Query(1.0, ge=0.001),
    db: Session = Depends(get_db)
):
    candles = db.query(Candle).order_by(Candle.timestamp.asc()).all()
    if not candles: return {"bricks": []}
    bricks_dict, window, S, w_p = {}, [], 0.0, weight_factor ** period
    curr_high, curr_low, direction = None, None, 0
    for c in candles:
        diff = c.high - c.low
        window.append(diff)
        S = diff + weight_factor * S
        if len(window) > period: S -= window.pop(0) * w_p
        step_size = max(0.01, S * multiplier)
        if curr_high is None:
            curr_high = c.close
            curr_low = c.close
            continue
        while True:
            brick_found = False
            if c.close >= curr_high + step_size:
                b_o, b_c = curr_high, curr_high + step_size
                curr_low, curr_high, direction = b_o, b_c, 1; brick_found = True
            elif c.close <= curr_low - step_size:
                b_o, b_c = curr_low, curr_low - step_size
                curr_high, curr_low, direction = b_o, b_c, -1; brick_found = True
            if not brick_found: break
        t_sec = int(c.timestamp // 1000)
        b_o = curr_low if direction == 1 else (curr_high if direction == -1 else curr_high)
        b_c = curr_high if direction == 1 else (curr_low if direction == -1 else curr_high)
        bricks_dict[t_sec] = {"time": t_sec, "open": round(b_o, 2), "high": round(max(curr_high, curr_low), 2), "low": round(min(curr_high, curr_low), 2), "close": round(b_c, 2)}
    return {"bricks": [bricks_dict[t] for t in sorted(bricks_dict.keys())]}

def check_open_long(pd, cd, pos): return pd == -1 and cd == 1 and not pos
def check_average_long(pd, cd, f, cnt, pos): return pos and pd == -1 and cd == 1 and f and cnt > 0
def check_close_long(cd, p, t, pos): return pos and cd == -1 and t is not None and p > t

def check_open_short(pd, cd, pos): return pd == 1 and cd == -1 and not pos
def check_average_short(pd, cd, f, cnt, pos): return pos and pd == 1 and cd == -1 and f and cnt > 0
def check_close_short(cd, p, t, pos): return pos and cd == 1 and t is not None and p < t

@router.get("/simulate")
def simulate_strategy(
    period: int = Query(100, ge=1, le=1000),
    weight_factor: float = Query(0.87, ge=0.01, le=1.0),
    multiplier: float = Query(1.0, ge=0.001),
    min_profit_pct: float = Query(0.2, ge=0.01),
    db: Session = Depends(get_db)
):
    candles = db.query(Candle).order_by(Candle.timestamp.asc()).all()
    if not candles: return {"signals": []}
    window, S, w_p = [], 0.0, weight_factor ** period
    curr_high, curr_low, direction = None, None, 0
    INITIAL_QTY = 1.0
    
    long_active = False
    long_entries, long_min_price, long_count, long_flag, long_target = [], None, 0, False, None
    
    short_active = False
    short_entries, short_max_price, short_count, short_flag, short_target = [], None, 0, False, None
    
    signals, history_lines = [], []

    for c in candles:
        diff = c.high - c.low
        window.append(diff)
        S = diff + weight_factor * S
        if len(window) > period: S -= window.pop(0) * w_p
        step_size = max(0.01, S * multiplier)
        if curr_high is None: curr_high = c.close; curr_low = c.close; continue
        
        while True:
            brick_formed = False
            pd = direction
            if c.close >= curr_high + step_size:
                b_o, b_c = curr_high, curr_high + step_size
                curr_low, curr_high, direction = b_o, b_c, 1; brick_formed = True
            elif c.close <= curr_low - step_size:
                b_o, b_c = curr_low, curr_low - step_size
                curr_high, curr_low, direction = b_o, b_c, -1; brick_formed = True
            
            if brick_formed:
                t, cd = int(c.timestamp // 1000), direction
                
                # --- LONG SIDE INDEPENDENT ---
                if long_active:
                    if check_close_long(cd, c.close, long_target, long_active):
                        signals.append({"time": t, "signal": "close_long", "price": round(c.close, 4)})
                        long_active, long_entries, long_target, long_min_price, long_count, long_flag = False, [], None, None, 0, False
                    elif check_average_long(pd, cd, long_flag, long_count, long_active):
                        long_entries.append((c.close, INITIAL_QTY * long_count))
                        w_a = sum(p * q for p, q in long_entries) / sum(q for _, q in long_entries)
                        long_target = w_a * (1 + min_profit_pct / 100)
                        signals.append({"time": t, "signal": "average_long", "price": round(c.close, 4), "counter": long_count, "avg_price": round(w_a, 4), "target": round(long_target, 4)})
                        long_flag = False
                elif check_open_long(pd, cd, long_active):
                    long_active, long_entries = True, [(c.close, INITIAL_QTY)]
                    long_min_price, long_target = curr_low, c.close * (1 + min_profit_pct/100)
                    signals.append({"time": t, "signal": "open_long", "price": round(c.close, 4), "min_price": round(long_min_price, 4), "target": round(long_target, 4)})

                # --- SHORT SIDE INDEPENDENT ---
                if short_active:
                    if check_close_short(cd, c.close, short_target, short_active):
                        signals.append({"time": t, "signal": "close_short", "price": round(c.close, 4)})
                        short_active, short_entries, short_target, short_max_price, short_count, short_flag = False, [], None, None, 0, False
                    elif check_average_short(pd, cd, short_flag, short_count, short_active):
                        short_entries.append((c.close, INITIAL_QTY * short_count))
                        w_a = sum(p * q for p, q in short_entries) / sum(q for _, q in short_entries)
                        short_target = w_a * (1 - min_profit_pct / 100)
                        signals.append({"time": t, "signal": "average_short", "price": round(c.close, 4), "counter": short_count, "avg_price": round(w_a, 4), "target": round(short_target, 4)})
                        short_flag = False
                elif check_open_short(pd, cd, short_active):
                    short_active, short_entries = True, [(c.close, INITIAL_QTY)]
                    short_max_price, short_target = curr_high, c.close * (1 - min_profit_pct/100)
                    signals.append({"time": t, "signal": "open_short", "price": round(c.close, 4), "max_price": round(short_max_price, 4), "target": round(short_target, 4)})

                # --- Update Averaging Counters (Both can be active) ---
                if long_active and cd == -1:
                    if long_min_price is not None and b_o < long_min_price:
                        long_count += 1; long_min_price = b_c; long_flag = True
                if short_active and cd == 1:
                    if short_max_price is not None and b_o > short_max_price:
                        short_count += 1; short_max_price = b_c; short_flag = True
            else: break
        
        # Collect history lines (per minute state)
        t_now = int(c.timestamp // 1000)
        if long_active:
            w_a = sum(p * q for p, q in long_entries) / sum(q for _, q in long_entries)
            history_lines.append({"time": t_now, "type": "long", "avg": round(w_a, 4), "target": round(long_target, 4)})
        if short_active:
            w_a = sum(p * q for p, q in short_entries) / sum(q for _, q in short_entries)
            history_lines.append({"time": t_now, "type": "short", "avg": round(w_a, 4), "target": round(short_target, 4)})

    t_q_l = sum(q for _, q in long_entries) if long_entries else 0
    t_q_s = sum(q for _, q in short_entries) if short_entries else 0
    l_avg = (sum(p * q for p, q in long_entries) / t_q_l) if t_q_l else None
    s_avg = (sum(p * q for p, q in short_entries) / t_q_s) if t_q_s else None
    
    return {
        "signals": signals, 
        "history_lines": history_lines,
        "current_long_active": long_active,
        "current_short_active": short_active,
        "long_avg_price": round(l_avg, 4) if l_avg else None,
        "short_avg_price": round(s_avg, 4) if s_avg else None,
        "long_target": round(long_target, 4) if long_target else None,
        "short_target": round(short_target, 4) if short_target else None
    }
