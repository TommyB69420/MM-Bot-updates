import os
import re
import threading
from queue import Queue, Empty
import discord
import time, random

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import reply_to_sender, send_discord_notification
from helper_functions import _find_and_click
from modules.auto_travel import execute_travel_to_city
from modules.money_handling import execute_sendmoney_to_player
from timer_functions import get_all_active_game_timers

# ---- config helpers (from your remote settings) --------------------------------
try:
    # if you exported the helpers from global_vars
    from global_vars import cfg_get, cfg_bool, cfg_int, cfg_float, cfg_list, cfg_int_nested
except Exception:
    # or from a dedicated helpers module if that's where you put them
    from global_vars import cfg_get, cfg_bool, cfg_int, cfg_float, cfg_list, cfg_int_nested  # type: ignore

def _to_int(val, default=0) -> int:
    try:
        if val is None:
            return default
        if isinstance(val, int):
            return val
        return int(str(val).strip())
    except Exception:
        return default

# ----- Config loading (from Dynamo-backed settings) -----
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN') or cfg_get('DiscordBot', 'bot_token')
LISTEN_CHANNEL_ID = _to_int(cfg_get('DiscordBot', 'listen_channel_id', '0'), 0)
CMD_PREFIX = cfg_get('DiscordBot', 'command_prefix', '!')

# Raise error if Discord bot is misconfigured
if not BOT_TOKEN or not LISTEN_CHANNEL_ID:
    raise RuntimeError("You do not have permission to use this script. Speak to the Author")

print(f"[DiscordBridge] Config loaded. Channel: {LISTEN_CHANNEL_ID} | Prefix: '{CMD_PREFIX}'")

# Matches webhook text like: "In-Game Message from <sender> at ..."
FROM_PATTERN = re.compile(r"In-Game Message from\s+(.+?)\s+at\b", re.IGNORECASE)

# Work queue and worker thread
work_queue: Queue = Queue()

def execute_send_timers_snapshot() -> bool:
    """
    Fetch timers live and send only those that are actively counting down (>0s).
    """
    try:
        timers = get_all_active_game_timers()
    except Exception as e:
        send_discord_notification(f"Failed to read timers: {e}")
        return False

    ticking = []
    for key, sec in timers.items():
        try:
            if sec and sec > 0 and sec != float("inf"):
                # format h:mm:ss
                s = int(round(sec))
                h, rem = divmod(s, 3600)
                m, s = divmod(rem, 60)
                ticking.append((key, f"{h:d}:{m:02d}:{s:02d}"))
        except Exception:
            continue

    if not ticking:
        send_discord_notification("**Timers snapshot**\n_All enabled timers are Ready._")
        return True

    # Sort longest first
    ticking.sort(key=lambda kv: kv[0])
    lines = [f"{k:28} : {v}" for k, v in ticking]
    body = "**Timers snapshot**\n```\n" + "\n".join(lines) + "\n```"
    send_discord_notification(body)
    return True


def worker():
    print("[DiscordBridge] Worker thread started.")
    while True:
        try:
            job = work_queue.get(timeout=1)
        except Empty:
            continue

        try:
            print(f"[DiscordBridge] Worker picked job: {job} | Queue size: {work_queue.qsize()}")

            ok = False
            action = job.get("action")

            # --- EXCLUSIVE BROWSER SECTION ---
            with global_vars.DRIVER_LOCK:
                if action == "reply_to_sender":
                    ok = reply_to_sender(job["to"], job["text"])
                    print(f"[DiscordBridge] reply_to_sender -> {job['to']} | {'OK' if ok else 'FAILED'}")

                elif action == "smuggle":
                    # Do NOT execute now; signal Main loop and let it run when timer/token allow.
                    global_vars._smuggle_request_target = job["target"]
                    global_vars._smuggle_request_active.set()
                    ok = True
                    print(f"[DiscordBridge] Smuggle request armed for '{job['target']}'. Awaiting trafficking timer & token.")

                elif action == "sendmoney":
                    ok = execute_sendmoney_to_player(job["target"], job["amount"])
                    print(f"[DiscordBridge] sendmoney -> {job['target']} ${job['amount']} | {'OK' if ok else 'FAILED'}")

                elif action == "timers":
                    ok = execute_send_timers_snapshot()
                    print(f"[DiscordBridge] timers snapshot | {'OK' if ok else 'FAILED'}")

                elif action == "log out":
                    ok = execute_logout()
                    print(f"[DiscordBridge] logout requested | {'OK' if ok else 'FAILED'}")

                elif action == "travel":
                    # Pull the last known city from globals (set by the main loop). If empty, we skip the "already-in-city" check.
                    current_city = getattr(global_vars, "LAST_KNOWN_CITY", "")
                    ok = execute_travel_to_city(
                        job["target_city"],
                        current_city=current_city,
                        discord_user_id=job.get("discord_user_id"),)
                    print(f"[DiscordBridge] travel -> {job['target_city']} | {'OK' if ok else 'FAILED'}")

                else:
                    print(f"[DiscordBridge][WARN] Unknown action: {action}")
            # --- END EXCLUSIVE SECTION ---

            time.sleep(random.uniform(0.3, 0.9))

        except Exception as e:
            print(f"[DiscordBridge][ERROR] Worker exception: {e}")
        finally:
            work_queue.task_done()

threading.Thread(target=worker, daemon=True).start()

# ----- Discord client -----
intents = discord.Intents.default()
intents.message_content = True  # Ensure Message Content Intent is enabled in your bot config
client = discord.Client(intents=intents)

def parse_tell(content: str):
    # !tell <player> <message...>
    parts = content.strip().split(maxsplit=2)
    if len(parts) < 3:
        return None, None
    _, player, msg = parts
    return player, msg

@client.event
async def on_ready():
    print(f"[DiscordBridge] Logged in as {client.user} ({client.user.id})")
    print(f"[DiscordBridge] Listening in channel id: {LISTEN_CHANNEL_ID}")

@client.event
async def on_message(message: discord.Message):
    # ignore our own messages
    if message.author == client.user:
        return

    # only listen in the configured channel
    if message.channel.id != LISTEN_CHANNEL_ID:
        return

    text = (message.content or "").strip()
    if not text:
        return

    # quick health check
    if text.lower() in {f"{CMD_PREFIX}ping", "!ping"}:
        await message.reply("pong")
        return

    # !timers
    if text.startswith(f"{CMD_PREFIX}timers"):
        work_queue.put({"action": "timers"})
        print(f"[DiscordBridge] Queued timers snapshot. Queue size: {work_queue.qsize()}")
        await message.add_reaction("⏱️")
        await message.reply("Queued a timers snapshot.")
        return

    # !logout
    if text.startswith(f"{CMD_PREFIX}log out"):
        work_queue.put({"action": "log out"})
        print(f"[DiscordBridge] Queued log out. Queue size: {work_queue.qsize()}")
        await message.add_reaction("👋")
        await message.reply("Logging out and stopping the script...")
        return

    # !smuggle <Player>
    if text.startswith(":smuggle") or text.startswith(f"{CMD_PREFIX}smuggle"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Usage: `:smuggle <Player>` or `!smuggle <Player>`")
            return
        target = parts[1].strip()
        work_queue.put({"action": "smuggle", "target": target})
        print(f"[DiscordBridge] Queued smuggle for '{target}'. Queue size: {work_queue.qsize()}")
        await message.add_reaction("📦")
        await message.reply(f"Queued smuggle for **{target}**.")
        return

    # !travel <City>
    if text.startswith(f"{CMD_PREFIX}travel"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            # Build allowed set dynamically from global aliases
            aliases = getattr(global_vars, "CITY_ALIASES", {}) or {}
            grouped = {}
            for alias, city in aliases.items():
                grouped.setdefault(city, []).append(alias)

            parts_list = []
            for city, alias_list in grouped.items():
                extras = [a for a in alias_list if a.lower() != city.lower()]
                if extras:
                    parts_list.append(f"{city} ({', '.join(extras)})")
                else:
                    parts_list.append(city)

            allowed = ", ".join(parts_list)

            await message.reply(f"Usage: `{CMD_PREFIX}travel <City>`\nAllowed: {allowed}")
            return

        key = parts[1].strip().lower()
        aliases = getattr(global_vars, "CITY_ALIASES", {}) or {}
        if key not in aliases:
            allowed = ", ".join(sorted(set(list(aliases.keys()) + list(aliases.values())))) or "Unknown"
            await message.reply(f"City must be one of: {allowed}.")
            return

        destination = aliases[key]

        work_queue.put({
            "action": "travel",
            "target_city": destination,
            "discord_user_id": message.author.id,  # used to resolve per-user webhook
        })
        print(f"[DiscordBridge] Queued travel -> {destination}. Queue size: {work_queue.qsize()}")
        await message.add_reaction("🛫")
        await message.reply(f"Queued travel to **{destination}**.")
        return

    # !sendmoney <Player> <Amount>
    if text.startswith(f"{CMD_PREFIX}sendmoney"):
        parts = text.split(maxsplit=3)
        if len(parts) < 3:
            await message.reply(f"Usage: `{CMD_PREFIX}sendmoney <player> <amount>`")
            return
        player = parts[1].strip()
        raw_amount = parts[2].strip()  # supports "100000", "100,000", "$100,000"
        digits = "".join(ch for ch in raw_amount if ch.isdigit())
        if not digits:
            await message.reply("Amount must contain digits (e.g., 100000 or $100,000).")
            print(f"[DiscordBridge][WARN] Bad amount '{raw_amount}' from {message.author}.")
            return
        amount_int = int(digits)

        work_queue.put({"action": "sendmoney", "target": player, "amount": amount_int})
        print(f"[DiscordBridge] Queued sendmoney: {player} <- {amount_int}. Queue size: {work_queue.qsize()}")
        await message.add_reaction("💸")
        await message.reply(f"Queued sendmoney: **{player}** ← ${amount_int:,}.")
        return

    # !tell <player> <message...>
    if text.startswith(f"{CMD_PREFIX}tell"):
        player, body = parse_tell(text)
        if not player or not body:
            await message.reply(f"Usage: `{CMD_PREFIX}tell <player> <message>`")
            return
        work_queue.put({"action": "reply_to_sender", "to": player, "text": body})
        print(f"[DiscordBridge] Queued tell -> {player}. Queue size: {work_queue.qsize()}")
        await message.add_reaction("📨")
        await message.reply(f"Queued reply to **{player}**.")
        return

    # Reply to a webhook alert (extract player from "In-Game Message from <Name> at ...")
    if message.reference and message.reference.resolved:
        ref_msg = message.reference.resolved  # type: ignore
        if isinstance(ref_msg, discord.Message):
            m = FROM_PATTERN.search(ref_msg.content or "")
            if m:
                player = m.group(1).strip()
                work_queue.put({"action": "reply_to_sender", "to": player, "text": text})
                print(f"[DiscordBridge] Queued threaded reply -> {player}. Queue size: {work_queue.qsize()}")
                await message.add_reaction("📨")
                await message.reply(f"Queued reply to **{player}**.")
                return

    # Use the help feature to get commands
    if text in {f"{CMD_PREFIX}help", f"{CMD_PREFIX}commands"}:
        # Build allowed city list dynamically from globals
        aliases = getattr(global_vars, "CITY_ALIASES", {}) or {}
        grouped = {}
        for alias, city in aliases.items():
            grouped.setdefault(city, []).append(alias)

        parts_list = []
        for city, alias_list in grouped.items():
            extras = [a for a in alias_list if a.lower() != city.lower()]
            if extras:
                parts_list.append(f"{city} ({', '.join(extras)})")
            else:
                parts_list.append(city)

        allowed = ", ".join(parts_list)

        await message.reply(
            "Commands:\n"
            f"- `{CMD_PREFIX}tell <player> <message>`\n"
            f"- `{CMD_PREFIX}smuggle <player>`\n"
            f"- `{CMD_PREFIX}sendmoney <player> <amount>`\n"
            f"- `{CMD_PREFIX}travel <City>` — Allowed: {allowed}\n"
            f"- `{CMD_PREFIX}timers`\n"
            f"- `{CMD_PREFIX}log out`\n"
            f"- `{CMD_PREFIX}ping`"
        )
        return


def run_discord_bot():
    print("[DiscordBridge] Starting Discord client...")
    client.run(BOT_TOKEN)

def start_discord_bridge():
    t = threading.Thread(target=run_discord_bot, daemon=True)
    t.start()
    print("[DiscordBridge] Thread launched.")
    return t

if __name__ == "__main__":
    start_discord_bridge()

def execute_logout():
    """Click the log out button, message discord and stop the script."""
    try:
        ok = _find_and_click(By.XPATH, "//a[normalize-space()='LOG OUT']")
        if ok:
            send_discord_notification("Bot logged out and stopped via Discord command.")
            print("[DiscordBridge] Logout successful. Exiting script...")
            os._exit(0)  # Hard exit
        else:
            send_discord_notification("Logout command failed - could not find button.")
        return ok
    except Exception as e:
        send_discord_notification(f"Logout failed: {e}")
        return False
