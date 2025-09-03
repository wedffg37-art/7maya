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
last_link_time = {}

# --- Normalize text ---
def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("ـ", "")
    text = re.sub(r"[^a-z\u0621-\u064A]+", "", text)
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    return text

def contains_link(message: str) -> bool:
    text = re.sub(r"\s+", "", message)
    return bool(re.search(r'https?://[^\s]+', text))

# --- Keep-Alive ---
@tasks.loop(minutes=1)
async def keep_alive():
    global session
    if session:
        try:
            url = "https://sevenmaya-teyl.onrender.com"
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

    # --- الروابط فقط ---
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

    await bot.process_commands(message)

# --- Run Bot ---
async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
