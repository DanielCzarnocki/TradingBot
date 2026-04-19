from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.status import Status
import logging
import time

console = Console()

class StatusDisplay:
    def __init__(self):
        self.statuses = {
            "app": {"label": "Starting new bot application", "status": "pending"},
            "venv": {"label": "Activating virtual environment", "status": "pending"},
            "server": {"label": "Starting the server", "status": "pending"},
            "monitoring": {"label": "Initializing monitoring", "status": "pending"},
            "background": {"label": "Background synchronization", "status": "done"}
        }
        self.live = None

    def _generate_table(self):
        table = Table(show_header=False, box=None, padding=(0, 1))
        for key, data in self.statuses.items():
            icon = "[yellow]●[/yellow]"
            label = data["label"]
            if data["status"] == "done":
                icon = "[green]✔[/green]"
                # Use the 'started/activated' version of the label if done
                if key == "app": label = "Application started"
                if key == "venv": label = "Virtual environment activated"
                if key == "server": label = "Server started (http://127.0.0.1:8000)"
                if key == "monitoring" and data.get("extra"): label = f"Monitoring: {data['extra']}"
                elif key == "monitoring": label = "Monitoring active (Live)"
            elif data["status"] == "syncing":
                icon = "[cyan]🔄[/cyan]"
                label = f"Background: {data.get('extra', 'Calculated gaps...')}" if key == "background" else f"Synchronizing: {data.get('extra', 'Calculated gaps...')}"
            elif data["status"] == "error":
                icon = "[red]✘[/red]"
            
            table.add_row(icon, label)
        return table

    def start(self):
        self.live = Live(self._generate_panel(), console=console, refresh_per_second=4)
        self.live.start()

    def update(self, key, status, extra=None):
        if key in self.statuses:
            self.statuses[key]["status"] = status
            if extra:
                self.statuses[key]["extra"] = extra
            if self.live:
                self.live.update(self._generate_panel())

    def _generate_panel(self):
        return Panel(
            self._generate_table(),
            title="[bold blue]New Bot Status[/bold blue]",
            border_style="bright_blue",
            expand=False
        )

    def stop(self):
        if self.live:
            self.live.stop()

# Helper to suppress noisy library logs
def setup_quiet_logging():
    loggers = [
        "uvicorn", "uvicorn.error", "uvicorn.access",
        "sqlalchemy.engine", "websockets.client", "requests", "urllib3", "asyncio"
    ]
    for logger_name in loggers:
        l = logging.getLogger(logger_name)
        l.handlers = []
        l.propagate = False
        l.setLevel(logging.CRITICAL)
