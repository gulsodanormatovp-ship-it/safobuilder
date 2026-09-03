# SafoBuilder Clone — Telegram Bot Builder Platform

To'liq funksiyali Telegram bot yaratish platformasi: foydalanuvchilar o'z bot tokenini
kiritib, tayyor shablonlardan (Kino, Pul, Taxi, Anketa, VipKanal, Aloqa, Konkurs,
Nakrutka, OpenBudget, Kafe POS) bitta tugma bosish bilan ishlaydigan bot oladi.
Boshqaruv ham Telegram bot ichidan, ham Mini App (Telegram Web App) orqali.

## Arxitektura

```
safobuilder/
├── bot/                 # Asosiy "SafoBuilder" platforma boti (aiogram)
│   ├── main.py          # Bot ishga tushirish nuqtasi
│   ├── keyboards.py     # Barcha reply/inline klaviaturalar
│   ├── handlers/        # /start, bot yaratish, mening botlarim, to'lov, profil...
│   └── child_bots/      # Har bir bot turi uchun mantiq (Kino, Taxi, Anketa...)
├── api/
│   └── main.py          # FastAPI: webhook qabul qiluvchi + Mini App uchun REST API
├── webapp/              # Telegram Mini App (bitta HTML/JS, ikkala rejimda ishlaydi:
│   │                       admin panel VA child-bot foydalanuvchi interfeysi)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── database/
│   ├── models.py        # SQLAlchemy modellar
│   └── db.py            # Session/engine sozlamalari
├── requirements.txt
└── .env.example
```

## Qanday ishlaydi

1. **Platforma boti** (`bot/main.py`) — SafoBuilder'dagi kabi menyu: Bot yaratish,
   Botlarim, Referal, Shaxsiy kabinet, Hisob to'ldirish, Murojaat, Qo'llanma.
2. **Bot yaratish**: foydalanuvchi turini tanlaydi → narxni ko'radi → BotFather'dan
   olingan tokenini yuboradi → tizim shu tokenga webhook o'rnatadi
   (`setWebhook` → `https://api.sizning-domen.uz/webhook/{bot_id}`).
3. **Runtime router** (`api/main.py`): har bir kelgan update `bot_id` bo'yicha
   qaysi child-bot turiga tegishli ekanini DB'dan topadi va mos handlerga
   (`bot/child_bots/*.py`) uzatadi. Shu tufayli 1 ta server 1000 ta child botni
   bitta webhook orqali boshqaradi — har biriga alohida process kerak emas.
4. **To'lov**: avtomatik (Click/Payme/Paynet — kelajakda API bilan ulanadi) va
   **manual** (Karta/chek) rejimlari bor. Manual rejimda foydalanuvchi chek rasmini
   yuboradi → admin guruhiga inline "✅ Tasdiqlash / ❌ Rad etish" tugmasi bilan
   boradi → tasdiqlansa balans avtomatik to'ldiriladi (`bot/handlers/payment.py`).
5. **Mini App**: bitta `webapp/index.html` ikki rejimda ishlaydi —
   `?mode=admin&bot_id=..` bo'lsa boshqaruv paneli (statistika, sozlamalar),
   `?mode=user&bot_id=..` bo'lsa o'sha bot turiga mos foydalanuvchi interfeysi
   (masalan Taxi Bot uchun xarita, Kafe POS uchun buyurtma ekrani).

## Ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN, DATABASE_URL, ADMIN_CHAT_ID to'ldiring
python -m bot.main      # platforma botini poll rejimida ishga tushiradi (dev uchun)
uvicorn api.main:app --reload --port 8000   # webhook + Mini App API
```

Production'da child botlar uchun `webhook`, platforma boti uchun ham webhook
tavsiya qilinadi (bitta domen, ikkita path).

## Hozir to'liq ishlangan bot turlari

- ✅ Kino Bot — kod orqali kino yuklash/olish
- ✅ Taxi Bot — buyurtma qabul qilish, haydovchiga tarqatish
- ✅ Anketa Bot — savol-javob, natijalarni eksport qilish

Qolgan 7 ta tur (Pul, OpenBudget, VipKanal, Aloqa, Kafe POS, Nakrutka, Konkurs)
uchun `bot/child_bots/base.py`dagi `ChildBot` klassidan meros olib, xuddi
`kino_bot.py` namunasidagi kabi 15-30 daqiqada qo'shish mumkin — pastda
"Yangi bot turi qo'shish" bo'limida qadamma-qadam ko'rsatilgan.

## Yangi bot turi qo'shish (masalan Pul Bot)

1. `bot/child_bots/pul_bot.py` yarating, `ChildBot`dan meros oling.
2. `handle_message`, `handle_callback` metodlarini yozing.
3. `bot/child_bots/__init__.py`dagi `BOT_TYPE_REGISTRY` ga qo'shing.
4. `bot/handlers/create_bot.py`dagi `BOT_TYPES` ro'yxatiga narx/tavsif qo'shing.
5. Kerak bo'lsa `webapp/`ga shu tur uchun alohida ekran (`renderPulBot()`) qo'shing.

Shunday qilib butun tizim bitta kodni o'zgartirmasdan yangi bot turlarini
qabul qiladi — bu SafoBuilder'ning ichki arxitekturasiga o'xshash yondashuv.
