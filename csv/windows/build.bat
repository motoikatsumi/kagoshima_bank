@echo off
chcp 65001 >nul
echo ============================================
echo   鹿児島銀行レポート - Windows版ビルド
echo ============================================
echo.

REM 前提: Python 3.9以上がインストール済み
REM 前提: Google Chromeがインストール済み

echo [1/3] 依存パッケージをインストール中...
pip install -r requirements_win.txt
if %ERRORLEVEL% neq 0 (
    echo エラー: パッケージのインストールに失敗しました
    pause
    exit /b 1
)
echo.

echo [2/3] アイコンファイルを生成中...
python generate_icon.py
echo.

echo [3/3] exe ファイルをビルド中...
REM --noconsole: コンソール窓を表示しない
REM --onefile: 1つのexeにまとめる
REM --add-data: レポートスクリプトをバンドル
REM --name: 出力exe名

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
    echo エラー: ビルドに失敗しました
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ビルド完了!
echo   出力: dist\KaginReport.exe
echo ============================================
echo.
echo 使い方:
echo   1. dist\KaginReport.exe を好きな場所にコピー
echo   2. ダブルクリックで起動
echo   3. 初回起動時にパスワード入力ダイアログが表示されます
echo   4. タスクトレイのアイコンを右クリックでメニュー表示
echo.
pause
