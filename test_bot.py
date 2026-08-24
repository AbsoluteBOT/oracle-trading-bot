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

    def test_risk_manager_position_calculation(self):
        """Prueba el cálculo cuantitativo del tamaño de posición."""
        # Balance = 1000 USDT, Risk = 2%, Leverage = 5x, Price = $50,000
        # Margin Allocated = 20 USDT
        # Notional Value = 100 USDT
        # Raw Quantity = 100 / 50000 = 0.002 BTC
        res = risk_manager.calculate_position_size(
            usdt_balance=1000.0,
            risk_percent=2.0,
            leverage=5,
            current_price=50000.0
        )
        self.assertTrue(res["is_valid"])
        self.assertAlmostEqual(res["margin_allocated"], 20.0)
        self.assertAlmostEqual(res["notional_value"], 100.0)
        self.assertAlmostEqual(res["quantity"], 0.002)

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


if __name__ == "__main__":
    unittest.main()


