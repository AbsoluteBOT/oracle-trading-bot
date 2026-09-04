import logging
from contextlib import asynccontextmanager
from typing import Literal, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator

from config import settings, update_settings_in_memory_and_env
from exchange_client import exchange_client
from telegram_notifier import notifier

# Configuración del logger principal
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


class WebhookPayload(BaseModel):
    """
    Modelo de validación Pydantic para los Webhooks entrantes de TradingView.
    """
    passphrase: str = Field(..., description="Clave secreta de autenticación del Webhook")
    action: Literal["buy", "sell", "close"] = Field(..., description="Acción de la orden: buy, sell o close")
    symbol: str = Field(..., description="Símbolo a operar (ej: BTC/USDT, ETHUSDT)")
    price: Optional[float] = Field(None, description="Precio reportado por la señal de TradingView")
    timeframe: Optional[str] = Field("1h", description="Marco temporal del gráfico (ej: 1h, 15m)")

    @field_validator("symbol")
    @classmethod
    def clean_symbol(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El campo 'symbol' no puede estar vacío.")
        return v.strip()


class ConfigUpdateRequest(BaseModel):
    """
    Modelo de validación Pydantic para actualización de parámetros desde la GUI.
    """
    exchange: Optional[str] = Field(None, description="Nombre del exchange (ej: bybit, binance, okx)")
    max_open_positions: Optional[int] = Field(None, ge=1, le=50, description="Límite máximo de posiciones abiertas")
    risk_percent: Optional[float] = Field(None, ge=0.1, le=100.0, description="% del balance por posición")
    default_leverage: Optional[int] = Field(None, ge=1, le=125, description="Apalancamiento")
    stop_loss_percent: Optional[float] = Field(None, ge=0.0, description="% Stop Loss")
    take_profit_percent: Optional[float] = Field(None, ge=0.0, description="% Take Profit")
    margin_mode: Optional[str] = Field(None, description="Modo de margen: ISOLATED o CROSSED")
    exchange_testnet: Optional[bool] = Field(None, description="Modo testnet")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ciclo de vida del servidor FastAPI: Inicializa CCXT al arrancar y cierra conexiones al apagar.
    """
    logger.info(f"🚀 Iniciando Bot de Trading Multi-Exchange ({settings.EXCHANGE.upper()})...")
    try:
        await exchange_client.initialize()
    except Exception as e:
        logger.error(f"⚠️ Error en inicialización al arrancar: {e}")
    
    yield
    
    logger.info("🛑 Deteniendo Bot de Trading...")
    await exchange_client.close()


app = FastAPI(
    title="TradingView Webhook Bot Multi-Exchange",
    description="Bot de Trading Automatizado de producción completa compatible con Bybit, Binance y más",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "status": "online",
        "bot": "Oracle TradingView Webhook Bot Multi-Exchange",
        "version": "2.0.0",
        "exchange": settings.EXCHANGE,
        "testnet": settings.is_testnet,
        "max_open_positions": settings.MAX_OPEN_POSITIONS,
        "risk_percent": settings.RISK_PERCENT,
        "leverage": settings.DEFAULT_LEVERAGE,
        "stop_loss_percent": settings.STOP_LOSS_PERCENT,
        "take_profit_percent": settings.TAKE_PROFIT_PERCENT
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "exchange": settings.EXCHANGE}


@app.get("/api/config")
async def get_config():
    """
    Endpoint para obtener los parámetros de configuración actuales del bot (usado por la GUI).
    """
    return {
        "exchange": settings.EXCHANGE,
        "max_open_positions": settings.MAX_OPEN_POSITIONS,
        "risk_percent": settings.RISK_PERCENT,
        "default_leverage": settings.DEFAULT_LEVERAGE,
        "stop_loss_percent": settings.STOP_LOSS_PERCENT,
        "take_profit_percent": settings.TAKE_PROFIT_PERCENT,
        "margin_mode": settings.MARGIN_MODE,
        "exchange_testnet": settings.is_testnet,
        "has_api_key": bool(settings.active_api_key)
    }


@app.post("/api/config")
async def update_config(payload: ConfigUpdateRequest):
    """
    Endpoint para actualizar los parámetros en tiempo real desde la GUI y persistir en .env.
    """
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"success": False, "message": "No se recibieron parámetros para actualizar."}

    updated_fields = update_settings_in_memory_and_env(updates)

    # Si se actualizó el exchange o testnet, re-inicializar la conexión de CCXT
    if "EXCHANGE" in updated_fields or "EXCHANGE_TESTNET" in updated_fields:
        try:
            await exchange_client.initialize(force_reinit=True)
        except Exception as e:
            logger.error(f"Error re-inicializando cliente de exchange: {e}")

    return {
        "success": True,
        "message": "Configuración actualizada y guardada exitosamente en .env",
        "updated_fields": updated_fields,
        "current_config": {
            "exchange": settings.EXCHANGE,
            "max_open_positions": settings.MAX_OPEN_POSITIONS,
            "risk_percent": settings.RISK_PERCENT,
            "default_leverage": settings.DEFAULT_LEVERAGE,
            "stop_loss_percent": settings.STOP_LOSS_PERCENT,
            "take_profit_percent": settings.TAKE_PROFIT_PERCENT,
            "margin_mode": settings.MARGIN_MODE,
            "exchange_testnet": settings.is_testnet
        }
    }


@app.post("/webhook")
async def handle_webhook(payload: WebhookPayload, request: Request):
    """
    Endpoint principal para recibir alertas desde TradingView (Market Oracle Pro Plus).
    """
    client_ip = request.client.host if request.client else "desconocido"
    logger.info(f"📩 Webhook recibido desde {client_ip}: Símbolo={payload.symbol}, Acción={payload.action}")

    # 1. Validar Passphrase de Seguridad
    if payload.passphrase != settings.WEBHOOK_PASSPHRASE:
        error_msg = "Acceso denegado: Passphrase del Webhook es inválida."
        logger.warning(f"🚨 Intento no autorizado desde IP {client_ip}")
        await notifier.send_error_notification(
            error_msg=f"{error_msg} (IP: {client_ip})",
            symbol=payload.symbol
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg
        )

    # 2. Procesar Orden en el Exchange activo
    try:
        result = await exchange_client.process_signal(
            action=payload.action,
            symbol=payload.symbol,
            price=payload.price
        )

        ex_name = (result.get("exchange") or settings.EXCHANGE).upper()

        # 3. Notificar a Telegram según el resultado
        if result.get("status") == "success":
            await notifier.send_trade_notification(
                symbol=result["symbol"],
                action=result["action"],
                entry_price=result["entry_price"],
                position_size_usdt=result["position_size_usdt"],
                amount_qty=result["amount_qty"],
                leverage=result["leverage"],
                margin_mode=result["margin_mode"],
                sl_price=result.get("sl_price"),
                tp_price=result.get("tp_price"),
                status=f"Exitosa ({ex_name})"
            )
        elif result.get("status") == "closed":
            act_info = result.get("action", "close").upper()
            await notifier.send_message(
                f"🟡 **POSICIÓN CERRADA EN {ex_name}**\n"
                f"- Símbolo: `{result['symbol']}`\n"
                f"- Acción: `{act_info}`\n"
                f"- Status: **Exitosa**"
            )
        elif result.get("status") == "skipped":
            logger.info(f"ℹ️ Orden omitida para {result.get('symbol')}: {result.get('reason')}")

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        error_detail = str(e)
        logger.error(f"❌ Error procesando orden para {payload.symbol}: {error_detail}")
        
        # Enviar alerta inmediata a Telegram ante cualquier fallo
        await notifier.send_error_notification(
            error_msg=f"Error en {payload.action.upper()} ({settings.EXCHANGE.upper()}): {error_detail}",
            symbol=payload.symbol
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fallo al ejecutar orden en {settings.EXCHANGE.upper()}: {error_detail}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

