import datetime
import os
import random
import re
import time

from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _navigate_to_page_via_menu, _get_element_text, _find_and_click

def consume_drugs():
    """
    Consumes Cocaine up to the [Drugs] ConsumeLimit (per 24h counter).
    After each consumption, runs the last earn to use the reset earn timer.
    Assumes it's only called when consume_drugs_time_remaining == 0.
    Returns True if at least one consumption/earn happened; otherwise False.
    """
    print("\n--- Beginning Consume Drugs Operation ---")

    # Local constant for file path (text file)
    DRUGS_LAST_CONSUMED_FILE = os.path.join(global_vars.COOLDOWN_DATA_DIR, "drugs_last_consumed.txt")

    # Config
    try:
        limit = global_vars.cfg_int('Drugs', 'ConsumeLimit', 0)
    except Exception:
        limit = 0

    if limit <= 0:
        print("Consume Drugs disabled or limit <= 0. Skipping.")
        return False

    # Navigate to profile page, then Consumables page
    if not _navigate_to_page_via_menu(
            "//a[normalize-space()='PROFILE']",
            "//a[normalize-space()='Consumables']",
            "Consumables"):
        print("FAILED: Could not open Consumables page (likely no apartment). Setting 12h cooldown.")

        # Set 12 hour cooldown to avoid spamming the page if you dont have an apartment.
        try:
            os.makedirs(global_vars.COOLDOWN_DATA_DIR, exist_ok=True)
            next_eligible = datetime.datetime.now() + datetime.timedelta(hours=12)
            with open(DRUGS_LAST_CONSUMED_FILE, "w") as f:
                f.write(next_eligible.strftime("%Y-%m-%d %H:%M:%S.%f"))
            global_vars._script_consume_drugs_cooldown_end_time = next_eligible
            print(f"Wrote next eligible time (+12h) to {DRUGS_LAST_CONSUMED_FILE}.")
        except Exception as e:
            print(f"WARNING: Could not write 12h cooldown timestamp: {e}")
            # Fall back to in-memory cooldown so we still back off this run
            global_vars._script_consume_drugs_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(hours=12)

        return False

    # Read Consumables 24h counter
    xpath_consumables = "//div[@id='nav_right']/div[normalize-space(text())='Consumables / 24h']/following-sibling::div[1]"
    txt = _get_element_text(By.XPATH, xpath_consumables) or ""
    m = re.fullmatch(r"\s*(\d+)\s*", txt)
    if not m:
        print(f"FAILED: Could not parse Consumables / 24h value from text: '{txt}'")
        return False
    count = int(m.group(1))

    print(f"Consumables / 24h currently at: {count}. Target limit: {limit}.")

    # If we are already at/over limit, set a short cooldown and stop
    if count >= limit:
        try:
            os.makedirs(global_vars.COOLDOWN_DATA_DIR, exist_ok=True)
            with open(DRUGS_LAST_CONSUMED_FILE, "w") as f:
                next_eligible = datetime.datetime.now() + datetime.timedelta(hours=3)
                f.write(next_eligible.strftime("%Y-%m-%d %H:%M:%S.%f"))
            print(f"Already at or above limit ({limit}); recorded next eligible time (+3h) in text file.")
            global_vars._script_consume_drugs_cooldown_end_time = next_eligible
        except Exception as e:
            print(f"WARNING: Could not write timestamp file for +3h cooldown: {e}")
        return False

    actions = 0
    max_cycles = max(0, limit - count)  # don't do more than necessary
    while count < limit and actions < max_cycles:
        # Click Cocaine
        if not _find_and_click(By.XPATH, "//div[@id='consumables']//div[contains(@onclick, 'type=Cocaine')]"):
            print("FAILED: Cocaine button not found/clickable. Stopping.")
            global_vars._script_consume_drugs_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(hours=1)
            break

        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 1.5)

        # Click the Income drop-down
        if not _find_and_click(By.XPATH, "//div[@id='nav_left']//a[contains(text(),'Income')]"):
            print("FAILED: Could not open Income menu after consuming. Stopping.")
            break

        # Only try the 'lastearn' quick button (retry once if needed)
        if not _find_and_click(By.XPATH, "//input[@name='lastearn']"):
            time.sleep(0.5)
            if not _find_and_click(By.XPATH, "//input[@name='lastearn']"):
                print("FAILED: 'lastearn' button not found. Stopping.")
                break

        actions += 1

        # Re-read consumables counter
        txt = _get_element_text(By.XPATH, xpath_consumables) or ""
        m = re.fullmatch(r"\s*(\d+)\s*", txt)
        if not m:
            print(f"FAILED: Could not parse Consumables / 24h value on recheck: '{txt}'")
            break
        new_count = int(m.group(1))
        print(f"Post-consume recheck — Consumables / 24h: {new_count}")

        if new_count <= count:
            # quick second read in case of UI lag, then bail
            time.sleep(0.4)
            txt2 = _get_element_text(By.XPATH, xpath_consumables) or ""
            m2 = re.fullmatch(r"\s*(\d+)\s*", txt2)
            fresh = int(m2.group(1)) if m2 else new_count
            if fresh <= count:
                print("Counter did not increase after consuming; stopping to avoid a loop.")
                break
            new_count = fresh

        count = new_count
        time.sleep(random.uniform(0.6, 1.2))

    # Only record the timestamp if we successfully hit the configured limit
    if count >= limit and actions > 0:
        try:
            os.makedirs(global_vars.COOLDOWN_DATA_DIR, exist_ok=True)
            with open(DRUGS_LAST_CONSUMED_FILE, "w") as f:
                # write NEXT eligible time (now + 25h), to match timer math style used by shop checks
                next_eligible = datetime.datetime.now() + datetime.timedelta(hours=25)
                f.write(next_eligible.strftime("%Y-%m-%d %H:%M:%S.%f"))
            print(f"Reached limit ({limit}); recorded next eligible time (+25h) in text file.")
        except Exception as e:
            print(f"WARNING: Could not write timestamp file: {e}")
        return True

    print("Did not reach configured ConsumeLimit; no timestamp written.")
    return False