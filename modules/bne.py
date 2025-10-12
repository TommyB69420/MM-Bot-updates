import datetime
import random
import re
import time

from selenium.webdriver import Keys
from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from database_functions import get_crime_targets_from_ddb, get_player_cooldown, set_player_data, remove_player_cooldown, \
    _set_last_timestamp
from helper_functions import _find_and_send_keys, _find_element, _find_and_click, _get_element_text
from modules.agg_helpers import log_aggravated_event
from timer_functions import get_current_game_time


def _get_suitable_bne_target(current_location, character_name, excluded_players, apartment_filters=None):
    """
    Returns a player whose stored home_city == current_location,
    apartment is in apartment_filters (if provided), and whose
    minor_crime_cooldown is free/expired.
    """
    game_now = get_current_game_time()

    # Normalize filters once (lowercase for case-insensitive compare)
    filters = [f.strip().lower() for f in (apartment_filters or []) if f and f.strip()]

    # Pull candidates from DDB (already contains HomeCity + Apartment info)
    candidates = list(get_crime_targets_from_ddb(current_location, global_vars.MINOR_CRIME_COOLDOWN_KEY))
    random.shuffle(candidates)

    for player_id, target_home_city in candidates:
        if not player_id:
            continue
        if player_id == character_name or (excluded_players and player_id in excluded_players):
            continue

        # Apartment filter (if any)
        if filters:
            if isinstance(target_home_city, dict):
                apt = (target_home_city.get("Apartment") or "").strip().lower()
            else:
                apt = ""
            if apt not in filters:
                continue

        cooldown_end_time = get_player_cooldown(player_id, global_vars.MINOR_CRIME_COOLDOWN_KEY)
        if cooldown_end_time is None or (game_now - cooldown_end_time).total_seconds() >= 0:
            return player_id

    return None

def _perform_bne_attempt(target_player_name, repay_enabled=False):
    """
    Performs a single Breaking & Entering attempt.
    Assumes we are already on the BnE page (via _open_aggravated_crime_page("BnE")).
    Returns status, target_name, amount_or_None
      status in {'success','failed_attempt','cooldown_target','no_apartment','general_error'}
    """

    # Clear any previous “current crime” repay markers (guarded in case globals don’t exist yet)
    try:
        global_vars.bne_player_for_repay = None
        global_vars.bne_amount_for_repay = None
        global_vars.bne_successful = False
    except Exception:
        pass

    # Fill the form and submit
    if not _find_and_send_keys(By.XPATH, "//input[@name='breaking']", target_player_name):
        return 'general_error', target_player_name, None
    # Dismiss/accept the suggestion popup so it doesn't cover the button
    try:
        name_input = _find_element(By.XPATH, "//input[@name='breaking']")
        if name_input:
            # Try to select the first suggestion and accept it
            name_input.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.05)
            name_input.send_keys(Keys.ENTER)
            time.sleep(0.05)
    except Exception:
        pass

    # click a neutral area to blur the input (collapses popup)
    _find_and_click(By.XPATH, "//div[@id='content']", pause=0.1)

    if not _find_and_click(By.XPATH, "//input[@name='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return 'general_error', target_player_name, None

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]") or ""
    now = get_current_game_time()
    clean = result_text.lower()

    # SUCCESS CASE
    if "you managed to break" in clean:
        try:
            # Parse stolen amount
            amt_match = re.search(r"found yourself \$?([\d,]+)", result_text, re.IGNORECASE)
            stolen = int(amt_match.group(1).replace(',', '')) if amt_match else 0

            # Parse apartment type if present
            apt_match = re.search(r"(Flat|Studio Unit|Penthouse|Palace)", result_text, re.IGNORECASE)
            apt = apt_match.group(1) if apt_match else "Unknown"

            # Parse target name up to the apostrophe
            name_match = re.search(r"break[- ]?into (.+?)(?:'|`)", result_text, re.IGNORECASE)
            name = name_match.group(1).strip() if name_match else target_player_name

            # Success cooldown: 1h40m–2h10m
            cd = now + datetime.timedelta(seconds=random.uniform(100 * 60, 130 * 60))
            set_player_data(name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd, apartment=apt)

            if repay_enabled:
                global_vars.bne_player_for_repay = name
                global_vars.bne_amount_for_repay = stolen
                global_vars.bne_successful = True

            log_aggravated_event("BnE", name, "Success", stolen)
            print(f"[BnE] SUCCESS: {name} | {apt} | ${stolen:,}")

            # If an item was also stolen, push the full success string to Discord with the repay flag state
            if "you also managed" in result_text.lower():
                repay_flag = "ON" if repay_enabled else "OFF"
                send_discord_notification(f"[BnE] ITEM STOLEN — Repay {repay_flag}\n{result_text.strip()}")
            return 'success', name, stolen
        except Exception as e:
            print(f"[BnE] ERROR parsing success: {e}")
            return 'general_error', target_player_name, None

    # FAILED ATTEMPT
    if "attempted to break" in clean:
        try:
            apt_match = re.search(r"(Flat|Studio Unit|Penthouse|Palace)", result_text, re.IGNORECASE)
            apt = apt_match.group(1) if apt_match else "Unknown"

            name_match = re.search(r"into (.+?)(?:'|`)", result_text, re.IGNORECASE)
            name = name_match.group(1).strip() if name_match else target_player_name

            cd = now + datetime.timedelta(seconds=random.uniform(100 * 60, 130 * 60))  # 1h40m–2h10m
            set_player_data(name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd, apartment=apt)
            log_aggravated_event("BnE", name, "Failed", 0)
            print(f"[BnE] FAILED: {name} | {apt}. Cooldown until {cd.strftime('%H:%M:%S')}.")
            return 'failed_attempt', name, None
        except Exception as e:
            print(f"[BnE] ERROR parsing fail: {e}")
            return 'general_error', target_player_name, None

    # RECENTLY SURVIVED
    if "try them again later" in result_text.lower():
        cd = now + datetime.timedelta(minutes=5)
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd)
        print(f"[BnE] AGG PRO: {target_player_name}. Retry after {cd.strftime('%H:%M:%S')}.")
        return 'cooldown_target', target_player_name, None

    # NO APARTMENT
    if "have an apartment" in result_text.lower():
        cd = now + datetime.timedelta(hours=24)
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd, apartment="No Apartment")
        print(f"[BnE] NO APARTMENT: {target_player_name}. Cooldown set 24h.")
        return 'no_apartment', target_player_name, None

    # WRONG CITY (victim's apartment not in your city)
    if "city as your victim" in result_text.lower():
        cd = now + datetime.timedelta(hours=24)
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd)
        print(f"[BnE] WRONG CITY / MOVED APARTMENT: {target_player_name}. 24h minor cooldown set.")
        return 'wrong_city', target_player_name, None

    # NON-EXISTENT TARGET
    if "the name you typed in" in result_text.lower():
        print(f"[BnE] Target '{target_player_name}' does not exist. Removing from cooldown DB.")
        remove_player_cooldown(target_player_name)
        return 'non_existent_target', target_player_name, None

    # FAILED TOO MANY RECENTLY
    if "as you have failed too many" in result_text.lower():
        now = get_current_game_time()
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return 'aggs_blocked', None, None

    # FALLBACK if unexpected result
    short_cd = now + datetime.timedelta(seconds=random.uniform(30, 60))
    set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, short_cd)
    log_aggravated_event("BnE", target_player_name, "Unexpected Result", 0)
    print(f"[BnE] Unrecognized result for '{target_player_name}'. Short cooldown applied.")
    return 'general_error', target_player_name, None