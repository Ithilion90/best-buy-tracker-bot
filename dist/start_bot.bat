@echo off
title Amazon Price Tracker Bot
echo.
echo ========================================
echo   AMAZON PRICE TRACKER BOT
echo ========================================
echo.

REM Controlla se esiste il file .env
if not exist ".env" (
    echo ERRORE: File .env non trovato!
    echo.
    echo 1. Rinomina ".env.example" in ".env"
    echo 2. Compila il BOT_TOKEN nel file .env
    echo 3. Riavvia questo script
    echo.
    pause
    exit /b 1
)

echo Avvio del bot in corso...
echo.
echo Per fermare il bot, chiudi questa finestra
echo o premi Ctrl+C
echo.
echo ========================================
echo.

BestBuyTrackerBot.exe

echo.
echo ========================================
echo Bot terminato. Premi un tasto per uscire
echo ========================================
pause
