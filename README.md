# True Mafia Black — Telegram bot

Videodagi uslubga yaqin, original Telegram Mafia bot skeleti. Kod botning ko‘rinadigan menyulari, guruhda lobby, rollarni maxfiy tarqatish, kecha/kunduz, ovoz berish, ovoz bermaganlarni hisobga olmaslik, jarimalar, profil va do‘konni o‘z ichiga oladi.

> Video source-code ko‘rsatmaganligi sababli bu loyiha videodagi aynan original kod emas, balki uning funksional qayta yaratilgan varianti.

## Ishga tushirish

```bash
cd /home/ubuntu/mafia_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env ichiga BotFather tokenini yozing
python bot.py
```

Botni guruhga admin qilib qo‘shing. `/start` — shaxsiy chatda, `/mafia` — guruhda lobby ochadi.

## O‘yin qoidalari

- 6–15 o‘yinchi qo‘llab-quvvatlanadi.
- Don/Mafia mafiyani himoya qiladi va tinch aholini yo‘q qiladi.
- Shifokor kechasi bir kishini qutqaradi.
- Komissar tekshiruv oladi.
- Suitsid ovoz berishda chiqarilsa yutadi.
- Advokat mafiyani tekshiruvda tinch aholi qilib ko‘rsatadi.
- Ovoz bermaganlar ovozga ega bo‘lmaydi; ketma-ket 3 marta ovoz bermasa chiqariladi.
- O‘yin faqat guruhda ishlaydi, rollar esa shaxsiy xabarda beriladi.
