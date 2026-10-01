import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
uvloop.install()

import os
import shutil

from bot import Bot, Vars, logger
from Tools.config import apply_all
from Tools.auto import main_updates
from Tools.my_token import expired_token_
from Tools.db import remove_expired_users
from Tools.cworker import ensure_workers
from TG.post import scheduled_posts_loop, autopublish_loop
from TG.backup import auto_backup_loop

folder_path = "Process"
if os.path.exists(folder_path) and os.path.isdir(folder_path):
  shutil.rmtree(folder_path)

# Copy any settings saved from /settings (or the environment) onto `Vars`
# before anything reads it. Previously this was never called anywhere, so
# every change made from the bot's settings panel silently reverted to the
# env-var defaults on the next restart.
apply_all()


async def main_exp_():
  while True:
    try:
      await remove_expired_users()
      expired_token_()
    except Exception as e:
      logger.exception(e)
    finally:
      await asyncio.sleep(3600)


async def _start_workers():
  # Spawns exactly `Vars.WORKERS` chapter-processing workers (default 3,
  # editable live from /settings -> Performance) and keeps that count in
  # sync if the setting changes later - see Tools/cworker.py.
  #
  # The previous version unconditionally spawned 20 raw workers here,
  # ignoring the WORKERS setting entirely - each worker runs its own
  # download/convert/upload pipeline (with its own thread pool for image
  # downloads), so that alone was often running several times more
  # concurrent work than intended. This was the single biggest source of
  # unnecessary RAM/CPU use in the bot.
  try:
    ensure_workers()
  except Exception as e:
    logger.exception(f"Failed to start workers - downloads won't process: {e}")
    for admin_id in Vars.ADMINS:
      await igrone_error(Bot.send_message)(
        admin_id, f"🚨 <b>Startup error:</b> chapter workers failed to start.\n<code>{e}</code>"
      )


async def _worker_watchdog():
  """ensure_workers() is a cheap, idempotent top-up (just checks each
  worker's task.done()), so re-running it periodically is a low-cost safety
  net against a worker task ever dying outside its own try/except (e.g. an
  error surfacing from queue.get() itself rather than from processing a
  card) - see worker()/ensure_workers() in Tools/cworker.py."""
  while True:
    await asyncio.sleep(300)
    try:
      ensure_workers()
    except Exception as e:
      logger.exception(f"Worker watchdog error: {e}")


async def _notify_shutdown():
  if Vars.LOG_CHANNEL:
    try:
      await Bot.send_message(Vars.LOG_CHANNEL, "<b>🛑 Bot is shutting down.</b>")
    except Exception as e:
      logger.warning(f"Cannot write to LOG_CHANNEL {Vars.LOG_CHANNEL}: {e}")


if __name__ == "__main__":
  Bot.startup_hooks.append(_start_workers)
  Bot.startup_hooks.append(_worker_watchdog)
  Bot.startup_hooks.append(main_updates)
  Bot.startup_hooks.append(scheduled_posts_loop)
  Bot.startup_hooks.append(autopublish_loop)
  Bot.startup_hooks.append(auto_backup_loop)
  if Vars.SHORTENER:
    Bot.startup_hooks.append(main_exp_)

  Bot.shutdown_hooks.append(_notify_shutdown)

  Bot.run()
