import discord
from discord.ext import commands, tasks
from flask import Flask
import threading
import os
import asyncio
import aiohttp
import re
import unicodedata
from datetime import timedelta, datetime
from discord.utils import utcnow
from difflib import SequenceMatcher

# --- Flask Keep-Alive ---
app = Flask(__name__)
bot_name = "Loading..."

@app.route("/")
def home():
    return f"Bot {bot_name} is operational"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- Discord Bot Setup ---
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Missing DISCORD_BOT_TOKEN in environment variables")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

session = None

# --- Warning Trackers ---
link_warnings = {}
badword_warnings = {}

last_link_time = {}
last_badword_time = {}

# --- قائمة الكلمات المسيئة ---
BAD_WORDS = [
    "fuck", "7mar","shit","bitch","asshole","bastard","dick","douche","cunt","fag","slut","قلوة","ختك","سوتيان","خرى","خرية","106",
    "whore","prick","motherfucker","nigger","cock","pussy","twat","jerk","idiot","سوة","سوى","سخون","سليب","منوي","حواي",
    "9LAWI","9lawi","zok","zb","MOK","moron","dumbass","nik","nik mok","9A7BA","الطبون","طبون","زبور","الزبور",
    "no9ch","نقش","lkelb", "الكلب", "الحمار", "zaml","كلب","نيك","نيك مك","كس","mok","نيك يماك","قحبة","ولد القحبة","حتشون",
    "ابن الكلب","حمار","غبي","قذر","حقير","كافر","زب","زبي","قلاوي","زك","نحويك","زامل","طيز",
    "الزك","نكمك","عطاي","حيوان","منيوك","خنزير","خائن","متسكع","أرعن","شكوبي",
    "حقيرة","لعينة","مشين","زانية","أوغاد","أهبل","لعين","منيك","ترمة",
    "مترم","بقرة","شرموطة","الشرموطة","العاهرة","قليل الأدب","ابن الشرموطة","غيول",
    "كس أمك","كس أختك","ابن القحبة","ابن الزانية","ابن العاهرة","ابن الحرام","ابن الزنا"
]

# --- قائمة الكلمات المسموحة (Whitelist) ---
ALLOWED_WORDS = ["ok","اك", "اوكي", "yes", "تمام", "نعم"]

# --- خريطة الحروف العربية/إنجليزية للكلمات المختلطة ---
MIXED_MAP = {
    "a": "ا", "A": "ا",
    "b": "ب", "B": "ب",
    "t": "ت", "T": "ت",
    "th": "ث", "TH": "ث",
    "j": "ج", "J": "ج",
    "h": "ح", "H": "ح",
    "kh": "خ", "KH": "خ",
    "d": "د", "D": "د",
    "dh": "ذ", "DH": "ذ",
    "r": "ر", "R": "ر",
    "z": "ز", "Z": "ز",
    "s": "س", "S": "س",
    "sh": "ش", "SH": "ش",
    "S": "ص", "s": "ص",
    "D": "ض", "d": "ض",
    "T": "ط", "t": "ط",
    "Z": "ظ", "z": "ظ",
    "e": "ع", "E": "ع",
    "gh": "غ", "GH": "غ",
    "f": "ف", "F": "ف",
    "q": "ق", "Q": "ق",
    "k": "ك", "K": "ك",
    "l": "ل", "L": "ل",
    "m": "م", "M": "م",
    "n": "ن", "N": "ن",
    "h": "ه", "H": "ه",
    "w": "و", "W": "و",
    "y": "ي", "Y": "ي",
    "i": "ي", "I": "ي",
    "o": "و", "O": "و",
    "4": "ا", "3": "ع", "7": "ح", "5": "خ", "2": "ء", "9": "ق", "0": "و", "$": "س", "@": "ا"
}

# --- Normalize text ---
REPLACEMENTS = {
    "@":"a","4":"a","à":"a","á":"a","â":"a","ä":"a","å":"a","ª":"a",
    "8":"b","ß":"b",
    "(":"c","¢":"c","©":"c","ç":"c",
    "3":"e","€":"e","&":"e","ë":"e","è":"e","é":"e","ê":"e",
    "6":"g","9":"g",
    "#":"h",
    "!":"i","1":"i","¡":"i","|":"i","í":"i","î":"i","ï":"i","ì":"i",
    "£":"l","¬":"l",
    "0":"o","ò":"o","ó":"o","ô":"o","ö":"o","ø":"o","¤":"o",
    "$":"s","5":"s","§":"s","š":"s",
    "7":"t","+":"t","†":"t",
    "2":"z","¥":"y",
    "¶":"p",
    "*":"","^":"","~":"","`":"","?":"","!":"","-":"","=":"",",":"",".":""
}

def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("ـ", "")
    for k, v in MIXED_MAP.items():
        text = text.replace(k, v)
    for k, v in REPLACEMENTS.items():
        text = text.replace(k, v)
    text = re.sub(r"[^a-z\u0621-\u064A]+", "", text)
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    return text

def is_similar(a: str, b: str, threshold: float = 0.8) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold

def contains_bad_word(message: str) -> bool:
    text = normalize_text(message)
    for allowed in ALLOWED_WORDS:
        if normalize_text(allowed) == text:
            return False
    for bad in BAD_WORDS:
        bad_norm = normalize_text(bad)
        if bad_norm in text:
            return True
        words = re.findall(r"[a-z0-9\u0621-\u064A]+", text)
        for w in words:
            if is_similar(w, bad_norm):
                return True
    return False

def contains_link(message: str) -> bool:
    text = re.sub(r"\s+", "", message)
    return bool(re.search(r'https?://[^\s]+', text))

# --- Keep-Alive ---
@tasks.loop(minutes=1)
async def keep_alive():
    global session
    if session:
        try:
            url = "https://sevenmaya-1.onrender.com"
            async with session.get(url) as response:
                print(f"💡 Keep-Alive ping status: {response.status}")
        except Exception as e:
            print(f"⚠️ Keep-Alive error: {e}")

@keep_alive.before_loop
async def before_keep_alive():
    await bot.wait_until_ready()

# --- Update Status ---
@tasks.loop(minutes=5)
async def update_status():
    try:
        activity = discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servers")
        await bot.change_presence(activity=activity)
    except Exception as e:
        print(f"⚠️ Status update failed: {e}")

# --- Bot Events ---
@bot.event
async def on_ready():
    global bot_name, session
    bot_name = str(bot.user)
    print(f"✅ Bot connected as {bot.user} ({len(bot.guilds)} servers)")

    if not session:
        session = aiohttp.ClientSession()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🚀 Flask server started in background")

    keep_alive.start()
    update_status.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    now = datetime.utcnow()

    # --- الروابط ---
    if not any(role.permissions.manage_messages for role in message.author.roles):
        if contains_link(message.content):
            # الغرفة الخاصة: حذف بعد 5 ثواني فقط
            if message.channel.id == 1403040565137899733:
                try:
                    await asyncio.sleep(5)
                    await message.delete()
                except:
                    pass
                return  # ⬅️ إيقاف التنفيذ هنا (لا تحذير ولا Timeout)

            # باقي الغرف
            try:
                await message.delete()
            except:
                pass

            last_time = last_link_time.get(user_id)
            if not last_time or (now - last_time) > timedelta(hours=1):
                last_link_time[user_id] = now
                embed = discord.Embed(
                    title="⚠️ تحذير من الروابط",
                    description=f"{message.author.mention} نشر الروابط ممنوع. المرة القادمة سيتم اسكاتك.",
                    color=0xFFFF00
                )
                await message.channel.send(embed=embed)
            else:
                try:
                    until_time = utcnow() + timedelta(hours=1)
                    await message.author.timeout(until_time, reason="نشر روابط")
                    embed = discord.Embed(
                        title="⛔ تم اسكاتك",
                        description=f"{message.author.mention} تم اسكاتك بسبب تكرار نشر الروابط.",
                        color=0xFF0000
                    )
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"⚠️ خطأ في الاسكات: {e}")
                last_link_time[user_id] = None

    # --- الكلمات المسيئة ---
    if contains_bad_word(message.content):
        try:
            await message.delete()
        except:
            pass

        last_time = last_badword_time.get(user_id)
        if not last_time or (now - last_time) > timedelta(hours=1):
            last_badword_time[user_id] = now
            embed = discord.Embed(
                title="⚠️ تحذير من الكلمات الحساسة",
                description=f"{message.author.mention} لا تستخدم كلمات مسيئة. المرة القادمة سيتم اسكاتك.",
                color=0xFFFF00
            )
            await message.channel.send(embed=embed)
        else:
            try:
                until_time = utcnow() + timedelta(hours=1)
                await message.author.timeout(until_time, reason="استخدام كلمات مسيئة")
                embed = discord.Embed(
                    title="⛔ تم اسكاتك",
                    description=f"{message.author.mention} تم اسكاتك بسبب تكرار استخدام كلمات مسيئة.",
                    color=0xFF0000
                )
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f"⚠️ خطأ في الاسكات: {e}")
            last_badword_time[user_id] = None

    await bot.process_commands(message)

# --- Run Bot ---
async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
