@echo off
chcp 65001 >nul
cd /d C:\Project\Trading_bot
echo.
echo ========================================
echo  NADO TRADING BOT - TELEGRAM
echo ========================================
echo.
echo Starting bot...
.venv\Scripts\python.exe final_bot.py
