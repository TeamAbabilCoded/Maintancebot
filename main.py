# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime
import pytz
from urllib.parse import quote

from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.utils.callback_data import CallbackData
from aiogram.types import ParseMode
from aiogram.types import Message
from utils.referral import cek_syarat_referral

import httpx
from config import BOT_TOKEN, ADMIN_ID

now_jakarta = datetime.now(pytz.timezone("Asia/Jakarta"))

# Import router notif
from routes.notif import router as notif_router

app = FastAPI()

# Register router notif tanpa prefix supaya endpoint /notif valid
app.include_router(notif_router)


API_BASE = "https://fluxion-fastapi.onrender.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

konfirmasi_cb = CallbackData("konfirmasi", "uid", "jumlah", "status")

# --- FSM States ---
class WithdrawState(StatesGroup):
    waiting_method = State()
    waiting_number = State()
    waiting_amount = State()

class VerifState(StatesGroup):
    waiting_input = State()

class KirimPoinState(StatesGroup):
    waiting_userid = State()
    waiting_jumlah = State()

# --- /start ---
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    uid = str(msg.from_user.id)
    username = msg.from_user.username or ""
    args = msg.get_args()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{API_BASE}/user/", json={"user_id": uid, "username": username})
            if response.status_code != 200:
                return await msg.answer("⚠️ Gagal menyimpan data user,,silahkan coba kembali /start.")
        except Exception as e:
            print("Exception saat POST /user:", e)
            return await msg.answer("⚠️ Gagal menyimpan data user,silahkan coba kembali /start.")

        if args and args != uid:
            try:
               response_ref = await client.post(f"{API_BASE}/referral", json={"user_id": uid, "ref_id": args})
               text_ref = await response_ref.text()
               print(f"POST /referral response: {response_ref.status_code} - {text_ref}")
            except Exception as e:
              print("Exception saat POST /referral:", e)
                # tidak perlu balas pesan ke user untuk referral error

    teks = (
        "👋 Selamat datang di *Fluxion Faucet!*\n\n"
        "📊 Kurs: *Rp350 - Rp700* per iklan\n"
        "💡 Cara dapat poin:\n"
        "- Tonton iklan\n"
        "- Klaim poin\n"
        "- Tarik ke DANA/OVO/Gopay\n\n"
        "Klik tombol di bawah untuk mulai:"
    )

    btn = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🚀 Mini App", web_app=WebAppInfo(url=f"https://miniapp-fluxion-faucet.vercel.app/?id={quote(uid)}")),
        InlineKeyboardButton("💰 Cek Saldo", callback_data="saldo"),
        InlineKeyboardButton("📜 Riwayat", callback_data="riwayat"),
        InlineKeyboardButton("💳 Tarik", callback_data="tarik"),
        InlineKeyboardButton("🧾 Verifikasi", callback_data="verifikasi"),
        InlineKeyboardButton("👥 Referral", callback_data="referral")
    )

    await msg.answer(teks, reply_markup=btn, parse_mode=ParseMode.MARKDOWN)

# --- Callback Handlers ---
@dp.callback_query_handler(lambda c: c.data == "saldo")
async def cek_saldo(cb: types.CallbackQuery):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/user/saldo/{cb.from_user.id}")
        saldo = r.json().get("saldo", 0)
    await cb.message.answer(f"💰 Saldo kamu: Rp {saldo} poin")

@dp.callback_query_handler(lambda c: c.data == "riwayat")
async def cek_riwayat(cb: types.CallbackQuery):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/user/riwayat/{cb.from_user.id}")
        riwayat = r.json().get("riwayat", [])
    if not riwayat:
        return await cb.message.answer("📭 Belum ada riwayat.")
    teks = "🕓 *Riwayat Terakhir:*\n"
    for i in riwayat[-10:]:
        teks += f"• {i['type']} +{i['amount']} ({i['time'].split('T')[0]})\n"
    await cb.message.answer(teks, parse_mode=ParseMode.MARKDOWN)

@dp.callback_query_handler(lambda c: c.data == "verifikasi")
async def mulai_verif(cb: types.CallbackQuery):
    await cb.message.answer("Silakan kirim data verifikasi kamu:")
    await VerifState.waiting_input.set()

@dp.message_handler(state=VerifState.waiting_input)
async def simpan_verif(msg: types.Message, state: FSMContext):
    async with httpx.AsyncClient() as client:
        await client.post(f"{API_BASE}/user/verifikasi", json={
            "user_id": str(msg.from_user.id),
            "input": msg.text
        })
    await msg.answer("✅ Verifikasi disimpan.")
    await state.finish()

# --- Withdraw flow ---
@dp.callback_query_handler(lambda c: c.data == "tarik")
async def pilih_metode(cb: types.CallbackQuery):
    btn = InlineKeyboardMarkup().add(
        InlineKeyboardButton("DANA", callback_data="metode_dana"),
        InlineKeyboardButton("OVO", callback_data="metode_ovo"),
        InlineKeyboardButton("GoPay", callback_data="metode_gopay")
    )
    await cb.message.answer("Pilih metode penarikan:", reply_markup=btn)
    await WithdrawState.waiting_method.set()
    await cb.answer()  # hilangkan loading spinner

@dp.callback_query_handler(lambda c: c.data.startswith("metode_"), state=WithdrawState.waiting_method)
async def proses_metode(cb: types.CallbackQuery, state: FSMContext):
    user_id = cb.from_user.id

    is_ok, jumlah, target = await cek_syarat_referral(user_id)
    if not is_ok:
        await cb.message.answer(
    f"🔔 *Informasi Aktivitas Referral Anda*\n\n"
    f"Terima kasih telah menggunakan layanan kami.\n\n"
    f"Saat ini, sistem mendeteksi bahwa dari total *{jumlah} referral* yang Anda undang, "
    f"belum memenuhi kriteria sebagai *referral aktif*.\n\n"
    f"Untuk melanjutkan proses penarikan saldo, silakan pastikan Anda telah mengundang minimal "
    f"*5 teman yang benar-benar aktif* menggunakan bot.\n\n"
    f"Langkah ini kami terapkan demi menjaga kualitas dan integritas sistem reward.\n\n"
    f"Apabila ada pertanyaan lebih lanjut, jangan ragu untuk menghubungi tim dukungan kami.\n\n"
    f"_Hormat kami,_\n"
    f"*Tim Fluxion Faucet*",
    parse_mode="Markdown"
        )
        await state.finish()
        await cb.answer()
        return

    metode = cb.data.split("_")[1].upper()  # hasil: DANA / OVO / GOPAY
    await state.update_data(metode=metode)
    await cb.message.answer(f"Masukkan nomor {metode} kamu:")
    await WithdrawState.waiting_number.set()
    await cb.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("metode_"), state=WithdrawState.waiting_method)
async def input_nomor(cb: types.CallbackQuery, state: FSMContext):
    metode = cb.data.split("_")[1]
    await state.update_data(metode=metode)
    await cb.message.answer("Masukkan nomor e-wallet:")
    await WithdrawState.waiting_number.set()

@dp.message_handler(state=WithdrawState.waiting_number)
async def input_jumlah(msg: types.Message, state: FSMContext):
    await state.update_data(nomor=msg.text)
    await msg.answer("Masukkan jumlah poin:")
    await WithdrawState.waiting_amount.set()

@dp.message_handler(state=WithdrawState.waiting_amount)
async def ajukan_tarik(msg: types.Message, state: FSMContext):
    uid = str(msg.from_user.id)
    try:
        jumlah = int(msg.text)
    except ValueError:
        await msg.answer("❌ Masukkan jumlah poin dalam angka.")
        return

    # ✅ Validasi minimum
    if jumlah < 100_000:
        await msg.answer("❌ Minimal penarikan adalah Rp100.000")
        return await state.finish()

    data = await state.get_data()

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/user/saldo/{uid}")
        saldo = r.json().get("saldo", 0)

        if saldo < jumlah:
            await msg.answer("❌ Saldo tidak cukup.")
            return await state.finish()

        await client.post(f"{API_BASE}/tarik/ajukan_tarik", json={
            "user_id": uid,
            "amount": jumlah,
            "metode": data["metode"],
            "nomor": data["nomor"]
        })

    await msg.answer("✅ Permintaan penarikan dikirim.")

    # Kirim ke admin dengan tombol ✅ ❌
    await bot.send_message(
    ADMIN_ID,
    f"🧾 Penarikan baru:\nUser: {uid}\nMetode: {data['metode']}\nNomor: {data['nomor']}\nJumlah: Rp {jumlah}",
    reply_markup=InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Terima", callback_data=konfirmasi_cb.new(uid=uid, jumlah=jumlah, status="terima")),
        InlineKeyboardButton("❌ Tolak", callback_data=konfirmasi_cb.new(uid=uid, jumlah=jumlah, status="tolak"))
    )
)

    await state.finish()

# --- tombol admin acc tarik ---
@dp.callback_query_handler(konfirmasi_cb.filter())
async def konfirmasi_penarikan(cb: types.CallbackQuery, callback_data: dict):
    uid = callback_data['uid']
    jumlah = int(callback_data['jumlah'])
    status = callback_data['status']  # "terima" atau "tolak"

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_BASE}/tarik/konfirmasi_tarik", json={
            "user_id": uid,
            "jumlah": jumlah,
            "status": "diterima" if status == "terima" else "ditolak"
        })

    if r.status_code == 200:
        await cb.message.edit_text(
            f"{'✅' if status == 'terima' else '❌'} Penarikan Rp {jumlah} dari {uid} telah dikonfirmasi.",
            parse_mode="Markdown"
        )
        # Notifikasi ke user (tambahan saja untuk jaga-jaga kalau backend gagal push)
        try:
            if status == "terima":
                await bot.send_message(int(uid), f"✅ Penarikan kamu sebesar Rp {jumlah} telah *DITERIMA*.")
            else:
                await bot.send_message(int(uid), f"❌ Penarikan kamu sebesar Rp {jumlah} *DITOLAK* oleh admin.")
        except Exception as e:
            print("Gagal kirim pesan ke user:", e)
    else:
        await cb.answer("❌ Gagal memproses permintaan.")

# --- Referral ---
@dp.callback_query_handler(lambda c: c.data == "referral")
async def referral(cb: types.CallbackQuery):
    uid = str(cb.from_user.id)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/referral/{uid}")
        data = r.json()
    jumlah = data.get("jumlah", 0)
    bot_user = await bot.get_me()
    link = f"https://t.me/{bot_user.username}?start={uid}"
    await cb.message.answer(f"🔗 Link Referral kamu:\n{link}\n👥 Total referral: {jumlah}")

# --- Admin Menu ---
@dp.message_handler(commands=["admin_menu"])
async def admin_menu(msg: types.Message):
    await admin_menu_target(msg.from_user.id, msg.answer)


async def admin_menu_target(user_id: int, reply_func):
    if user_id != ADMIN_ID:
        return await reply_func("❌ Akses ditolak.")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/user/statistik")
            data = r.json()
    except Exception as e:
        return await reply_func("⚠️ Gagal mengambil data statistik.")

    teks = (
        "📊 <b>Statistik:</b>\n"
        f"👤 Total User : <b>{data.get('total_user')}</b>\n"
        f"💰 Total Poin : <b>{data.get('total_poin')}</b>\n"
        f"💸 Total Penarikan : <b>{data.get('total_tarik')}</b>\n"
        f"📤 Penarikan Tertunda : <b>{data.get('pending_tarik')}</b>\n"
        f"✅ Terverifikasi : <b>{data.get('total_verifikasi')}</b>\n\n"
        f"<i>🕒 Terakhir diperbarui: {now_jakarta.strftime('%H:%M:%S')}</i>"
    )
    btn = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🎁 Kirim Poin", callback_data="kirim_poin"),
        InlineKeyboardButton("🔄 Refresh", callback_data="admin_menu"),
        InlineKeyboardButton("🔙 Kembali", callback_data="back_home")
    )
    await reply_func(teks, reply_markup=btn, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data == "admin_menu")
async def refresh_admin_menu(cb: types.CallbackQuery):
    await admin_menu_target(cb.from_user.id, cb.message.edit_text)


@dp.callback_query_handler(lambda c: c.data == "back_home")
async def back_to_home(cb: types.CallbackQuery):
    btn = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("📜 Riwayat", callback_data="riwayat"),
        InlineKeyboardButton("💼 Cek Saldo", callback_data="saldo")
    )
    await cb.message.edit_text("🏠 <b>Kembali ke Menu Utama</b>", reply_markup=btn, parse_mode="HTML")
    
@dp.callback_query_handler(lambda c: c.data == "kirim_poin")
async def kirim_poin(cb: types.CallbackQuery):
    await cb.message.answer("Masukkan user ID:")
    await KirimPoinState.waiting_userid.set()

	
@dp.message_handler(state=KirimPoinState.waiting_userid)
async def input_user(msg: types.Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())  # Pastikan user ID integer
    except ValueError:
        return await msg.reply("⚠️ User ID tidak valid. Harus berupa angka.")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_BASE}/user/{uid}")
    except Exception:
        btn = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Kembali", callback_data="admin_menu")
        )
        return await msg.reply("⚠️ Gagal menghubungi server. Coba lagi nanti.", reply_markup=btn)

    if resp.status_code != 200:
        btn = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Kembali", callback_data="admin_menu")
        )
        return await msg.reply("❌ User ID tidak ditemukan.", reply_markup=btn)

    await state.update_data(userid=uid)
    await msg.answer("Masukkan jumlah poin:")
    await KirimPoinState.waiting_jumlah.set()

@dp.message_handler(state=KirimPoinState.waiting_jumlah)
async def kirimkan_poin(msg: types.Message, state: FSMContext):
    try:
        jumlah = int(msg.text)
        if jumlah <= 0:
            raise ValueError("Jumlah harus lebih dari 0")
    except:
        return await msg.answer("❌ Jumlah poin harus berupa angka yang valid.")

    data = await state.get_data()
    uid = data["userid"]

    async with httpx.AsyncClient() as client:
        await client.post(f"{API_BASE}/poin/kirim_poin", json={"user_id": uid, "amount": jumlah})

    await msg.answer("✅ Poin dikirim.")
    try:
        await bot.send_message(int(uid), f"🎁 Kamu menerima bonus +{jumlah} poin!")
    except:
        pass

    await state.finish()

# === AUTO BROADCAST === #
async def auto_broadcast():
    db = SessionLocal()
    semua = db.query(User).all()
    pesan = "🚀 Selesaikan tugas hari ini di Fluxion Faucet dan raih bonus menarik 🎁. Jangan lewatkan kesempatanmu!"

    async with httpx.AsyncClient() as client:
        for u in semua:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    data={"chat_id": u.user_id, "text": pesan}
                )
            except:
                pass  # Gagal kirim = abaikan (opsional: bisa logging)

# === Jadwal 5x sehari === #
scheduler = AsyncIOScheduler()
scheduler.add_job(auto_broadcast, CronTrigger(hour=7, minute=0))   # Pagi
scheduler.add_job(auto_broadcast, CronTrigger(hour=10, minute=0))  # Menjelang siang
scheduler.add_job(auto_broadcast, CronTrigger(hour=13, minute=0))  # Siang
scheduler.add_job(auto_broadcast, CronTrigger(hour=17, minute=0))  # Sore
scheduler.add_job(auto_broadcast, CronTrigger(hour=20, minute=0))  # Malam


@dp.message_handler(commands=["approve"])
async def approve_user_cmd(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.reply("Kamu bukan admin.")
        return

    args = msg.text.split()
    if len(args) < 2:
        await msg.reply("Format salah. Contoh: /approve 123456789")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await msg.reply("User ID harus berupa angka. Contoh: /approve 123456789")
        return

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_BASE}/approve_user/{user_id}")
        if r.status_code == 200:
            await msg.reply(f"✅ User {user_id} berhasil di-approve.")
        else:
            try:
                detail = r.json().get('detail', 'Tidak diketahui')
            except Exception:
                detail = (r.text[:200] or 'Tidak diketahui')
            await msg.reply(f"⚠️ Gagal approve: {detail}")

# --- FastAPI Uvicorn Integration ---
async def main():
    from uvicorn import Config, Server
    config = Config(app=app, host="0.0.0.0", port=8000)
    server = Server(config)
    asyncio.create_task(server.serve())
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
