"""Bot client + runtime variables.

Every value in `Vars` starts from an environment variable (or a safe default).
Admins can override most of them at runtime from the bot itself
(/settings) - those overrides are stored in the database and applied on top of
the environment by `Tools.config.apply_all()`.
"""
import asyncio
import os
import re
import shutil
import sys
from time import time

import pyrogram
from loguru import logger
from pyrogram import filters
from pyrogram.types import BotCommand

from Tools.pics import PICS as _PICS


# --------------------------------------------------------------------------- #
# env helpers
# --------------------------------------------------------------------------- #
_FALSE = {"", "none", "null", "off", "false", "0", "no", "disable", "disabled"}


def as_bool(value, default=False) -> bool:
  if value is None:
    return default
  if isinstance(value, bool):
    return value
  return str(value).strip().lower() not in _FALSE


def as_int(value, default=0) -> int:
  try:
    return int(str(value).strip())
  except (TypeError, ValueError):
    return default


def as_channel(value):
  """Channel ids may be numeric ids or usernames. Empty/none/off -> None."""
  if value is None:
    return None
  value = str(value).strip()
  if value.lower() in _FALSE:
    return None
  try:
    return int(value)
  except ValueError:
    return value.lstrip("@").replace("https://t.me/", "")


def as_int_list(value) -> list:
  return [int(x) for x in re.split(r"[,\s]+", str(value or "")) if x.strip().lstrip("-").isdigit()]


def parse_fsb(value: str) -> list:
  """'Button text: username, Other: -100123' -> [[text, chat], ...]"""
  out = []
  for part in str(value or "").split(","):
    if ":" not in part:
      continue
    text, chat = part.rsplit(":", 1)
    chat = as_channel(chat)
    if text.strip() and chat:
      out.append([text.strip(), chat])
  return out


env = os.environ.get


class Vars:
  # ---- credentials (env only) ------------------------------------------------
  API_ID = as_int(env("API_ID"))
  API_HASH = env("API_HASH", "")
  BOT_TOKEN = env("BOT_TOKEN", "")
  DB_URL = env("DB_URL", "")          # empty -> local JSON files in ./data
  DB_NAME = env("DB_NAME", "Manhwadb")
  PORT = as_int(env("PORT"), 5000)
  WEBS_HOST = env("WEBS_HOST")        # set it on Render/Koyeb to open a health-check port
  plugins = dict(root="TG")

  # ---- people ---------------------------------------------------------------
  OWNER = as_int(env("OWNER"))
  ADMINS = as_int_list(env("ADMINS"))
  if OWNER and OWNER not in ADMINS:
    ADMINS.append(OWNER)

  # ---- channels (editable in /settings) -------------------------------------------
  POST_CHANNEL = as_channel(env("POST_CHANNEL"))
  DUMP_CHANNEL = as_channel(env("DUMP_CHANNEL"))
  LOG_CHANNEL = as_channel(env("LOG_CHANNEL"))
  CONSTANT_DUMP_CHANNEL = as_channel(env("CONSTANT_DUMP_CHANNEL"))

  # ---- access ---------------------------------------------------------------
  IS_PRIVATE = as_bool(env("IS_PRIVATE"))
  PRIVATE_TXT = env("PRIVATE_TXT", "<b>🔒 This bot is private right now.\nYou don't have permission to use it.</b>")
  FORCE_SUB_TEXT = env("FORCE_SUB_TEXT", "<b><i>❗️ You must join our channel before using this feature:</i></b>")
  FORCE_SUB_CHANNEL = env("FORCE_SUB_CHANNEL", "")   # "Text: username, Text2: -100123"

  SHORTENER = as_bool(env("SHORTENER"))
  SHORTENER_API = env("SHORTENER_API", "")      # put {} for the url, ex: https://x.com/api?url={}
  DURATION = as_int(env("DURATION"), 20)        # hours a verified token stays valid
  BYPASS_TXT = env("BYPASS_TXT", (
    "<blockquote><b>🚨 ʙʏᴘᴀss ᴅᴇᴛᴇᴄᴛᴇᴅ 🚨</b></blockquote>\n\n"
    "<blockquote expandable><b>ᴘʟᴇᴀsᴇ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ ᴘʀᴏᴘᴇʀʟʏ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.</b></blockquote>"))

  # ---- performance (editable in /settings) --------------------------------------
  WORKERS = as_int(env("WORKERS"), 3)            # chapters processed at the same time
  DL_THREADS = as_int(env("DL_THREADS"), 4)      # simultaneous image downloads
  IMG_QUALITY = as_int(env("IMG_QUALITY"), 70)   # default JPEG quality (10-100)
  AUTO_UPDATES = as_bool(env("AUTO_UPDATES"), True)
  STORAGE_REUSE = as_bool(env("STORAGE_REUSE"), True)   # serve already-stored chapters from the storage channel instead of re-downloading
  UPDATE_INTERVAL = as_int(env("UPDATE_INTERVAL"), 10)   # minutes between subscription checks

  # ---- progress bar ---------------------------------------------------------
  PROGRESS = as_bool(env("PROGRESS"), True)
  PROGRESS_STYLE = env("PROGRESS_STYLE", "smooth")
  PROGRESS_INTERVAL = as_int(env("PROGRESS_INTERVAL"), 4)   # seconds between message edits

  # ---- post design (editable in /settings) -----------------------------------
  POST_TEMPLATE = as_int(env("POST_TEMPLATE"), 1)
  POST_STYLISH = as_bool(env("POST_STYLISH"), True)
  POST_PREMIUM_EMOJI = as_bool(env("POST_PREMIUM_EMOJI"), True)
  POST_BUTTON = env("POST_BUTTON", "📖 Read Now")
  POST_FOOTER = env("POST_FOOTER", "")
  POST_DESC_LEN = as_int(env("POST_DESC_LEN"), 320)
  POST_SPOILER = as_bool(env("POST_SPOILER"), False)

  FILESTORE_ENABLED = as_bool(env("FILESTORE_ENABLED"), False)
  FILESTORE_API_URL = env("FILESTORE_API_URL", "")       # e.g. "https://your-app.example.com"
  FILESTORE_API_KEY = env("FILESTORE_API_KEY", "")       # bearer token from that bot's /newapikey
  FILESTORE_BOT_USERNAME = env("FILESTORE_BOT_USERNAME", "")   # no @, e.g. "MyFileStoreBot" - optional, for reference only

  BACKUP_ENABLED = as_bool(env("BACKUP_ENABLED"), False)
  BACKUP_INTERVAL_DAYS = as_int(env("BACKUP_INTERVAL_DAYS"), 1)

  PICS = _PICS
  PING = time()


remove_site_sf = ["cf"]


def is_admin(user_id) -> bool:
  return bool(user_id) and (user_id == Vars.OWNER or user_id in Vars.ADMINS)


async def _admin_check(_, __, update):
  user = getattr(update, "from_user", None)
  return bool(user and is_admin(user.id))


async def _owner_check(_, __, update):
  user = getattr(update, "from_user", None)
  return bool(user and Vars.OWNER and user.id == Vars.OWNER)


# Dynamic filters (they read Vars on every update, so /settings changes apply at once)
admin_only = filters.create(_admin_check, "AdminOnly")
owner_only = filters.create(_owner_check, "OwnerOnly")


# --------------------------------------------------------------------------- #
# health server (tiny replacement for flask + gunicorn)
# --------------------------------------------------------------------------- #
async def _health(reader, writer):
  try:
    await asyncio.wait_for(reader.read(512), 3)
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
    await writer.drain()
  except Exception:
    pass
  finally:
    writer.close()


class Manhwa_Bot(pyrogram.Client):
  def __init__(self):
    super().__init__(
      "ManhwaBot",
      api_id=Vars.API_ID,
      api_hash=Vars.API_HASH,
      bot_token=Vars.BOT_TOKEN,
      plugins=Vars.plugins,
      workers=as_int(env("CLIENT_WORKERS"), 16),
      max_concurrent_transmissions=2,
    )
    self.__version__ = pyrogram.__version__
    self.username = None
    self.startup_hooks = []    # async callables run once after login
    self.shutdown_hooks = []   # sync/async callables run on stop

  async def start(self):
    await super().start()
    me = await self.get_me()
    self.username = me.username

    try:
      await self.set_bot_commands([
        BotCommand("start", "🚀 Check if the bot is alive"),
        BotCommand("search", "🔍 Search for a manga/manhwa/manhua"),
        BotCommand("help", "❓ How to use this bot"),
        BotCommand("user_setting", "⚙️ Open your personal settings"),
        BotCommand("subs", "📌 View your subscriptions"),
        BotCommand("queue", "📊 Check your download queue"),
        BotCommand("clean_tasks", "🧹 Clear your pending tasks"),
        BotCommand("my_plan", "💎 View your premium plan"),
        BotCommand("stats", "📈 Bot system stats"),
      ])
      from pyrogram.types import BotCommandScopeChat
      for admin in set(Vars.ADMINS):
        try:
          await self.set_bot_commands([
            BotCommand("settings", "🛠 Bot settings (admin)"),
            BotCommand("newpost", "📮 Create a channel post"),
            BotCommand("postsettings", "📢 Set Post/Dump channels"),
            BotCommand("scheduled", "🕒 Scheduled posts"),
            BotCommand("autopublish", "🔁 Auto-Publish watch list"),
            BotCommand("backup", "💾 Export the database"),
            BotCommand("restore", "📥 Import a database backup"),
            BotCommand("start", "🚀 Check if the bot is alive"),
            BotCommand("search", "🔍 Search for a manga/manhwa/manhua"),
            BotCommand("user_setting", "⚙️ Open your personal settings"),
            BotCommand("queue", "📊 Check your download queue"),
            BotCommand("stats", "📈 Bot system stats"),
          ], scope=BotCommandScopeChat(admin))
        except Exception:
          pass  # admin never opened the bot yet
    except Exception as e:
      logger.warning(f"Failed to set bot commands menu: {e}")

    if os.path.exists("restart_msg.txt"):
      try:
        with open("restart_msg.txt") as f:
          chat_id, message_id = f.read().split(":")
        await self.edit_message_text(int(chat_id), int(message_id), "<code>Restarted Successfully</code>")
      except Exception as e:
        logger.warning(f"restart message: {e}")
      finally:
        os.remove("restart_msg.txt")

    shutil.rmtree("Process", ignore_errors=True)

    if Vars.WEBS_HOST:
      try:
        await asyncio.start_server(_health, "0.0.0.0", Vars.PORT)
        logger.info(f"Health server listening on :{Vars.PORT}")
      except Exception as e:
        logger.warning(f"Health server failed: {e}")

    for hook in self.startup_hooks:
      asyncio.create_task(hook())

    logger.info(f"Manhwa Bot started as {me.first_name} | @{me.username}")
    if Vars.LOG_CHANNEL:
      try:
        await self.send_message(Vars.LOG_CHANNEL, f"<b>🔥 @{me.username} is online.</b>")
      except Exception as e:
        logger.warning(f"Cannot write to LOG_CHANNEL {Vars.LOG_CHANNEL}: {e}")

  async def stop(self, *args, **kwargs):
    for hook in self.shutdown_hooks:
      try:
        res = hook()
        if asyncio.iscoroutine(res):
          await res
      except Exception as e:
        logger.warning(f"shutdown hook: {e}")
    await super().stop(*args, **kwargs)
    logger.info("Manhwa Bot stopped")


Bot = Manhwa_Bot()
