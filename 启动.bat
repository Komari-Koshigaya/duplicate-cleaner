@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 检查依赖
python -c "import ttkbootstrap" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt -q
)

:: 使用 pythonw 启动，不显示黑框
start "" pythonw -m duplicate_cleaner
