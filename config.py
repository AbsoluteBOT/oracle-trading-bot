import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración global de la aplicación cargada desde variables de entorno o archivo .env.
    """
    WEBHOOK_PASSPHRASE: str = "super_secret_passphrase_123"
    
    # Credenciales de Binance Futuros
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET_KEY: str = ""
    BINANCE_TESTNET: bool = True  # Por defecto True para pruebas seguras
    
    # Parámetros de Trading y Riesgo
    DEFAULT_LEVERAGE: int = 5
    MARGIN_MODE: str = "ISOLATED"  # ISOLATED o CROSSED
    RISK_PERCENT: float = 2.0      # % del balance total de Futuros por posición
    STOP_LOSS_PERCENT: float = 1.5 # % de Stop Loss por defecto
    TAKE_PROFIT_PERCENT: float = 3.0 # % de Take Profit por defecto
    
    # Notificaciones de Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    
    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
