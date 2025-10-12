import datetime
import random

from selenium.webdriver.common.by import By

import global_vars
from database_functions import set_player_data, remove_player_cooldown, _set_last_timestamp
from helper_functions import _find_and_send_keys, _find_and_click, _get_element_text
from modules.agg_helpers import log_aggravated_event, _open_aggravated_crime_page
from modules.money_handling import transfer_money
from timer_functions import get_current_game_time

def _perform_hack_attempt(target_player_name, min_steal, max_steal, retried_targets=None):
    """Performs a single hacking attempt."""

    if retried_targets is None:
        retried_targets = set()

    global_vars.hacked_player_for_repay = None
    global_vars.hacked_amount_for_repay = None
    global_vars.hacked_successful = False

    steal_amount = random.randint(min_steal, max_steal)
    crime_type = "Hack"

    if not _find_and_send_keys(By.XPATH, "//input[@name='hack']", target_player_name):
        return 'general_error', target_player_name, None
    if not _find_and_send_keys(By.XPATH, "//input[@name='cap']", str(steal_amount)):
        return 'general_error', target_player_name, None

    if not _find_and_click(By.XPATH, "//input[@name='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return 'general_error', target_player_name, None

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event(crime_type, target_player_name, "Script Error (No Result Msg)", 0)
        return 'general_error', target_player_name, None

    now = get_current_game_time()

    if "players account has increased security" in result_text:
        set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=3))
        return 'cooldown_target', target_player_name, None

    if "name you typed in" in result_text:
        print(f"INFO: Target '{target_player_name}' does not exist.")
        remove_player_cooldown(target_player_name)
        return 'non_existent_target', target_player_name, None

    if "as you have failed too many" in (result_text or "").lower():
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return 'aggs_blocked', None, None

    if "no money in their account" in result_text:
        # Allow the transfer+retry only once per target (for this cycle)
        if target_player_name in retried_targets:
            print(f"INFO: Target '{target_player_name}' still has no money and retry already used. Skipping further retries.")
            set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1))
            return 'no_money', target_player_name, None

        print(f"INFO: Target '{target_player_name}' has no money. Sending $1 and retrying once...")
        if transfer_money(1, target_player_name):
            retried_targets.add(target_player_name)
            print("Transfer successful. Retrying hack on same target using configured amount...")
            # Re-open Hack page after returning from Bank so the Hack form exists again
            if not _open_aggravated_crime_page("Hack"):
                print("FAILED: Could not re-open Hack page after transfer. Aborting retry.")
                return 'general_error', target_player_name, None
            # Re-enter details in the same way you already do (kept identical to your current flow)
            if not _find_and_send_keys(By.XPATH, "//input[@name='hack']", target_player_name):
                return 'general_error', target_player_name, None
            if not _find_and_send_keys(By.XPATH, "//input[@name='cap']", str(steal_amount)):
                return 'general_error', target_player_name, None
            if not _find_and_click(By.XPATH, "//input[@name='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
                return 'general_error', target_player_name, None
            # Read the new result and continue evaluation below
            result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]") or ""

            # If they still have no money after the $1 prime, park them for 24 hours and move on
            if "no money in their account" in (result_text or ""):
                print(f"INFO: Target '{target_player_name}' still has no money after $1 prime. Parking for 24h and moving on.")
                set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=24))
                return 'no_money', target_player_name, None
        else:
            print("Failed to transfer $1, skipping retry.")
            set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1))
            return 'no_money', target_player_name, None

    if f"You managed to {crime_type.lower()}" in result_text and "bank account" in result_text and "You transferred $" in result_text:
        try:
            stolen_name_match = \
                result_text.split(f"You managed to {crime_type.lower()} into ")[1].split("'s bank account")[0].strip()
            stolen_amount_str = result_text.split("You transferred $")[1].split(" to a fake account")[0].strip()
            stolen_actual_amount = int(''.join(filter(str.isdigit, stolen_amount_str)))

            set_player_data(stolen_name_match, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=12))
            global_vars.hacked_player_for_repay = stolen_name_match
            global_vars.hacked_amount_for_repay = stolen_actual_amount
            global_vars.hacked_successful = True
            log_aggravated_event(crime_type, stolen_name_match, "Success", stolen_actual_amount)
            return 'success', stolen_name_match, stolen_actual_amount
        except Exception:
            log_aggravated_event(crime_type, target_player_name, "Script Error (Parse Success)", 0)
            return 'general_error', target_player_name, None

    if "could not guess their password" in result_text:
        set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=12))
        log_aggravated_event(crime_type, target_player_name, "Failed", 0)
        return 'failed_password', target_player_name, None

    if "behind a proxy server" in result_text:
        set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=12))
        log_aggravated_event(crime_type, target_player_name, "Failed", 0)
        return 'failed_proxy', target_player_name, None

    log_aggravated_event(crime_type, target_player_name, "Failed", 0)
    return 'general_error', target_player_name, None