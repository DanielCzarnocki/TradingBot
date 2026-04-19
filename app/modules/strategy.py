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
        
    bricks_dict = {}
    window, S, w_p = [], 0.0, weight_factor ** period
    curr_high, curr_low, direction = None, None, 0
    
    for c in candles:
        diff = c.high - c.low
        window.append(diff)
        S = diff + weight_factor * S
        if len(window) > period: S -= window.pop(0) * w_p
        
        step_size = max(0.01, S * multiplier)
        if curr_high is None: curr_high = c.close; curr_low = c.close; continue
            
        while True:
            brick_found = False
            # Standard Renko: require 2x step for reversal
            if c.close >= curr_high + step_size:
                b_o, b_c = curr_high, curr_high + step_size
                curr_low, curr_high, direction = b_o, b_c, 1
                brick_found = True
            elif c.close <= curr_low - step_size:
                b_o, b_c = curr_low, curr_low - step_size
                curr_high, curr_low, direction = b_o, b_c, -1
                brick_found = True
            
            if not brick_found: break

        t_sec = int(c.timestamp // 1000)
        # Ribbon Fill
        if direction == 1: b_o, b_c = curr_low, curr_high
        elif direction == -1: b_o, b_c = curr_high, curr_low
        else: b_o, b_c = curr_high, curr_high
        
        bricks_dict[t_sec] = {
            "time": t_sec, "open": round(b_o, 2), "high": round(max(curr_high, curr_low), 2),
            "low": round(min(curr_high, curr_low), 2), "close": round(b_c, 2)
        }
            
    sorted_bricks = [bricks_dict[t] for t in sorted(bricks_dict.keys())]
    return {"bricks": sorted_bricks}

# Base strategy functions
def check_open_long(prev, curr, pos): return prev == -1 and curr == 1 and pos is None
def check_average_long(p, c, f, cnt, pos): return pos == "long" and p == -1 and c == 1 and f and cnt > 0
def check_close_long(c, price, target, pos): return pos == "long" and c == -1 and target and price > target

def check_open_short(prev, curr, pos): return prev == 1 and curr == -1 and pos is None
def check_average_short(p, c, f, cnt, pos): return pos == "short" and p == 1 and c == -1 and f and cnt > 0
def check_close_short(c, price, target, pos): return pos == "short" and c == 1 and target and price < target

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
    position, INITIAL_QTY = None, 1.0
    
    long_entries, long_min_price, long_count, long_flag, long_target = [], None, 0, False, None
    short_entries, short_max_price, short_count, short_flag, short_target = [], None, 0, False, None
    signals = []

    for c in candles:
        diff = c.high - c.low
        window.append(diff)
        S = diff + weight_factor * S
        if len(window) > period: S -= window.pop(0) * w_p
        step_size = max(0.01, S * multiplier)

        if curr_high is None: curr_high = c.close; curr_low = c.close; continue
        
        while True:
            brick_formed = False
            prev_dir = direction
            
            # Form BULLISH - require crossing curr_high + step_size
            if c.close >= curr_high + step_size:
                curr_low, curr_high, direction = curr_high, curr_high + step_size, 1
                brick_formed = True
            # Form BEARISH - require crossing curr_low - step_size
            elif c.close <= curr_low - step_size:
                curr_high, curr_low, direction = curr_low, curr_low - step_size, -1
                brick_formed = True
            
            if brick_formed:
                t = int(c.timestamp // 1000)
                # Position Updates
                if check_close_long(direction, c.close, long_target, position):
                    signals.append({"time": t, "signal": "close_long", "price": round(c.close, 4)})
                    position, long_entries, long_target, long_min_price, long_count, long_flag = None, [], None, None, 0, False
                elif check_average_long(prev_dir, direction, long_flag, long_count, position):
                    long_entries.append((c.close, INITIAL_QTY * long_count))
                    w_a = sum(p * q for p, q in long_entries) / sum(q for _, q in long_entries)
                    long_target = w_a * (1 + min_profit_pct / 100)
                    signals.append({"time": t, "signal": "average_long", "price": round(c.close, 4), "counter": long_count, "avg_price": round(w_a, 4), "target": round(long_target, 4)})
                    long_count, long_flag = 0, False
                elif check_open_long(prev_dir, direction, position):
                    position, long_entries = "long", [(c.close, INITIAL_QTY)]
                    long_min_price, long_target = curr_low, c.close * (1 + min_profit_pct/100)
                    signals.append({"time": t, "signal": "open_long", "price": round(c.close, 4), "min_price": round(long_min_price, 4), "target": round(long_target, 4)})

                elif check_close_short(direction, c.close, short_target, position):
                    signals.append({"time": t, "signal": "close_short", "price": round(c.close, 4)})
                    position, short_entries, short_target, short_max_price, short_count, short_flag = None, [], None, None, 0, False
                elif check_average_short(prev_dir, direction, short_flag, short_count, position):
                    short_entries.append((c.close, INITIAL_QTY * short_count))
                    w_a = sum(p * q for p, q in short_entries) / sum(q for _, q in short_entries)
                    short_target = w_a * (1 - min_profit_pct / 100)
                    signals.append({"time": t, "signal": "average_short", "price": round(c.close, 4), "counter": short_count, "avg_price": round(w_a, 4), "target": round(short_target, 4)})
                    short_count, short_flag = 0, False
                elif check_open_short(prev_dir, direction, position):
                    position, short_entries = "short", [(c.close, INITIAL_QTY)]
                    short_max_price, short_target = curr_high, c.close * (1 - min_profit_pct/100)
                    signals.append({"time": t, "signal": "open_short", "price": round(c.close, 4), "max_price": round(short_max_price, 4), "target": round(short_target, 4)})

                # Averaging counters
                if position == "long" and direction == -1:
                    if long_min_price and curr_high < long_min_price: long_count += 1; long_min_price = curr_low; long_flag = True
                if position == "short" and direction == 1:
                    if short_max_price and curr_low > short_max_price: short_count += 1; short_max_price = curr_high; short_flag = True
            else: break

    return {"signals": signals}
