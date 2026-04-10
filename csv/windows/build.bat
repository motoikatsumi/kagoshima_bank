@echo off
echo ============================================
echo   Kagin Report - Build exe
echo ============================================
echo.

echo [1/3] Installing Python packages...
pip install -r requirements_win.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)
echo.

echo [2/3] Generating icon file...
python generate_icon.py
echo.

echo [3/3] Building exe with PyInstaller...

if exist kagin_icon.ico (
    pyinstaller --noconsole --onefile ^
        --name "KaginReport" ^
        --icon kagin_icon.ico ^
        --add-data "kagin_slack_report_win.py;." ^
        --hidden-import keyring.backends.Windows ^
        --hidden-import pystray._win32 ^
        kagin_app.py
) else (
    pyinstaller --noconsole --onefile ^
        --name "KaginReport" ^
        --add-data "kagin_slack_report_win.py;." ^
        --hidden-import keyring.backends.Windows ^
        --hidden-import pystray._win32 ^
        kagin_app.py
)

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Build Complete!
echo   Output: dist\KaginReport.exe
echo ============================================
echo.
echo Usage:
echo   1. Copy dist\KaginReport.exe to your preferred location
echo   2. Double-click to launch
echo   3. Password dialog appears on first launch
echo   4. Right-click tray icon for menu
echo.
pause
