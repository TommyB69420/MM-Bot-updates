import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from helper_functions import _click_quick_xpath, _get_current_url, _find_and_click, _find_element

def map_promo_choice(promo_name: str):
    """
    Lookup-based promo choice against global_vars.PROMO_MAP.
    Returns 'one' or 'two' if a keyword matches, else None for manual.
    """
    key = (promo_name or "").lower().strip()
    for keyword, choice in global_vars.PROMO_MAP.items():
        if keyword in key:
            return choice
    return None

def take_promotion():
    """
    Automatically checks and takes promotions.
      - Observes [Misc] TakePromo in settings.ini (existing)
      - If [Misc] PromoSpam = True, spam-clicks the logo rapidly until a promotion appears (or 25 minutes elapsed).
      - Once on a promotion page, proceed with existing mapped-choice handling.
    Returns True if a promotion was taken; False otherwise.
    """
    print("\n--- Promotion Check ---")

    # read the spam config (default False)
    try:
        promo_spam_enabled = global_vars.cfg_bool('Misc', 'PromoSpam', False)
    except Exception:
        promo_spam_enabled = False

    # If promo-spam is enabled, aggressively click the logo repeatedly (fast)
    if promo_spam_enabled:
        print("PromoSpam enabled — spamming logo until promotion appears (max 25 minutes).")
        start = time.monotonic()
        max_seconds = 25 * 60  # 25 minutes
        while (time.monotonic() - start) < max_seconds:
            # Use the quick helper to avoid expensive waits
            _click_quick_xpath(By.XPATH, "//*[@id='logo_hit']")
            # small tiny pause — keep it aggressive but not insane
            time.sleep(0.3)

            curr_url = (_get_current_url() or "").lower()
            if "promotion" in curr_url:
                print("PromoSpam: promotion page detected — exiting spam loop.")
                break
        else:
            # timeout: no promotion after max duration
            print("PromoSpam: No promotion detected after 25 minutes. Backing off.")
            global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
            return False

    else:
        # Not using spam — perform single click as before
        if not _find_and_click(By.XPATH, "//*[@id='logo_hit']", pause=global_vars.ACTION_PAUSE_SECONDS):
            print("Promo: Could not click logo.")
            return False
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # If we weren't in the spam branch (or after spam loop) ensure we're on promo page
    curr_url = (_get_current_url() or "").lower()
    if "promotion" not in curr_url:
        print("Promo: No promotion detected.")
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
        return False

    print("Promo page detected — parsing details...")

    # Read promo header (existing logic)
    header_el = _find_element(By.XPATH, "//*[@id='holder_top']/h1")
    promo_name = (header_el.text if header_el else "").strip()
    if not promo_name:
        print("Promo: Could not read promotion header.")
        return False

    print(f"Detected Promotion: {promo_name}")

    choice = map_promo_choice(promo_name)
    if choice not in {"one", "two"}:
        msg = f"Unable to auto-take promotion — manual action required: {promo_name}"
        print("Promo:", msg)
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))

        # --- Rate-limit Discord spam to 5 notifications per promo (resets on success or promo change) ---
        last_name = getattr(global_vars, "_promo_unable_last_name", None)
        if last_name != promo_name:
            setattr(global_vars, "_promo_unable_notify_count", 0)
            setattr(global_vars, "_promo_unable_last_name", promo_name)

        count = getattr(global_vars, "_promo_unable_notify_count", 0)
        if count < 5:
            try:
                send_discord_notification(msg)
            except Exception:
                pass
            setattr(global_vars, "_promo_unable_notify_count", count + 1)
        # else: silently suppress further pings

        return False

    # Click the mapped option
    if not _find_and_click(By.ID, choice, pause=global_vars.ACTION_PAUSE_SECONDS):
        print(f"Promo: Could not click option '{choice}'.")
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
        return False

    # Continue
    if not _find_and_click(By.XPATH, "//*[@id='holder_content']/form/center/input", pause=global_vars.ACTION_PAUSE_SECONDS):
        print("Promo: Could not click Continue.")
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
        return False

    print("Promo: Continue clicked — promotion accepted.")
    try:
        send_discord_notification(f"Taking promotion: {promo_name}")
    except Exception:
        pass

    # Reset the "unable" spam counter after a successful accept
    setattr(global_vars, "_promo_unable_notify_count", 0)
    setattr(global_vars, "_promo_unable_last_name", None)

    setattr(global_vars, "force_reselect_earn", True)
    print("Promo: Flag set to force reselecting earn on next cycle.")

    return True