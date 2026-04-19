from sqlalchemy import Column, String
from app.database.settings_connection import BaseSettings

class AppSetting(BaseSettings):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String)
