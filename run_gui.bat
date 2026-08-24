@echo off
title Oracle Trading Bot - Configuración
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\pythonw.exe" bot_config_gui.py
) else (
    start "" pythonw bot_config_gui.py
)
exit
