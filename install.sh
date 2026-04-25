#!/bin/bash

echo "🚀 INSTALL AUTOPAY BOT"

# Input dari user
read -p "Masukkan BOT TOKEN: " BOT_TOKEN
read -p "Masukkan ADMIN ID: " ADMIN_ID

echo "📦 Install dependencies..."
apt update -y
apt install -y python3 python3-venv python3-pip git

# Clone repo
cd /root
rm -rf autopay_bot
git clone https://github.com/kiryusekei/v4/autopay-bot.git autopay_bot

cd autopay_bot

# Buat venv
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# Simpan ke environment file
echo "BOT_TOKEN=$BOT_TOKEN" > .env
echo "ADMIN_IDS=$ADMIN_ID" >> .env

echo "✅ Install selesai!"
echo "👉 Jalankan bot: source venv/bin/activate && python bot.py"
