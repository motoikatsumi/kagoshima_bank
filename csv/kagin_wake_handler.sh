#!/bin/bash
# スリープ解除後にcaffeinateを起動し、Pythonスクリプトで鹿銀→Slack報告を実行
# 各タスク時間帯に合わせて60分間スリープを防止する

SCRIPT_DIR="/Users/yudakouji/Documents/Claude/Projects/kagoshima_bank/csv"
LOG_FILE="${SCRIPT_DIR}/kagin_cron.log"
PYTHON="/usr/bin/python3"

/usr/bin/caffeinate -dimsu -t 3600 &
echo "$(date): caffeinate started (PID: $!)" >> /tmp/kagin_wake.log

# 30秒待機（ネットワーク接続安定化のため）
sleep 30

# Pythonスクリプト実行
echo "$(date): Python スクリプト開始" >> "$LOG_FILE"
$PYTHON "${SCRIPT_DIR}/kagin_slack_report.py" >> "$LOG_FILE" 2>&1
echo "$(date): Python スクリプト完了 (exit: $?)" >> "$LOG_FILE"
