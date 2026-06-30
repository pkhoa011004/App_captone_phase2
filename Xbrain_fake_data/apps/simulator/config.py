import os

class Settings:
    SERVICE_NAME: str = os.getenv("SERVICE_NAME", "tf1-telemetry-simulator")
    TRACER_NAME: str = os.getenv("TRACER_NAME", "tf1.telemetry_simulator")
    LOKI_TIMEOUT: int = int(os.getenv("LOKI_TIMEOUT", "5"))
    DEFAULT_LOKI_URL: str = os.getenv("DEFAULT_LOKI_URL", "http://localhost:3100")

settings = Settings()
