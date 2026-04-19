import asyncio
import logging
import time
from datetime import datetime
import requests
from sqlalchemy import func
from app.database.connection import SessionLocal
from app.database.models import Candle
from app.modules.state import state

logger = logging.getLogger(__name__)

# Global lock to prevent SQLite database locks from concurrent writes
db_lock = asyncio.Lock()

class HistorySynchronizer:
    def __init__(self, symbol="LTCUSDT", interval="1m", status_ui=None):
        self.symbol = symbol
        self.interval = interval
        self.interval_ms = 60000
        self.status_ui = status_ui
        self.base_url = "https://api.mexc.com/api/v3/klines"

    def _fetch_klines(self, start_time, end_time=None, limit=500):
        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "startTime": start_time,
            "limit": limit
        }
        if end_time:
            params["endTime"] = end_time
            
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"MEXC API error: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return []

    async def _save_candles(self, data):
        """Asynchronously save candles while respecting the global DB lock."""
        if not data:
            return 0
        
        async with db_lock:
            db = SessionLocal()
            count = 0
            try:
                for item in data:
                    ts = int(item[0])
                    # We check and add within the lock to ensure consistency
                    existing = db.query(Candle).filter(Candle.timestamp == ts).first()
                    if not existing:
                        candle = Candle(
                            timestamp=ts,
                            open=float(item[1]),
                            high=float(item[2]),
                            low=float(item[3]),
                            close=float(item[4]),
                            volume=float(item[5])
                        )
                        db.add(candle)
                        count += 1
                    else:
                        # Update existing for the very newest data (polling updates)
                        existing.open = float(item[1])
                        existing.high = float(item[2])
                        existing.low = float(item[3])
                        existing.close = float(item[4])
                        existing.volume = float(item[5])
                
                db.commit()
                return count
            except Exception as e:
                db.rollback()
                logger.error(f"Database save error: {e}")
                return 0
            finally:
                db.close()

    async def sync_latest(self):
        """Sync from the newest candle in DB until now."""
        db = SessionLocal()
        last_candle = db.query(Candle).order_by(Candle.timestamp.desc()).first()
        db.close()
        
        start_ts = last_candle.timestamp + self.interval_ms if last_candle else 0
        now = int(time.time() * 1000)
        
        if start_ts >= now - self.interval_ms:
            if self.status_ui:
                self.status_ui.update("background", "done")
            return

        if self.status_ui:
            self.status_ui.update("background", "syncing", extra="Fetching latest...")
        
        current_start = start_ts
        while current_start < now - self.interval_ms:
            end_time = current_start + (500 * self.interval_ms)
            if end_time > now:
                end_time = now
                
            data = self._fetch_klines(current_start, end_time)
            if not data:
                break
                
            synced = await self._save_candles(data)
            if len(data) > 0:
                current_start = data[-1][0] + self.interval_ms
            else:
                break
            
            if self.status_ui:
                dt_str = datetime.fromtimestamp(current_start/1000).strftime('%H:%M')
                self.status_ui.update("background", "syncing", extra=f"Syncing latest... ({dt_str})")
            
            await asyncio.sleep(0.1)

    async def backfill_history(self, limit_days=30):
        """Fetch historical data backwards."""
        now = int(time.time() * 1000)
        max_backfill = now - (limit_days * 24 * 3600 * 1000)
        
        while True:
            db = SessionLocal()
            first_candle = db.query(Candle).order_by(Candle.timestamp.asc()).first()
            db.close()
            
            if not first_candle or first_candle.timestamp <= max_backfill:
                break
            
            current_end = first_candle.timestamp - self.interval_ms
            start_time = current_end - (500 * self.interval_ms)
            
            data = self._fetch_klines(start_time, current_end)
            if not data:
                break
                
            await self._save_candles(data)
            
            if len(data) < 10:
                break
                
            if self.status_ui:
                dt_str = datetime.fromtimestamp(data[0][0]/1000).strftime('%Y-%m-%d')
                self.status_ui.update("background", "syncing", extra=f"Backfill: {dt_str}")
                
            await asyncio.sleep(0.5)
        
        if self.status_ui:
            self.status_ui.update("background", "done")

    async def repair_history(self):
        """High-speed gap identification and repair."""
        if self.status_ui:
            self.status_ui.update("background", "syncing", extra="Scanning for gaps...")
            
        db = SessionLocal()
        try:
            timestamps = [r[0] for r in db.query(Candle.timestamp).order_by(Candle.timestamp.asc()).all()]
        finally:
            db.close()
        
        if len(timestamps) < 2:
            return

        gaps = []
        for i in range(1, len(timestamps)):
            diff = timestamps[i] - timestamps[i-1]
            if diff > self.interval_ms:
                gaps.append((timestamps[i-1] + self.interval_ms, timestamps[i] - self.interval_ms))

        if not gaps:
            return

        for i, (gap_start, gap_end) in enumerate(gaps):
            if self.status_ui:
                self.status_ui.update("background", "syncing", extra=f"Repairing gap {i+1}/{len(gaps)}")
            
            # Get the closing price before the gap for fallback synthesis
            db = SessionLocal()
            last_candle = db.query(Candle).filter(Candle.timestamp == gap_start - self.interval_ms).first()
            last_close = last_candle.close if last_candle else 0.0
            db.close()

            current = gap_start
            while current <= gap_end:
                fetch_end = min(current + 500 * self.interval_ms, gap_end)
                data = self._fetch_klines(current, fetch_end)
                
                # Defend against MEXC treating invalid start times by returning current time data
                if data and int(data[0][0]) > fetch_end:
                    data = []
                    
                if data:
                    await self._save_candles(data)
                    current = data[-1][0] + self.interval_ms
                    last_close = float(data[-1][4])
                else:
                    # Synthesize empty candles to permanently close dead gaps
                    dummies = []
                    t = current
                    while t <= fetch_end:
                        dummies.append([str(t), str(last_close), str(last_close), str(last_close), str(last_close), "0"])
                        t += self.interval_ms
                    await self._save_candles(dummies)
                    current = fetch_end + self.interval_ms
                    
                await asyncio.sleep(0.1)
        
        if self.status_ui:
            self.status_ui.update("background", "done")

class RestPollingMonitor:
    def __init__(self, symbol="LTCUSDT", status_ui=None):
        self.symbol = symbol
        self.status_ui = status_ui
        self.is_running = False
        self.base_url = "https://api.mexc.com/api/v3/klines"
        self.synchronizer = HistorySynchronizer(symbol=symbol, status_ui=status_ui)

    async def start(self):
        self.is_running = True
        if self.status_ui:
            self.status_ui.update("monitoring", "done", extra="Live (Polling)")
        state.update_status("Live", "Polling REST API")

        while self.is_running:
            try:
                # Fetch latest 5 candles to ensure no misses
                params = {"symbol": self.symbol, "interval": "1m", "limit": 5}
                response = requests.get(self.base_url, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        await self.synchronizer._save_candles(data)
                
                await asyncio.sleep(5) # Poll every 5 seconds
            except Exception as e:
                logger.error(f"Polling monitor error: {e}")
                await asyncio.sleep(10)

async def start_monitoring(status_ui=None):
    synchronizer = HistorySynchronizer(status_ui=status_ui)
    monitor = RestPollingMonitor(status_ui=status_ui)
    
    # 1. Start Polling Monitor in background
    asyncio.create_task(monitor.start())
    await asyncio.sleep(1)
    
    # 2. Sequential catch-up
    await synchronizer.sync_latest()
    
    # 3. Background maintenance
    asyncio.create_task(synchronizer.repair_history())
    asyncio.create_task(synchronizer.backfill_history())
