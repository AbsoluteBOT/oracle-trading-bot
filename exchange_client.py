import logging
from typing import Dict, Any, Optional
import ccxt.async_support as ccxt

from config import settings
from risk_manager import risk_manager

logger = logging.getLogger("exchange_client")


class UniversalExchangeClient:
    """
    Cliente de Exchange de Futuros/Perpetuos universal impulsado por CCXT.
    Soporta Bybit, Binance, OKX, Bitget, etc.
    """

    def __init__(self):
        self.exchange: Optional[ccxt.Exchange] = None
        self.current_exchange_id: Optional[str] = None

    async def initialize(self, force_reinit: bool = False):
        """
        Inicializa dinámicamente la instancia del exchange configurado en settings.EXCHANGE.
        """
        target_exchange_id = settings.EXCHANGE.lower().strip() or "bybit"

        if self.exchange is not None and self.current_exchange_id == target_exchange_id and not force_reinit:
            return

        if self.exchange is not None:
            await self.close()

        logger.info(f"⚡ Inicializando cliente para Exchange: {target_exchange_id.upper()}...")

        # Resolver clase de CCXT
        if target_exchange_id in ['binance', 'binanceusdm', 'binance_futures']:
            exchange_class = ccxt.binanceusdm
        elif target_exchange_id in ['bybit']:
            exchange_class = ccxt.bybit
        elif hasattr(ccxt, target_exchange_id):
            exchange_class = getattr(ccxt, target_exchange_id)
        else:
            raise ValueError(f"El exchange '{target_exchange_id}' no es soportado por CCXT.")

        # Obtener apiKey y secret considerando BYBIT_API_KEY y EXCHANGE_API_KEY
        if target_exchange_id == 'bybit':
            api_key = settings.BYBIT_API_KEY or settings.EXCHANGE_API_KEY or settings.active_api_key
            secret_key = settings.BYBIT_SECRET_KEY or settings.EXCHANGE_SECRET_KEY or settings.active_secret_key
        else:
            api_key = settings.active_api_key
            secret_key = settings.active_secret_key

        config_params: Dict[str, Any] = {
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {}
        }


        if settings.EXCHANGE_PASSWORD:
            config_params['password'] = settings.EXCHANGE_PASSWORD

        # Opciones por defecto para derivados según el exchange
        if target_exchange_id == 'bybit':
            config_params['options']['defaultType'] = 'linear'
        elif target_exchange_id in ['binance', 'binanceusdm']:
            config_params['options']['defaultType'] = 'future'
            config_params['options']['adjustForTimeDifference'] = True

        self.exchange = exchange_class(config_params)
        self.current_exchange_id = target_exchange_id

        if settings.is_testnet:
            try:
                self.exchange.set_sandbox_mode(True)
                logger.info(f"🧪 Modo Testnet para {target_exchange_id.upper()} ACTIVADO.")
            except Exception as e:
                logger.warning(f"Nota/Aviso al activar sandbox/testnet en {target_exchange_id}: {e}")
        else:
            try:
                self.exchange.set_sandbox_mode(False)
            except Exception:
                pass
            logger.info(f"🌐 Modo REAL / Mainnet para {target_exchange_id.upper()} ACTIVADO.")


        try:
            await self.exchange.load_markets()
            logger.info(f"✅ Mercados de {target_exchange_id.upper()} cargados con éxito ({len(self.exchange.markets)} pares).")
        except Exception as e:
            logger.error(f"❌ Error al conectar con {target_exchange_id.upper()}: {e}")

    async def close(self):
        """
        Cierra la conexión asíncrona de CCXT.
        """
        if self.exchange:
            ex_name = self.current_exchange_id or "exchange"
            try:
                await self.exchange.close()
            except Exception as e:
                logger.debug(f"Error al cerrar exchange: {e}")
            self.exchange = None
            self.current_exchange_id = None
            logger.info(f"Conexión con {ex_name.upper()} cerrada.")

    def find_market_symbol(self, raw_symbol: str) -> str:
        """
        Busca el símbolo correspondiente en los mercados cargados del exchange.
        """
        if not self.exchange or not self.exchange.markets:
            return risk_manager.normalize_symbol(raw_symbol)

        norm = risk_manager.normalize_symbol(raw_symbol)
        if norm in self.exchange.markets:
            return norm

        # Buscar coincidencias sin sufijo / o :
        clean = raw_symbol.upper().replace(".P", "").replace("/", "").replace(":", "")
        for m_symbol in self.exchange.markets.keys():
            m_clean = m_symbol.upper().replace("/", "").replace(":", "")
            if clean == m_clean:
                return m_symbol

        return norm

    async def set_leverage_and_margin(self, symbol: str, leverage: int, margin_mode: str):
        """
        Configura el apalancamiento y el tipo de margen (ISOLATED/CROSSED).
        """
        if not self.exchange:
            await self.initialize()

        try:
            await self.exchange.set_leverage(leverage, symbol)
            logger.info(f"Apalancamiento de {leverage}x configurado para {symbol} en {self.exchange.id.upper()}.")
        except Exception as e:
            logger.warning(f"Nota/Aviso al configurar apalancamiento en {symbol} ({self.exchange.id}): {e}")

        try:
            mode = margin_mode.upper()
            await self.exchange.set_margin_mode(mode, symbol)
            logger.info(f"Modo de margen {mode} configurado para {symbol} en {self.exchange.id.upper()}.")
        except Exception as e:
            logger.debug(f"Nota/Aviso al configurar tipo de margen en {symbol} ({self.exchange.id}): {e}")

    async def get_usdt_balance(self) -> float:
        """
        Obtiene el balance disponible en USDT en la cuenta de Futuros/Perpetuos.
        """
        if not self.exchange:
            await self.initialize()

        try:
            params = {}
            if self.exchange.id in ['binanceusdm', 'binance']:
                params = {'type': 'future'}
            elif self.exchange.id == 'bybit':
                params = {'type': 'linear'}

            balance = await self.exchange.fetch_balance(params)
            
            # 1. Probar estructura estándar CCXT dict por moneda
            usdt_info = balance.get('USDT', {})
            if isinstance(usdt_info, dict):
                free = usdt_info.get('free')
                total = usdt_info.get('total')
                if free is not None and float(free) > 0:
                    return float(free)
                if total is not None and float(total) > 0:
                    return float(total)

            # 2. Probar estructura balance['free']['USDT']
            free_dict = balance.get('free', {})
            if isinstance(free_dict, dict) and 'USDT' in free_dict and free_dict['USDT'] is not None:
                return float(free_dict['USDT'])

            # 3. Probar estructura balance['total']['USDT']
            total_dict = balance.get('total', {})
            if isinstance(total_dict, dict) and 'USDT' in total_dict and total_dict['USDT'] is not None:
                return float(total_dict['USDT'])

            return 0.0
        except Exception as e:
            logger.error(f"Error al consultar balance de USDT en {self.exchange.id}: {e}")
            raise RuntimeError(f"Fallo al obtener balance de {self.exchange.id}: {e}")

    async def get_open_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Consulta la posición abierta actual para el símbolo especificado.
        """
        if not self.exchange:
            await self.initialize()

        try:
            positions = await self.exchange.fetch_positions([symbol])
            for pos in positions:
                contracts = float(pos.get('contracts', 0) or pos.get('positionAmt', 0) or pos.get('size', 0))
                if abs(contracts) > 0:
                    side = pos.get('side', '').lower()
                    if not side or side == 'both':
                        side = 'long' if contracts > 0 else 'short'
                    return {
                        'contracts': abs(contracts),
                        'side': side,
                        'entryPrice': float(pos.get('entryPrice', 0) or pos.get('entry_price', 0)),
                        'unrealizedPnl': float(pos.get('unrealizedPnl', 0) or pos.get('unrealisedPnl', 0)),
                        'info': pos
                    }
        except Exception as e:
            logger.error(f"Error consultando posiciones abiertas de {symbol} en {self.exchange.id}: {e}")
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

        logger.info(f"🔄 Cerrando posición existente {current_side.upper()} de {contracts} contratos en {symbol} ({self.exchange.id.upper()})...")
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

        norm_symbol = self.find_market_symbol(symbol)
        action_clean = action.lower().strip()
        risk_pct = risk_percent if risk_percent is not None else settings.RISK_PERCENT
        lev = leverage if leverage is not None else settings.DEFAULT_LEVERAGE
        m_mode = margin_mode or settings.MARGIN_MODE

        logger.info(f"📥 Procesando Señal ({self.exchange.id.upper()}): Acción='{action_clean}', Símbolo='{norm_symbol}', Precio TV={price}")

        # 1. Verificar mercado válido
        if norm_symbol not in self.exchange.markets:
            await self.exchange.load_markets()
            norm_symbol = self.find_market_symbol(symbol)
            if norm_symbol not in self.exchange.markets:
                raise ValueError(f"El símbolo '{norm_symbol}' (original '{symbol}') no está disponible en {self.exchange.id.upper()}.")

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
                "exchange": self.exchange.id,
                "message": f"Posición cerrada en {norm_symbol}"
            }

        # 4. Obtener precio actual de entrada mercado si no vino en el webhook
        if not price or price <= 0:
            ticker = await self.exchange.fetch_ticker(norm_symbol)
            entry_price = float(ticker.get('last') or ticker.get('close') or 0.0)
        else:
            entry_price = float(price)

        # 5. Obtener balance de USDT y calcular tamaño de posición
        balance_usdt = await self.get_usdt_balance()
        risk_result = risk_manager.calculate_position_size(
            usdt_balance=balance_usdt,
            risk_percent=risk_pct,
            leverage=lev,
            current_price=entry_price,
            market_limits=market_info,
            sl_percent=settings.STOP_LOSS_PERCENT
        )

        if not risk_result["is_valid"]:
            raise ValueError(f"Riesgo/Posición Inválida: {risk_result['reason']}")

        raw_qty = risk_result["quantity"]
        min_qty = risk_result.get("min_qty", 0.001)
        amount_formatted = float(self.exchange.amount_to_precision(norm_symbol, raw_qty))
        if amount_formatted < min_qty:
            amount_formatted = min_qty


        # 6. Ejecutar orden a MERCADO
        order_side = 'buy' if action_clean == 'buy' else 'sell'
        logger.info(f"🚀 Ejecutando Orden Mercado {order_side.upper()} de {amount_formatted} contratos en {norm_symbol} ({self.exchange.id.upper()})...")

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

        # Estrategias adaptativas de Stop Loss para distintos exchanges (Bybit vs Binance vs Otros)
        try:
            if self.exchange.id == 'bybit':
                sl_order = await self.exchange.create_order(
                    symbol=norm_symbol,
                    type='market',
                    side=opposite_side,
                    amount=amount_formatted,
                    params={
                        'stopPrice': sl_formatted,
                        'triggerPrice': sl_formatted,
                        'reduceOnly': True
                    }
                )
            else:
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
            logger.error(f"Error al colocar Stop Loss en {norm_symbol} ({self.exchange.id}): {e}")

        try:
            if self.exchange.id == 'bybit':
                tp_order = await self.exchange.create_order(
                    symbol=norm_symbol,
                    type='market',
                    side=opposite_side,
                    amount=amount_formatted,
                    params={
                        'stopPrice': tp_formatted,
                        'triggerPrice': tp_formatted,
                        'reduceOnly': True
                    }
                )
            else:
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
            logger.error(f"Error al colocar Take Profit en {norm_symbol} ({self.exchange.id}): {e}")

        position_size_usdt = amount_formatted * entry_price

        return {
            "status": "success",
            "exchange": self.exchange.id,
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


# Instancia única reutilizable
exchange_client = UniversalExchangeClient()
