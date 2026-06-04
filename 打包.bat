@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   Duplicate Cleaner 打包工具
echo ==========================================
echo.

echo [1/2] 检查依赖...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo 安装 PyInstaller...
    pip install pyinstaller -q
)

echo [2/2] 开始打包...
echo.

python build.py

echo.
echo 打包完成！
echo 文件位置: dist\DuplicateCleaner.exe
echo.
pause
