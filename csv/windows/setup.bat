@echo off
chcp 65001 >nul
echo ============================================
echo   鹿児島銀行レポート - セットアップ
echo ============================================
echo.

REM ============================================================
REM === [1] Python のインストール確認・自動インストール ===
REM ============================================================
echo [1/5] Python の確認...
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
    echo   Python %PYVER% が見つかりました。
) else (
    echo   Python が見つかりません。自動インストールを開始します...
    echo.

    REM winget が使えるか確認
    winget --version >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo   winget で Python 3.11 をインストール中...
        winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
        if %ERRORLEVEL% neq 0 (
            echo.
            echo   [エラー] winget でのインストールに失敗しました。
            echo   https://www.python.org/downloads/ から手動でインストールしてください。
            echo   ※「Add Python to PATH」に必ずチェックを入れてください。
            pause
            exit /b 1
        )
    ) else (
        echo   winget が利用できません。公式サイトからダウンロードします...
        echo.
        echo   ブラウザが開きます。以下の手順でインストールしてください：
        echo     1. 「Download Python 3.x.x」をクリック
        echo     2. インストーラーを実行
        echo     3. ⚠️「Add Python to PATH」に必ずチェックを入れる
        echo     4. 「Install Now」をクリック
        echo.
        start https://www.python.org/downloads/
        echo   インストールが完了したら何かキーを押してください...
        pause >nul
    )

    REM PATH を再読み込み（新しいcmdセッションで確認）
    echo.
    echo   Python のインストールを確認中...

    REM 環境変数を更新するため、新しいcmdで確認
    for /f "tokens=2" %%v in ('cmd /c "python --version" 2^>^&1') do set PYVER=%%v
    if defined PYVER (
        echo   Python %PYVER% のインストールを確認しました。
    ) else (
        echo.
        echo   [警告] Python がまだPATHに見つかりません。
        echo   コマンドプロンプトを一度閉じて、再度 setup.bat を実行してください。
        echo   （インストール後にPATHが反映されるには再起動が必要な場合があります）
        pause
        exit /b 1
    )
)
echo.

REM ============================================================
REM === [2] Google Chrome の確認 ===
REM ============================================================
echo [2/5] Google Chrome の確認...
set "CHROME_FOUND=0"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"

if "%CHROME_FOUND%"=="1" (
    echo   Google Chrome が見つかりました。
) else (
    echo   Google Chrome が見つかりません。
    echo.
    choice /c YN /m "  Google Chrome を自動インストールしますか？ (Y/N)"
    if %ERRORLEVEL% equ 1 (
        winget --version >nul 2>&1
        if %ERRORLEVEL% equ 0 (
            echo   winget で Google Chrome をインストール中...
            winget install Google.Chrome --accept-package-agreements --accept-source-agreements
        ) else (
            echo   ブラウザが開きます。Chrome をインストールしてください。
            start https://www.google.com/chrome/
            echo   インストールが完了したら何かキーを押してください...
            pause >nul
        )
    ) else (
        echo   [警告] Chrome なしでは動作しません。後で必ずインストールしてください。
    )
)
echo.

REM ============================================================
REM === [3] 依存パッケージのインストール ===
REM ============================================================
echo [3/5] Python パッケージをインストール中...
pip install -r requirements_win.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo   [エラー] パッケージのインストールに失敗しました。
    pause
    exit /b 1
)
echo   パッケージのインストール完了。
echo.

REM ============================================================
REM === [4] .env ファイルの確認 ===
REM ============================================================
echo [4/5] 設定ファイルの確認...
if exist ".env" (
    echo   .env ファイルが見つかりました。
) else (
    echo   .env ファイルが見つかりません。
    echo   Slackトークンの設定が必要です。
    echo.
    set /p "SLACK_TOKEN=  Slack Bot Token を入力してください: "
    if defined SLACK_TOKEN (
        echo # 鹿児島銀行レポートシステム設定ファイル> .env
        echo SLACK_BOT_TOKEN=%SLACK_TOKEN%>> .env
        echo   .env ファイルを作成しました。
    ) else (
        echo   [警告] .env ファイルを手動で作成してください。
    )
)
echo.

REM ============================================================
REM === [5] 自動起動の登録 ===
REM ============================================================
echo [5/5] 自動起動の設定...
echo Windows起動時の自動起動を設定しますか？
echo.
choice /c YN /m "自動起動を有効にする (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo.
    echo 自動起動を登録中...

    REM 現在のディレクトリにある KaginReport.exe のパスを取得
    set "EXE_PATH=%~dp0KaginReport.exe"

    if exist "%EXE_PATH%" (
        reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v KaginReport /t REG_SZ /d "\"%EXE_PATH%\"" /f
        echo 自動起動を登録しました: %EXE_PATH%
    ) else (
        echo.
        echo KaginReport.exe が見つかりません。
        echo 先に build.bat でビルドし、dist\KaginReport.exe をこのフォルダにコピーしてください。
    )
) else (
    echo 自動起動の設定をスキップしました。
    echo 後からトレイアイコンのメニューでも設定できます。
)

echo.

REM === パスワードの事前設定 ===
echo.
echo パスワードを事前に設定しますか？
echo （アプリ初回起動時にも設定できます）
echo.
choice /c YN /m "今すぐパスワードを設定する (Y/N)"
if %ERRORLEVEL% equ 1 (
    echo.
    python -c "import keyring; pw = input('銀行パスワードを入力: '); keyring.set_password('kagin_bank', 'kagin_assist', pw); print('パスワードを保存しました')"
    if %ERRORLEVEL% neq 0 (
        echo.
        echo パスワード設定に失敗しました。アプリ起動時に設定してください。
    )
) else (
    echo アプリ初回起動時にパスワード入力ダイアログが表示されます。
)

echo.
echo ============================================
echo   セットアップ完了
echo ============================================
echo.
echo KaginReport.exe をダブルクリックして起動してください。
echo タスクトレイにアイコンが表示されます。
echo.
pause
