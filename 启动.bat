@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -c "import ttkbootstrap" 2>nul
if errorlevel 1 (
    pip install -r requirements.txt -q
)

start "" pythonw duplicate_cleaner_gui.py
