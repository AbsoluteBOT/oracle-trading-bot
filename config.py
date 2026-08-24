import os
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración global de la aplicación cargada desde variables de entorno o archivo .env.
    """
    WEBHOOK_PASSPHRASE: str = "super_secret_passphrase_123"
    
    # Configuración de Exchange (ej: bybit, binance, okx, bitget)
    EXCHANGE: str = "bybit"
    EXCHANGE_API_KEY: str = ""
    EXCHANGE_SECRET_KEY: str = ""
    EXCHANGE_PASSWORD: str = ""
    EXCHANGE_TESTNET: bool = True
    
    # Credenciales heredadas de Binance Futuros (Compatibilidad)
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET_KEY: str = ""
    BINANCE_TESTNET: bool = True
    
    # Parámetros de Trading y Riesgo
    DEFAULT_LEVERAGE: int = 5
    MARGIN_MODE: str = "ISOLATED"  # ISOLATED o CROSSED
    RISK_PERCENT: float = 2.0      # % del balance total por posición
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

    @property
    def active_api_key(self) -> str:
        return self.EXCHANGE_API_KEY or self.BINANCE_API_KEY

    @property
    def active_secret_key(self) -> str:
        return self.EXCHANGE_SECRET_KEY or self.BINANCE_SECRET_KEY

    @property
    def is_testnet(self) -> bool:
        if self.EXCHANGE_API_KEY:
            return self.EXCHANGE_TESTNET
        return self.BINANCE_TESTNET


settings = Settings()


def update_settings_in_memory_and_env(updates: Dict[str, Any], env_file_path: str = ".env") -> Dict[str, Any]:
    """
    Actualiza los atributos del objeto global 'settings' en memoria y los persiste en el archivo .env.
    """
    # 1. Actualizar atributos en el objeto settings
    updated_fields = {}
    for key, value in updates.items():
        key_upper = key.upper()
        if hasattr(settings, key_upper):
            # Casting según el tipo del atributo existente
            current_val = getattr(settings, key_upper)
            if isinstance(current_val, bool):
                new_val = bool(value)
            elif isinstance(current_val, int):
                new_val = int(value)
            elif isinstance(current_val, float):
                new_val = float(value)
            else:
                new_val = str(value)
            setattr(settings, key_upper, new_val)
            updated_fields[key_upper] = new_val

    # 2. Persistir en archivo .env
    lines = []
    if os.path.exists(env_file_path):
        with open(env_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    env_dict = {}
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, v = stripped.split("=", 1)
            env_dict[k.strip()] = v.strip()

    # Actualizar diccionario con nuevos campos
    for k, v in updated_fields.items():
        env_dict[k] = str(v)

    # Reconstruir contenido de .env manteniendo orden y comentarios
    new_lines = []
    processed_keys = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            key_name = k.strip()
            if key_name in env_dict:
                new_lines.append(f"{key_name}={env_dict[key_name]}\n")
                processed_keys.add(key_name)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Añadir llaves que no existían previamente en .env
    for k, v in env_dict.items():
        if k not in processed_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{k}={v}\n")

    with open(env_file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return updated_fields

