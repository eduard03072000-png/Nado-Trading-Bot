@echo off
echo Stopping all Python processes...
taskkill /F /IM python.exe /T 2>nul
timeout /t 2 /nobreak >nul

echo Starting bot...
cd /d C:\Project\Trading_bot
start /min python telegram_trading_bot.py

echo Bot restarted!
timeout /t 2 /nobreak >nul
tasklist | findstr python
