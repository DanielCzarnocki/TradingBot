from sqlalchemy import Column, String, Float, Integer
from app.database.settings_connection import BaseSettings

class AppSetting(BaseSettings):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String)

class StrategySettings(BaseSettings):
    __tablename__ = "strategy_settings"

    id = Column(Integer, primary_key=True, default=1)
    period = Column(Integer, default=100)
    weight_factor = Column(Float, default=0.87)
    multiplier = Column(Float, default=1.0)
    min_profit_pct = Column(Float, default=0.2)
    initial_qty = Column(Float, default=1.0)
    contract_size = Column(Float, default=0.01)
    
    # Trigger Multipliers
    mult_long_prob = Column(Float, default=1.0)
    mult_short_prob = Column(Float, default=1.0)
    mult_long_pnl = Column(Float, default=1.0)
    mult_short_pnl = Column(Float, default=1.0)
    mult_res_long = Column(Float, default=1.0)
    mult_res_short = Column(Float, default=1.0)
