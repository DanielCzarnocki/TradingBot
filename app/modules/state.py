class GlobalState:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
            cls._instance.monitoring_status = "Initializing"
            cls._instance.monitoring_extra = "Starting up..."
        return cls._instance

    def update_status(self, status, extra=None):
        self.monitoring_status = status
        self.monitoring_extra = extra

    def get_status(self):
        return {
            "status": self.monitoring_status,
            "extra": self.monitoring_extra
        }

# Singleton instance
state = GlobalState()
