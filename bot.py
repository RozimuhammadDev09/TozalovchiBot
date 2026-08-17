# cleaner_bot.py
import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.utils.exceptions import (
    BotBlocked,
    ChatNotFound,
    MessageCantBeDeleted,
    MessageToDeleteNotFound,
    RetryAfter,
    Unauthorized,
)
from dotenv import load_dotenv

from keywords import KEYWORDS

# ---------------- CONFIG ----------------
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi! Railway/serverda muhit o'zgaruvchisi sifatida "
        "BOT_TOKEN ni o'rnating (yoki lokal test uchun .env fayl yarating)."
    )

# Bu ID'lardagi foydalanuvchilarning xabarlari HECH QACHON o'chirilmaydi
# (masalan, guruh adminlari). Railway'da ADMIN_IDS=123456,789012 kabi
# vergul bilan ajratib bering.
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}

# Qo'shimcha "signal" asosidagi aniqlashni yoqish/o'chirish (pastga qarang).
# Standart: yoqilgan. O'chirish uchun ENABLE_HEURISTICS=0 qiling.
ENABLE_HEURISTICS = os.getenv("ENABLE_HEURISTICS", "1") == "1"

# ---- LOGGING ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---- Kalit so'zlar regexi (aniq mos kelish) ----
KEYWORDS_LOWER = list({k.lower() for k in KEYWORDS})
KEYWORD_PATTERN = re.compile(
    "|".join(re.escape(k) for k in KEYWORDS_LOWER), re.IGNORECASE
)

# ---- Qo'shimcha spam signallari ----
# Har qanday telefon raqami (faqat aniq raqamlarni ro'yxatlashtirib
# o'tirmasdan, umumiy naqsh orqali)
PHONE_PATTERN = re.compile(r"(?:\+?\d[\s\-]?){9,13}")
# t.me havolasi yoki @username tilga olinishi (kontakt/reklama belgisi)
TELEGRAM_LINK_PATTERN = re.compile(r"(t\.me/|telegram\.me/|@[a-zA-Z0-9_]{5,32}\b)")
# Ketma-ket 4 tadan ortiq emoji (reklama postlariga xos bezak)
MANY_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]{4,}"
)
# http(s) havola
URL_PATTERN = re.compile(r"https?://\S+")

bot = Bot(token=TOKEN, parse_mode=None)
dp = Dispatcher(bot)


def get_text(message: types.Message) -> str:
    """Oddiy matn, caption yoki forward xabarlardan matnni oladi."""
    return (message.text or message.caption or "").strip()


def is_spam(text: str) -> bool:
    if not text:
        return False

    lowered = text.lower()

    # 1) Aniq qora ro'yxatdagi ibora topilsa — darhol spam
    if KEYWORD_PATTERN.search(lowered):
        return True

    if not ENABLE_HEURISTICS:
        return False

    # 2) Bir nechta "shubhali signal" birga kelsa ham spam deb hisoblanadi.
    #    Faqat bitta signal (masalan, oddiy telefon raqami) yetarli emas —
    #    bu haqiqiy foydalanuvchi xabarlarini bekorga o'chirib yubormaslik uchun.
    signals = 0
    if PHONE_PATTERN.search(text):
        signals += 1
    if TELEGRAM_LINK_PATTERN.search(lowered):
        signals += 1
    if MANY_EMOJI_PATTERN.search(text):
        signals += 1
    if URL_PATTERN.search(lowered):
        signals += 1

    return signals >= 2


async def try_delete(message: types.Message, attempt: int = 0) -> None:
    try:
        await message.delete()
        logger.info(f"O'chirildi: chat={message.chat.id} user={message.from_user.id}")
    except MessageToDeleteNotFound:
        pass  # xabar allaqachon o'chirilgan
    except MessageCantBeDeleted:
        logger.error(
            f"Xabarni o'chirib bo'lmadi (huquq yo'q). Chat: {message.chat.id}. "
            "Botni guruhda ADMIN qilib, 'Delete messages' huquqini bering."
        )
    except RetryAfter as e:
        if attempt < 3:
            await asyncio.sleep(e.timeout)
            await try_delete(message, attempt + 1)
    except (Unauthorized, BotBlocked, ChatNotFound):
        logger.error("Bot guruhdan chiqarilgan/bloklangan yoki chat topilmadi.")
    except Exception as e:
        logger.error(f"Xabar o'chirilmadi! Sabab: {e}")


async def process(message: types.Message) -> None:
    # Faqat guruh/superguruhlarda ishlasin
    if message.chat.type not in ("group", "supergroup"):
        return

    # Adminlarni tegmaymiz
    if message.from_user and message.from_user.id in ADMIN_IDS:
        return

    text = get_text(message)
    if is_spam(text):
        await try_delete(message)


@dp.message_handler(content_types=types.ContentTypes.ANY)
async def cleaner(message: types.Message):
    await process(message)


@dp.edited_message_handler(content_types=types.ContentTypes.ANY)
async def cleaner_edited(message: types.Message):
    # Ko'plab spamerlar xabarni yuborgandan keyin tahrirlab, reklama matnini
    # qo'shishadi — buni ham tekshiramiz.
    await process(message)


async def on_startup(_):
    logger.info("Bot ishga tushdi va guruhlarni tozalashga tayyor.")


if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,  # eski xabarlarni o'qimaydi -> tezroq ishga tushadi
        on_startup=on_startup,
    )