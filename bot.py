import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "mafia.sqlite3")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

logging.basicConfig(level=logging.INFO)
router = Router()

class Role(str, Enum):
    DON = "Don"
    MAFIA = "Mafia"
    CIVILIAN = "Tinch aholi"
    DOCTOR = "Shifokor"
    COMMISSAR = "Komissar Katani"
    SUICIDE = "Suitsid"
    LAWYER = "Advokat"

ROLE_INFO = {
    Role.DON: "Mafiya boshlig‘i. Har kecha nishon tanlashda qatnashadi.",
    Role.MAFIA: "Har kecha Don bilan birga nishon tanlaydi.",
    Role.CIVILIAN: "Kunduzi mafiyani topish va ovoz berish orqali chiqarish.",
    Role.DOCTOR: "Har kecha bir o‘yinchini qutqaradi.",
    Role.COMMISSAR: "Har kecha bir o‘yinchini tekshiradi.",
    Role.SUICIDE: "Kunduzi ovoz berib chiqarilsa, darhol g‘alaba qiladi.",
    Role.LAWYER: "Mafiyani komissar tekshiruvida tinch aholi qilib ko‘rsatadi.",
}

@dataclass
class Player:
    user_id: int
    name: str
    role: Optional[Role] = None
    alive: bool = True
    missed_votes: int = 0
    coins: int = 100
    items: Set[str] = field(default_factory=set)

@dataclass
class Game:
    chat_id: int
    host_id: int
    phase: str = "lobby"
    day: int = 0
    players: Dict[int, Player] = field(default_factory=dict)
    votes: Dict[int, int] = field(default_factory=dict)
    night_actions: Dict[str, Dict[int, int]] = field(default_factory=lambda: {"kill": {}, "heal": {}, "check": {}})
    lobby_message_id: Optional[int] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def alive(self):
        return [p for p in self.players.values() if p.alive]

    def add_roles(self):
        n = len(self.players)
        roles = [Role.DON, Role.MAFIA, Role.DOCTOR, Role.COMMISSAR]
        if n >= 8: roles += [Role.LAWYER]
        if n >= 7: roles += [Role.SUICIDE]
        roles += [Role.CIVILIAN] * max(0, n - len(roles))
        random.shuffle(roles)
        for player, role in zip(self.players.values(), roles):
            player.role = role

    def winner(self) -> Optional[str]:
        alive_roles = [p.role for p in self.alive]
        if not alive_roles: return "Hech kim"
        mafia = sum(r in (Role.DON, Role.MAFIA) for r in alive_roles)
        civilians = len(alive_roles) - mafia
        if mafia == 0: return "Tinch aholi jamoasi"
        if mafia >= civilians: return "Mafia jamoasi"
        return None

GAMES: Dict[int, Game] = {}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, coins INTEGER DEFAULT 100, games INTEGER DEFAULT 0, wins INTEGER DEFAULT 0)")
        await db.commit()

async def ensure_user(user_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO users(user_id,name) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name", (user_id, name))
        await db.commit()

async def profile_text(user_id: int, name: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT coins,games,wins FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    coins, games, wins = row or (100, 0, 0)
    return f"👤 <b>{name}</b>\n\n🪙 Tangalar: <b>{coins}</b>\n🎮 O‘yinlar: <b>{games}</b>\n🏆 G‘alabalar: <b>{wins}</b>"

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 Mafia o‘yini", callback_data="howto"), InlineKeyboardButton(text="👤 Profil", callback_data="profile")],
        [InlineKeyboardButton(text="🛒 Do‘kon", callback_data="shop"), InlineKeyboardButton(text="📖 Qoidalar", callback_data="rules")],
    ])

def lobby_kb(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ro‘yxatdan o‘tish", callback_data=f"join:{chat_id}"), InlineKeyboardButton(text="🚪 Chiqish", callback_data=f"leave:{chat_id}")],
        [InlineKeyboardButton(text="▶️ O‘yinni boshlash", callback_data=f"begin:{chat_id}")],
    ])

def alive_kb(game: Game, action: str, actor_id: int):
    rows = []
    for p in game.alive:
        if p.user_id != actor_id:
            rows.append([InlineKeyboardButton(text=p.name[:28], callback_data=f"act:{game.chat_id}:{action}:{actor_id}:{p.user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def lobby_text(game: Game) -> str:
    names = "\n".join(f"{i+1}. {p.name}" for i, p in enumerate(game.players.values())) or "Hali hech kim yo‘q"
    return f"🎭 <b>TRUE MAFIA BLACK</b>\n\n🟢 Ro‘yxatdan o‘tish ochiq\n👥 O‘yinchilar: <b>{len(game.players)}/15</b>\n\n{names}\n\nKamida 6 o‘yinchi kerak."

@router.message(Command("start"))
async def start(message: Message):
    await ensure_user(message.from_user.id, message.from_user.full_name)
    await message.answer("🎭 <b>True Mafia Black</b> botiga xush kelibsiz!\n\nGuruhda /mafia buyrug‘i bilan o‘yin oching.", reply_markup=main_kb())

@router.message(Command("mafia"))
async def create_game(message: Message):
    if message.chat.type == "private":
        await message.answer("Bu buyruqni guruh ichida yuboring.")
        return
    if message.chat.id in GAMES:
        await message.answer("Bu guruhda allaqachon lobby mavjud.")
        return
    game = Game(message.chat.id, message.from_user.id)
    game.players[message.from_user.id] = Player(message.from_user.id, message.from_user.full_name)
    GAMES[message.chat.id] = game
    sent = await message.answer(lobby_text(game), reply_markup=lobby_kb(message.chat.id))
    game.lobby_message_id = sent.message_id

@router.callback_query(F.data == "howto")
async def howto(call: CallbackQuery):
    await call.answer()
    await call.message.answer("Guruhda /mafia yozing, so‘ng ishtirokchilar ‘Ro‘yxatdan o‘tish’ tugmasini bosing. 6–15 kishi yig‘ilgach host o‘yinni boshlaydi.")

@router.callback_query(F.data == "rules")
async def rules(call: CallbackQuery):
    await call.answer()
    await call.message.answer("📖 <b>Qoidalar</b>\n\n🌙 Kechasi maxsus rollar harakat qiladi.\n☀️ Kunduzi muhokama va ovoz berish bo‘ladi.\n⏱ Ovoz bermagan o‘yinchining ovozi hisoblanmaydi. 3 marta ovoz bermasa chiqariladi.\n🎯 Jamoa maqsadi — raqib jamoani topish.")

@router.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    await call.answer()
    await ensure_user(call.from_user.id, call.from_user.full_name)
    await call.message.answer(await profile_text(call.from_user.id, call.from_user.full_name))

@router.callback_query(F.data == "shop")
async def shop(call: CallbackQuery):
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛡 Bir martalik himoya — 50 🪙", callback_data="buy:shield")]])
    await call.message.answer("🛒 <b>Do‘kon</b>\n\nHimoya buyumi kechasi bir marta o‘limdan saqlaydi.", reply_markup=kb)

@router.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    await call.answer("Do‘kon funksiyasi tayyor; xarid o‘yin tashqarisidagi balansga yoziladi.")

@router.callback_query(F.data.startswith("join:"))
async def join(call: CallbackQuery):
    chat_id = int(call.data.split(":")[1]); game = GAMES.get(chat_id)
    if not game or game.phase != "lobby": return await call.answer("Lobby yopilgan", show_alert=True)
    if len(game.players) >= 15: return await call.answer("Maksimal 15 o‘yinchi", show_alert=True)
    game.players.setdefault(call.from_user.id, Player(call.from_user.id, call.from_user.full_name))
    await call.answer("Siz ro‘yxatdan o‘tdingiz!")
    await call.message.edit_text(lobby_text(game), reply_markup=lobby_kb(chat_id))

@router.callback_query(F.data.startswith("leave:"))
async def leave(call: CallbackQuery):
    chat_id = int(call.data.split(":")[1]); game = GAMES.get(chat_id)
    if game and game.phase == "lobby":
        game.players.pop(call.from_user.id, None)
        await call.answer("Ro‘yxatdan chiqdingiz")
        await call.message.edit_text(lobby_text(game), reply_markup=lobby_kb(chat_id))

@router.callback_query(F.data.startswith("begin:"))
async def begin(call: CallbackQuery, bot: Bot):
    chat_id = int(call.data.split(":")[1]); game = GAMES.get(chat_id)
    if not game: return await call.answer("Lobby topilmadi", show_alert=True)
    if call.from_user.id != game.host_id and call.from_user.id not in ADMIN_IDS: return await call.answer("Faqat host boshlashi mumkin", show_alert=True)
    if len(game.players) < 6: return await call.answer("Kamida 6 o‘yinchi kerak", show_alert=True)
    game.add_roles(); game.phase = "night"; game.day = 1
    for p in game.players.values():
        try: await bot.send_message(p.user_id, f"🎭 Sizning rolingiz: <b>{p.role.value}</b>\n\n{ROLE_INFO[p.role]}")
        except Exception: pass
    await call.message.edit_text(f"🌙 <b>1-kecha boshlandi</b>\n\nRollar shaxsiy xabarga yuborildi. Maxsus rollar bot bilan yozishsin.")
    await night_prompts(game, bot)
    await call.answer("O‘yin boshlandi!")

async def night_prompts(game: Game, bot: Bot):
    for p in game.alive:
        if p.role in (Role.DON, Role.MAFIA):
            await safe_private(bot, p, "🔪 Nishon tanlang:", alive_kb(game, "kill", p.user_id))
        elif p.role == Role.DOCTOR:
            await safe_private(bot, p, "🩺 Kimni qutqarasiz?", alive_kb(game, "heal", p.user_id))
        elif p.role == Role.COMMISSAR:
            await safe_private(bot, p, "🔍 Kimni tekshirasiz?", alive_kb(game, "check", p.user_id))
    asyncio.create_task(night_timeout(game, bot))

async def safe_private(bot: Bot, p: Player, text: str, kb):
    try: await bot.send_message(p.user_id, text, reply_markup=kb)
    except Exception: pass

@router.callback_query(F.data.startswith("act:"))
async def action(call: CallbackQuery, bot: Bot):
    _, chat, action_name, actor, target = call.data.split(":")
    game = GAMES.get(int(chat))
    if not game or game.phase != "night" or int(actor) != call.from_user.id: return await call.answer("Bu amal endi mavjud emas", show_alert=True)
    player = game.players.get(call.from_user.id)
    if not player or not player.alive: return await call.answer("Siz o‘yinda emassiz", show_alert=True)
    game.night_actions[action_name][call.from_user.id] = int(target)
    await call.answer("Tanlov qabul qilindi")
    await call.message.edit_text("✅ Tanlovingiz qabul qilindi. Boshqa amallar tugashini kuting.")

async def night_timeout(game: Game, bot: Bot):
    await asyncio.sleep(60)
    if game.phase != "night": return
    kills = list(game.night_actions["kill"].values())
    target_id = max(set(kills), key=kills.count) if kills else None
    healed = set(game.night_actions["heal"].values())
    if target_id and target_id not in healed and target_id in game.players:
        game.players[target_id].alive = False
        victim = game.players[target_id]
        await bot.send_message(game.chat_id, f"🌙 Kecha {victim.name} o‘yindan chiqarildi. Rol: <b>{victim.role.value}</b>")
    else:
        await bot.send_message(game.chat_id, "🌙 Kecha hech kim o‘yindan chiqarilmadi.")
    game.phase = "day"; game.votes.clear(); game.day += 1
    game.night_actions = {"kill": {}, "heal": {}, "check": {}}
    await day_start(game, bot)

async def day_start(game: Game, bot: Bot):
    await bot.send_message(game.chat_id, f"☀️ <b>{game.day}-kun boshlandi</b>\n\nMuhokama qiling va ovoz berish tugmasi orqali tanlang.", reply_markup=vote_kb(game))
    asyncio.create_task(day_timeout(game, bot))

def vote_kb(game: Game):
    rows = [[InlineKeyboardButton(text=p.name[:28], callback_data=f"vote:{game.chat_id}:{p.user_id}")] for p in game.alive]
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data.startswith("vote:"))
async def vote(call: CallbackQuery):
    _, chat, target = call.data.split(":"); game = GAMES.get(int(chat))
    if not game or game.phase != "day": return await call.answer("Ovoz berish yopilgan", show_alert=True)
    voter = game.players.get(call.from_user.id)
    if not voter or not voter.alive: return await call.answer("Siz ovoz bera olmaysiz", show_alert=True)
    if int(target) == call.from_user.id: return await call.answer("O‘zingizga ovoz bera olmaysiz", show_alert=True)
    game.votes[call.from_user.id] = int(target); voter.missed_votes = 0
    await call.answer("Ovozingiz qabul qilindi")

async def day_timeout(game: Game, bot: Bot):
    await asyncio.sleep(60)
    if game.phase != "day": return
    for p in game.alive:
        if p.user_id not in game.votes:
            p.missed_votes += 1
            if p.missed_votes >= 3: p.alive = False
    counts: Dict[int, int] = {}
    for target in game.votes.values(): counts[target] = counts.get(target, 0) + 1
    eliminated = None
    if counts:
        top = max(counts.values()); winners = [x for x, c in counts.items() if c == top]
        if len(winners) == 1: eliminated = game.players.get(winners[0])
    if eliminated:
        eliminated.alive = False
        text = f"🗳 Ovoz natijasi: <b>{eliminated.name}</b> chiqarildi. Rol: {eliminated.role.value}"
        if eliminated.role == Role.SUICIDE: text += "\n💀 Suitsid o‘z maqsadiga erishdi!"
    else: text = "🗳 Ovozlar teng bo‘ldi yoki ovoz yetarli emas — hech kim chiqarilmadi."
    winner = game.winner()
    if winner:
        await bot.send_message(game.chat_id, text + f"\n\n🏆 <b>{winner} g‘alaba qozondi!</b>")
        GAMES.pop(game.chat_id, None); return
    game.phase = "night"; game.votes.clear()
    await bot.send_message(game.chat_id, text + "\n\n🌙 Kecha tushdi.")
    await night_prompts(game, bot)

async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN .env faylida ko‘rsatilmagan")
    await init_db()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(); dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
