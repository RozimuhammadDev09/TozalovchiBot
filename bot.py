# cleaner_bot.py
import asyncio
import logging
import re
import unicodedata

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from keywords import KEYWORDS

# ---------------- CONFIG ----------------
TOKEN = "8657353210:AAFo831iUZEmxTtC7yrep-QKgiaCy2M0vJw"

# ---- Admin ID'lar ----
# Shu ID'dagi odamlar xabarida kalit so'z bo'lsa ham o'chirilmaydi.
# Yangi admin qo'shish uchun shu ro'yxatga ID sonini qo'shib qo'ying (vergul bilan).
ADMIN_IDS = {
    6302873072,
}

# ---- Kalit so'zlar endi keywords.py faylidan olinadi ----


# ---------------- MATN NORMALLASHTIRISH ----------------
# Bu qism kalit so'z bor xabarlarning "ko'rinmas" sabablarga ko'ra
# o'chirilmay qolishining oldini oladi:
#  - turli xil apostrof/tirnoqcha belgilari (o'zbek tilida ko'p uchraydi)
#  - ortiqcha yoki bir nechta bo'sh joylar
#  - unicode shakl farqlari (masalan, keng/tor harflar)
#  - ko'rinmas (zero-width) belgilar orqali filtrni "aldash"

# Apostrofga o'xshash barcha belgilarni bitta ko'rinishga keltiramiz
_APOSTROPHE_VARIANTS = "'\u2019\u2018`\u00b4\u02bb\u02bc\u201b\u2032"
_APOSTROPHE_MAP = str.maketrans({ch: "'" for ch in _APOSTROPHE_VARIANTS})

# Ko'rinmas / nol-kenglikdagi belgilar (spamerlar so'zni buzish uchun ishlatadi)
_ZERO_WIDTH_RE = re.compile(
    "[\u200b\u200c\u200d\u200e\u200f\ufeff\u2060]"
)

# Ketma-ket bo'sh joylarni bittaga tushiramiz
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    if not s:
        return ""
    # Unicode formalarini bir xillashtirish (masalan, keng/tor belgilar)
    s = unicodedata.normalize("NFKC", s)
    # Ko'rinmas belgilarni olib tashlash
    s = _ZERO_WIDTH_RE.sub("", s)
    # Apostrof turlarini bittalashtirish
    s = s.translate(_APOSTROPHE_MAP)
    # Katta-kichik harflarni bir xillashtirish (ko'p tilli matn uchun casefold)
    s = s.casefold()
    # Ketma-ket bo'sh joylarni bittaga tushirish va chetlarini kesish
    s = _MULTI_SPACE_RE.sub(" ", s).strip()
    return s


# ---- Kalit so'zlarni ham xuddi shu qoidalar bilan normallashtiramiz ----
NORMALIZED_KEYWORDS = sorted(
    {normalize_text(k) for k in KEYWORDS if normalize_text(k)},
    key=len,
    reverse=True,  # uzunroq iboralar birinchi tekshirilsin
)

# ---- REGEX pattern (bitta marta compile qilinadi -> juda tez ishlaydi) ----
REGEX_PATTERN = re.compile(
    "|".join(re.escape(k) for k in NORMALIZED_KEYWORDS)
)

# ---- LOGGING ----
logging.basicConfig(
    level=logging.ERROR,  # faqat xatolar chiqsin
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------- START BOT ----------------
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)


def contains_keyword(raw_text: str) -> bool:
    if not raw_text:
        return False
    return REGEX_PATTERN.search(normalize_text(raw_text)) is not None


async def process_message(message: types.Message):
    # Faqat guruh/superguruhlarda ishlasin
    if message.chat.type not in ("group", "supergroup"):
        return

    # Adminlar yozgan xabarlarda kalit so'z bo'lsa ham o'chirilmasin
    if message.from_user and message.from_user.id in ADMIN_IDS:
        return

    # Oddiy matn yoki rasm/video ostidagi izoh (caption) - ikkalasi ham tekshiriladi
    text_to_check = message.text or message.caption or ""

    if contains_keyword(text_to_check):
        try:
            await message.delete()
        except Exception as e:
            # Faqat bitta ERROR log bo'ladi, Railwayni portlatmaydi
            logger.error(f"Xabar o'chirilmadi! Sabab: {e}")


# Oddiy yuborilgan xabarlar (matn, rasm/video/fayl caption'lari bilan)
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def cleaner(message: types.Message):
    await process_message(message)


# Tahrirlangan xabarlar ham tekshirilsin
# (kimdir xabarni yozib, keyin tahrirlab kalit so'z qo'shishi mumkin)
@dp.edited_message_handler(content_types=types.ContentTypes.ANY)
async def cleaner_edited(message: types.Message):
    await process_message(message)


async def on_startup(_):
    # hech qanday print/log yo'q -> Railway safe
    pass


if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,   # eski xabarlarni o'qimaydi -> log kam
        on_startup=on_startup,
    )