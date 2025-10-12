import datetime
import random

from selenium.webdriver.common.by import By

import global_vars
from database_functions import set_player_data, _set_last_timestamp
from helper_functions import _find_and_send_keys, _find_and_click, _get_element_text
from modules.agg_helpers import log_aggravated_event
from timer_functions import get_current_game_time

def _perform_mugging_attempt(target_player_name, min_steal, max_steal):
    """Performs a mugging attempt."""

    global_vars.mugging_player_for_repay = None
    global_vars.mugging_amount_for_repay = None
    global_vars.mugging_successful = False

    steal_amount = random.randint(min_steal, max_steal)
    crime_type = "Mugging"

    if not _find_and_send_keys(By.XPATH, "//input[@name='mugging']", target_player_name):
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

    if "try them again later" in result_text:
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=5))
        return 'cooldown_target', target_player_name, None

    if "must be online" in result_text:
        print(f"Target '{target_player_name}' is not online. Skipping pickpocketing.")
        return 'not_online', target_player_name, None

    if "The name you typed in" in result_text:
        print(f"INFO: Target '{target_player_name}' does not exist.")
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=15))
        return 'non_existent_target', target_player_name, None

    if "The victim must be in the same" in result_text:
        print(f"INFO: Target '{target_player_name}' is not in the same city.")
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=30))
        return 'wrong_city', target_player_name, None

    # Failed too many
    if "as you have failed too many" in result_text.lower():
        now = get_current_game_time()
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return 'aggs_blocked', None, None

    if f"You mugged" in result_text and "for $" in result_text:
        try:
            stolen_name_match = result_text.split("You mugged ")[1].split(" for $")[0].strip()
            stolen_amount_str = result_text.split(" for $")[1].split("!")[0].strip()
            stolen_actual_amount = int(''.join(filter(str.isdigit, stolen_amount_str)))

            set_player_data(stolen_name_match, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1, minutes=55))
            global_vars.mugging_player_for_repay = stolen_name_match
            global_vars.mugging_amount_for_repay = stolen_actual_amount
            global_vars.mugging_successful = True
            log_aggravated_event(crime_type, stolen_name_match, "Success", stolen_actual_amount)
            return 'success', stolen_name_match, stolen_actual_amount
        except Exception:
            log_aggravated_event(crime_type, target_player_name, "Script Error (Parse Success)", 0)
            return 'general_error', target_player_name, None

    if "and failed!" in result_text:
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1, minutes=55))
        log_aggravated_event(crime_type, target_player_name, "Failed", 0)
        return 'failed_attempt', target_player_name, None

    log_aggravated_event(crime_type, target_player_name, "Failed", 0)
    return 'general_error', target_player_name, None