@echo off
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul
cd /d C:\Project\Trading_bot
start "" python telegram_trading_bot.py
echo Bot restarted!
