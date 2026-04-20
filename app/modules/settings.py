from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.settings_connection import get_settings_db
from app.database.settings_models import AppSetting, StrategySettings
from pydantic import BaseModel
from typing import Dict

router = APIRouter(prefix="/api/settings")

class SettingsUpdate(BaseModel):
    settings: Dict[str, str]

@router.get("")
def get_all_settings(db: Session = Depends(get_settings_db)):
    """Fetch all saved settings as a key-value dictionary."""
    records = db.query(AppSetting).all()
    return {r.key: r.value for r in records}

@router.post("")
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_settings_db)):
    """Overwrite or create multiple settings."""
    for key, value in payload.settings.items():
        existing = db.query(AppSetting).filter(AppSetting.key == key).first()
        if existing:
            existing.value = str(value)
        else:
            new_setting = AppSetting(key=key, value=str(value))
            db.add(new_setting)

    # Also sync to StrategySettings typed table (for autonomous reading by strategy engine)
    ss = db.query(StrategySettings).filter(StrategySettings.id == 1).first()
    if not ss:
        ss = StrategySettings(id=1)
        db.add(ss)

    s = payload.settings
    if "trend_period" in s:   ss.period = int(s["trend_period"])
    if "weight_factor" in s:  ss.weight_factor = float(s["weight_factor"])
    if "multiplier" in s:     ss.multiplier = float(s["multiplier"])
    if "min_profit" in s:     ss.min_profit_pct = float(s["min_profit"])
    if "initial_qty" in s:    ss.initial_qty = float(s["initial_qty"])
    if "contract_size" in s:  ss.contract_size = float(s["contract_size"])

    db.commit()
    return {"status": "success"}
