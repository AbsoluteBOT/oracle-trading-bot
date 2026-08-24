import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("risk_manager")


class RiskManager:
    """
    Gestor de Riesgo Cuantitativo para la gestión de apalancamiento, cálculo de tamaño
    de posición por Stop Loss y ajuste automático a mínimos del exchange.
    """

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Normaliza símbolos de TradingView (ej: 'BYBIT:BTCUSDT', 'BTC/USDT', 'BTCUSDT.P', 'BTC/USDT:USDT')
        al formato estándar de CCXT ('BTC/USDT:USDT' o 'BTC/USDT').
        """
        sym = symbol.strip().upper()

        # Si viene con prefijo de exchange de TradingView (ej: BYBIT:BTCUSDT -> BTCUSDT)
        if ":" in sym and not sym.endswith(":USDT"):
            parts = sym.split(":")
            if len(parts) == 2 and "/" not in parts[0]:
                sym = parts[1]

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
        market_limits: Dict[str, Any] = None,
        sl_percent: float = None
    ) -> Dict[str, Any]:
        """
        Calcula la cantidad de contratos a operar basados en el dinero arriesgado y la distancia del Stop Loss.
        
        Formula de Riesgo por Stop Loss:
          - Dinero Arriesgado (USDT) = usdt_balance * (risk_percent / 100)
          - Distancia SL = sl_percent / 100  (ej: 2.0% -> 0.02)
          - Valor Nocional (USDT) = Dinero Arriesgado / Distancia SL
            Ejemplo: Balance=200 USDT, Risk=7.5% ($15 arriesgados), SL=2.0% (0.02)
            -> Nocional = 15.0 / 0.02 = $750 USDT Nocionales
          - Cantidad de Contratos (Raw Qty) = Valor Nocional / Precio Actual

        Si la cantidad calculada es menor al min_amount o min_qty exigido por el exchange,
        se ajusta automáticamente al mínimo en lugar de cancelarse o redondearse a 0.
        """
        if usdt_balance <= 0 or current_price <= 0:
            return {
                "is_valid": False,
                "reason": "Balance de cuenta o precio inválido (<= 0)",
                "quantity": 0.0,
                "margin_allocated": 0.0,
                "notional_value": 0.0
            }

        risk_amount = usdt_balance * (risk_percent / 100.0)

        effective_sl = sl_percent if sl_percent is not None and sl_percent > 0 else None

        if effective_sl:
            sl_distance = effective_sl / 100.0
            notional_value = risk_amount / sl_distance
        else:
            # Fallback si no hay SL especificado
            margin_allocated_base = risk_amount
            notional_value = margin_allocated_base * leverage

        raw_quantity = notional_value / current_price
        margin_allocated = notional_value / leverage if leverage > 0 else notional_value

        # Extraer límites de la exchange (min_qty y min_cost)
        min_qty = 0.001
        min_cost = 5.0

        if market_limits:
            amount_limits = market_limits.get("limits", {}).get("amount", {})
            cost_limits = market_limits.get("limits", {}).get("cost", {})
            if "min" in amount_limits and amount_limits["min"] is not None and float(amount_limits["min"]) > 0:
                min_qty = float(amount_limits["min"])
            if "min" in cost_limits and cost_limits["min"] is not None and float(cost_limits["min"]) > 0:
                min_cost = float(cost_limits["min"])

        # 1. Ajuste automático por min_qty (Mínimo de contratos/monedas)
        if raw_quantity < min_qty:
            logger.info(f"⚠️ Cantidad calculada ({raw_quantity:.6f}) menor al mínimo del exchange ({min_qty}). Ajustando al mínimo.")
            raw_quantity = min_qty
            notional_value = raw_quantity * current_price
            margin_allocated = notional_value / leverage if leverage > 0 else notional_value

        # 2. Ajuste automático por min_cost (Nocional mínimo)
        if notional_value < min_cost:
            logger.info(f"⚠️ Valor nocional (${notional_value:.2f}) menor al costo mínimo del exchange (${min_cost:.2f}). Ajustando al mínimo.")
            raw_quantity = max(min_qty, min_cost / current_price)
            notional_value = raw_quantity * current_price
            margin_allocated = notional_value / leverage if leverage > 0 else notional_value

        return {
            "is_valid": True,
            "reason": "OK",
            "quantity": raw_quantity,
            "margin_allocated": margin_allocated,
            "notional_value": notional_value,
            "risk_amount": risk_amount,
            "min_qty": min_qty
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
