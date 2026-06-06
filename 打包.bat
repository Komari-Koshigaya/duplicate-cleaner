@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   Duplicate Cleaner Build Tool
echo ==========================================
echo.

echo [1/2] Check dependencies...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller -q
)

echo [2/2] Building...
echo.

python build.py

echo.
echo Build complete!
echo File: dist\DuplicateCleaner.exe
echo.
pause
