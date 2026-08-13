import logging
from typing import Dict, Any, Optional
import ccxt.async_support as ccxt

from config import settings
from risk_manager import risk_manager

logger = logging.getLogger("exchange_client")


class BinanceFuturesClient:
    """
    Cliente de Binance Futuros (USDT-M) basado en CCXT asíncrono.
    """

    def __init__(self):
        self.exchange: Optional[ccxt.binanceusdm] = None

    async def initialize(self):
        """
        Inicializa la instancia de CCXT y carga los mercados.
        """
        if self.exchange is None:
            self.exchange = ccxt.binanceusdm({
                'apiKey': settings.BINANCE_API_KEY,
                'secret': settings.BINANCE_SECRET_KEY,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                }
            })

            if settings.BINANCE_TESTNET:
                self.exchange.set_sandbox_mode(True)
                logger.info("🧪 Modo Testnet Binance Futuros ACTIVADO.")

            try:
                await self.exchange.load_markets()
                logger.info("✅ Mercados de Binance Futuros cargados con éxito.")
            except Exception as e:
                logger.error(f"❌ Error al conectar con Binance Futuros: {e}")

    async def close(self):
        """
        Cierra la conexión asíncrona de CCXT.
        """
        if self.exchange:
            await self.exchange.close()
            self.exchange = None
            logger.info("Conexión con Binance Futuros cerrada.")

    async def set_leverage_and_margin(self, symbol: str, leverage: int, margin_mode: str):
        """
        Configura el apalancamiento y el tipo de margen (ISOLATED/CROSSED).
        """
        if not self.exchange:
            await self.initialize()

        try:
            await self.exchange.set_leverage(leverage, symbol)
            logger.info(f"Apalancamiento de {leverage}x configurado para {symbol}.")
        except Exception as e:
            logger.warning(f"Nota/Aviso al configurar apalancamiento en {symbol}: {e}")

        try:
            mode = margin_mode.upper()
            await self.exchange.set_margin_mode(mode, symbol)
            logger.info(f"Modo de margen {mode} configurado para {symbol}.")
        except Exception as e:
            logger.debug(f"Nota/Aviso al configurar tipo de margen en {symbol}: {e}")

    async def get_usdt_balance(self) -> float:
        """
        Obtiene el balance disponible en USDT en la cuenta de Futuros.
        """
        if not self.exchange:
            await self.initialize()

        try:
            balance = await self.exchange.fetch_balance({'type': 'future'})
            usdt_info = balance.get('USDT', {})
            free_balance = float(usdt_info.get('free', 0.0) or usdt_info.get('total', 0.0))
            return free_balance
        except Exception as e:
            logger.error(f"Error al consultar balance de USDT: {e}")
            raise RuntimeError(f"Fallo al obtener balance de Binance: {e}")

    async def get_open_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Consulta la posición abierta actual para el símbolo especificado.
        """
        if not self.exchange:
            await self.initialize()

        try:
            positions = await self.exchange.fetch_positions([symbol])
            for pos in positions:
                contracts = float(pos.get('contracts', 0) or pos.get('positionAmt', 0))
                if abs(contracts) > 0:
                    side = pos.get('side', '').lower()
                    if not side or side == 'both':
                        side = 'long' if contracts > 0 else 'short'
                    return {
                        'contracts': abs(contracts),
                        'side': side,
                        'entryPrice': float(pos.get('entryPrice', 0)),
                        'unrealizedPnl': float(pos.get('unrealizedPnl', 0)),
                        'info': pos
                    }
        except Exception as e:
            logger.error(f"Error consultando posiciones abiertas de {symbol}: {e}")
        return None

    async def close_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Cierra la posición actual abierta para un símbolo dado.
        """
        if not self.exchange:
            await self.initialize()

        pos = await self.get_open_position(symbol)
        if not pos or pos['contracts'] <= 0:
            logger.info(f"No hay posición abierta activa que cerrar en {symbol}.")
            return None

        contracts = pos['contracts']
        current_side = pos['side']
        close_side = 'sell' if current_side == 'long' else 'buy'

        logger.info(f"🔄 Cerrando posición existente {current_side.upper()} de {contracts} contratos en {symbol}...")
        try:
            formatted_amount = float(self.exchange.amount_to_precision(symbol, contracts))
            order = await self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=close_side,
                amount=formatted_amount,
                params={'reduceOnly': True}
            )
            logger.info(f"✅ Posición previa en {symbol} cerrada con éxito.")
            return order
        except Exception as e:
            logger.error(f"❌ Error al cerrar posición previa en {symbol}: {e}")
            raise e

    async def process_signal(
        self,
        action: str,
        symbol: str,
        price: Optional[float] = None,
        risk_percent: float = None,
        leverage: int = None,
        margin_mode: str = None
    ) -> Dict[str, Any]:
        """
        Flujo completo de ejecución de señal recibida desde TradingView.
        """
        if not self.exchange:
            await self.initialize()

        norm_symbol = risk_manager.normalize_symbol(symbol)
        action_clean = action.lower().strip()
        risk_pct = risk_percent or settings.RISK_PERCENT
        lev = leverage or settings.DEFAULT_LEVERAGE
        m_mode = margin_mode or settings.MARGIN_MODE

        logger.info(f"📥 Procesando Señal: Acción='{action_clean}', Símbolo='{norm_symbol}', Precio TV={price}")

        # 1. Verificar mercado válido
        if norm_symbol not in self.exchange.markets:
            await self.exchange.load_markets()
            if norm_symbol not in self.exchange.markets:
                raise ValueError(f"El símbolo '{norm_symbol}' no está disponible en Binance Futuros.")

        market_info = self.exchange.markets[norm_symbol]

        # 2. Configurar margen y apalancamiento
        await self.set_leverage_and_margin(norm_symbol, lev, m_mode)

        # 3. Revisar y cerrar posición contraria o existente si aplica
        open_pos = await self.get_open_position(norm_symbol)
        if open_pos:
            current_side = open_pos['side']  # 'long' o 'short'
            new_side = 'long' if action_clean == 'buy' else 'short' if action_clean == 'sell' else 'close'

            if action_clean == 'close' or current_side != new_side:
                await self.close_position(norm_symbol)

        # Si la orden es simplemente para cerrar posición, finalizamos aquí
        if action_clean == 'close':
            return {
                "status": "closed",
                "symbol": norm_symbol,
                "action": "close",
                "message": f"Posición cerrada en {norm_symbol}"
            }

        # 4. Obtener precio actual de entrada mercado si no vino en el webhook
        if not price or price <= 0:
            ticker = await self.exchange.fetch_ticker(norm_symbol)
            entry_price = float(ticker['last'])
        else:
            entry_price = float(price)

        # 5. Obtener balance de USDT y calcular tamaño de posición
        balance_usdt = await self.get_usdt_balance()
        risk_result = risk_manager.calculate_position_size(
            usdt_balance=balance_usdt,
            risk_percent=risk_pct,
            leverage=lev,
            current_price=entry_price,
            market_limits=market_info
        )

        if not risk_result["is_valid"]:
            raise ValueError(f"Riesgo/Posición Inválida: {risk_result['reason']}")

        raw_qty = risk_result["quantity"]
        amount_formatted = float(self.exchange.amount_to_precision(norm_symbol, raw_qty))

        if amount_formatted <= 0:
            raise ValueError(f"Cantidad formateada ({amount_formatted}) insuficiente para el lote mínimo.")

        # 6. Ejecutar orden a MERCADO
        order_side = 'buy' if action_clean == 'buy' else 'sell'
        logger.info(f"🚀 Ejecutando Orden Mercado {order_side.upper()} de {amount_formatted} contratos en {norm_symbol}...")

        main_order = await self.exchange.create_order(
            symbol=norm_symbol,
            type='market',
            side=order_side,
            amount=amount_formatted
        )

        # 7. Calcular y colocar órdenes de Stop Loss y Take Profit
        sl_price, tp_price = risk_manager.calculate_sl_tp_prices(
            action=action_clean,
            entry_price=entry_price,
            sl_percent=settings.STOP_LOSS_PERCENT,
            tp_percent=settings.TAKE_PROFIT_PERCENT
        )

        sl_formatted = float(self.exchange.price_to_precision(norm_symbol, sl_price))
        tp_formatted = float(self.exchange.price_to_precision(norm_symbol, tp_price))

        opposite_side = 'sell' if order_side == 'buy' else 'buy'

        sl_order = None
        tp_order = None

        try:
            # Stop Loss Market
            sl_order = await self.exchange.create_order(
                symbol=norm_symbol,
                type='STOP_MARKET',
                side=opposite_side,
                amount=amount_formatted,
                params={
                    'stopPrice': sl_formatted,
                    'reduceOnly': True
                }
            )
            logger.info(f"🛡️ Stop Loss configurado a ${sl_formatted} en {norm_symbol}")
        except Exception as e:
            logger.error(f"Error al colocar Stop Loss en {norm_symbol}: {e}")

        try:
            # Take Profit Market
            tp_order = await self.exchange.create_order(
                symbol=norm_symbol,
                type='TAKE_PROFIT_MARKET',
                side=opposite_side,
                amount=amount_formatted,
                params={
                    'stopPrice': tp_formatted,
                    'reduceOnly': True
                }
            )
            logger.info(f"🎯 Take Profit configurado a ${tp_formatted} en {norm_symbol}")
        except Exception as e:
            logger.error(f"Error al colocar Take Profit en {norm_symbol}: {e}")

        position_size_usdt = amount_formatted * entry_price

        return {
            "status": "success",
            "symbol": norm_symbol,
            "action": action_clean,
            "entry_price": entry_price,
            "amount_qty": amount_formatted,
            "position_size_usdt": position_size_usdt,
            "leverage": lev,
            "margin_mode": m_mode,
            "sl_price": sl_formatted,
            "tp_price": tp_formatted,
            "main_order_id": main_order.get("id"),
            "sl_order_id": sl_order.get("id") if sl_order else None,
            "tp_order_id": tp_order.get("id") if tp_order else None
        }


exchange_client = BinanceFuturesClient()
