#!/bin/bash
# 鹿児島銀行レポート用 - 翌日のスリープ解除スケジュール設定
# 毎日実行して翌日の4回分のスリープ解除を予約する

TOMORROW=$(date -v+1d +"%m/%d/%Y")

sudo pmset schedule wake "$TOMORROW 08:49:00"
sudo pmset schedule wake "$TOMORROW 11:49:00"
sudo pmset schedule wake "$TOMORROW 14:49:00"
sudo pmset schedule wake "$TOMORROW 18:19:00"
sudo pmset schedule wake "$TOMORROW 20:55:00"

echo "$(date): 翌日($TOMORROW)のスリープ解除スケジュールを設定しました（8:49, 11:49, 14:49, 18:19）"
