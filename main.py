from fastapi import FastAPI
import uvicorn
import logging
import traceback
import sys
from app.modules.visualization import router as visualization_router
from app.modules.data_provider import router as data_router
from app.modules.strategy import router as strategy_router
from app.modules.settings import router as settings_router
from app.database.settings_connection import engine_settings, BaseSettings
from app.modules.console_utils import StatusDisplay, setup_quiet_logging
from app.modules.monitoring import start_monitoring
import asyncio

# Configure logging
setup_quiet_logging()
logging.basicConfig(level=logging.WARNING)

status_ui = StatusDisplay()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize settings DB tables
    BaseSettings.metadata.create_all(bind=engine_settings)
    
    # Finalize the "Starting the server" status
    status_ui.update("server", "done")
    
    # Start the monitoring task in the background
    asyncio.create_task(start_monitoring(status_ui=status_ui))
    yield

app = FastAPI(title="New Bot API", lifespan=lifespan)

# Include modules
app.include_router(visualization_router)
app.include_router(data_router)
app.include_router(strategy_router)
app.include_router(settings_router)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "New Bot Server is running"}

if __name__ == "__main__":
    try:
        status_ui.start()
        status_ui.update("app", "done")
        status_ui.update("venv", "done")
        
        # Run uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
    except Exception as e:
        status_ui.stop()
        print("\n" + "="*50)
        print(" APPLICATION CRASHED ")
        print("="*50)
        traceback.print_exc()
        print("="*50)
        input("Press Enter to close...")
    finally:
        status_ui.stop()
