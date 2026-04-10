@echo off
chcp 65001 >nul
echo ============================================
echo   鹿児島銀行レポート - セットアップ
echo ============================================
echo.

REM === 自動起動の登録 ===
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
