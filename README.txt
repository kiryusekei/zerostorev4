╔══════════════════════════════════════════════════════════╗
║        TELEGRAM AUTOPAY STORE BOT - Nexus         ║
║   Single Token | All Buttons | Bypass Admin | Broadcast  ║
╚══════════════════════════════════════════════════════════╝


═══════════════════════════════════════════
        CARA INSTALL & SETUP
═══════════════════════════════════════════

LANGKAH 1 — BUAT BOT TELEGRAM
──────────────────────────────
• Buka Telegram → cari @BotFather
• Kirim: /newbot
• Ikuti instruksi, catat BOT_TOKEN
• Contoh token: 7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

LANGKAH 2 — DAPATKAN TELEGRAM ID KAMU
───────────────────────────────────────
• Cari @userinfobot di Telegram
• Kirim /start → catat angka "Id" kamu
• Contoh: 1957639198

LANGKAH 3 — UPLOAD FILE KE VPS
────────────────────────────────
mkdir -p /root/autopay_bot
cd /root/autopay_bot
# Upload bot.py dan requirements.txt ke folder ini

LANGKAH 4 — INSTALL PYTHON & DEPENDENCIES
───────────────────────────────────────────
apt update && apt install -y python3 python3-pip
pip3 install -r requirements.txt

LANGKAH 5 — EDIT KONFIGURASI
──────────────────────────────
Edit file bot.py bagian paling atas:
   BOT_TOKEN  = "token_dari_BotFather_kamu"
   ADMIN_IDS  = [1957639198]   ← ID Telegram kamu

ATAU pakai environment variable (lebih aman):
   export BOT_TOKEN="token_dari_BotFather_kamu"
   export ADMIN_IDS="1957639198"

LANGKAH 6 — TEST JALANKAN DULU
────────────────────────────────
python3 /root/autopay_bot/bot.py
# Kalau berhasil keluar log: "🤖 AUTOPAY BOT aktif!"
# Tekan Ctrl+C untuk stop, lanjut ke systemd


═══════════════════════════════════════════
     SETUP SYSTEMD (BOT ONLINE TERUS)
═══════════════════════════════════════════

1. Edit file autopay-bot.service:
   Ganti baris ini:
     WorkingDirectory=/root/autopay_bot
     ExecStart=/usr/bin/python3 /root/autopay_bot/bot.py
     Environment="BOT_TOKEN=ISI_TOKEN_BOTFATHER_DISINI"
     Environment="ADMIN_IDS=ISI_TELEGRAM_ID_ADMIN_DISINI"

2. Copy service file ke systemd:
   cp autopay-bot.service /etc/systemd/system/

3. Reload dan aktifkan service:
   systemctl daemon-reload
   systemctl enable autopay-bot
   systemctl start autopay-bot

4. Cek status bot:
   systemctl status autopay-bot

5. Lihat log real-time:
   journalctl -u autopay-bot -f

6. Restart bot manual:
   systemctl restart autopay-bot

7. Stop bot:
   systemctl stop autopay-bot


═══════════════════════════════════════════
         SEMUA FITUR BOT
═══════════════════════════════════════════

UNTUK USER:
  ✅ /start   → Halaman utama (foto/video + tombol)
  ✅ Katalog  → Daftar produk + harga + stok real-time
  ✅ Beli     → Pilih qty + QRIS auto-generate
  ✅ Auto-delivery setelah bayar (cek tiap 5 detik)
  ✅ Invoice dengan QR Code QRIS
  ✅ Notifikasi expired kalau tidak bayar 5 menit
  ✅ Bantuan  → Panduan cara beli

UNTUK ADMIN (tombol ⚙️ Panel Admin di /start):
  ✅ Tambah Produk     → nama, harga, deskripsi
  ✅ Tambah Stok       → 1 item atau banyak sekaligus (pisah ---)
  ✅ Kelola Produk     → edit nama/harga/deskripsi, hapus
  ✅ Bypass Pembayaran → ambil produk gratis tanpa QRIS
  ✅ Kelola Media Start→ set/hapus foto atau video di /start
  ✅ Broadcast Teks    → kirim teks ke semua user
  ✅ Broadcast Foto    → kirim foto+caption ke semua user
  ✅ Broadcast Video   → kirim video+caption ke semua user
  ✅ Statistik Toko    → produk, stok, transaksi, pendapatan
  ✅ Notif stok baru   → otomatis kirim ke semua user saat stok ditambah


═══════════════════════════════════════════
         CARA PAKAI ADMIN
═══════════════════════════════════════════

BUKA PANEL ADMIN:
  Kirim /start ke bot → Klik tombol ⚙️ Panel Admin

TAMBAH PRODUK BARU:
  Panel Admin → ➕ Tambah Produk
  Bot akan tanya: nama → harga → deskripsi

TAMBAH STOK:
  Panel Admin → 📦 Tambah Stok Produk → Pilih produk
  Kirim isi stok:
  
  Contoh 1 item:
  ─────────────────────────────
  ☁️ VPS Tencent Services (TC)
  LOGIN ROOT VPS | PASSWORD : 👇
  FORMAT: root@IPVPS <PASSWORD>
  43.156.150.198 yha

  ====================
  Thank you for using our services
  ─────────────────────────────
  
  Contoh 2 item sekaligus (pisahkan dengan ---):
  ─────────────────────────────
  akun1@email.com | pass1
  ---
  akun2@email.com | pass2
  ─────────────────────────────

BYPASS ORDER (GRATIS TANPA BAYAR):
  Pilih produk → atur qty → klik 🔓 Bypass Pembayaran (Admin)
  Produk langsung dikirim tanpa QRIS

SET FOTO/VIDEO START:
  Panel Admin → 🖼️ Kelola Media Start
  → Upload Foto Baru / Upload Video Baru

BROADCAST:
  Panel Admin → 📢 Broadcast
  Pilih: Teks / Foto / Video
  Kirim konten → bot otomatis sebar ke semua user


═══════════════════════════════════════════
         FORMAT STOK YANG DIKIRIM
═══════════════════════════════════════════

Setelah user bayar, bot kirim pesan seperti ini:

  🎉 Pembelian Berhasil 🎉
  Produk: VPS TENCENT 2C 2G
  Tanggal: 18/3/2026 Pukul 15.03.00

  ☁️ VPS Tencent Services (TC)
  LOGIN ROOT VPS | PASSWORD : 👇
  FORMAT: root@IPVPS <PASSWORD>
  43.156.150.198 nexus

  ====================
  Thank you for using our services


═══════════════════════════════════════════
         TROUBLESHOOTING
═══════════════════════════════════════════

"Conflict: terminated by other getUpdates":
  → Bot sedang jalan di tempat lain, matikan dulu

"Unauthorized":
  → BOT_TOKEN salah, cek kembali di BotFather

QRIS tidak muncul:
  → Cek koneksi ke payment.vpnnexus.biz.id
  → Test manual: curl "https://payment.vpnnexus.biz.id/api/deposit?amount=5000&apikey=8d5ab019-1c72-4701-92f7-29c64730edf3"

Bot tidak merespons:
  → Pastikan user sudah /start bot terlebih dahulu
  → Cek log: journalctl -u autopay-bot -f

Tombol Admin tidak muncul:
  → Pastikan ADMIN_IDS sudah diisi dengan ID Telegram kamu
  → Kirim /start lagi setelah set ADMIN_IDS


═══════════════════════════════════════════
         FILE STRUKTUR
═══════════════════════════════════════════

/root/autopay_bot/
├── bot.py                  ← File utama bot
├── requirements.txt        ← Library dependencies
├── autopay-bot.service     ← Systemd service file
├── README.txt              ← Panduan ini
└── store.db                ← Database (auto-dibuat)


Dibuat dengan ❤️ | AUTOPAY Store Bot
