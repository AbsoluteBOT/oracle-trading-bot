import unittest
import asyncio
from fastapi.testclient import TestClient

from config import settings
from main import app
from risk_manager import risk_manager
from telegram_notifier import TelegramNotifier


class TestTradingBot(unittest.TestCase):
    """
    Pruebas unitarias para verificar la gestión de riesgo, validación de webhook,
    normalización multi-exchange y API de configuración GUI.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_symbol_normalization(self):
        """Prueba la normalización de símbolos recibidos de TradingView (incluyendo Bybit)."""
        self.assertEqual(risk_manager.normalize_symbol("BTC/USDT"), "BTC/USDT:USDT")
        self.assertEqual(risk_manager.normalize_symbol("BTCUSDT"), "BTC/USDT:USDT")
        self.assertEqual(risk_manager.normalize_symbol("ETHUSDT.P"), "ETH/USDT:USDT")
        self.assertEqual(risk_manager.normalize_symbol("SOL/USDT:USDT"), "SOL/USDT:USDT")
        self.assertEqual(risk_manager.normalize_symbol("BYBIT:BTCUSDT"), "BTC/USDT:USDT")
        self.assertEqual(risk_manager.normalize_symbol("BINANCE:ETHUSDT.P"), "ETH/USDT:USDT")

    def test_risk_manager_position_calculation_by_sl(self):
        """
        Prueba el cálculo de posición por Stop Loss:
        Balance = 200 USDT, Risk % = 7.5% ($15 USDT arriesgados), SL = 2.0% (0.02)
        Nocional exacto = $15 / 0.02 = $750 USDT.
        """
        res = risk_manager.calculate_position_size(
            usdt_balance=200.0,
            risk_percent=7.5,
            leverage=5,
            current_price=50000.0,
            sl_percent=2.0
        )
        self.assertTrue(res["is_valid"])
        self.assertAlmostEqual(res["risk_amount"], 15.0)
        self.assertAlmostEqual(res["notional_value"], 750.0)
        self.assertAlmostEqual(res["quantity"], 0.015)

    def test_risk_manager_auto_adjust_min_qty(self):
        """
        Prueba que si la cantidad calculada es menor al mínimo del exchange (ej: 0.01 ETH),
        se ajuste automáticamente al mínimo permitido en lugar de fallar o cancelar.
        """
        market_limits = {"limits": {"amount": {"min": 0.01}, "cost": {"min": 5.0}}}
        res = risk_manager.calculate_position_size(
            usdt_balance=10.0,
            risk_percent=0.1,
            leverage=5,
            current_price=3000.0,
            market_limits=market_limits,
            sl_percent=5.0
        )
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["quantity"], 0.01)
        self.assertAlmostEqual(res["notional_value"], 30.0)


    def test_sl_tp_calculation(self):
        """Prueba el cálculo de niveles de Stop Loss y Take Profit."""
        # Buy LONG @ $100. SL = 1.5%, TP = 3.0% -> SL = $98.5, TP = $103.0
        sl_buy, tp_buy = risk_manager.calculate_sl_tp_prices("buy", 100.0, 1.5, 3.0)
        self.assertEqual(sl_buy, 98.5)
        self.assertEqual(tp_buy, 103.0)

        # Sell SHORT @ $100. SL = 1.5%, TP = 3.0% -> SL = $101.5, TP = $97.0
        sl_sell, tp_sell = risk_manager.calculate_sl_tp_prices("sell", 100.0, 1.5, 3.0)
        self.assertEqual(sl_sell, 101.5)
        self.assertEqual(tp_sell, 97.0)

    def test_webhook_unauthorized_passphrase(self):
        """Prueba que el Webhook rechace peticiones con passphrase incorrecta."""
        payload = {
            "passphrase": "passphrase_incorrecta",
            "action": "buy",
            "symbol": "BTC/USDT",
            "price": 60000.0,
            "timeframe": "1h"
        }
        response = self.client.post("/webhook", json=payload)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Passphrase del Webhook es inválida", response.json()["detail"])

    def test_webhook_invalid_action(self):
        """Prueba que la validación de Pydantic rechace acciones no permitidas."""
        payload = {
            "passphrase": settings.WEBHOOK_PASSPHRASE,
            "action": "invalid_action",
            "symbol": "BTC/USDT",
            "price": 60000.0
        }
        response = self.client.post("/webhook", json=payload)
        self.assertEqual(response.status_code, 422)  # Unprocessable Entity de Pydantic

    def test_api_config_get_and_post(self):
        """Prueba la obtención y actualización de parámetros vía API REST (para la GUI)."""
        # 1. GET /api/config
        get_res = self.client.get("/api/config")
        self.assertEqual(get_res.status_code, 200)
        config_data = get_res.json()
        self.assertIn("exchange", config_data)
        self.assertIn("risk_percent", config_data)
        self.assertIn("default_leverage", config_data)

        # 2. POST /api/config
        update_payload = {
            "exchange": "bybit",
            "risk_percent": 3.5,
            "default_leverage": 10,
            "stop_loss_percent": 2.0,
            "take_profit_percent": 5.0
        }
        post_res = self.client.post("/api/config", json=update_payload)
        self.assertEqual(post_res.status_code, 200)
        post_data = post_res.json()
        self.assertTrue(post_data.get("success"))
        self.assertEqual(settings.EXCHANGE, "bybit")
        self.assertEqual(settings.RISK_PERCENT, 3.5)
        self.assertEqual(settings.DEFAULT_LEVERAGE, 10)

    def test_boolean_testnet_parsing(self):
        """Prueba que los valores booleanos de testnet ('False', 'false', False) se parseen correctamente."""
        from config import parse_bool, update_settings_in_memory_and_env
        self.assertFalse(parse_bool("False"))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool(False))
        self.assertTrue(parse_bool("True"))
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool(True))

        # Probar actualización de settings
        update_settings_in_memory_and_env({"exchange_testnet": False})
        self.assertFalse(settings.is_testnet)

        update_settings_in_memory_and_env({"exchange_testnet": True})
        self.assertTrue(settings.is_testnet)

    def test_bybit_api_key_resolution(self):
        """Prueba que la resolución de claves lea de BYBIT_API_KEY y BYBIT_SECRET_KEY."""
        settings.EXCHANGE = "bybit"
        settings.BYBIT_API_KEY = "test_bybit_key"
        settings.BYBIT_SECRET_KEY = "test_bybit_secret"
        self.assertEqual(settings.active_api_key, "test_bybit_key")
        self.assertEqual(settings.active_secret_key, "test_bybit_secret")

    def test_bybit_native_sl_tp_in_create_order(self):
        """
        Prueba que al ejecutar órdenes en Bybit, se pasen explícitamente stopLoss y takeProfit
        en los params de create_order con tpslMode='Full' y positionIdx=0.
        """
        from unittest.mock import AsyncMock, patch, MagicMock
        from exchange_client import UniversalExchangeClient

        client = UniversalExchangeClient()
        mock_exchange = MagicMock()
        mock_exchange.id = "bybit"
        mock_exchange.markets = {
            "BTC/USDT:USDT": {
                "id": "BTCUSDT",
                "symbol": "BTC/USDT:USDT",
                "type": "swap",
                "spot": False,
                "linear": True,
                "precision": {"amount": 0.001, "price": 0.1},
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 5.0}}
            }
        }
        mock_exchange.amount_to_precision.return_value = "0.010"
        mock_exchange.price_to_precision.side_effect = lambda sym, price: f"{price:.1f}"
        mock_exchange.set_leverage = AsyncMock()
        mock_exchange.set_margin_mode = AsyncMock()
        mock_exchange.fetch_positions = AsyncMock(return_value=[])
        mock_exchange.fetch_balance = AsyncMock(return_value={"USDT": {"free": 1000.0, "total": 1000.0}})
        mock_exchange.create_order = AsyncMock(return_value={"id": "bybit_order_123"})
        mock_exchange.set_trading_stop = AsyncMock()

        client.exchange = mock_exchange
        client.current_exchange_id = "bybit"

        # 1. Probar Orden BUY
        result_buy = asyncio.run(client.process_signal(
            action="buy",
            symbol="BTC/USDT",
            price=50000.0
        ))

        self.assertEqual(result_buy["status"], "success")
        self.assertEqual(result_buy["action"], "buy")
        mock_exchange.create_order.assert_called()
        call_kwargs = mock_exchange.create_order.call_args[1]
        self.assertEqual(call_kwargs["symbol"], "BTC/USDT:USDT")
        self.assertEqual(call_kwargs["side"], "buy")
        self.assertIn("stopLoss", call_kwargs["params"])
        self.assertIn("takeProfit", call_kwargs["params"])
        self.assertEqual(call_kwargs["params"]["tpslMode"], "Full")
        self.assertEqual(call_kwargs["params"]["positionIdx"], 0)

        # 2. Probar Orden SELL (Short sin posición previa)
        mock_exchange.create_order.reset_mock()
        result_sell = asyncio.run(client.process_signal(
            action="sell",
            symbol="BTC/USDT",
            price=50000.0
        ))

        self.assertEqual(result_sell["status"], "success")
        self.assertEqual(result_sell["action"], "sell")
        call_kwargs_sell = mock_exchange.create_order.call_args[1]
        self.assertEqual(call_kwargs_sell["symbol"], "BTC/USDT:USDT")
        self.assertEqual(call_kwargs_sell["side"], "sell")
        self.assertIn("stopLoss", call_kwargs_sell["params"])
        self.assertIn("takeProfit", call_kwargs_sell["params"])
        # Para sell, SL está arriba (ej: 50750) y TP abajo (ej: 48500)
        self.assertGreater(float(call_kwargs_sell["params"]["stopLoss"]), 50000.0)
        self.assertLess(float(call_kwargs_sell["params"]["takeProfit"]), 50000.0)

    def test_sell_execution_closes_long_position(self):
        """
        Prueba que si ya existe un LONG abierto, una señal SELL cierre/reduzca la posición
        en lugar de abrir una posición adicional conflictiva.
        """
        from unittest.mock import AsyncMock, MagicMock
        from exchange_client import UniversalExchangeClient

        client = UniversalExchangeClient()
        mock_exchange = MagicMock()
        mock_exchange.id = "bybit"
        mock_exchange.markets = {
            "BTC/USDT:USDT": {
                "id": "BTCUSDT",
                "symbol": "BTC/USDT:USDT",
                "type": "swap",
                "precision": {"amount": 0.001, "price": 0.1}
            }
        }
        mock_exchange.amount_to_precision.return_value = "0.050"
        # Simulamos posición Long activa de 0.05 BTC
        mock_exchange.fetch_positions = AsyncMock(return_value=[
            {
                "symbol": "BTC/USDT:USDT",
                "contracts": 0.05,
                "side": "long",
                "entryPrice": 50000.0,
                "unrealizedPnl": 10.0
            }
        ])
        mock_exchange.create_order = AsyncMock(return_value={"id": "close_order_999"})

        client.exchange = mock_exchange
        client.current_exchange_id = "bybit"

        result = asyncio.run(client.process_signal(
            action="sell",
            symbol="BTC/USDT",
            price=51000.0
        ))

        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["action"], "sell")
        mock_exchange.create_order.assert_called_once()
        close_args = mock_exchange.create_order.call_args[1]
        self.assertEqual(close_args["side"], "sell")
        self.assertTrue(close_args["params"]["reduceOnly"])

    def test_max_open_positions_guard(self):
        """
        Prueba que el guard MAX_OPEN_POSITIONS:
        1. Omita la apertura de nuevos pares si positions >= MAX_OPEN_POSITIONS.
        2. Permita señales de cierre para pares ya abiertos.
        3. Envíe la notificación a Telegram con el mensaje exacto.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from exchange_client import UniversalExchangeClient

        client = UniversalExchangeClient()
        mock_exchange = MagicMock()
        mock_exchange.id = "bybit"
        mock_exchange.markets = {
            "BTC/USDT:USDT": {"id": "BTCUSDT", "symbol": "BTC/USDT:USDT", "precision": {"amount": 0.001, "price": 0.1}},
            "ETH/USDT:USDT": {"id": "ETHUSDT", "symbol": "ETH/USDT:USDT", "precision": {"amount": 0.01, "price": 0.01}},
            "SOL/USDT:USDT": {"id": "SOLUSDT", "symbol": "SOL/USDT:USDT", "precision": {"amount": 0.1, "price": 0.01}}
        }
        mock_exchange.amount_to_precision.return_value = "1.0"
        mock_exchange.price_to_precision.return_value = "100.0"

        # 2 posiciones activas ya abiertas (BTC y ETH)
        active_positions = [
            {"symbol": "BTC/USDT:USDT", "contracts": 0.01, "side": "long", "entryPrice": 50000.0},
            {"symbol": "ETH/USDT:USDT", "contracts": 0.5, "side": "long", "entryPrice": 3000.0}
        ]

        def mock_fetch_pos(symbols=None, params=None):
            if symbols:
                sym = symbols[0]
                return [p for p in active_positions if p["symbol"] == sym]
            return active_positions

        mock_exchange.fetch_positions = AsyncMock(side_effect=mock_fetch_pos)
        mock_exchange.create_order = AsyncMock(return_value={"id": "order_test"})
        client.exchange = mock_exchange
        client.current_exchange_id = "bybit"

        settings.MAX_OPEN_POSITIONS = 2

        with patch("exchange_client.notifier.send_message", new_callable=AsyncMock) as mock_notifier:
            # 1. Intento de abrir un NUEVO par (SOL/USDT) cuando el límite es 2 -> Debe OMITIRSE
            result_skip = asyncio.run(client.process_signal(
                action="buy",
                symbol="SOL/USDT",
                price=100.0
            ))

            self.assertEqual(result_skip["status"], "skipped")
            self.assertIn("límite máximo de 2", result_skip["reason"])
            mock_notifier.assert_called_once_with(
                "⚠️ Orden omitida para SOL/USDT:USDT: Se alcanzó el límite máximo de 2 posiciones abiertas."
            )

            # 2. Intento de CERRAR un par ya existente (BTC/USDT) con acción SELL -> NO debe omitirse
            result_close = asyncio.run(client.process_signal(
                action="sell",
                symbol="BTC/USDT",
                price=52000.0
            ))
            self.assertEqual(result_close["status"], "closed")

            # 3. Intento de CERRAR con acción CLOSE -> NO debe omitirse
            result_explicit_close = asyncio.run(client.process_signal(
                action="close",
                symbol="ETH/USDT"
            ))
            self.assertEqual(result_explicit_close["status"], "closed")


if __name__ == "__main__":
    unittest.main()


