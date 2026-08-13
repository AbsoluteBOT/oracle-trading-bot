import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("risk_manager")


class RiskManager:
    """
    Gestor de Riesgo Cuantitativo para la gestión de apalancamiento, cálculo de tamaño
    de posición y generación de niveles de Stop Loss y Take Profit.
    """

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Normaliza símbolos de TradingView (ej: 'BTC/USDT', 'BTCUSDT', 'BTC/USDT:USDT')
        al formato estándar de CCXT Binance Futuros USDT-M ('BTC/USDT:USDT' o 'BTC/USDT').
        """
        sym = symbol.strip().upper()
        if sym.endswith(".P"):
            sym = sym[:-2]  # Elimina extensión de TradingView como BTCUSDT.P

        if "/" not in sym:
            if sym.endswith("USDT"):
                base = sym[:-4]
                sym = f"{base}/USDT"

        if ":" not in sym and "/" in sym:
            sym = f"{sym}:USDT"

        return sym

    @staticmethod
    def calculate_position_size(
        usdt_balance: float,
        risk_percent: float,
        leverage: int,
        current_price: float,
        market_limits: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Calcula la cantidad de contratos a operar basados en un porcentaje del balance total.
        
        Formula:
          - Margen Asignado (USDT) = Balance * (Risk % / 100)
          - Valor Nocional Total (USDT) = Margen Asignado * Apalancamiento
          - Cantidad de Contratos (Raw Qty) = Valor Nocional / Precio Entrante
        """
        if usdt_balance <= 0 or current_price <= 0:
            return {
                "is_valid": False,
                "reason": "Balance de cuenta o precio inválido (<= 0)",
                "quantity": 0.0,
                "margin_allocated": 0.0,
                "notional_value": 0.0
            }

        margin_allocated = usdt_balance * (risk_percent / 100.0)
        notional_value = margin_allocated * leverage
        raw_quantity = notional_value / current_price

        min_qty = 0.001
        min_cost = 5.0  # Mínimo nocional aproximado en Binance Futuros (5 USDT)

        if market_limits:
            amount_limits = market_limits.get("limits", {}).get("amount", {})
            cost_limits = market_limits.get("limits", {}).get("cost", {})
            if "min" in amount_limits and amount_limits["min"] is not None:
                min_qty = float(amount_limits["min"])
            if "min" in cost_limits and cost_limits["min"] is not None:
                min_cost = float(cost_limits["min"])

        if raw_quantity < min_qty:
            return {
                "is_valid": False,
                "reason": f"Cantidad calculada ({raw_quantity:.6f}) menor al mínimo permitido ({min_qty})",
                "quantity": 0.0,
                "margin_allocated": margin_allocated,
                "notional_value": notional_value
            }

        if notional_value < min_cost:
            return {
                "is_valid": False,
                "reason": f"Valor nocional (${notional_value:.2f}) menor al mínimo permitido por la exchange (${min_cost:.2f} USDT)",
                "quantity": 0.0,
                "margin_allocated": margin_allocated,
                "notional_value": notional_value
            }

        return {
            "is_valid": True,
            "reason": "OK",
            "quantity": raw_quantity,
            "margin_allocated": margin_allocated,
            "notional_value": notional_value
        }

    @staticmethod
    def calculate_sl_tp_prices(
        action: str,
        entry_price: float,
        sl_percent: float,
        tp_percent: float
    ) -> Tuple[float, float]:
        """
        Calcula los precios absolutos de Stop Loss y Take Profit.
        """
        action_lower = action.lower()
        if action_lower == "buy":
            sl_price = entry_price * (1.0 - sl_percent / 100.0)
            tp_price = entry_price * (1.0 + tp_percent / 100.0)
        elif action_lower == "sell":
            sl_price = entry_price * (1.0 + sl_percent / 100.0)
            tp_price = entry_price * (1.0 - tp_percent / 100.0)
        else:
            sl_price = 0.0
            tp_price = 0.0

        return round(sl_price, 4), round(tp_price, 4)


risk_manager = RiskManager()
