import datetime
import random
import re
import time

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from helper_functions import _find_and_click, _get_element_text
from timer_functions import get_all_active_game_timers

def do_events():
    """
    Checks for and attempts the in the game event based on settings.ini.
    Returns True if an action was performed (attacked or cooldown set), False otherwise.
    """

    print("\n--- Beginning Event Operation ---")

    # Click the logo to go to the game home page
    if not _find_and_click(By.XPATH, "//*[@id='logo_hit']"):
        print("Failed to click game logo to navigate to home page.")
        return False
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Click the button to navigate to the event page
    event_page_button_xpath = "//*[self::a or self::button][contains(text(), 'help defend your local city')]"
    if not _find_and_click(By.XPATH, event_page_button_xpath):
        print("Event button 'help defend your local city' not found or not clickable.")
        # If the event button is not available, set a cooldown and return. It prevents constant re-checking when no event is active
        print("Setting event re-check cooldown for 5-7 minutes.")
        global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(5, 7))
        return False

    time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

    # Check for the 'ATTACK' button
    attack_button_xpath = "//a[@class='declinebutton' and contains(text(), 'ATTACK')]"
    if _find_and_click(By.XPATH, attack_button_xpath):
        print("Successfully clicked 'ATTACK' button for the event!")
        # If attacked, read the event_time_remaining from timer_functions.py
        all_timers = get_all_active_game_timers()
        event_time_remaining = all_timers.get('event_time_remaining', float('inf'))

        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

        if event_time_remaining > 0 and event_time_remaining != float('inf'):
            print(f"Event attack successful. Next event action available in {event_time_remaining:.2f} seconds.")
        else:
            print("Event attack successful, but could not determine event cooldown from game timers. Will re-evaluate soon.")
            # Set a fallback cooldown if the game timer is not immediately available
            global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
        return True
    else:
        print("ATTACK button not available on the event page. Event might be on cooldown or completed.")
        # If attack button not available, set a cooldown of 5-7 minutes
        print("Setting event re-check cooldown for 5-7 minutes.")
        global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(5, 7))
        return False

def event_reset_agg_strength() -> bool:
    """
    Discord-triggered flow:
      - Click logo (home)
      - Open event page via the 'help defend your local city' link
          * if missing: notify "No event is currently active" and return False
      - Click skull image to reset agg strength
          * if missing: notify "no skulls remaining" (continue False)
      - Read 'Collected: N' and notify the number
      - Immediately run aggravated crime (no pre-check of last-action file)
        and, on success, set the normal aggravated-crime timestamp.
    """
    # Go to the main page via logo
    _find_and_click(By.XPATH, "//div[@id='logo_hit']")

    # Click the event page link
    if not _find_and_click(By.XPATH, "//a[normalize-space()='help defend your local city']", pause=global_vars.ACTION_PAUSE_SECONDS):
        send_discord_notification("No event is currently active")
        return False

    # Click an agg reset item (Skull, Fries, etc.)
    resetagg_items = ["Skull", "Fries", "Purple Egg", "Gingerbread Man"]  # Add more keywords here as needed

    item_clicked = None
    for item in resetagg_items:
        resetaggstr = f"//img[contains(@title, '{item} -')]"
        if _find_and_click(By.XPATH, resetaggstr, pause=global_vars.ACTION_PAUSE_SECONDS):
            print(f"Used {item} to reset your agg strength.")
            item_clicked = item
            break  # stop after the first one that works

    if not item_clicked:
        send_discord_notification("No agg strength reset items found.")
        return False

    # Read 'Collected: N' for the specific item we just used (bind to item_clicked)
    time.sleep(0.5)
    collected_xpath = (
        f"//div[@id='eventboss_collecteditems']"
        f"//div[.//img[contains(@title, '{item_clicked} -')]]"
        f"//h3[starts-with(normalize-space(),'Collected:')]"
    )
    collected_text = _get_element_text(By.XPATH, collected_xpath, timeout=3) or ""
    m = re.search(r"Collected:\s*([0-9]+)", collected_text)
    if m:
        remaining = int(m.group(1))
        send_discord_notification(f"{item_clicked} items remaining: {remaining}")

    elif not _get_element_text(By.XPATH, f"//img[contains(@title, '{item_clicked} -')]", timeout=1):
        # If the item tile vanished completely, assume 0 remaining
        send_discord_notification(f"{item_clicked} items remaining: 0")
        print(f"[eventagg] {item_clicked} tile missing after use -> assuming 0 remaining.")

    # Clear the last-action file so the main loop will attempt an aggravated crime
    try:
        with open(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, "w", encoding="utf-8") as f:
            f.write("")  # truncate to empty
        print("[eventagg] Cleared aggravated_crimes_last_action file (loop will trigger aggs).")
        return True
    except Exception as e:
        print(f"[eventagg] failed to clear last-action file: {e}")
        return False
