import logging
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator

from config import settings
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ciclo de vida del servidor FastAPI: Inicializa CCXT al arrancar y cierra conexiones al apagar.
    """
    logger.info("🚀 Iniciando Bot de Trading Automatizado...")
    try:
        await exchange_client.initialize()
    except Exception as e:
        logger.error(f"⚠️ Error en inicialización al arrancar: {e}")
    
    yield
    
    logger.info("🛑 Deteniendo Bot de Trading...")
    await exchange_client.close()


app = FastAPI(
    title="TradingView Webhook Bot para Binance Futuros",
    description="Bot de Trading Automatizado de producción completa en Binance Futuros (USDT-M)",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "status": "online",
        "bot": "Binance Futures TradingView Webhook Bot",
        "version": "1.0.0",
        "testnet": settings.BINANCE_TESTNET
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


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

    # 2. Procesar Orden en Binance Futuros
    try:
        result = await exchange_client.process_signal(
            action=payload.action,
            symbol=payload.symbol,
            price=payload.price
        )

        # 3. Notificar a Telegram si fue exitosa
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
                status="Exitosa"
            )
        elif result.get("status") == "closed":
            await notifier.send_message(
                f"🟡 **POSICIÓN CERRADA EN BINANCE FUTUROS**\n"
                f"- Símbolo: `{result['symbol']}`\n"
                f"- Status: **Exitosa**"
            )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        error_detail = str(e)
        logger.error(f"❌ Error procesando orden para {payload.symbol}: {error_detail}")
        
        # Enviar alerta inmediata a Telegram ante cualquier fallo
        await notifier.send_error_notification(
            error_msg=f"Error en {payload.action.upper()}: {error_detail}",
            symbol=payload.symbol
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fallo al ejecutar orden en Binance: {error_detail}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
