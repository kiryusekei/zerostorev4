#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   TELEGRAM AUTOPAY STORE BOT - Nexus   ║
║   Single Token | All Buttons | Admin Bypass  ║
╚══════════════════════════════════════════════╝
"""

import os, asyncio, sqlite3, aiohttp, logging
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

# ══════════════════════════════════════════════
#                 KONFIGURASI
# ══════════════════════════════════════════════
# ─────────────────────────────────────────────────
#  EDIT HANYA DI SINI — ISI TOKEN & ADMIN ID KAMU
BOT_TOKEN  = "ISI_TOKEN_BOTFATHER_DISINI"
ADMIN_IDS  = [123456789]   # ganti dengan ID Telegram kamu
API_KEY    = "8d5ab019-1c72-470c64730edf3"
# ─────────────────────────────────────────────────
PAY_BASE      = "https://payment.vpnnexus.biz.id/api"
DB_PATH       = "store.db"
POLL_INTERVAL = 5
EXPIRE_SEC    = 300

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════
#                  DATABASE
# ══════════════════════════════════════════════
def init_db():
    c = sqlite3.connect(DB_PATH)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stock_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            is_sold INTEGER DEFAULT 0,
            sold_at TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            transaction_id TEXT UNIQUE,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    c.commit(); c.close()

def db():
    return sqlite3.connect(DB_PATH)

def get_setting(key, default=None):
    r = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default

def set_setting(key, value):
    c = db()
    c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
    c.commit(); c.close()

def register_user(uid, username, first_name):
    c = db()
    c.execute("INSERT OR IGNORE INTO users(id,username,first_name) VALUES(?,?,?)",
              (uid, username or "", first_name or ""))
    c.commit(); c.close()

def all_user_ids():
    return [r[0] for r in db().execute("SELECT id FROM users").fetchall()]

def get_stats():
    c = db()
    prods = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    sales = c.execute("SELECT COUNT(*) FROM transactions WHERE status='paid'").fetchone()[0]
    users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    rev   = c.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE status='paid'").fetchone()[0]
    stock = c.execute("SELECT COUNT(*) FROM stock_items WHERE is_sold=0").fetchone()[0]
    c.close()
    return prods, sales, users, rev, stock

def get_all_products():
    return db().execute("""
        SELECT p.id, p.name, p.price,
               COUNT(CASE WHEN s.is_sold=0 THEN 1 END) AS stok
        FROM products p LEFT JOIN stock_items s ON p.id=s.product_id
        GROUP BY p.id ORDER BY p.id
    """).fetchall()

def get_product(pid):
    return db().execute("""
        SELECT p.id, p.name, p.price, p.description,
               COUNT(CASE WHEN s.is_sold=0 THEN 1 END) AS stok
        FROM products p LEFT JOIN stock_items s ON p.id=s.product_id
        WHERE p.id=? GROUP BY p.id
    """, (pid,)).fetchone()

def take_stock(product_id, qty):
    c = db()
    rows = c.execute(
        "SELECT id,content FROM stock_items WHERE product_id=? AND is_sold=0 LIMIT ?",
        (product_id, qty)).fetchall()
    now = datetime.now().isoformat()
    for r in rows:
        c.execute("UPDATE stock_items SET is_sold=1,sold_at=? WHERE id=?", (now, r[0]))
    c.commit(); c.close()
    return rows

def save_transaction(user_id, username, transaction_id, product_id, qty, amount):
    c = db()
    c.execute(
        "INSERT INTO transactions(user_id,username,transaction_id,product_id,quantity,amount,status)"
        " VALUES(?,?,?,?,?,?,'pending')",
        (user_id, username or "", transaction_id, product_id, qty, amount))
    c.commit(); c.close()

def update_transaction_status(transaction_id, status):
    c = db()
    c.execute("UPDATE transactions SET status=? WHERE transaction_id=?", (status, transaction_id))
    c.commit(); c.close()

def rp(n):
    return "Rp " + f"{n:,}".replace(",", ".")


# ══════════════════════════════════════════════
#              PAYMENT API
# ══════════════════════════════════════════════
async def create_qris(amount: int):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{PAY_BASE}/deposit",
                             params={"amount": amount, "apikey": API_KEY},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status") == "success":
                        return d["data"]
    except Exception as e:
        log.error(f"create_qris: {e}")
    return None

async def check_qris(txid: str) -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{PAY_BASE}/status/payment",
                             params={"transaction_id": txid, "apikey": API_KEY},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return (await r.json()).get("paid", False)
    except Exception as e:
        log.error(f"check_qris: {e}")
    return False


# ══════════════════════════════════════════════
#              FORMATTERS
# ══════════════════════════════════════════════
def fmt_welcome(prods, sales, users, stock, uname_bot, user):
    return (
        f"💚 *Selamat Datang di @{uname_bot}*, {user.first_name}!\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏪 *Sekilas Info Toko:*\n"
        f"• Total Jenis Produk: {prods}\n"
        f"• Total Penjualan: {sales} transaksi\n"
        f"• Total Pengguna: {users} User\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Profil Anda:*\n"
        f"• Username: @{user.username or 'Tidak ada'}\n"
        f"• User ID: `{user.id}`\n\n"
        f"*pilih menu di bawah untuk melanjutkan.*"
    )

def fmt_catalog(products):
    lines = [
        "🛒 *KATALOG PRODUK*",
        "🪙 Pilih Produk di bawah ini",
        "*Sesuai dengan stok tersedia* 🌙",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, (pid, name, price, stok) in enumerate(products, 1):
        stok_txt = f"✅ Stok Tersedia: {stok}" if stok > 0 else "❌ Stok Tersedia: *Habis*"
        lines += [
            f"\n[ {i} ]  *{name}*",
            "- - - - - - - - - - - - - - - - - - -",
            f"💰 Harga: {rp(price)}",
            stok_txt,
            "━━━━━━━━━━━━━━━━━━━━━",
        ]
    lines.append("\n*pilih produk yang anda inginkan:*")
    return "\n".join(lines)

def fmt_product_detail(prod, qty=1):
    pid_, name, price, desc, stok = prod
    return (
        f"📦 *{name}*\n\n"
        f"*Harga Satuan:* {rp(price)}\n"
        f"*Stok Tersisa:* {stok}\n\n"
        f"📋 *Deskripsi:*\n{desc or 'Tidak ada deskripsi.'}\n\n"
        f"{'━'*20}\n"
        f"*Total Harga:* {rp(price * qty)}\n\n"
        f"*Silakan tentukan jumlah yang ingin dibeli:*"
    )

def fmt_invoice(name, qty, price, fee, total, exp_min, txid):
    return (
        f"🧾 *INVOICE PEMBAYARAN*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Produk:* {name}\n"
        f"*Jumlah:* {qty} item\n"
        f"*Harga Produk:* {rp(price * qty)}\n"
        f"*Fee Transaksi:* {rp(fee)}\n"
        f"*Total Bayar:* {rp(total)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ Berlaku: *{exp_min} menit*\n"
        f"🔑 Invoice: `{txid}`\n\n"
        f"Silakan pindai (scan) QR Code di atas menggunakan "
        f"aplikasi e-wallet atau m-banking Anda untuk menyelesaikan pembayaran.\n\n"
        f"Pesanan akan otomatis dikirim setelah pembayaran berhasil."
    )

HARI_ID = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]

def fmt_delivery_card(user_id, username, prod_name, price, qty, txid, content):
    """Kartu notifikasi pengiriman produk - mirip screenshot."""
    now      = datetime.now()
    hari     = HARI_ID[now.weekday()]
    tanggal  = now.strftime("%d.%m.%Y")
    waktu    = now.strftime("%H:%M") + " WIB"
    uname    = f"@{username}" if username else f"id:{user_id}"
    total    = rp(price * qty)

    header = (
        f"🎁 *PEMBELIAN BERHASIL* 🎁\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    card = (
        f"👤 *Username*  :  {uname}\n"
        f"🪪 *ID*            :  `{user_id}`\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        f"📦 *Produk*    :  {prod_name}\n"
        f"💰 *Harga*      :  {total}\n"
        f"🔢 *Jumlah*    :  {qty} item\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        f"📅 *Hari*          :  {hari}\n"
        f"🗓️ *Tanggal*    :  {tanggal}\n"
        f"🕐 *Waktu*       :  {waktu}\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        f"🔑 *Invoice*    :  `{txid}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    item_block = f"```\n{content}\n```\n\n"
    footer = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Catatan:* Simpan nomor invoice untuk support\n\n"
        f"⚠️ Ingat deskripsi ya, jadi pembeli yang bijak\n"
        f"patuh terhadap TOS / larangan 🙏\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    return header + card + item_block + footer

def fmt_success(name, date_str):
    # Legacy - masih dipakai di beberapa tempat
    return (
        f"🎉 *Pembelian Berhasil* 🎉\n"
        f"*Produk:* {name}\n"
        f"*Tanggal:* {date_str}"
    )

def fmt_expired_msg(txid, name):
    return (
        f"⚠️ *Waktu Pembayaran Berakhir* ⚠️\n\n"
        f"Invoice Anda dengan nomor `{txid}` untuk produk *{name}* telah kedaluwarsa.\n\n"
        f"Pesanan Anda telah dibatalkan secara otomatis oleh sistem. "
        f"Jika Anda masih ingin melanjutkan pembelian, silakan buat pesanan baru."
    )

def fmt_stock_notif(name, price, stok, bot_uname):
    return (
        f"📦 *Stok Baru Tersedia!*\n\n"
        f"[ {name} ]\n"
        f"- - - - - - - - - - - - - - - - - - -\n"
        f"💰 Harga: {rp(price)}\n"
        f"✅ Stok Tersedia: {stok}\n"
        f"{'─'*25}\n"
        f"Pantau item tersedia dan jangan lupa Selalu baca deskripsi ya kk😇🙏\n\n"
        f"🤍 AUTOPAY @{bot_uname}"
    )


# ══════════════════════════════════════════════
#              KEYBOARDS
# ══════════════════════════════════════════════
def kb_main(is_admin=False):
    rows = [[
        InlineKeyboardButton("🛒 Pembelian", callback_data="menu_purchase"),
        InlineKeyboardButton("🆘 Bantuan",   callback_data="menu_help"),
    ]]
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ Panel Admin", callback_data="adm_panel")])
    return InlineKeyboardMarkup(rows)

def kb_catalog(products):
    rows, nums = [], []
    for i, (pid, *_) in enumerate(products, 1):
        nums.append(InlineKeyboardButton(str(i), callback_data=f"prod_{pid}"))
        if len(nums) == 5:
            rows.append(nums); nums = []
    if nums:
        rows.append(nums)
    rows.append([InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

def kb_product(pid, qty, max_stok, is_admin=False):
    rows = [
        [
            InlineKeyboardButton("➖", callback_data=f"qty_dec_{pid}_{qty}"),
            InlineKeyboardButton(str(qty), callback_data="noop"),
            InlineKeyboardButton("➕", callback_data=f"qty_inc_{pid}_{qty}"),
        ],
        [InlineKeyboardButton(f"🛍️ Beli Semua Stok ({max_stok})", callback_data=f"qty_all_{pid}_{max_stok}")],
        [InlineKeyboardButton("✅ Lanjutkan Pembelian", callback_data=f"buy_{pid}_{qty}")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🔓 Bypass Pembayaran (Admin)", callback_data=f"bypass_{pid}_{qty}")])
    rows.append([InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="menu_purchase")])
    return InlineKeyboardMarkup(rows)

def kb_admin_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Tambah Produk",           callback_data="adm_add_prod")],
        [InlineKeyboardButton("📦 Tambah Stok Produk",      callback_data="adm_add_stock")],
        [InlineKeyboardButton("📋 Daftar & Kelola Produk",  callback_data="adm_list_prod")],
        [InlineKeyboardButton("🖼️ Kelola Media Start",      callback_data="adm_photo_menu")],
        [InlineKeyboardButton("📢 Broadcast",               callback_data="adm_broadcast_menu")],
        [InlineKeyboardButton("📊 Statistik Toko",          callback_data="adm_stats")],
        [InlineKeyboardButton("🔙 Menu Utama",              callback_data="main_menu")],
    ])

def kb_cancel_admin():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="adm_cancel")]])

def kb_back_admin():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali ke Admin", callback_data="adm_panel")]])

def kb_broadcast_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Broadcast Teks",  callback_data="adm_bc_text")],
        [InlineKeyboardButton("🖼️ Broadcast Foto",  callback_data="adm_bc_photo")],
        [InlineKeyboardButton("🎬 Broadcast Video", callback_data="adm_bc_video")],
        [InlineKeyboardButton("🔙 Kembali",         callback_data="adm_panel")],
    ])

def kb_photo_menu():
    media_id   = get_setting("start_media_id")
    media_type = get_setting("start_media_type", "photo")
    rows = []
    if media_id:
        label = "🖼️ Foto aktif" if media_type == "photo" else "🎬 Video aktif"
        rows.append([InlineKeyboardButton(f"✅ {label}", callback_data="noop")])
        rows.append([InlineKeyboardButton("🗑️ Hapus Media Start", callback_data="adm_media_del")])
    rows += [
        [InlineKeyboardButton("🖼️ Upload Foto Baru",  callback_data="adm_media_photo")],
        [InlineKeyboardButton("🎬 Upload Video Baru", callback_data="adm_media_video")],
        [InlineKeyboardButton("🔙 Kembali",           callback_data="adm_panel")],
    ]
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════
#            ADMIN STATES
# ══════════════════════════════════════════════
S_IDLE        = None
S_PROD_NAME   = "prod_name"
S_PROD_PRICE  = "prod_price"
S_PROD_DESC   = "prod_desc"
S_STOCK_ITEMS = "stock_items"
S_MEDIA_PHOTO = "media_photo"
S_MEDIA_VIDEO = "media_video"
S_BC_TEXT     = "bc_text"
S_BC_PHOTO    = "bc_photo"
S_BC_VIDEO    = "bc_video"
S_EDIT_NAME   = "edit_name"
S_EDIT_PRICE  = "edit_price"
S_EDIT_DESC   = "edit_desc"


def _clear(ctx):
    for k in ["state","s_pid","s_name","s_price","edit_pid","p_name","p_price"]:
        ctx.user_data.pop(k, None)


# ══════════════════════════════════════════════
#      SAFE EDIT HELPERS
# ══════════════════════════════════════════════
async def safe_edit(q, text, kb=None, md=ParseMode.MARKDOWN):
    kw = {"text": text, "parse_mode": md}
    if kb: kw["reply_markup"] = kb
    try:
        await q.edit_message_text(**kw)
    except Exception:
        await q.message.reply_text(**kw)


# ══════════════════════════════════════════════
#                  /start
# ══════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)
    prods, sales, users, rev, stock = get_stats()
    bot_info = await ctx.bot.get_me()
    is_admin = user.id in ADMIN_IDS
    text     = fmt_welcome(prods, sales, users, stock, bot_info.username, user)
    kb       = kb_main(is_admin)

    media_id   = get_setting("start_media_id")
    media_type = get_setting("start_media_type", "photo")

    if media_id:
        try:
            if media_type == "photo":
                await update.message.reply_photo(
                    photo=media_id, caption=text,
                    parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            else:
                await update.message.reply_video(
                    video=media_id, caption=text,
                    parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            return
        except Exception:
            pass

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


# ══════════════════════════════════════════════
#         SINGLE CALLBACK QUERY HANDLER
# ══════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    d   = q.data
    await q.answer()

    # ── noop ─────────────────────────────────────────
    if d == "noop":
        return

    # ── Menu Utama ────────────────────────────────────
    if d == "main_menu":
        register_user(uid, q.from_user.username, q.from_user.first_name)
        prods, sales, users, rev, stock = get_stats()
        bot_info = await ctx.bot.get_me()
        text = fmt_welcome(prods, sales, users, stock, bot_info.username, q.from_user)
        await safe_edit(q, text, kb_main(uid in ADMIN_IDS))
        return

    # ── Pembelian / Katalog ───────────────────────────
    if d == "menu_purchase":
        products = get_all_products()
        if not products:
            await safe_edit(q, "❌ Belum ada produk tersedia.",
                            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")]]))
            return
        await safe_edit(q, fmt_catalog(products), kb_catalog(products))
        return

    # ── Bantuan ───────────────────────────────────────
    if d == "menu_help":
        await safe_edit(q,
            "🆘 *BANTUAN*\n━━━━━━━━━━━━━━━━\n\n"
            "*Cara Membeli Produk:*\n"
            "1. Ketuk tombol 🛒 *Pembelian*\n"
            "2. Pilih produk yang ingin dibeli\n"
            "3. Tentukan jumlah pembelian\n"
            "4. Ketuk ✅ *Lanjutkan Pembelian*\n"
            "5. Scan QR Code QRIS yang muncul\n"
            "6. Produk otomatis dikirim setelah bayar\n\n"
            "*Catatan:*\n"
            "• Pembayaran berlaku selama 5 menit\n"
            "• Produk Non-refundable kecuali ada keterangan\n"
            "• Hubungi admin jika ada kendala",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")]]))
        return

    # ── Detail Produk ─────────────────────────────────
    if d.startswith("prod_"):
        pid  = int(d.split("_")[1])
        prod = get_product(pid)
        if not prod:
            return
        await safe_edit(q, fmt_product_detail(prod, 1),
                        kb_product(pid, 1, prod[4], uid in ADMIN_IDS))
        return

    # ── Qty buttons ───────────────────────────────────
    if d.startswith("qty_"):
        parts  = d.split("_")
        action = parts[1]
        if action == "dec":
            pid, cur = int(parts[2]), int(parts[3])
            qty = max(1, cur - 1)
        elif action == "inc":
            pid, cur = int(parts[2]), int(parts[3])
            prod = get_product(pid)
            qty  = min(cur + 1, prod[4]) if prod else cur
        else:  # all
            pid, qty = int(parts[2]), int(parts[3])
        prod = get_product(pid)
        if not prod:
            return
        qty = max(1, min(qty, prod[4]))
        await safe_edit(q, fmt_product_detail(prod, qty),
                        kb_product(pid, qty, prod[4], uid in ADMIN_IDS))
        return

    # ── Beli Normal ───────────────────────────────────
    if d.startswith("buy_"):
        parts = d.split("_")
        pid, qty = int(parts[1]), int(parts[2])
        await _process_buy(q, ctx, uid, pid, qty, bypass=False)
        return

    # ── Bypass Admin ──────────────────────────────────
    if d.startswith("bypass_"):
        if uid not in ADMIN_IDS:
            await q.answer("❌ Hanya admin!", show_alert=True)
            return
        parts = d.split("_")
        pid, qty = int(parts[1]), int(parts[2])
        await _process_buy(q, ctx, uid, pid, qty, bypass=True)
        return

    # ══════════════════════════════════════════════════
    #              ADMIN PANEL CALLBACKS
    # ══════════════════════════════════════════════════
    if d.startswith("adm_") and uid not in ADMIN_IDS:
        await q.answer("❌ Bukan admin!", show_alert=True)
        return

    # ── Panel utama ───────────────────────────────────
    if d == "adm_panel":
        prods, sales, users, rev, stock = get_stats()
        await safe_edit(q,
            f"⚙️ *PANEL ADMIN*\n━━━━━━━━━━━━━━━━\n"
            f"📦 Produk: {prods}  |  🗃️ Stok: {stock}\n"
            f"💰 Penjualan: {sales} transaksi\n"
            f"👥 Pengguna: {users}\n"
            f"💵 Pendapatan: {rp(rev)}\n"
            f"━━━━━━━━━━━━━━━━\nPilih menu:",
            kb_admin_main())
        return

    # ── Cancel ────────────────────────────────────────
    if d == "adm_cancel":
        _clear(ctx)
        prods, sales, users, rev, stock = get_stats()
        await safe_edit(q,
            f"⚙️ *PANEL ADMIN*\n━━━━━━━━━━━━━━━━\n"
            f"📦 Produk: {prods}  |  🗃️ Stok: {stock}\n"
            f"━━━━━━━━━━━━━━━━\nPilih menu:",
            kb_admin_main())
        return

    # ── Tambah Produk ─────────────────────────────────
    if d == "adm_add_prod":
        ctx.user_data["state"] = S_PROD_NAME
        await safe_edit(q, "📝 *Tambah Produk Baru*\n\nMasukkan *nama produk*:", kb_cancel_admin())
        return

    # ── Tambah Stok ───────────────────────────────────
    if d == "adm_add_stock":
        products = get_all_products()
        if not products:
            await safe_edit(q, "❌ Belum ada produk. Tambah produk dulu.", kb_back_admin())
            return
        rows = [
            [InlineKeyboardButton(f"[{pid}] {name}  (stok: {stok})",
                                  callback_data=f"adm_stk_{pid}")]
            for pid, name, price, stok in products
        ]
        rows.append([InlineKeyboardButton("❌ Batal", callback_data="adm_cancel")])
        await safe_edit(q, "📦 *Tambah Stok*\n\nPilih produk:", InlineKeyboardMarkup(rows))
        return

    if d.startswith("adm_stk_"):
        pid  = int(d.split("_")[2])
        prod = get_product(pid)
        ctx.user_data.update({"state": S_STOCK_ITEMS,
                              "s_pid": pid, "s_name": prod[1], "s_price": prod[2]})
        await safe_edit(q,
            f"📦 *Tambah Stok untuk* `{prod[1]}`\n\n"
            f"Kirim isi stok. Untuk *multiple item* pisahkan dengan baris `---`\n\n"
            f"*Contoh 1 item:*\n"
            f"```\n☁️ VPS Tencent Services (TC)\n"
            f"LOGIN ROOT VPS | PASSWORD : 👇\n"
            f"FORMAT: root@IPVPS <PASSWORD>\n"
            f"43.156.150.198 nexus\n\n"
            f"====================\n"
            f"Thank you for using our services```\n\n"
            f"*Contoh 2 item sekaligus:*\n"
            f"```\nakun1@mail.com|pass123\n---\nakun2@mail.com|pass456```",
            kb_cancel_admin())
        return

    # ── Daftar & Kelola Produk ────────────────────────
    if d == "adm_list_prod":
        products = get_all_products()
        if not products:
            await safe_edit(q, "❌ Belum ada produk.", kb_back_admin())
            return
        rows = [
            [InlineKeyboardButton(f"📦 {name}  [{stok} stok]",
                                  callback_data=f"adm_manage_{pid}")]
            for pid, name, price, stok in products
        ]
        rows.append([InlineKeyboardButton("🔙 Kembali", callback_data="adm_panel")])
        await safe_edit(q, "📋 *Daftar Produk*\nPilih produk untuk dikelola:",
                        InlineKeyboardMarkup(rows))
        return

    if d.startswith("adm_manage_"):
        pid  = int(d.split("_")[2])
        prod = get_product(pid)
        if not prod:
            return
        pid_, name, price, desc, stok = prod
        c = db()
        total_sold = c.execute(
            "SELECT COUNT(*) FROM stock_items WHERE product_id=? AND is_sold=1", (pid,)
        ).fetchone()[0]
        c.close()
        await safe_edit(q,
            f"📦 *{name}*\n━━━━━━━━━━━━━━━━\n"
            f"💰 Harga: {rp(price)}\n"
            f"✅ Stok Tersedia: {stok}\n"
            f"📊 Total Terjual: {total_sold}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📋 Deskripsi:\n{desc or '-'}",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Edit Nama",      callback_data=f"adm_ename_{pid}")],
                [InlineKeyboardButton("💰 Edit Harga",     callback_data=f"adm_eprice_{pid}")],
                [InlineKeyboardButton("📋 Edit Deskripsi", callback_data=f"adm_edesc_{pid}")],
                [InlineKeyboardButton("🗑️ Hapus Produk",   callback_data=f"adm_delask_{pid}")],
                [InlineKeyboardButton("🔙 Kembali",        callback_data="adm_list_prod")],
            ]))
        return

    if d.startswith("adm_ename_"):
        pid = int(d.split("_")[2])
        ctx.user_data.update({"state": S_EDIT_NAME, "edit_pid": pid})
        await safe_edit(q, "✏️ Masukkan *nama baru* untuk produk:", kb_cancel_admin())
        return

    if d.startswith("adm_eprice_"):
        pid = int(d.split("_")[2])
        ctx.user_data.update({"state": S_EDIT_PRICE, "edit_pid": pid})
        await safe_edit(q, "💰 Masukkan *harga baru* (angka saja):", kb_cancel_admin())
        return

    if d.startswith("adm_edesc_"):
        pid = int(d.split("_")[2])
        ctx.user_data.update({"state": S_EDIT_DESC, "edit_pid": pid})
        await safe_edit(q, "📋 Masukkan *deskripsi baru*:", kb_cancel_admin())
        return

    if d.startswith("adm_delask_"):
        pid  = int(d.split("_")[2])
        prod = get_product(pid)
        await safe_edit(q,
            f"⚠️ Yakin hapus produk *{prod[1]}*?\n\n"
            f"Semua stok ({prod[4]} item) juga ikut terhapus!",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ya, Hapus!", callback_data=f"adm_dodel_{pid}"),
                InlineKeyboardButton("❌ Batal",      callback_data="adm_panel"),
            ]]))
        return

    if d.startswith("adm_dodel_"):
        pid = int(d.split("_")[2])
        c   = db()
        c.execute("DELETE FROM stock_items WHERE product_id=?", (pid,))
        c.execute("DELETE FROM products WHERE id=?", (pid,))
        c.commit(); c.close()
        await safe_edit(q, "✅ Produk berhasil dihapus!", kb_back_admin())
        return

    # ── Kelola Media Start ────────────────────────────
    if d == "adm_photo_menu":
        await safe_edit(q, "🖼️ *Kelola Media Start*\nMedia ditampilkan saat pengguna /start:",
                        kb_photo_menu())
        return

    if d == "adm_media_del":
        set_setting("start_media_id", "")
        set_setting("start_media_type", "")
        await safe_edit(q, "✅ Media start berhasil dihapus!", kb_back_admin())
        return

    if d == "adm_media_photo":
        ctx.user_data["state"] = S_MEDIA_PHOTO
        await safe_edit(q, "🖼️ Kirim *foto* yang ingin dijadikan media start:",
                        kb_cancel_admin())
        return

    if d == "adm_media_video":
        ctx.user_data["state"] = S_MEDIA_VIDEO
        await safe_edit(q, "🎬 Kirim *video* yang ingin dijadikan media start:",
                        kb_cancel_admin())
        return

    # ── Broadcast Menu ────────────────────────────────
    if d == "adm_broadcast_menu":
        await safe_edit(q, "📢 *Broadcast*\n\nPilih jenis broadcast:", kb_broadcast_menu())
        return

    if d == "adm_bc_text":
        ctx.user_data["state"] = S_BC_TEXT
        await safe_edit(q,
            "📝 Kirim *pesan teks* yang ingin di-broadcast:\n"
            "_(Markdown didukung)_", kb_cancel_admin())
        return

    if d == "adm_bc_photo":
        ctx.user_data["state"] = S_BC_PHOTO
        await safe_edit(q,
            "🖼️ Kirim *foto* beserta caption (opsional) untuk di-broadcast:",
            kb_cancel_admin())
        return

    if d == "adm_bc_video":
        ctx.user_data["state"] = S_BC_VIDEO
        await safe_edit(q,
            "🎬 Kirim *video* beserta caption (opsional) untuk di-broadcast:",
            kb_cancel_admin())
        return

    # ── Statistik ─────────────────────────────────────
    if d == "adm_stats":
        prods, sales, users, rev, stock = get_stats()
        c = db()
        pending = c.execute("SELECT COUNT(*) FROM transactions WHERE status='pending'").fetchone()[0]
        expired = c.execute("SELECT COUNT(*) FROM transactions WHERE status='expired'").fetchone()[0]
        bypass  = c.execute("SELECT COUNT(*) FROM transactions WHERE status='bypass'").fetchone()[0]
        c.close()
        await safe_edit(q,
            f"📊 *STATISTIK TOKO*\n━━━━━━━━━━━━━━━━\n"
            f"📦 Total Produk: {prods}\n"
            f"🗃️ Total Stok Tersedia: {stock}\n"
            f"✅ Transaksi Berhasil: {sales}\n"
            f"🔓 Bypass Admin: {bypass}\n"
            f"⏳ Transaksi Pending: {pending}\n"
            f"❌ Transaksi Expired: {expired}\n"
            f"👥 Total Pengguna: {users}\n"
            f"💵 Total Pendapatan: {rp(rev)}\n"
            f"━━━━━━━━━━━━━━━━",
            kb_back_admin())
        return


# ══════════════════════════════════════════════
#         PROSES BUY (NORMAL + BYPASS)
# ══════════════════════════════════════════════
async def _process_buy(q, ctx, uid, pid, qty, bypass=False):
    prod = get_product(pid)
    if not prod:
        await q.answer("Produk tidak ditemukan!", show_alert=True)
        return
    pid_, name, price, desc, stok = prod

    if stok < qty:
        await q.answer(f"⚠️ Stok hanya {stok}!", show_alert=True)
        return

    username = q.from_user.username

    # ── BYPASS: langsung kirim tanpa bayar ───────────
    if bypass:
        items = take_stock(pid, qty)
        if not items:
            await q.message.reply_text("❌ Stok habis saat bypass!")
            return
        txid = f"BYPASS{uid}{int(datetime.now().timestamp())}"
        save_transaction(uid, username, txid, pid, qty, 0)
        update_transaction_status(txid, "bypass")
        for _, content in items:
            card = fmt_delivery_card(
                uid, username, name, price, qty, txid, content)
            await q.message.reply_text(card, parse_mode=ParseMode.MARKDOWN)
        return

    # ── NORMAL: buat QRIS ────────────────────────────
    loading = await q.message.reply_text("⏳ Membuat QRIS pembayaran...")
    pay = await create_qris(price * qty)
    if not pay:
        await loading.edit_text("❌ Gagal membuat QRIS. Coba lagi.")
        return

    txid     = pay["transaction_id"]
    qris_url = pay["qris_url"]
    fee      = pay["fee"]
    total    = pay["total_amount"]
    exp_min  = pay.get("expired_minutes", 5)

    save_transaction(uid, username, txid, pid, qty, total)
    await loading.delete()

    await q.message.reply_photo(
        photo=qris_url,
        caption=fmt_invoice(name, qty, price, fee, total, exp_min, txid),
        parse_mode=ParseMode.MARKDOWN)

    ctx.application.create_task(
        _poll_payment(ctx.application, uid, username, txid, pid, qty, name, price, EXPIRE_SEC))


async def _poll_payment(app, user_id, username, txid, pid, qty, prod_name, price, timeout):
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        if await check_qris(txid):
            update_transaction_status(txid, "paid")
            items = take_stock(pid, qty)
            if not items:
                await app.bot.send_message(
                    user_id,
                    "✅ Pembayaran berhasil!\n⚠️ Stok kosong, hubungi admin!",
                    parse_mode=ParseMode.MARKDOWN)
                return
            for _, content in items:
                card = fmt_delivery_card(
                    user_id, username, prod_name, price, qty, txid, content)
                await app.bot.send_message(
                    user_id, card, parse_mode=ParseMode.MARKDOWN)
            return
    update_transaction_status(txid, "expired")
    await app.bot.send_message(
        user_id, fmt_expired_msg(txid, prod_name),
        parse_mode=ParseMode.MARKDOWN)


# ══════════════════════════════════════════════
#     ADMIN MESSAGE HANDLER (text + photo + video)
# ══════════════════════════════════════════════
async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        return
    state = ctx.user_data.get("state")
    if not state:
        return

    msg = update.message

    # ── Tambah Produk ─────────────────────────────────
    if state == S_PROD_NAME:
        ctx.user_data.update({"state": S_PROD_PRICE, "p_name": msg.text})
        await msg.reply_text(
            f"✅ Nama: *{msg.text}*\n\n💰 Masukkan *harga* (contoh: `33780`):",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb_cancel_admin())
        return

    if state == S_PROD_PRICE:
        try:
            price = int(msg.text.replace(".", "").replace(",", ""))
            ctx.user_data.update({"state": S_PROD_DESC, "p_price": price})
            await msg.reply_text(
                f"✅ Harga: *{rp(price)}*\n\n📋 Masukkan *deskripsi produk*:",
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb_cancel_admin())
        except ValueError:
            await msg.reply_text(
                "❌ Harga harus angka! Contoh: `33780`",
                parse_mode=ParseMode.MARKDOWN)
        return

    if state == S_PROD_DESC:
        name  = ctx.user_data["p_name"]
        price = ctx.user_data["p_price"]
        c = db()
        c.execute("INSERT INTO products(name,description,price) VALUES(?,?,?)",
                  (name, msg.text, price))
        c.commit(); c.close()
        _clear(ctx)
        await msg.reply_text(
            f"✅ *Produk berhasil ditambahkan!*\n\n"
            f"*Nama:* {name}\n*Harga:* {rp(price)}\n"
            f"*Deskripsi:* {msg.text[:120]}{'...' if len(msg.text)>120 else ''}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin_main())
        return

    # ── Tambah Stok ───────────────────────────────────
    if state == S_STOCK_ITEMS:
        pid   = ctx.user_data["s_pid"]
        pname = ctx.user_data["s_name"]
        pprice= ctx.user_data["s_price"]
        items = [i.strip() for i in (msg.text or "").split("---") if i.strip()]
        if not items:
            await msg.reply_text(
                "⚠️ Tidak ada item! Pisahkan dengan `---`",
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb_cancel_admin())
            return
        c = db()
        for item in items:
            c.execute("INSERT INTO stock_items(product_id,content) VALUES(?,?)", (pid, item))
        c.commit(); c.close()
        prod = get_product(pid)
        _clear(ctx)
        await msg.reply_text(
            f"✅ *Berhasil tambah {len(items)} item stok* ke *{pname}*!\n"
            f"Stok sekarang: *{prod[4]}*",
            parse_mode=ParseMode.MARKDOWN)
        # Notifikasi stok baru ke semua user
        bot_info = await ctx.bot.get_me()
        notif    = fmt_stock_notif(pname, pprice, prod[4], bot_info.username)
        sent     = 0
        for u in all_user_ids():
            if u == uid: continue
            try:
                await ctx.bot.send_message(u, notif, parse_mode=ParseMode.MARKDOWN)
                sent += 1
                await asyncio.sleep(0.04)
            except Exception:
                pass
        await msg.reply_text(
            f"📢 Notifikasi stok terkirim ke *{sent}* pengguna.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin_main())
        return

    # ── Edit Nama ─────────────────────────────────────
    if state == S_EDIT_NAME:
        pid = ctx.user_data["edit_pid"]
        c = db(); c.execute("UPDATE products SET name=? WHERE id=?", (msg.text, pid)); c.commit(); c.close()
        _clear(ctx)
        await msg.reply_text(
            f"✅ Nama produk diubah ke *{msg.text}*!",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin_main())
        return

    # ── Edit Harga ────────────────────────────────────
    if state == S_EDIT_PRICE:
        try:
            price = int(msg.text.replace(".", "").replace(",", ""))
            pid   = ctx.user_data["edit_pid"]
            c = db(); c.execute("UPDATE products SET price=? WHERE id=?", (price, pid)); c.commit(); c.close()
            _clear(ctx)
            await msg.reply_text(
                f"✅ Harga diubah ke *{rp(price)}*!",
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb_admin_main())
        except ValueError:
            await msg.reply_text("❌ Harga harus angka!", reply_markup=kb_cancel_admin())
        return

    # ── Edit Deskripsi ────────────────────────────────
    if state == S_EDIT_DESC:
        pid = ctx.user_data["edit_pid"]
        c = db(); c.execute("UPDATE products SET description=? WHERE id=?", (msg.text, pid)); c.commit(); c.close()
        _clear(ctx)
        await msg.reply_text("✅ Deskripsi berhasil diperbarui!",
                             reply_markup=kb_admin_main())
        return

    # ── Upload Media Start: Foto ──────────────────────
    if state == S_MEDIA_PHOTO:
        if msg.photo:
            set_setting("start_media_id",   msg.photo[-1].file_id)
            set_setting("start_media_type", "photo")
            _clear(ctx)
            await msg.reply_text("✅ Foto start berhasil disimpan!", reply_markup=kb_admin_main())
        else:
            await msg.reply_text("⚠️ Kirim *foto* ya!", parse_mode=ParseMode.MARKDOWN)
        return

    # ── Upload Media Start: Video ─────────────────────
    if state == S_MEDIA_VIDEO:
        if msg.video:
            set_setting("start_media_id",   msg.video.file_id)
            set_setting("start_media_type", "video")
            _clear(ctx)
            await msg.reply_text("✅ Video start berhasil disimpan!", reply_markup=kb_admin_main())
        else:
            await msg.reply_text("⚠️ Kirim *video* ya!", parse_mode=ParseMode.MARKDOWN)
        return

    # ── Broadcast Teks ────────────────────────────────
    if state == S_BC_TEXT:
        text_bc = msg.text or ""
        if not text_bc:
            await msg.reply_text("⚠️ Pesan kosong!")
            return
        all_uids = all_user_ids()
        wait_msg = await msg.reply_text(f"📢 Mengirim ke {len(all_uids)} pengguna...")
        sent = 0
        for u in all_uids:
            try:
                await ctx.bot.send_message(u, text_bc, parse_mode=ParseMode.MARKDOWN)
                sent += 1
                await asyncio.sleep(0.04)
            except Exception:
                pass
        _clear(ctx)
        await wait_msg.edit_text(
            f"✅ Broadcast selesai! Terkirim ke *{sent}* pengguna.",
            parse_mode=ParseMode.MARKDOWN)
        await msg.reply_text("Kembali ke panel:", reply_markup=kb_admin_main())
        return

    # ── Broadcast Foto ────────────────────────────────
    if state == S_BC_PHOTO:
        if not msg.photo:
            await msg.reply_text("⚠️ Kirim *foto* ya!", parse_mode=ParseMode.MARKDOWN)
            return
        photo_id = msg.photo[-1].file_id
        caption  = msg.caption or ""
        all_uids = all_user_ids()
        wait_msg = await msg.reply_text(f"📢 Mengirim foto ke {len(all_uids)} pengguna...")
        sent = 0
        for u in all_uids:
            try:
                await ctx.bot.send_photo(u, photo=photo_id, caption=caption,
                                         parse_mode=ParseMode.MARKDOWN)
                sent += 1
                await asyncio.sleep(0.04)
            except Exception:
                pass
        _clear(ctx)
        await wait_msg.edit_text(
            f"✅ Broadcast foto selesai! Terkirim ke *{sent}* pengguna.",
            parse_mode=ParseMode.MARKDOWN)
        await msg.reply_text("Kembali ke panel:", reply_markup=kb_admin_main())
        return

    # ── Broadcast Video ───────────────────────────────
    if state == S_BC_VIDEO:
        if not msg.video:
            await msg.reply_text("⚠️ Kirim *video* ya!", parse_mode=ParseMode.MARKDOWN)
            return
        video_id = msg.video.file_id
        caption  = msg.caption or ""
        all_uids = all_user_ids()
        wait_msg = await msg.reply_text(f"📢 Mengirim video ke {len(all_uids)} pengguna...")
        sent = 0
        for u in all_uids:
            try:
                await ctx.bot.send_video(u, video=video_id, caption=caption,
                                         parse_mode=ParseMode.MARKDOWN)
                sent += 1
                await asyncio.sleep(0.04)
            except Exception:
                pass
        _clear(ctx)
        await wait_msg.edit_text(
            f"✅ Broadcast video selesai! Terkirim ke *{sent}* pengguna.",
            parse_mode=ParseMode.MARKDOWN)
        await msg.reply_text("Kembali ke panel:", reply_markup=kb_admin_main())
        return


# ══════════════════════════════════════════════
#                    MAIN
# ══════════════════════════════════════════════
def main():
    init_db()
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("=" * 55)
        print("⚠️  Isi BOT_TOKEN di environment atau langsung di bot.py!")
        print("   export BOT_TOKEN='token_dari_BotFather'")
        print("   export ADMIN_IDS='id_telegram_kamu'")
        print("=" * 55)
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
        message_handler))

    log.info("🤖 AUTOPAY BOT aktif!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
