import discord
from discord.ext import commands, tasks
from flask import Flask
import threading
import os
import aiohttp
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# --- Flask Keep-Alive ---
app = Flask(__name__)
ALLOWED_CHANNEL_ID = 1403040565137899733
bot_name = "Loading..."

@app.route("/")
def home():
    return f"Bot {bot_name} is operational ✅"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Discord Bot Setup ---
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Missing DISCORD_BOT_TOKEN in environment variables")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.session = None
        self.last_link_time = {}

    async def setup_hook(self):
        # إنشاء جلسة aiohttp واحدة
        self.session = aiohttp.ClientSession()
        # تشغيل Flask في Thread منفصل
        threading.Thread(target=run_flask, daemon=True).start()
        print("🚀 Flask server started in background")
        # بدء المهام الدورية
        self.update_status.start()
        self.keep_alive.start()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

# --- تحديث الحالة كل 5 دقائق لتقليل الضغط على Discord ---
@tasks.loop(minutes=5)
async def update_status(self):
    try:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers"
        )
        await self.change_presence(activity=activity)
    except Exception as e:
        print(f"⚠️ Status update failed: {e}")

@update_status.before_loop
async def before_status_update(self):
    await self.wait_until_ready()

# --- Keep-Alive Ping كل 5 دقائق ---
@tasks.loop(minutes=5)
async def keep_alive(self):
    if self.session:
        try:
            url = "https://sevenmaya-2-hh9c.onrender.com"  # ضع رابطك المباشر
            async with self.session.get(url) as resp:
                print(f"💡 KeepAlive ping: {resp.status}")
        except Exception as e:
            print(f"⚠️ KeepAlive error: {e}")

@keep_alive.before_loop
async def before_keep_alive(self):
    await self.wait_until_ready()

# --- تنظيف النص ---
def normalize_text(self, text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.lower().replace("ـ", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    return text

# --- كشف الروابط ---
def contains_link(self, message: discord.Message) -> bool:
    spotify_whitelist = ["spotify.com", "open.spotify.com", "spotify.link"]
    shorteners = ["bit.ly", "tinyurl.com", "t.co", "goo.gl",
                  "is.gd", "cutt.ly", "rebrand.ly", "shorturl.at"]

    full_content = message.content
    for embed in message.embeds:
        if embed.url:
            full_content += " " + embed.url
        if embed.description:
            full_content += " " + embed.description
        if embed.title:
            full_content += " " + embed.title

    content = self.normalize_text(full_content)

    markdown_links = re.findall(r"\[.*?\]\((.*?)\)", full_content)
    for link in markdown_links:
        if not any(domain in link.lower() for domain in spotify_whitelist):
            return True

    if re.search(r"https?://", content):
        if not any(domain in content for domain in spotify_whitelist):
            return True

    domain_pattern = r"[a-z0-9\-]+\.(com|net|org|gg|io|me|co|xyz|info|app|site|store|online|tech|dev|link)"
    if re.search(domain_pattern, content):
        if not any(domain in content for domain in spotify_whitelist):
            return True

    if "discord.com/invite" in content:
        return True

    if any(short in content for short in shorteners):
        return True

    for attachment in message.attachments:
        filename = self.normalize_text(attachment.filename)
        if re.search(domain_pattern, filename):
            return True

    return False

# --- معالجة الرسائل ---
@MyBot.listen("on_message")
async def on_message(self, message):
    if message.author.bot:
        return

    user_id = message.author.id
    now = datetime.now(timezone.utc)

    if not any(role.permissions.manage_messages for role in message.author.roles):
        if self.contains_link(message):
            if message.channel.id == ALLOWED_CHANNEL_ID:
                try:
                    await asyncio.sleep(5)
                    await message.delete()
                except:
                    pass
                return
            try:
                await message.delete()
            except:
                pass

            last_time = self.last_link_time.get(user_id)
            if not last_time or (now - last_time) > timedelta(hours=1):
                self.last_link_time[user_id] = now
                embed = discord.Embed(
                    title="⚠️ تحذير من الروابط",
                    description=f"{message.author.mention} نشر الروابط ممنوع. المرة القادمة سيتم اسكاتك.",
                    color=0xFFFF00
                )
                await message.channel.send(embed=embed)
            else:
                try:
                    until_time = now + timedelta(hours=1)
                    await message.author.timeout(until_time, reason="نشر روابط")
                    embed = discord.Embed(
                        title="⛔ تم اسكاتك",
                        description=f"{message.author.mention} تم اسكاتك بسبب تكرار نشر الروابط.",
                        color=0xFF0000
                    )
                    await message.channel.send(embed=embed)
                except Exception as e:
                    print("⚠️ Timeout error:", e)
            self.last_link_time[user_id] = None

    await self.process_commands(message)

# --- تشغيل البوت ---
bot = MyBot()
bot.run(TOKEN)
