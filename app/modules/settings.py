from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.settings_connection import get_settings_db
from app.database.settings_models import AppSetting
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
            
    db.commit()
    return {"status": "success"}
