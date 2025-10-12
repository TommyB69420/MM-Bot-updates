import datetime
import random
import re
import time

from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support import expected_conditions as ec

import global_vars
from comms_journals import send_discord_notification
from database_functions import _set_last_timestamp
from helper_functions import _get_element_text, _find_and_click
from modules.agg_helpers import log_aggravated_event
from modules.agg_repay import _get_business_owner_and_repay
from timer_functions import parse_game_datetime, get_current_game_time


def _perform_armed_robbery_attempt(player_data, selected_business_name=None):
    """
    Performs an armed robbery attempt, including selecting a valid business and handling outcomes.
    Assumes the script is ALREADY on the Armed Robbery specific business selection page.
    Returns True on successful initiation of an attempt (even if it fails or yields no money),
    False otherwise (e.g., no eligible targets after retries).
    """
    global_vars.armed_robbery_amount_for_repay = None
    global_vars.armed_robbery_business_name_for_repay = None
    global_vars.armed_robbery_successful = False

    # --- Locate dropdown ---
    dropdown_xpath = "/html/body/div[4]/div[4]/div[2]/div[2]/form/p[2]/select"
    try:
        dropdown_element = global_vars.wait.until(ec.presence_of_element_located((By.XPATH, dropdown_xpath)))
    except TimeoutException:
        print("FAILED: Armed Robbery dropdown not found. Cannot proceed with armed robbery.")
        global_vars._script_armed_robbery_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(1, 3))
        return False

    select = Select(dropdown_element)
    options = select.options

    # --- Find eligible businesses ---
    eligible_businesses = []
    for option in options:
        business_text = option.text.strip()
        if business_text != "Please Select..." and "Drug House" not in business_text and "*" in business_text:
            business_name_for_value = business_text.replace('*', '').strip()
            eligible_businesses.append((business_name_for_value, business_text))

    if not eligible_businesses:
        print("No businesses with an asterisk (excluding Drug House) found for Armed Robbery. Setting short re-check timer.")
        global_vars._script_armed_robbery_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(45, 110))
        return False

    selected_business_name, selected_business_full_option_text = random.choice(eligible_businesses)
    print(f"Attempting Armed Robbery at: {selected_business_name} (Full option text: {selected_business_full_option_text})")

    # --- Select business ---
    try:
        select.select_by_visible_text(selected_business_full_option_text)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        print(f"Successfully selected business '{selected_business_name}' from dropdown.")
    except Exception as e:
        print(f"FAILED: Could not select business '{selected_business_name}' in dropdown using Select class: {e}")
        return False

    # --- Click 'Commit Crime' button ---
    commit_crime_button_xpath = "//input[@name='B1']"
    if not _find_and_click(By.XPATH, commit_crime_button_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        print("FAILED: Could not click final 'Commit Crime' button for Armed Robbery.")
        return False

    # --- Get result text ---
    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event("Armed Robbery", selected_business_name, "Script Error (No Result Msg)", 0)
        return True

    # --- Knockout handling ---
    knockout_text = _get_element_text(By.XPATH, "//span[@class='large']")
    if knockout_text and "It knocked you right out" in global_vars.driver.page_source:
        print(f"Knockout detected! Timer string: '{knockout_text}'")

        release_time = parse_game_datetime(knockout_text)
        current_game_time_text = _get_element_text(By.XPATH, "//*[@id='header_time']/div")
        current_game_time = parse_game_datetime(current_game_time_text)

        if release_time and current_game_time:
            seconds_remaining = (release_time - current_game_time).total_seconds()
            if 0 < seconds_remaining < 600:
                readable_minutes = int(seconds_remaining // 60)
                readable_seconds = int(seconds_remaining % 60)
                global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds_remaining + 5)

                print(f"Knocked out until {release_time}. Sleeping actions for {seconds_remaining:.0f} seconds.")
                send_discord_notification(
                    f"KO! You’ve been knocked out by debris during an armed robbery.\n"
                    f"Release in {readable_minutes}m {readable_seconds}s (at {release_time.strftime('%I:%M:%S %p')})"
                )
                return True

        else:
            print("Failed to parse knockout release time. Proceeding with default logic.")

    # --- Result cases ---

    now = get_current_game_time()

    # Failed too many
    if "as you have failed too many" in (result_text or "").lower():
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return False

    if "You managed to hold up the" in result_text:
        try:
            business_match = re.search(r'hold up the (.+?)(?: and| -| nothing|!| for \$|$)', result_text)
            stolen_business_name = business_match.group(1).strip() if business_match else selected_business_name or "Unknown Business"
            stolen_business_name = re.sub(r'[\`\n\r\t]', '', stolen_business_name).strip().lower()

            if " for $" in stolen_business_name:
                stolen_business_name = stolen_business_name.split(" for $")[0].strip()

            # Normalize to known business keys
            for known_business in global_vars.PUBLIC_BUSINESS_OCCUPATION_MAP:
                if known_business in stolen_business_name:
                    stolen_business_name = known_business
                    break

            amount_match = re.search(r'\$\d[\d,]*', result_text)
            stolen_actual_amount = int(amount_match.group(0).replace('$', '').replace(',', '')) if amount_match else 0

            print(f"Successfully robbed {stolen_business_name}. Stolen: ${stolen_actual_amount}")

            log_aggravated_event("Armed Robbery", stolen_business_name, "Success", stolen_actual_amount)
            global_vars.armed_robbery_amount_for_repay = stolen_actual_amount
            global_vars.armed_robbery_business_name_for_repay = stolen_business_name
            global_vars.armed_robbery_successful = True

            if stolen_actual_amount > 0 and global_vars.cfg_bool('Armed Robbery', 'Repay', False):
                print(f"Repaying ${stolen_actual_amount} to {stolen_business_name}")
                _get_business_owner_and_repay(stolen_business_name, stolen_actual_amount, player_data)
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                print("Repayment completed.")
            else:
                print("No repayment needed (either 0 stolen or repay disabled).")

            return True

        except Exception as e:
            print(f"Error parsing success result: {e}")
            log_aggravated_event("Armed Robbery", selected_business_name or "Unknown Business", "Script Error (Success Parse)", 0)
            global_vars.armed_robbery_successful = False
            return True

    print("Armed Robbery failed. No success message found.")
    log_aggravated_event("Armed Robbery", selected_business_name or "Unknown Business", "Failed", 0)
    return True