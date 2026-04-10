#!/usr/bin/env python3
"""
鹿児島銀行レポート - Windowsトレイアプリケーション

機能:
  - タスクトレイにアイコン表示
  - 右クリックメニューから手動実行
  - スケジュール実行（8:50, 11:50, 14:50, 18:20）
  - Windows起動時に自動起動
  - パスワード設定（Windows資格情報マネージャー）
"""

import os
import sys
import time
import threading
import logging
import ctypes
from datetime import datetime

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import keyring

# ============================================================
# パス設定
# ============================================================
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    APP_EXE = sys.executable
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_EXE = os.path.abspath(__file__)

LOG_FILE = os.path.join(APP_DIR, "kagin_app.log")

# ============================================================
# ログ設定
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("kagin_app")

# ============================================================
# 定数
# ============================================================
APP_NAME = "鹿児島銀行レポート"
KEYRING_SERVICE = "kagin_bank"
KEYRING_USERNAME = "kagin_assist"
REGISTRY_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "KaginReport"

# スケジュール実行時刻 (HH:MM)
SCHEDULE_TIMES = ["08:50", "11:50", "14:50", "18:20"]

# スリープ防止用定数
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


# ============================================================
# アイコン生成
# ============================================================

def create_tray_icon_image(color="#2c3e50"):
    """銀行風トレイアイコンを生成"""
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 屋根（三角形）
    draw.polygon([(32, 4), (4, 24), (60, 24)], fill=color)
    # 建物本体
    draw.rectangle([8, 24, 56, 56], fill=color)
    # 柱
    for x in [16, 26, 36, 46]:
        draw.rectangle([x - 1, 28, x + 3, 52], fill='white')
    # 土台
    draw.rectangle([4, 56, 60, 62], fill=color)

    return img


def create_running_icon():
    """実行中アイコン（黄色系）"""
    return create_tray_icon_image(color="#d4ac0d")


def create_normal_icon():
    """通常アイコン（濃青）"""
    return create_tray_icon_image(color="#2c3e50")


def create_error_icon():
    """エラーアイコン（赤）"""
    return create_tray_icon_image(color="#c0392b")


# ============================================================
# Windows スリープ防止
# ============================================================

def prevent_sleep():
    """処理中のスリープを防止"""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
        logger.info("スリープ防止: ON")
    except Exception as e:
        logger.warning(f"スリープ防止設定失敗: {e}")


def allow_sleep():
    """スリープ防止を解除"""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        logger.info("スリープ防止: OFF")
    except Exception as e:
        logger.warning(f"スリープ防止解除失敗: {e}")


# ============================================================
# 自動起動（レジストリ）
# ============================================================

def is_autostart_enabled():
    """自動起動が有効か確認"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


def enable_autostart():
    """Windows起動時の自動起動を有効化"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_SET_VALUE
        )
        if getattr(sys, 'frozen', False):
            exe_path = f'"{APP_EXE}"'
        else:
            exe_path = f'"{sys.executable}" "{APP_EXE}"'
        winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        logger.info(f"自動起動を有効化: {exe_path}")
        return True
    except Exception as e:
        logger.error(f"自動起動有効化エラー: {e}")
        return False


def disable_autostart():
    """自動起動を無効化"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
        winreg.CloseKey(key)
        logger.info("自動起動を無効化")
        return True
    except Exception as e:
        logger.error(f"自動起動無効化エラー: {e}")
        return False


def toggle_autostart(icon, menu_item):
    """自動起動のON/OFF切替"""
    if is_autostart_enabled():
        disable_autostart()
        icon.notify("自動起動を無効にしました", APP_NAME)
    else:
        enable_autostart()
        icon.notify("自動起動を有効にしました", APP_NAME)


# ============================================================
# スリープ解除タスク（タスクスケジューラ）
# ============================================================

TASK_NAME_PREFIX = "KaginReport_Wake"


def _build_task_xml(time_str, exe_path):
    """タスクスケジューラ用XMLを生成（スリープ解除 + アプリ起動）"""
    h, m = time_str.split(":")
    # アプリが既に起動中なら内蔵スケジューラが処理するため、
    # タスクは「アプリが起動していない場合の保険」として機能
    if getattr(sys, 'frozen', False):
        command = exe_path
        arguments = ""
    else:
        command = sys.executable
        arguments = f'"{exe_path}"'

    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Kagin Report - Wake and run at {time_str}</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{h}:{m}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{APP_DIR}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>'''
    return xml


def is_wake_schedule_enabled():
    """スリープ解除タスクが登録されているか確認"""
    import subprocess
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", f"{TASK_NAME_PREFIX}_0850"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def enable_wake_schedule():
    """全スケジュール時刻のスリープ解除タスクを登録"""
    import subprocess
    import tempfile

    exe_path = APP_EXE
    success = True

    for stime in SCHEDULE_TIMES:
        task_name = f"{TASK_NAME_PREFIX}_{stime.replace(':', '')}"
        xml_content = _build_task_xml(stime, exe_path)

        # XMLを一時ファイルに書き出し
        tmp_path = os.path.join(tempfile.gettempdir(), f"{task_name}.xml")
        try:
            with open(tmp_path, "w", encoding="utf-16") as f:
                f.write(xml_content)

            result = subprocess.run(
                ["schtasks", "/Create", "/TN", task_name, "/XML", tmp_path, "/F"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                logger.info(f"Wake task registered: {task_name} ({stime})")
            else:
                logger.error(f"Wake task failed: {task_name}: {result.stderr}")
                success = False
        except Exception as e:
            logger.error(f"Wake task error: {task_name}: {e}")
            success = False
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    return success


def disable_wake_schedule():
    """全スケジュール時刻のスリープ解除タスクを削除"""
    import subprocess

    success = True
    for stime in SCHEDULE_TIMES:
        task_name = f"{TASK_NAME_PREFIX}_{stime.replace(':', '')}"
        try:
            result = subprocess.run(
                ["schtasks", "/Delete", "/TN", task_name, "/F"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                logger.info(f"Wake task removed: {task_name}")
            else:
                logger.warning(f"Wake task delete failed: {task_name}: {result.stderr.strip()}")
        except Exception as e:
            logger.error(f"Wake task delete error: {task_name}: {e}")
            success = False

    return success


def toggle_wake_schedule(icon, menu_item):
    """スリープ解除スケジュールのON/OFF切替"""
    if is_wake_schedule_enabled():
        disable_wake_schedule()
        icon.notify("Sleep wake schedule disabled", APP_NAME)
    else:
        if enable_wake_schedule():
            icon.notify("Sleep wake schedule enabled", APP_NAME)
        else:
            icon.notify("Failed to set wake schedule (need admin?)", APP_NAME)


# ============================================================
# パスワード管理
# ============================================================

def has_password():
    """パスワードが保存されているか確認"""
    try:
        pw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        return pw is not None and len(pw) > 0
    except Exception:
        return False


def show_password_dialog():
    """パスワード入力ダイアログを表示（tkinter）"""
    import tkinter as tk
    from tkinter import simpledialog, messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    password = simpledialog.askstring(
        "パスワード設定",
        "鹿児島銀行のログインパスワードを入力してください:",
        show='*',
        parent=root
    )

    if password:
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, password)
            messagebox.showinfo("完了", "パスワードを保存しました。", parent=root)
            logger.info("パスワードを設定しました")
        except Exception as e:
            messagebox.showerror("エラー", f"パスワード保存に失敗しました:\n{e}", parent=root)
            logger.error(f"パスワード保存エラー: {e}")
    root.destroy()


# ============================================================
# レポート実行
# ============================================================

class ReportRunner:
    """レポート処理の実行管理"""

    def __init__(self):
        self._running = False
        self._lock = threading.Lock()
        self.icon = None

    @property
    def is_running(self):
        return self._running

    def run_report(self, manual=False):
        """レポート処理を実行（スレッドセーフ）"""
        with self._lock:
            if self._running:
                logger.warning("既に処理が実行中です")
                if self.icon:
                    self.icon.notify("処理が既に実行中です", APP_NAME)
                return
            self._running = True

        trigger = "手動" if manual else "スケジュール"
        logger.info(f"===== レポート処理開始 ({trigger}) =====")

        # アイコンを実行中に変更
        if self.icon:
            self.icon.icon = create_running_icon()
            self.icon.notify(f"処理を開始しました ({trigger})", APP_NAME)

        prevent_sleep()

        try:
            # レポートスクリプトをインポート・実行
            from kagin_slack_report_win import main as run_report_main
            result = run_report_main()

            if result and result.get("error"):
                logger.error(f"レポート処理エラー: {result['error']}")
                if self.icon:
                    self.icon.icon = create_error_icon()
                    self.icon.notify(
                        f"エラー: {result['error']}", APP_NAME
                    )
            else:
                success = result.get("success", 0) if result else 0
                total = result.get("total", 0) if result else 0
                logger.info(f"レポート処理完了: {success}/{total} 店舗成功")
                if self.icon:
                    self.icon.icon = create_normal_icon()
                    self.icon.notify(
                        f"処理完了: {success}/{total} 店舗", APP_NAME
                    )

        except Exception as e:
            logger.error(f"レポート処理で例外発生: {e}")
            if self.icon:
                self.icon.icon = create_error_icon()
                self.icon.notify(f"処理エラー: {e}", APP_NAME)

        finally:
            allow_sleep()
            with self._lock:
                self._running = False
            logger.info("===== レポート処理終了 =====")


# ============================================================
# スケジューラ
# ============================================================

class Scheduler:
    """スケジュール実行を管理（スリープ復帰にも対応）"""

    def __init__(self, runner: ReportRunner):
        self.runner = runner
        self.schedule_times = SCHEDULE_TIMES
        self._executed_today = {}  # {date_str: set(time_str)}
        self._stop_event = threading.Event()

    def get_next_run_time(self):
        """次回実行時刻を返す"""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        executed = self._executed_today.get(today_str, set())

        for stime in self.schedule_times:
            if stime in executed:
                continue
            h, m = map(int, stime.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if now < target:
                return stime
        return "明日 " + self.schedule_times[0]

    def _check_and_run(self):
        """スケジュール時刻をチェックし、該当すれば実行"""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # 日付が変わったら実行済みセットをリセット
        if today_str not in self._executed_today:
            self._executed_today.clear()
            self._executed_today[today_str] = set()

        executed = self._executed_today[today_str]

        for stime in self.schedule_times:
            if stime in executed:
                continue

            h, m = map(int, stime.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff_seconds = (now - target).total_seconds()

            # 予定時刻を過ぎてから10分以内なら実行（スリープ復帰対応）
            if 0 <= diff_seconds <= 600:
                executed.add(stime)
                logger.info(f"スケジュール実行: {stime}")
                thread = threading.Thread(
                    target=self.runner.run_report,
                    kwargs={"manual": False},
                    daemon=True,
                )
                thread.start()
                return  # 一度に1つだけ実行

    def run_loop(self):
        """スケジューラのメインループ（別スレッドで実行）"""
        logger.info(f"スケジューラ開始: 実行時刻 = {self.schedule_times}")
        while not self._stop_event.is_set():
            try:
                self._check_and_run()
            except Exception as e:
                logger.error(f"スケジューラエラー: {e}")
            self._stop_event.wait(30)  # 30秒ごとにチェック
        logger.info("スケジューラ終了")

    def stop(self):
        """スケジューラを停止"""
        self._stop_event.set()


# ============================================================
# トレイメニュー
# ============================================================

def build_tray_app():
    """トレイアプリケーションを構築して起動"""

    runner = ReportRunner()
    scheduler = Scheduler(runner)

    def on_manual_run(icon, menu_item):
        """手動実行"""
        if not has_password():
            icon.notify("パスワードが未設定です。先にパスワードを設定してください。", APP_NAME)
            return
        thread = threading.Thread(
            target=runner.run_report,
            kwargs={"manual": True},
            daemon=True,
        )
        thread.start()

    def on_set_password(icon, menu_item):
        """パスワード設定"""
        thread = threading.Thread(target=show_password_dialog, daemon=True)
        thread.start()

    def on_open_log(icon, menu_item):
        """ログファイルを開く"""
        log_path = os.path.join(APP_DIR, "kagin_report.log")
        if os.path.exists(log_path):
            os.startfile(log_path)
        else:
            app_log = LOG_FILE
            if os.path.exists(app_log):
                os.startfile(app_log)

    def on_quit(icon, menu_item):
        """アプリ終了"""
        logger.info("アプリケーション終了")
        scheduler.stop()
        icon.stop()

    def get_status_text(menu_item):
        """ステータステキスト"""
        if runner.is_running:
            return "⏳ 処理実行中..."
        next_time = scheduler.get_next_run_time()
        return f"次回: {next_time}"

    def get_autostart_text(menu_item):
        """自動起動ステータステキスト"""
        if is_autostart_enabled():
            return "✅ Windows起動時に自動起動"
        return "  Windows起動時に自動起動"

    def get_wake_text(menu_item):
        """スリープ解除スケジュールのステータステキスト"""
        if is_wake_schedule_enabled():
            return "✅ スリープ解除で自動実行"
        return "  スリープ解除で自動実行"

    # メニュー構成
    menu = pystray.Menu(
        item(get_status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("▶ 今すぐ実行", on_manual_run),
        pystray.Menu.SEPARATOR,
        item("🔑 パスワード設定", on_set_password),
        item(get_autostart_text, toggle_autostart),
        item(get_wake_text, toggle_wake_schedule),
        item("📄 ログを開く", on_open_log),
        pystray.Menu.SEPARATOR,
        item("終了", on_quit),
    )

    icon = pystray.Icon(
        name="kagin_report",
        icon=create_normal_icon(),
        title=APP_NAME,
        menu=menu,
    )

    runner.icon = icon

    def on_setup(icon):
        """トレイアイコン表示後の初期化"""
        icon.visible = True

        # 初回起動時のパスワード確認
        if not has_password():
            logger.info("パスワード未設定 → 設定ダイアログを表示")
            icon.notify("初回起動: パスワードを設定してください", APP_NAME)
            show_password_dialog()

        # スケジューラスレッド起動
        scheduler_thread = threading.Thread(
            target=scheduler.run_loop, daemon=True
        )
        scheduler_thread.start()

        logger.info("トレイアプリケーション起動完了")
        next_time = scheduler.get_next_run_time()
        icon.notify(f"起動しました。次回実行: {next_time}", APP_NAME)

    # トレイアイコン起動（ブロッキング）
    icon.run(setup=on_setup)


# ============================================================
# エントリポイント
# ============================================================

def main():
    logger.info("=" * 60)
    logger.info(f"{APP_NAME} 起動")
    logger.info(f"アプリディレクトリ: {APP_DIR}")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    logger.info("=" * 60)

    build_tray_app()


if __name__ == "__main__":
    main()
