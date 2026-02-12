@echo off
echo ================================================================
echo            NADO TRADING BOT - REFACTORED VERSION
echo ================================================================
echo.

REM Проверка .env
if not exist .env (
    echo [ERROR] .env file not found!
    echo.
    echo Please create .env file with:
    echo   NADO_PRIVATE_KEY=...
    echo   TELEGRAM_BOT_TOKEN=...
    echo   NADO_NETWORK=mainnet
    echo.
    pause
    exit /b 1
)

echo [INFO] Starting bot...
echo.

REM Активировать виртуальное окружение если есть
if exist .venv\Scripts\activate.bat (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
)

REM Запустить бота
python main.py

pause
