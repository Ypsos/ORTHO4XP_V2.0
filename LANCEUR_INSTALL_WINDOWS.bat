@echo off
:: ============================================================
::  ORTHO4XP V2 — Lanceur universel Windows
::  Double-cliquez sur ce fichier pour démarrer
:: ============================================================
cd /d "%~dp0"
where python >nul 2>&1
if %errorlevel%==0 (
    python INSTALL_PREREQUIS.py
) else (
    echo Python introuvable. Veuillez installer Python 3.12 depuis python.org
    pause
)
