import logging
import httpx
from config import settings

logger = logging.getLogger("telegram_notifier")


class TelegramNotifier:
    """
    Gestor asíncrono para enviar notificaciones de trading y alertas a Telegram.
    """

    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Envía un mensaje de texto a Telegram.
        """
        if not self.is_configured:
            logger.warning("TelegramNotifier no está configurado (falta TOKEN o CHAT_ID). Notificación omitida.")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.api_url, json=payload)
                if response.status_code == 200:
                    logger.info("Notificación enviada exitosamente a Telegram.")
                    return True
                else:
                    logger.error(f"Error enviando mensaje a Telegram. Status: {response.status_code}, Res: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Excepción al conectar con la API de Telegram: {e}")
            return False

    async def send_trade_notification(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        position_size_usdt: float,
        amount_qty: float,
        leverage: int,
        margin_mode: str,
        sl_price: float = None,
        tp_price: float = None,
        status: str = "Exitosa"
    ) -> bool:
        """
        Envía una notificación estructurada cuando se ejecuta una orden.
        """
        action_upper = action.upper()
        if action_upper == "BUY":
            action_desc = "COMPRA (LONG)"
            icon = "🟢"
        elif action_upper == "SELL":
            action_desc = "VENTA (SHORT)"
            icon = "🔴"
        else:
            action_desc = "CIERRE DE POSICIÓN"
            icon = "🟡"

        sl_str = f"${sl_price:,.2f}" if sl_price else "N/A"
        tp_str = f"${tp_price:,.2f}" if tp_price else "N/A"

        message = (
            f"{icon} **ORDEN EJECUTADA EN {settings.EXCHANGE.upper()} FUTUROS**\n"
            f"- Símbolo: `{symbol}`\n"
            f"- Acción: {action_desc}\n"
            f"- Precio Entrada: `${entry_price:,.2f}`\n"
            f"- Tamaño Posición: `${position_size_usdt:,.2f} USDT` (`{amount_qty}` contratos)\n"
            f"- Apalancamiento: `{leverage}x` ({margin_mode})\n"
            f"- Stop Loss: `{sl_str}`\n"
            f"- Take Profit: `{tp_str}`\n"
            f"- Status: **{status}**"
        )

        return await self.send_message(message)

    async def send_error_notification(self, error_msg: str, symbol: str = None) -> bool:
        """
        Envía una alerta inmediata cuando ocurre un error en la ejecución.
        """
        symbol_info = f" en `{symbol}`" if symbol else ""
        message = (
            f"🚨 **ALERTA DE ERROR EN BOT DE TRADING**\n"
            f"Ocurrió un fallo al procesar orden{symbol_info}:\n"
            f"```\n{error_msg}\n```"
        )
        return await self.send_message(message)


notifier = TelegramNotifier()
