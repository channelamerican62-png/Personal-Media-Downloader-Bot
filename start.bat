@echo off
title Shaxsiy Media Downloader Telegram Bot
echo ====================================================
echo Shaxsiy Media Yuklovchi Telegram Bot ishga tushirilmoqda...
echo ====================================================

REM Check if Python is available
py -3.11 --version >nul 2>&1
if %errorlevel% equ 0 (
    py -3.11 bot.py
) else (
    python bot.py
)

pause
