#!/usr/bin/env python3
"""
鹿児島銀行 FB-Web 取引履歴取得 → Slack報告スクリプト (Windows版)
Selenium + Slack API (Bot Token) を使用
"""

import os
import sys
import re
import time
import csv
import json
import logging
from datetime import datetime, timedelta
from io import StringIO

import requests
import keyring
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException
)

# ============================================================
# パス設定（exe化対応）
# ============================================================
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 設定
# ============================================================
def _load_env():
    """同ディレクトリの .env ファイルから設定を読み込む"""
    env_path = os.path.join(APP_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

_load_env()
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

# 店舗設定: (店舗名, ドロップダウンindex, SlackチャンネルID, CSV保存名)
BRANCHES = [
    ("本店",     0, "C6E56LEUQ",   "honten.csv"),
    ("宇宿支店", 1, "CASG7M5S4",   "usuki.csv"),
    ("伊敷支店", 2, "CG5FK92M8",   "ishiki.csv"),
    ("国分支店", 3, "C06SJ08FQ83", "kokubu.csv"),
    ("寿支店",   4, "C01B7R06UJF", "kotobuki.csv"),
]

BANK_URL = "https://ib.kagin.co.jp/cmn/IBGate/i201102CT"

# エラー通知先（assist-kouzi）
ERROR_NOTIFY_USER = "U07RHH282"
CSV_DIR = APP_DIR
LOG_FILE = os.path.join(CSV_DIR, "kagin_report.log")

# ============================================================
# ログ設定（外部から制御可能）
# ============================================================
logger = logging.getLogger("kagin_report")


def setup_logging():
    """ロギングを初期化（まだ設定されていなければ）"""
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(formatter)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(sh)


# ============================================================
# Slack API ヘルパー
# ============================================================

def slack_get_history(channel_id, limit=10):
    """チャンネルの最新メッセージを取得"""
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    params = {"channel": channel_id, "limit": limit}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        if data.get("ok"):
            return data.get("messages", [])
        else:
            logger.warning(f"Slack history error: {data.get('error')}")
            return []
    except Exception as e:
        logger.error(f"Slack history request failed: {e}")
        return []


def slack_post_message(channel_id, text):
    """チャンネルにメッセージを送信"""
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"channel": channel_id, "text": text}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        data = resp.json()
        logger.info(f"Slack API応答 [{channel_id}]: status={resp.status_code}, ok={data.get('ok')}, ts={data.get('ts')}, channel={data.get('channel')}, error={data.get('error')}")
        if data.get("ok"):
            logger.info(f"Slack送信成功: {channel_id} (ts={data.get('ts')})")
            return True
        else:
            logger.error(f"Slack送信エラー: {data}")
            return False
    except Exception as e:
        logger.error(f"Slack送信失敗: {e}")
        return False


def slack_join_channel(channel_id):
    """ボットをチャンネルに参加させる"""
    url = "https://slack.com/api/conversations.join"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"channel": channel_id}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        data = resp.json()
        if data.get("ok"):
            logger.info(f"チャンネル {channel_id} に参加しました")
            return True
        else:
            logger.warning(f"チャンネル参加エラー: {data.get('error')}")
            return False
    except Exception as e:
        logger.error(f"チャンネル参加失敗: {e}")
        return False


def normalize_key(date_str, name_str):
    """日付と摘要を正規化してキーを作成"""
    date_clean = date_str.strip().replace("\u3000", "").replace(" ", "")
    name_clean = name_str.strip().replace("\u3000", " ").replace("\u00a0", " ").strip()
    name_clean = re.sub(r'\s+', ' ', name_clean)
    return f"{date_clean}|{name_clean}"


def extract_reported_keys(channel_id, limit=50):
    """
    Slackチャンネルの最新メッセージから、報告済みの取引キーを抽出する。
    キー = "日付|摘要" （複数の形式に対応）
    """
    messages = slack_get_history(channel_id, limit)
    reported = set()
    for msg in messages:
        text = msg.get("text", "")
        for line in text.split("\n"):
            line = line.strip().strip("`")
            if not line:
                continue

            date_match = re.match(r'^(\d{4}/\d{2}/\d{2})', line)
            if not date_match:
                continue

            date_str = date_match.group(1)
            rest = line[len(date_str):]

            # パイプ区切り（新スクリプト形式）
            if "|" in rest:
                parts = rest.split("|")
                if len(parts) >= 2:
                    name = parts[1].strip()
                    if name:
                        key = normalize_key(date_str, name)
                        reported.add(key)
                continue

            # タブ区切り
            if "\t" in rest:
                parts = rest.split("\t")
                name_found = False
                for p in parts:
                    name = p.strip()
                    if name and not re.match(r'^[\d,]+円$', name):
                        key = normalize_key(date_str, name)
                        reported.add(key)
                        name_found = True
                        break
                if not name_found:
                    amounts = [p.strip() for p in parts if re.match(r'^[\d,]+円$', p.strip())]
                    if len(amounts) >= 2:
                        amt_val = amounts[0].replace(",", "").replace("円", "")
                        bal_val = amounts[1].replace(",", "").replace("円", "")
                        key = normalize_key(date_str, f"_amt{amt_val}_bal{bal_val}")
                        reported.add(key)
                    elif len(amounts) == 1:
                        amt_val = amounts[0].replace(",", "").replace("円", "")
                        key = normalize_key(date_str, f"_amt{amt_val}")
                        reported.add(key)
                continue

            # スペース区切り
            parts = rest.strip().split(None, 1)
            if parts:
                name = parts[0].strip()
                if name and not re.match(r'^[\d,]+円$', name):
                    key = normalize_key(date_str, name)
                    reported.add(key)
                elif name and re.match(r'^[\d,]+円$', name):
                    amounts = re.findall(r'[\d,]+円', rest)
                    if len(amounts) >= 2:
                        amt_val = amounts[0].replace(",", "").replace("円", "")
                        bal_val = amounts[1].replace(",", "").replace("円", "")
                        key = normalize_key(date_str, f"_amt{amt_val}_bal{bal_val}")
                        reported.add(key)

    logger.info(f"Slack履歴 {len(messages)} 件のメッセージを取得, 抽出された報告済みキー数: {len(reported)}")
    if reported:
        sample = list(reported)[:10]
        for s in sample:
            logger.info(f"  報告済みキー例: {s}")
    return reported


# ============================================================
# Windows資格情報マネージャーからパスワード取得
# ============================================================

KEYRING_SERVICE = "kagin_bank"
KEYRING_USERNAME = "kagin_assist"


def get_password():
    """Windows資格情報マネージャーからパスワードを取得"""
    try:
        password = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if password:
            logger.info("Windows資格情報からパスワードを取得しました")
            return password
        logger.warning("パスワードが保存されていません")
        return None
    except Exception as e:
        logger.error(f"パスワード取得エラー: {e}")
        return None


def set_password(password):
    """Windows資格情報マネージャーにパスワードを保存"""
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, password)
        logger.info("パスワードをWindows資格情報に保存しました")
        return True
    except Exception as e:
        logger.error(f"パスワード保存エラー: {e}")
        return False


# ============================================================
# 銀行データ取得 (Selenium)
# ============================================================

CHROME_PROFILE_DIR = os.path.join(CSV_DIR, "chrome_profile")


def create_driver():
    """Chromeドライバーを作成（ヘッドレスモード、専用プロファイル使用）"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--no-first-run")

    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
    options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(3)
    return driver


def login_to_bank(driver):
    """銀行サイトにログイン"""
    logger.info("銀行サイトにアクセス中...")
    driver.get(BANK_URL)
    time.sleep(5)

    try:
        corp_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "CORP_ID"))
        )
        logger.info("ログインページを検出")

        if not corp_input.get_attribute("value"):
            corp_input.clear()
            corp_input.send_keys("9209368184")
            logger.info("契約法人IDを入力")

        time.sleep(1)
        usr_input = driver.find_element(By.NAME, "USR_NAME")
        if not usr_input.get_attribute("value"):
            usr_input.clear()
            usr_input.send_keys("assist")
            logger.info("利用者IDを入力")

        time.sleep(1)

        # Windows資格情報からパスワードを取得
        password = get_password()
        if password:
            pw_input = driver.find_element(By.NAME, "MASK_LOGIN_PWD")
            pw_input.click()
            time.sleep(0.5)

            actions = ActionChains(driver)
            actions.click(pw_input)
            for char in password:
                actions.send_keys(char)
                actions.pause(0.1)
            actions.perform()
            logger.info(f"パスワード入力完了（{len(password)}文字）")

            time.sleep(2)

            login_clicked = False
            selectors = [
                (By.CSS_SELECTOR, "input[value='ログイン']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.CSS_SELECTOR, "input[type='image']"),
                (By.XPATH, "//input[contains(@value, 'ログイン')]"),
                (By.XPATH, "//button[contains(text(), 'ログイン')]"),
                (By.XPATH, "//a[contains(text(), 'ログイン')]"),
            ]
            for by, selector in selectors:
                try:
                    btn = driver.find_element(by, selector)
                    logger.info(f"ログインボタン発見: {by}={selector}, tag={btn.tag_name}")
                    btn.click()
                    login_clicked = True
                    break
                except NoSuchElementException:
                    continue

            if not login_clicked:
                logger.info("ボタンが見つからないため、JSでフォーム送信を試行")
                try:
                    driver.execute_script("document.forms[0].submit();")
                    login_clicked = True
                except Exception as e:
                    logger.error(f"フォーム送信失敗: {e}")

            logger.info(f"ログインボタンクリック: {login_clicked}")
            time.sleep(8)

            current_url = driver.current_url
            logger.info(f"ログイン後URL: {current_url}")
            logger.info(f"ログイン後タイトル: {driver.title}")

            try:
                page_source = driver.page_source
                if "パスワード" in page_source and ("誤り" in page_source or "エラー" in page_source or "正しく" in page_source):
                    logger.warning("パスワードエラーが検出されました")
                    for keyword in ["誤り", "エラー", "正しく", "失敗", "ロック"]:
                        if keyword in page_source:
                            idx = page_source.index(keyword)
                            snippet = page_source[max(0, idx-30):idx+50]
                            snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                            logger.warning(f"エラー文言: {snippet}")
            except Exception:
                pass

            driver.implicitly_wait(2)
            try:
                driver.find_element(By.NAME, "CORP_ID")
                logger.warning("ログインページのまま。ログインに失敗した可能性があります。")
                driver.save_screenshot(os.path.join(CSV_DIR, "login_failed.png"))
                return False
            except (NoSuchElementException, StaleElementReferenceException):
                logger.info("ログイン完了")
                return True
            finally:
                driver.implicitly_wait(3)
        else:
            logger.error("パスワードが設定されていません。トレイメニューから設定してください。")
            return False

    except TimeoutException:
        logger.info("すでにログイン済み、またはログインページではありません")
        return True


def debug_page_info(driver):
    """デバッグ用: 現在のページ情報をログ出力"""
    logger.info(f"  現在のURL: {driver.current_url}")
    logger.info(f"  ページタイトル: {driver.title}")

    driver.implicitly_wait(1)
    frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
    driver.implicitly_wait(3)
    if frames:
        logger.info(f"  フレーム数: {len(frames)}")
        for i, f in enumerate(frames):
            name = f.get_attribute("name") or f.get_attribute("id") or "unnamed"
            src = f.get_attribute("src") or "no-src"
            logger.info(f"    フレーム[{i}]: name={name}, src={src}")

    links = driver.find_elements(By.TAG_NAME, "a")
    link_texts = [l.text.strip() for l in links if l.text.strip()][:20]
    logger.info(f"  リンク一覧: {link_texts}")

    screenshot_path = os.path.join(CSV_DIR, "debug_screenshot.png")
    driver.save_screenshot(screenshot_path)
    logger.info(f"  スクリーンショット保存: {screenshot_path}")


def navigate_to_transaction_history(driver):
    """入出金明細照会ページへ移動"""
    logger.info("現在のページ情報を取得中...")
    debug_page_info(driver)

    try:
        driver.implicitly_wait(2)
        frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
        driver.implicitly_wait(3)

        if frames:
            for i, frame in enumerate(frames):
                try:
                    driver.switch_to.frame(frame)
                    logger.info(f"フレーム[{i}]に切り替え")

                    links = driver.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        text = link.text.strip()
                        if "入出金明細" in text or "明細照会" in text:
                            try:
                                driver.execute_script("arguments[0].click();", link)
                            except Exception:
                                link.click()
                            time.sleep(3)
                            driver.switch_to.default_content()
                            logger.info("入出金明細照会ページへ移動（フレーム内JSクリック）")
                            return True

                    link_texts = [l.text.strip() for l in links if l.text.strip()][:15]
                    logger.info(f"  フレーム[{i}]のリンク: {link_texts}")

                    driver.switch_to.default_content()
                except Exception as e:
                    logger.warning(f"フレーム[{i}]切り替えエラー: {e}")
                    driver.switch_to.default_content()

        driver.switch_to.default_content()
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            text = link.text.strip()
            if "入出金明細" in text or "明細照会" in text:
                link.click()
                time.sleep(3)
                logger.info("入出金明細照会ページへ移動")
                return True

        inputs = driver.find_elements(By.TAG_NAME, "input")
        for inp in inputs:
            alt = inp.get_attribute("alt") or ""
            val = inp.get_attribute("value") or ""
            title = inp.get_attribute("title") or ""
            if any("入出金" in s or "明細" in s for s in [alt, val, title]):
                inp.click()
                time.sleep(3)
                logger.info(f"入出金明細ボタンをクリック: alt={alt}, value={val}")
                return True

        logger.warning("入出金明細リンクが見つかりません。")
        return False

    except Exception as e:
        logger.error(f"ページ遷移エラー: {e}")
        return False


def set_date_range(driver):
    """照会期間を設定（前日〜今日の2日間）"""
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    try:
        js_result = driver.execute_script("""
            function setSelectValue(id, value) {
                var el = document.getElementById(id);
                if (!el) return false;
                var strVal = String(value).padStart(2, '0');
                for (var i = 0; i < el.options.length; i++) {
                    if (el.options[i].value === strVal || el.options[i].text.trim() === strVal) {
                        el.selectedIndex = i;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        return true;
                    }
                }
                var plainVal = String(parseInt(value));
                for (var i = 0; i < el.options.length; i++) {
                    if (el.options[i].value === plainVal || el.options[i].text.trim() === plainVal) {
                        el.selectedIndex = i;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        return true;
                    }
                }
                return false;
            }

            var results = {};
            results.y1 = setSelectValue('year_1', arguments[0]);
            results.m1 = setSelectValue('month_1', arguments[1]);
            results.d1 = setSelectValue('date_1', arguments[2]);
            results.y2 = setSelectValue('year_2', arguments[3]);
            results.m2 = setSelectValue('month_2', arguments[4]);
            results.d2 = setSelectValue('date_2', arguments[5]);

            var getVal = function(id) {
                var el = document.getElementById(id);
                return el ? el.options[el.selectedIndex].text.trim() : 'N/A';
            };
            results.from_date = getVal('year_1') + '/' + getVal('month_1') + '/' + getVal('date_1');
            results.to_date = getVal('year_2') + '/' + getVal('month_2') + '/' + getVal('date_2');

            return JSON.stringify(results);
        """, str(yesterday.year), f"{yesterday.month:02d}", f"{yesterday.day:02d}",
            str(today.year), f"{today.month:02d}", f"{today.day:02d}")

        result = json.loads(js_result)
        logger.info(f"開始日設定後: {result.get('from_date', 'N/A')}")
        logger.info(f"終了日設定後: {result.get('to_date', 'N/A')}")
        logger.info(f"照会期間: {yesterday.strftime('%Y/%m/%d')} ～ {today.strftime('%Y/%m/%d')}")
        return True

    except Exception as e:
        logger.error(f"日付設定エラー: {e}")
        try:
            html_path = os.path.join(CSV_DIR, "date_page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info(f"日付ページHTML保存: {html_path}")
        except Exception:
            pass
        return False


def select_branch(driver, branch_index):
    """店舗を選択"""
    try:
        branch_select = Select(driver.find_element(By.ID, "braAcct_1"))
        branch_select.select_by_index(branch_index)
        time.sleep(1)
        logger.info(f"店舗インデックス {branch_index} を選択")
        return True
    except Exception as e:
        logger.warning(f"braAcct_1が見つかりません。入出金明細照会ページへ再遷移します: {e}")
        try:
            navigate_to_transaction_history(driver)
            time.sleep(2)
            branch_select = Select(driver.find_element(By.ID, "braAcct_1"))
            branch_select.select_by_index(branch_index)
            time.sleep(1)
            logger.info(f"再遷移後、店舗インデックス {branch_index} を選択")
            return True
        except Exception as e2:
            logger.error(f"店舗選択エラー（再遷移後も失敗）: {e2}")
            return False


def click_inquiry_button(driver):
    """表示条件変更（doInquire）を実行"""
    try:
        driver.execute_script("doInquire();")
        logger.info("doInquire() を実行しました")
        time.sleep(5)
        return True
    except Exception as e:
        logger.warning(f"doInquire()失敗: {e}")

    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            onclick = link.get_attribute("onclick") or ""
            text = link.text.strip()
            if "doInquire" in onclick or "表示条件変更" in text:
                link.click()
                logger.info(f"表示条件変更リンクをクリック: {text}")
                time.sleep(5)
                return True
    except Exception as e:
        logger.warning(f"表示条件変更リンクのクリック失敗: {e}")

    logger.error("照会ボタンが見つかりません")
    return False


def extract_table_data(driver):
    """取引テーブルからデータを抽出"""
    js_code = """
    var table = document.querySelector('table.typeE2');
    var data = [];
    if (table) {
        for (var i = 1; i < table.rows.length; i++) {
            var row = table.rows[i];
            var cells = row.querySelectorAll('td');
            if (cells.length >= 5) {
                var d = (cells[0].textContent || '').trim();
                var desc = (cells[1].textContent || '').trim();
                var out_amt = (cells[2].textContent || '').trim().replace(/円/g,'').replace(/,/g,'');
                var in_amt = (cells[3].textContent || '').trim().replace(/円/g,'').replace(/,/g,'');
                var bal = (cells[4].textContent || '').trim().replace(/円/g,'').replace(/,/g,'');
                if (d.match(/^\\d{4}/)) {
                    data.push(d + '|' + desc + '|' + out_amt + '|' + in_amt + '|' + bal);
                }
            }
        }
    }
    return JSON.stringify(data);
    """
    try:
        result = driver.execute_script(js_code)
        rows = json.loads(result) if result else []
        logger.info(f"テーブルから {len(rows)} 件の取引を取得")
        return rows
    except Exception as e:
        logger.error(f"テーブルデータ抽出エラー: {e}")
        return []


def check_next_page(driver):
    """次のページがあるか確認し、あれば移動"""
    try:
        next_links = driver.find_elements(By.LINK_TEXT, "次へ")
        if next_links:
            next_links[0].click()
            time.sleep(3)
            return True

        result = driver.execute_script("""
            var links = document.querySelectorAll('a');
            for (var i = 0; i < links.length; i++) {
                if (links[i].textContent.indexOf('次へ') >= 0 || links[i].textContent.indexOf('次ページ') >= 0) {
                    links[i].click();
                    return true;
                }
            }
            return false;
        """)
        if result:
            time.sleep(3)
            return True

        return False
    except Exception:
        return False


def get_branch_data(driver, branch_name, branch_index):
    """特定の店舗の取引データを取得"""
    logger.info(f"--- {branch_name} のデータ取得開始 ---")

    if not select_branch(driver, branch_index):
        return []

    set_date_range(driver)
    click_inquiry_button(driver)
    time.sleep(3)

    all_data = []
    page = 1
    while True:
        logger.info(f"ページ {page} のデータ取得中...")
        rows = extract_table_data(driver)
        if rows:
            all_data.extend(rows)

        if check_next_page(driver):
            page += 1
        else:
            break

    logger.info(f"{branch_name}: 合計 {len(all_data)} 件の取引を取得")
    return all_data


# ============================================================
# CSV保存
# ============================================================

def save_csv(data_rows, filename):
    """取引データをCSVに保存（上書き）"""
    filepath = os.path.join(CSV_DIR, filename)
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["日付", "摘要", "出金金額", "入金金額", "残高"])
        for row_str in data_rows:
            parts = row_str.split("|")
            if len(parts) >= 5:
                writer.writerow(parts[:5])
    logger.info(f"CSV保存: {filepath} ({len(data_rows)} 件)")


# ============================================================
# Slack報告
# ============================================================

def format_transaction_message(branch_name, new_transactions):
    """Slackに送信するメッセージを整形"""
    lines = ["```"]

    for tx in new_transactions:
        parts = tx.split("|")
        if len(parts) >= 5:
            date = parts[0].strip()
            desc = parts[1].strip()
            out_amt = parts[2].strip()
            in_amt = parts[3].strip()
            balance = parts[4].strip()

            if in_amt and in_amt != "0":
                try:
                    amt_str = f"{int(in_amt):,}円"
                except ValueError:
                    amt_str = f"{in_amt}円"
            elif out_amt and out_amt != "0":
                try:
                    amt_str = f"{int(out_amt):,}円"
                except ValueError:
                    amt_str = f"{out_amt}円"
            else:
                amt_str = ""

            try:
                bal_str = f"{int(balance):,}円"
            except ValueError:
                bal_str = f"{balance}円"

            lines.append(f"{date}\t{desc}\t\t{amt_str}\t{bal_str}")

    lines.append("```")
    return "\n".join(lines)


def report_to_slack(branch_name, channel_id, data_rows):
    """Slackチャンネルに未報告の取引を投稿する"""
    if not data_rows:
        logger.info(f"{branch_name}: 取引データなし → スキップ")
        return

    reported_keys = extract_reported_keys(channel_id, limit=200)
    logger.info(f"{branch_name}: 報告済み {len(reported_keys)} 件")

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    target_dates = [today.strftime("%Y/%m/%d"), yesterday.strftime("%Y/%m/%d")]
    logger.info(f"{branch_name}: 対象日付: {target_dates}")

    new_transactions = []
    for row_str in data_rows:
        parts = row_str.split("|")
        if len(parts) >= 2:
            date_str = parts[0].strip()
            if date_str not in target_dates:
                continue
            desc = parts[1].strip() if len(parts) >= 2 else ""
            if not desc and len(parts) >= 5:
                out_amt = parts[2].strip()
                in_amt = parts[3].strip()
                balance = parts[4].strip()
                amt = in_amt if (in_amt and in_amt != "0") else out_amt
                key = normalize_key(parts[0], f"_amt{amt}_bal{balance}")
            else:
                key = normalize_key(parts[0], desc)
            if key not in reported_keys:
                new_transactions.append(row_str)

    if not new_transactions:
        logger.info(f"{branch_name}: 新規取引なし → スキップ")
        return

    logger.info(f"{branch_name}: 新規 {len(new_transactions)} 件の取引を報告")

    message = format_transaction_message(branch_name, new_transactions)
    logger.info(f"{branch_name}: メッセージ長={len(message)}文字")
    slack_post_message(channel_id, message)


# ============================================================
# メイン処理
# ============================================================

def slack_notify_error(error_message):
    """エラー発生時にassist-kouziへ通知"""
    text = f"⚠️ 鹿銀スクリプトエラー\n```{error_message}```"
    slack_post_message(ERROR_NOTIFY_USER, text)


def slack_connection_test():
    """Slack APIの接続テスト"""
    logger.info("--- Slack接続テスト開始 ---")
    url = "https://slack.com/api/auth.test"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        logger.info(f"auth.test応答: ok={data.get('ok')}, user={data.get('user')}, team={data.get('team')}")
        if not data.get("ok"):
            logger.error(f"Slackトークンが無効です: {data.get('error')}")
            return False
        logger.info("Slack接続テスト成功")
        return True
    except Exception as e:
        logger.error(f"Slack接続テスト失敗: {e}")
        return False


def main():
    """メイン処理。戻り値: {"success": int, "total": int, "error": str or None}"""
    setup_logging()
    logger.info("=" * 60)
    logger.info("鹿児島銀行 Slack報告スクリプト開始 (Windows版)")
    logger.info("=" * 60)

    result = {"success": 0, "total": len(BRANCHES), "error": None}

    if not slack_connection_test():
        result["error"] = "Slack接続に失敗しました"
        logger.error(result["error"])
        return result

    logger.info("各チャンネルにボットを参加させています...")
    for branch_name, _, channel_id, _ in BRANCHES:
        slack_join_channel(channel_id)
    time.sleep(1)

    driver = None
    try:
        driver = create_driver()

        if not login_to_bank(driver):
            result["error"] = "銀行ログインに失敗しました"
            logger.error(result["error"])
            slack_notify_error(result["error"])
            return result

        nav_ok = navigate_to_transaction_history(driver)
        if not nav_ok:
            error_msg = "入出金明細照会ページへの遷移に失敗しました"
            logger.error(error_msg)
            slack_notify_error(error_msg)

        for branch_name, branch_index, channel_id, csv_filename in BRANCHES:
            try:
                data_rows = get_branch_data(driver, branch_name, branch_index)

                if data_rows:
                    save_csv(data_rows, csv_filename)
                    result["success"] += 1

                report_to_slack(branch_name, channel_id, data_rows)
                time.sleep(2)

            except Exception as e:
                logger.error(f"{branch_name} 処理エラー: {e}")
                slack_notify_error(f"{branch_name} 処理エラー: {e}")
                continue

        if result["success"] == 0:
            result["error"] = f"全{len(BRANCHES)}店舗でデータ取得に失敗しました"
            logger.error(result["error"])
            slack_notify_error(result["error"])

    except Exception as e:
        result["error"] = f"致命的エラー: {e}"
        logger.error(result["error"])
        slack_notify_error(result["error"])

    finally:
        if driver:
            driver.quit()
            logger.info("ブラウザ終了")

    logger.info("スクリプト完了")
    return result


if __name__ == "__main__":
    main()
