#!/usr/bin/env python3
"""
Oracle Trading Bot - Configuración de Parámetros GUI
Programa gráfico sencillo para visualizar y actualizar los parámetros del bot de trading en tiempo real.
"""

import os
import json
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox

from config import settings, update_settings_in_memory_and_env

DEFAULT_BOT_URL = "http://localhost:8000"


class BotConfigApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Oracle Trading Bot - Panel de Configuración")
        self.geometry("480x630")
        self.resizable(False, False)

        # Estilos modernos
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        # Paleta de colores
        bg_dark = "#1e1e2e"
        fg_light = "#cdd6f4"
        accent_blue = "#89b4fa"

        self.configure(bg=bg_dark)
        
        self.style.configure(".", background=bg_dark, foreground=fg_light, font=("Segoe UI", 10))
        self.style.configure("TLabel", background=bg_dark, foreground=fg_light)
        self.style.configure("TCheckbutton", background=bg_dark, foreground=fg_light)
        self.style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground=accent_blue)
        self.style.configure("Status.TLabel", font=("Segoe UI", 9, "italic"), foreground="#a6adc8")
        
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), background="#a6e3a1", foreground="#11111b")
        self.style.map("Primary.TButton", background=[("active", "#94e2d5")])

        self.style.configure("Secondary.TButton", font=("Segoe UI", 9), background="#45475a", foreground=fg_light)
        self.style.map("Secondary.TButton", background=[("active", "#585b70")])

        # Variables de control
        self.var_bot_url = tk.StringVar(value=DEFAULT_BOT_URL)
        self.var_exchange = tk.StringVar(value=settings.EXCHANGE)
        self.var_max_pos = tk.StringVar(value=str(settings.MAX_OPEN_POSITIONS))
        self.var_risk = tk.StringVar(value=str(settings.RISK_PERCENT))
        self.var_leverage = tk.StringVar(value=str(settings.DEFAULT_LEVERAGE))
        self.var_tp = tk.StringVar(value=str(settings.TAKE_PROFIT_PERCENT))
        self.var_sl = tk.StringVar(value=str(settings.STOP_LOSS_PERCENT))
        self.var_margin = tk.StringVar(value=settings.MARGIN_MODE)
        self.var_testnet = tk.BooleanField(value=settings.is_testnet)
        self.var_status = tk.StringVar(value="Listo. Presiona 'Cargar Datos Actuales' para sincronizar con el bot.")

        self._create_widgets()
        
        # Intentar cargar datos actuales al iniciar
        self.after(500, self.load_current_config)

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        header = ttk.Label(main_frame, text="⚙️ Configuración del Bot", style="Header.TLabel")
        header.pack(anchor=tk.W, pady=(0, 15))

        # URL del Bot
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=4)
        ttk.Label(url_frame, text="URL Servidor Bot:").pack(side=tk.LEFT)
        ttk.Entry(url_frame, textvariable=self.var_bot_url, width=24).pack(side=tk.RIGHT)

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Formulario de Parámetros
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        row = 0
        # 1. Exchange
        ttk.Label(form_frame, text="Exchange (Broker):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ex_combo = ttk.Combobox(
            form_frame,
            textvariable=self.var_exchange,
            values=["bybit", "binance", "okx", "bitget", "kucoinfutures"],
            state="readonly",
            width=18
        )
        ex_combo.grid(row=row, column=1, sticky=tk.E, pady=5)

        row += 1
        # 2. Max Posiciones Abiertas
        ttk.Label(form_frame, text="Máx. Posiciones Abiertas:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(form_frame, textvariable=self.var_max_pos, width=20).grid(row=row, column=1, sticky=tk.E, pady=5)

        row += 1
        # 3. % de Cartera
        ttk.Label(form_frame, text="% de Cartera a Usar (Riesgo):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(form_frame, textvariable=self.var_risk, width=20).grid(row=row, column=1, sticky=tk.E, pady=5)

        row += 1
        # 4. Apalancamiento (Leverage)
        ttk.Label(form_frame, text="Apalancamiento (Leverage x):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(form_frame, textvariable=self.var_leverage, width=20).grid(row=row, column=1, sticky=tk.E, pady=5)

        row += 1
        # 5. Take Profit %
        ttk.Label(form_frame, text="Take Profit (%):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(form_frame, textvariable=self.var_tp, width=20).grid(row=row, column=1, sticky=tk.E, pady=5)

        row += 1
        # 6. Stop Loss %
        ttk.Label(form_frame, text="Stop Loss (%):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(form_frame, textvariable=self.var_sl, width=20).grid(row=row, column=1, sticky=tk.E, pady=5)

        row += 1
        # 7. Modo de Margen
        ttk.Label(form_frame, text="Modo de Margen:").grid(row=row, column=0, sticky=tk.W, pady=5)
        margin_combo = ttk.Combobox(
            form_frame,
            textvariable=self.var_margin,
            values=["ISOLATED", "CROSSED"],
            state="readonly",
            width=18
        )
        margin_combo.grid(row=row, column=1, sticky=tk.E, pady=5)

        row += 1
        # 8. Modo Testnet
        ttk.Label(form_frame, text="Modo Testnet (Pruebas):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Checkbutton(form_frame, text="Activo", variable=self.var_testnet).grid(row=row, column=1, sticky=tk.E, pady=5)

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Botones de Acción
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        btn_load = ttk.Button(btn_frame, text="🔄 Cargar Datos Actuales", style="Secondary.TButton", command=self.load_current_config)
        btn_load.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        btn_save = ttk.Button(btn_frame, text="✅ Aceptar y Guardar", style="Primary.TButton", command=self.save_config)
        btn_save.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # Barra de Estado
        status_lbl = ttk.Label(main_frame, textvariable=self.var_status, style="Status.TLabel", wraplength=440)
        status_lbl.pack(anchor=tk.W, pady=(10, 0))

    def load_current_config(self):
        """Intenta leer la configuración directamente del servidor API del bot. Si falla, lee de .env"""
        bot_url = self.var_bot_url.get().strip().rstrip("/")
        api_endpoint = f"{bot_url}/api/config"

        try:
            req = urllib.request.Request(api_endpoint, headers={"User-Agent": "BotConfigGUI/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.var_exchange.set(data.get("exchange", "bybit"))
                    self.var_max_pos.set(str(data.get("max_open_positions", 2)))
                    self.var_risk.set(str(data.get("risk_percent", 2.0)))
                    self.var_leverage.set(str(data.get("default_leverage", 5)))
                    self.var_tp.set(str(data.get("take_profit_percent", 3.0)))
                    self.var_sl.set(str(data.get("stop_loss_percent", 1.5)))
                    self.var_margin.set(data.get("margin_mode", "ISOLATED"))
                    self.var_testnet.set(bool(data.get("exchange_testnet", True)))
                    self.var_status.set("🟢 Datos cargados exitosamente desde el bot activo.")
                    return
        except Exception as e:
            # Fallback a lectura de archivo local .env
            self.var_exchange.set(settings.EXCHANGE)
            self.var_max_pos.set(str(settings.MAX_OPEN_POSITIONS))
            self.var_risk.set(str(settings.RISK_PERCENT))
            self.var_leverage.set(str(settings.DEFAULT_LEVERAGE))
            self.var_tp.set(str(settings.TAKE_PROFIT_PERCENT))
            self.var_sl.set(str(settings.STOP_LOSS_PERCENT))
            self.var_margin.set(settings.MARGIN_MODE)
            self.var_testnet.set(settings.is_testnet)
            self.var_status.set(f"🟡 Bot no detectado en HTTP ({e}). Datos cargados desde archivo .env local.")

    def save_config(self):
        """Valida y envía los nuevos parámetros al bot y actualiza .env"""
        try:
            max_pos = int(self.var_max_pos.get())
            risk = float(self.var_risk.get())
            leverage = int(self.var_leverage.get())
            tp = float(self.var_tp.get())
            sl = float(self.var_sl.get())
            exchange = self.var_exchange.get().strip().lower()
            margin = self.var_margin.get().strip().upper()
            testnet = bool(self.var_testnet.get())

            if max_pos < 1 or max_pos > 50:
                raise ValueError("El máximo de posiciones debe ser entre 1 y 50.")
            if risk <= 0 or risk > 100:
                raise ValueError("El % de cartera debe estar entre 0.1 y 100.")
            if leverage < 1 or leverage > 125:
                raise ValueError("El apalancamiento debe ser un entero entre 1 y 125.")
            if tp <= 0 or sl <= 0:
                raise ValueError("Take Profit y Stop Loss deben ser mayores a 0.")

        except ValueError as val_err:
            messagebox.showerror("Error de Validación", str(val_err))
            return

        payload_dict = {
            "exchange": exchange,
            "max_open_positions": max_pos,
            "risk_percent": risk,
            "default_leverage": leverage,
            "take_profit_percent": tp,
            "stop_loss_percent": sl,
            "margin_mode": margin,
            "exchange_testnet": testnet
        }

        bot_url = self.var_bot_url.get().strip().rstrip("/")
        api_endpoint = f"{bot_url}/api/config"

        updated_online = False
        try:
            req_data = json.dumps(payload_dict).encode("utf-8")
            req = urllib.request.Request(
                api_endpoint,
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "BotConfigGUI/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    if resp_json.get("success"):
                        updated_online = True
        except Exception as e:
            updated_online = False

        # Persistir también localmente en .env y memoria por seguridad
        update_settings_in_memory_and_env(payload_dict)

        if updated_online:
            msg = "✅ ¡Parámetros actualizados exitosamente en el Bot en vivo y guardados en .env!"
            self.var_status.set(msg)
            messagebox.showinfo("Éxito", msg)
        else:
            msg = "🟡 Parámetros guardados en el archivo .env local (El bot no estaba activo en HTTP)."
            self.var_status.set(msg)
            messagebox.showwarning("Guardado Local", msg)


if __name__ == "__main__":
    app = BotConfigApp()
    app.mainloop()
