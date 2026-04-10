@echo off
setlocal enabledelayedexpansion
echo ============================================
echo   Kagin Report - Setup
echo ============================================
echo.

REM ============================================================
REM === [1] Check / Install Python ===
REM ============================================================
echo [1/5] Checking Python...
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
    echo   Python %PYVER% found.
) else (
    echo   Python not found. Starting auto-install...
    echo.

    winget --version >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo   Installing Python 3.11 via winget...
        winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
        if %ERRORLEVEL% neq 0 (
            echo.
            echo   [ERROR] winget install failed.
            echo   Please install manually from https://www.python.org/downloads/
            echo   IMPORTANT: Check "Add Python to PATH" during install.
            pause
            exit /b 1
        )
    ) else (
        echo   winget not available. Opening Python download page...
        echo.
        echo   Install steps:
        echo     1. Click "Download Python 3.x.x"
        echo     2. Run the installer
        echo     3. CHECK "Add Python to PATH"
        echo     4. Click "Install Now"
        echo.
        start https://www.python.org/downloads/
        echo   Press any key after installation is complete...
        pause >nul
    )

    echo.
    echo   Verifying Python installation...

    for /f "tokens=2" %%v in ('cmd /c "python --version" 2^>^&1') do set PYVER=%%v
    if defined PYVER (
        echo   Python %PYVER% confirmed.
    ) else (
        echo.
        echo   [WARNING] Python not found in PATH.
        echo   Please close this window and run setup.bat again.
        echo   (PATH changes may require a restart)
        pause
        exit /b 1
    )
)
echo.

REM ============================================================
REM === [2] Check / Install Google Chrome ===
REM ============================================================
echo [2/5] Checking Google Chrome...
set "CHROME_FOUND=0"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"

if "%CHROME_FOUND%"=="1" (
    echo   Google Chrome found.
) else (
    echo   Google Chrome not found.
    echo.
    choice /c YN /m "  Install Google Chrome automatically? (Y/N)"
    if !ERRORLEVEL! equ 1 (
        winget --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            echo   Installing Google Chrome via winget...
            winget install Google.Chrome --accept-package-agreements --accept-source-agreements
        ) else (
            echo   Opening Chrome download page...
            start https://www.google.com/chrome/
            echo   Press any key after installation is complete...
            pause >nul
        )
    ) else (
        echo   [WARNING] Chrome is required. Please install it later.
    )
)
echo.

REM ============================================================
REM === [3] Install Python packages ===
REM ============================================================
echo [3/5] Installing Python packages...
pip install -r requirements_win.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo   [ERROR] Package installation failed.
    pause
    exit /b 1
)
echo   Packages installed successfully.
echo.

REM ============================================================
REM === [4] Check .env file (Slack token) ===
REM ============================================================
echo [4/5] Checking .env config file...
if exist ".env" (
    echo   .env file found.
) else (
    echo   .env file not found. Slack token setup required.
    echo.
    set /p "SLACK_TOKEN=  Enter Slack Bot Token: "
    if defined SLACK_TOKEN (
        echo SLACK_BOT_TOKEN=%SLACK_TOKEN%> .env
        echo   .env file created.
    ) else (
        echo   [WARNING] Please create .env file manually.
    )
)
echo.

REM ============================================================
REM === [5] Auto-start on Windows boot ===
REM ============================================================
echo [5/6] Auto-start configuration...
choice /c YN /m "Enable auto-start on Windows boot? (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo.
    set "EXE_PATH=%~dp0KaginReport.exe"

    if exist "%EXE_PATH%" (
        reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v KaginReport /t REG_SZ /d "\"%EXE_PATH%\"" /f
        echo   Auto-start registered: %EXE_PATH%
    ) else (
        echo.
        echo   KaginReport.exe not found.
        echo   Run build.bat first, then copy dist\KaginReport.exe here.
    )
) else (
    echo   Skipped. You can enable this later from the tray icon menu.
)

echo.

REM ============================================================
REM === [6] Wake-from-sleep schedule ===
REM ============================================================
echo [6/6] Wake-from-sleep configuration...
echo   This creates Task Scheduler tasks that wake your PC
echo   from sleep at scheduled times (08:50, 11:50, 14:50, 18:20).
echo.
choice /c YN /m "Enable wake-from-sleep schedule? (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo.
    python -c "import sys; sys.path.insert(0,'.'); from kagin_app import enable_wake_schedule; r=enable_wake_schedule(); print('Wake schedule registered.' if r else 'Some tasks failed.')"
    if %ERRORLEVEL% neq 0 (
        echo   Failed. You can enable this later from the tray icon menu.
    )
) else (
    echo   Skipped. You can enable this later from the tray icon menu.
)

echo.

REM === Bank password setup ===
echo.
choice /c YN /m "Set bank password now? (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo.
    python -c "import keyring; pw = input('Enter bank password: '); keyring.set_password('kagin_bank', 'kagin_assist', pw); print('Password saved.')"
    if %ERRORLEVEL% neq 0 (
        echo.
        echo   Password setup failed. You can set it when the app starts.
    )
) else (
    echo   Password dialog will appear on first app launch.
)

echo.
echo ============================================
echo   Setup Complete!
echo ============================================
echo.
echo Double-click KaginReport.exe to start.
echo The app icon will appear in the system tray.
echo.
pause
