from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database.connection import get_db
from app.database.models import Candle
from app.modules.state import state
from typing import List, Optional

router = APIRouter(prefix="/api")

@router.get("/candles")
def get_candles(
    limit: int = Query(1000, le=5000),
    before: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Candle)
    
    if before:
        # Fetch candles with timestamp strictly less than 'before'
        query = query.filter(Candle.timestamp < before)
    
    # Order by timestamp descending to get the most recent ones (relative to 'before' or 'now')
    # and limit the result.
    candles = query.order_by(desc(Candle.timestamp)).limit(limit).all()
    
    # Lightweight Charts expects ascending order
    candles.reverse()
    
    # Format for the frontend
    formatted = [
        {
            "time": int(c.timestamp // 1000), # to seconds
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume
        }
        for c in candles
    ]
    
    return {"candles": formatted}
    
@router.get("/status")
def get_status():
    return state.get_status()
