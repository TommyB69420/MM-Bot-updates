import datetime
import random
import re
import time
from urllib.parse import urlsplit

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from selenium.webdriver.common.by import By

import global_vars
from database_functions import get_crime_targets_from_ddb, get_player_cooldown, _set_last_timestamp
from helper_functions import _find_and_click, _find_element, _navigate_to_page_via_menu, _get_element_text_quiet, enqueue_community_services, community_service_queue_count
from timer_functions import get_current_game_time

def player_online_hours():

    # Open the online list
    if not _find_and_click(
        By.XPATH,
        "/html/body/div[5]/div[1]/div[2]/div[1]/span[1]",
        pause=global_vars.ACTION_PAUSE_SECONDS * 2
    ):
        print("[OnlineHours] Could not open online list; skipping.")
        return False

    container = _find_element(By.XPATH, "/html/body/div[5]/div[3]/div[2]")
    if not container:
        print("[OnlineHours] Online players container not found; skipping.")
        # still go to /localcity/local.asp to leave the page in a good state
        try:
            cur = urlsplit(global_vars.driver.current_url)
            target = f"{cur.scheme}://{cur.netloc}/localcity/local.asp"
            global_vars.driver.get(target)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception as e:
            print(f"[OnlineHours] Navigation error to /localcity/local.asp: {e}")
        return False

    # Collect player names from <a id="profileLink:<name>:" ...>
    names = set()
    for link in container.find_elements(By.TAG_NAME, "a"):
        id_attr = link.get_attribute("id") or ""
        m = re.search(r'^profileLink:([^:]+):', id_attr)
        if m:
            names.add(m.group(1))

    if not names:
        print("[OnlineHours] No online players detected.")
        # Navigate to /localcity/local.asp before returning
        try:
            cur = urlsplit(global_vars.driver.current_url)
            target = f"{cur.scheme}://{cur.netloc}/localcity/local.asp"
            global_vars.driver.get(target)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception as e:
            print(f"[OnlineHours] Navigation error to /localcity/local.asp: {e}")
        return True

    # Increment OnlineHours in DynamoDB (only if the item exists)
    table = global_vars.get_players_table()
    pk = global_vars.DDB_PLAYER_PK

    updated = 0
    skipped_missing = 0
    for player_name in names:
        try:
            table.update_item(
                Key={pk: player_name},
                UpdateExpression="SET OnlineHours = if_not_exists(OnlineHours, :zero) + :one",
                ExpressionAttributeValues={":zero": 0, ":one": 1},
                ConditionExpression=Attr(pk).exists(),  # only update existing items
            )
            updated += 1
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                skipped_missing += 1
            else:
                print(f"[OnlineHours] Update error for {player_name}: {e}")

    print(f"[OnlineHours] +1 for {updated} players (skipped missing: {skipped_missing}).")

    # Go to /localcity/local.asp at the end
    try:
        cur = urlsplit(global_vars.driver.current_url)
        target = f"{cur.scheme}://{cur.netloc}/localcity/local.asp"
        global_vars.driver.get(target)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    except Exception as e:
        print(f"[OnlineHours] Navigation error to /localcity/local.asp: {e}")

    return True

def log_aggravated_event(crime_type, target, status, amount):
    """Logs an aggravated crime event."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"{timestamp} - Crime: {crime_type}, Target: {target}, Status: {status}, Amount: {amount}\n"
    print(f"LOG: {log_message.strip()}")
    try:
        with open(global_vars.AGGRAVATED_CRIMES_LOG_FILE, 'a') as f:
            f.write(log_message)
    except Exception as e:
        print(f"Error writing to aggravated crimes log file: {e}")

def _open_aggravated_crime_page(crime_type):
    """
    Navigates to the specified aggravated crime page (Hack, Pickpocket, Armed Robbery, or Torch).
    The process is skipped if the current URL is already on the Aggrivated Crime page
    """
    if "income/agcrime.asp" not in global_vars.driver.current_url:
        if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//a[@href='/income/agcrime.asp'][normalize-space()='Aggravated Crimes']",
            "Aggravated Crime Page"):
            return False

        # check the page-level fail box before touching any radio <<<
        fail_text = _get_element_text_quiet(By.XPATH, "//div[@id='fail']")
        if fail_text:
            # Example text: "You cannot commit an aggravated crime until you have completed another 1 Services to your community!"
            m = re.search(r"another\s+(\d+)\s+Services", (fail_text or ""), re.IGNORECASE)
            if m:
                needed = int(m.group(1))
                if needed > 0:
                    enqueue_community_services(needed)
                    print(f"Aggravated Crime gate requires {needed} Community Service(s). Queued them.")
                    return False  # Bail out here; Main will process the CS queue.

    radio_button_xpath = {
        "Hack": "//input[@type='radio' and @value='hack' and @name='agcrime']",
        "Pickpocket": "//input[@type='radio' and @value='pickpocket' and @name='agcrime']",
        "Mugging": "//input[@id='mugging']",
        "BnE": "//input[@id='breaking']",
        "Torch": "//input[@type='radio' and @value='torchbusiness' and @name='agcrime']",
        "Armed Robbery": "//input[@type='radio' and @value='armed' and @name='agcrime']",
    }

    if not _find_and_click(By.XPATH, radio_button_xpath[crime_type]):
        print(f"Failed to select {crime_type} radio button.")
        return False

    if not _find_and_click(By.XPATH, "//input[@type='submit' and @class='submit' and @value='Commit Crime']"):
        print(f"Failed to click initial 'Commit Crime' button for {crime_type}.")
        return False
    print(f"Successfully opened {crime_type}.")
    return True

def _get_suitable_crime_target(my_home_city, character_name, excluded_players, cooldown_key):
    """Retrieves a suitable player from DynamoDB for a crime."""
    game_now = get_current_game_time()  # use the game clock

    # Pull candidates from DDB (prefiltered by city for major crimes)
    candidates = list(get_crime_targets_from_ddb(my_home_city, cooldown_key))
    random.shuffle(candidates)

    for player_id, target_home_city in candidates:
        if not player_id:
            continue
        if player_id == character_name or (excluded_players and player_id in excluded_players):
            continue

        # City rule: already enforced by get_crime_targets_from_ddb for Major;
        # for Minor, it's always allowed.
        cooldown_end_time = get_player_cooldown(player_id, cooldown_key)
        if cooldown_end_time is None or (game_now - cooldown_end_time).total_seconds() >= 0:
            return player_id

    return None

def _get_suitable_pp_mug_target_online(character_name, excluded_players):
    """Retrieves a suitable player for pickpocketing/mugging from the online list."""
    if not _find_and_click(By.XPATH, "/html/body/div[5]/div[1]/div[2]/div[1]/span[2]", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return None

    online_players_container = _find_element(By.XPATH, "/html/body/div[5]/div[3]/div[1]")
    if not online_players_container:
        return None

    online_player_links = online_players_container.find_elements(By.TAG_NAME, "a")
    available_players = []

    for link in online_player_links:
        player_id_attr = link.get_attribute("id")
        if player_id_attr and player_id_attr.startswith("profileLink:"):
            match = re.search(r'profileLink:([^:]+):', player_id_attr)
            if match:
                player_name = match.group(1)
                if player_name == character_name or (excluded_players and player_name in excluded_players):
                    continue

                cooldown_end_time = get_player_cooldown(player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY)
                game_now = get_current_game_time()

                if cooldown_end_time is None or (game_now - cooldown_end_time).total_seconds() >= 0:
                    available_players.append(player_name)

    if available_players:
        random.shuffle(available_players)
        return available_players[0]
    return None

def execute_aggravated_crime_logic(player_data):
    """Manages hacking, pickpocketing, mugging, armed robberies, and torch operations."""

    # import here to prevent circular import issue
    from modules.agg_repay import _repay_player
    from modules.armed_robbery import _perform_armed_robbery_attempt
    from modules.bne import _get_suitable_bne_target, _perform_bne_attempt
    from modules.hack import _perform_hack_attempt
    from modules.mug import _perform_mugging_attempt
    from modules.pickpocket import _perform_pickpocket_attempt
    from modules.torch import _perform_torch_attempt

    # Hard block: cannot attempt AgCrime while Services are queued
    if community_service_queue_count() > 0:
        print("Aggravated Crime blocked: mandatory Community Service queued. Skipping until queue is cleared.")
        global_vars._script_agg_crime_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
        return False

    do_hack      = global_vars.cfg_bool('Hack', 'DoHack', False)
    hack_repay   = global_vars.cfg_bool('Hack', 'Repay', False)
    hack_min     = global_vars.cfg_int('Hack', 'min_amount', 1)
    hack_max     = global_vars.cfg_int('Hack', 'max_amount', 100)

    do_pickpocket    = global_vars.cfg_bool('PickPocket', 'DoPickPocket', False)
    pickpocket_repay = global_vars.cfg_bool('PickPocket', 'Repay', False)
    pickpocket_min   = global_vars.cfg_int('PickPocket', 'min_amount', 1)
    pickpocket_max   = global_vars.cfg_int('PickPocket', 'max_amount', 100)

    do_mugging    = global_vars.cfg_bool('Mugging', 'DoMugging', False)
    mugging_repay = global_vars.cfg_bool('Mugging', 'Repay', False)
    mugging_min   = global_vars.cfg_int('Mugging', 'min_amount', 1)
    mugging_max   = global_vars.cfg_int('Mugging', 'max_amount', 100)

    do_bne     = global_vars.cfg_bool('BnE', 'DoBnE', False)
    bne_repay  = global_vars.cfg_bool('BnE', 'Repay', True)
    # Handles either a single value like "Flat" or a CSV like "Flat, Studio Unit"
    bne_target_apartments = [s.lower() for s in global_vars.cfg_list('BnE', 'BnETarget')]

    do_armed_robbery = global_vars.cfg_bool('Armed Robbery', 'DoArmedRobbery', False)
    do_torch         = global_vars.cfg_bool('Torch', 'DoTorch', False)

    # --- PRIORITY: Torch over Armed Robbery when both are enabled ---
    if do_torch and do_armed_robbery:
        print("\n--- Aggravated Crimes (priority: Torch first, second Armed Robbery) ---")

        # 1) Try Torch first
        if _open_aggravated_crime_page("Torch"):
            if _perform_torch_attempt(player_data):
                _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
                print("Torch attempt initiated. Main Aggravated Crime cooldown set.")
                return True
        else:
            # If we couldn't even open the page, still consider AR fallback
            print("FAILED to open Torch page; considering Armed Robbery fallback.")

        # 2) Fallback to Armed Robbery if Torch wasn't viable
        print("Torch unavailable/no viable targets — trying Armed Robbery…")
        if _open_aggravated_crime_page("Armed Robbery") and _perform_armed_robbery_attempt(player_data):
            _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
            print("Armed Robbery attempt initiated. Main Aggravated Crime cooldown set.")
            return True

        # 3) Neither Torch nor AR could be initiated
        # (Short re-check timers may already be set by the subroutines.)
        print("No viable Torch or Armed Robbery targets right now.")
        return False


    enabled_crimes = [crime_type for crime_type, enabled_status in {
        'Hack': do_hack,
        'Pickpocket': do_pickpocket,
        'Mugging': do_mugging,
        'Armed Robbery': do_armed_robbery,
        'Torch': do_torch,
        'BnE': do_bne,
    }.items() if enabled_status]

    if not enabled_crimes:
        return False

    # Randomly select one of the enabled crimes
    crime_type = random.choice(enabled_crimes)

    # If Hack was selected but you're not in home city, switch to another enabled crime
    if crime_type == "Hack":
        current_city = player_data.get("Location")
        if current_city != player_data.get("Home City"):
            fallback_pool = [c for c in enabled_crimes if c != "Hack"]
            if not fallback_pool:
                print(f"Skipping Hack: not in home city ('{current_city}' vs '{player_data.get('Home City')}'), and no other crimes enabled.")
                return False
            crime_type = random.choice(fallback_pool)
            print(f"Skipping Hack outside home city. Switching to {crime_type}.")

    print(f"\n--- Beginning Aggravated Crime ({crime_type}) Operation ---")

    crime_attempt_initiated = False

    # Hacking
    if crime_type == "Hack":
        min_steal = hack_min
        max_steal = hack_max
        cooldown_key = global_vars.MAJOR_CRIME_COOLDOWN_KEY

        # Only hack if in home city
        current_city = player_data.get("Location")
        if current_city != player_data.get("Home City"):
            print(f"Skipping Hack: Current city '{current_city}' is not home city '{player_data.get('Home City')}'.")
            return False

        if not _open_aggravated_crime_page("Hack"):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()
        retried_no_money = set()

        while attempts_in_cycle < max_attempts_per_cycle:
            current_target_player = _get_suitable_crime_target(player_data['Home City'], player_data['Character Name'], tried_players_in_cycle, cooldown_key)
            if not current_target_player:
                print(f"No more suitable {crime_type} targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
                print(f"Will retry {crime_type} in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_hack_attempt(current_target_player, min_steal, max_steal, retried_no_money)

            if status == 'success':
                if hack_repay and global_vars.hacked_player_for_repay and global_vars.hacked_amount_for_repay:
                    if global_vars.hacked_player_for_repay in retried_no_money:
                        print(f"Skipping repay to {global_vars.hacked_player_for_repay} because we primed with $1 for the retry (looks botty otherwise).")
                    else:
                        _repay_player(global_vars.hacked_player_for_repay, global_vars.hacked_amount_for_repay)
                print(f"{crime_type} successful! Exiting attempts for this cycle.")
                break

            elif status in ['cooldown_target', 'not_online', 'no_money', 'non_existent_target', 'wrong_city']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page("Hack"):
                    print(f"FAILED: Failed to re-open {crime_type} page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break

            elif status in ['failed_password', 'failed_attempt', 'failed_proxy', 'general_error']:
                print(f"{crime_type} failed for {target_attempted} (status: {status}). Exiting attempts for this cycle.")
                break

    # Pickpocket
    elif crime_type == "Pickpocket":
        min_steal = pickpocket_min
        max_steal = pickpocket_max
        cooldown_key = global_vars.MINOR_CRIME_COOLDOWN_KEY

        if not _open_aggravated_crime_page(crime_type):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()

        while attempts_in_cycle < max_attempts_per_cycle:
            current_target_player = _get_suitable_pp_mug_target_online(player_data['Character Name'], tried_players_in_cycle)
            if not current_target_player:
                print(f"No more suitable {crime_type} targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
                print(f"Will retry {crime_type} in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_pickpocket_attempt(current_target_player, min_steal, max_steal)

            if status == 'success':
                if pickpocket_repay:
                    if global_vars.pickpocketed_player_for_repay and global_vars.pickpocketed_amount_for_repay:
                        _repay_player(global_vars.pickpocketed_player_for_repay, global_vars.pickpocketed_amount_for_repay)
                print(f"{crime_type} successful! Exiting attempts for this cycle.")
                break
            elif status in ['cooldown_target', 'not_online', 'no_money', 'failed_proxy', 'non_existent_target', 'wrong_city']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page(crime_type):
                    print(f"FAILED: Failed to re-open {crime_type} page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break


            elif status in ['failed_password', 'failed_attempt', 'general_error']:
                print(f"{crime_type} failed for {target_attempted} (status: {status}). Exiting attempts for this cycle.")
                break

    # Mugging
    elif crime_type == "Mugging":
        min_steal = mugging_min
        max_steal = mugging_max
        cooldown_key = global_vars.MINOR_CRIME_COOLDOWN_KEY

        if not _open_aggravated_crime_page(crime_type):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()

        while attempts_in_cycle < max_attempts_per_cycle:
            current_target_player = _get_suitable_pp_mug_target_online(player_data['Character Name'], tried_players_in_cycle)
            if not current_target_player:
                print(f"No more suitable {crime_type} targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
                print(f"Will retry {crime_type} in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_mugging_attempt(current_target_player, min_steal, max_steal)

            if status == 'success':
                if mugging_repay:
                    if global_vars.mugging_player_for_repay and global_vars.mugging_amount_for_repay:
                        _repay_player(global_vars.mugging_player_for_repay, global_vars.mugging_amount_for_repay)
                print(f"{crime_type} successful! Exiting attempts for this cycle.")
                break
            elif status in ['cooldown_target', 'not_online', 'no_money', 'failed_proxy', 'non_existent_target', 'wrong_city']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page(crime_type):
                    print(f"FAILED: Failed to re-open {crime_type} page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break

            elif status in ['failed_password', 'failed_attempt', 'general_error']:
                print(f"{crime_type} failed for {target_attempted} (status: {status}). Exiting attempts for this cycle.")
                break

    # BnE
    elif crime_type == "BnE":
        if not _open_aggravated_crime_page("BnE"):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()

        current_city = player_data.get("Location")
        character_name = player_data.get("Character Name")

        while attempts_in_cycle < max_attempts_per_cycle:
            # First try with the configured apartment filter (if any)
            current_target_player = _get_suitable_bne_target(
                current_city, character_name, tried_players_in_cycle, apartment_filters=bne_target_apartments)

            # Fallback to anyone if a filter was set but no target found
            if not current_target_player and bne_target_apartments:
                print(f"No BnE targets with apartments {bne_target_apartments}. Falling back to any apartment.")
                current_target_player = _get_suitable_bne_target(current_city, character_name, tried_players_in_cycle, apartment_filters=None)

            if not current_target_player:
                print("No more suitable BnE targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(
                    minutes=retry_minutes)
                print(f"Will retry BnE in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_bne_attempt(current_target_player, repay_enabled=bne_repay)

            if status == 'success':
                if bne_repay and global_vars.bne_player_for_repay and global_vars.bne_amount_for_repay:
                    _repay_player(global_vars.bne_player_for_repay, global_vars.bne_amount_for_repay)
                print("BnE successful! Exiting attempts for this cycle.")
                break

            elif status == 'failed_attempt':
                print("BnE attempt failed. Exiting attempts for this cycle.")
                break

            elif status in ['cooldown_target', 'no_apartment', 'general_error', 'wrong_city', 'non_existent_target']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page("BnE"):
                    print("FAILED: Failed to re-open BnE page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break

    # Armed Robbery
    elif crime_type == "Armed Robbery":
        if not _open_aggravated_crime_page("Armed Robbery"):
            return False
        if _perform_armed_robbery_attempt(player_data):
            crime_attempt_initiated = True
            _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
            print("Armed Robbery attempt initiated. Main Aggravated Crime cooldown set.")
            return True
        else:
            print("Armed Robbery attempt not initiated (e.g., no suitable targets found or pre-attempt failures).")
            return False

    # Torch
    elif crime_type == "Torch":
        if not _open_aggravated_crime_page("Torch"):
            return False
        if _perform_torch_attempt(player_data):
            crime_attempt_initiated = True
            _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
            print("Torch attempt initiated. Main Aggravated Crime cooldown set.")
            return True
        else:
            print("Torch: No eligible targets with asterisk found. Skipping general cooldown for now.")
            return False

    # --- Final cooldown handling ---
    short_retry_set = (global_vars._script_aggravated_crime_recheck_cooldown_end_time and global_vars._script_aggravated_crime_recheck_cooldown_end_time > datetime.datetime.now())

    if crime_attempt_initiated and not short_retry_set:
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
        print(f"Finished {crime_type} attempts for this cycle. Aggravated Crime cooldown set.")
        return True
    elif not short_retry_set:
        retry_minutes = random.randint(3, 5)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
        print(f"Finished {crime_type} attempts for this cycle. No crime attempt initiated. Will retry in {retry_minutes} minutes.")
        return False
    else:
        print(f"Short retry cooldown already set for {crime_type}. Skipping long cooldown.")
        return False