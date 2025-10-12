import datetime
import random
import re
import time

from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support import expected_conditions as ec

import global_vars
from database_functions import _set_last_timestamp
from helper_functions import _find_and_click, _get_element_text
from modules.agg_helpers import log_aggravated_event
from modules.agg_repay import _get_business_owner_and_repay
from timer_functions import get_current_game_time

def _perform_torch_attempt(player_data):
    """
    Performs a torch attempt, including selecting a valid business and handling outcomes.
    Assumes the script is ALREADY on the Torch specific business selection page.
    Returns True on successful initiation of an attempt (even if it fails or yields no money),
    False otherwise (e.g., no eligible targets after retries).
    """
    global_vars.torch_amount_for_repay = None
    global_vars.torch_business_name_for_repay = None
    global_vars.torch_successful = False

    torch_repay = global_vars.cfg_bool('Torch', 'Repay', False)
    blacklist_raw = [s.lower() for s in global_vars.cfg_list('Torch', 'Blacklist')]
    blacklist_items = {item.strip() for item in blacklist_raw if item.strip()}
    blacklist_items.add("drug house") # Always blacklist drug house
    blacklist_items.add("fire station")  # Always blacklist fire station

    dropdown_xpath = "/html/body/div[4]/div[4]/div[2]/div[2]/form/p[2]/select"
    try:
        dropdown_element = global_vars.wait.until(ec.presence_of_element_located((By.XPATH, dropdown_xpath)))
    except TimeoutException:
        print("FAILED: Torch dropdown not found. Cannot proceed with torch.")
        # Setting a short re-check cooldown if the dropdown itself isn't found
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(1, 3))
        return False

    select = Select(dropdown_element)
    options = select.options

    eligible_businesses = []
    for option in options:
        business_text = option.text.strip()
        # Ensure it's not the default "Please Select..." option and contains an asterisk
        if business_text == "Please Select..." or "*" not in business_text:
            continue

        business_name_for_value = business_text.replace('*', '').strip()

        is_blacklisted = False
        if "public" in blacklist_items and business_name_for_value in global_vars.public_businesses:
            is_blacklisted = True
        if "private" in blacklist_items and business_name_for_value in global_vars.private_businesses:
            is_blacklisted = True
        for item in blacklist_items:
            if item != "public" and item != "private" and item in business_name_for_value.lower():
                is_blacklisted = True
                break

        if not is_blacklisted:
            eligible_businesses.append((business_name_for_value, business_text))
        else:
            print(f"Skipping blacklisted business for Torch: {business_name_for_value}")

    if not eligible_businesses:
        print(f"No eligible businesses found for Torch after applying blacklist. Setting short re-check cooldown.")
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(
            minutes=random.uniform(1, 3))
        return False

    selected_business_tuple = random.choice(eligible_businesses)
    selected_business_name = selected_business_tuple[0]
    selected_business_full_option_text = selected_business_tuple[1]

    print(f"Attempting Torch at: {selected_business_name}")

    try:
        select.select_by_visible_text(selected_business_full_option_text)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        print(f"Successfully selected business '{selected_business_name}' from dropdown.")
    except Exception as e:
        print(f"FAILED: Could not select business '{selected_business_name}' in dropdown: {e}")
        return False

    commit_crime_button_xpath = "//input[@name='B1']"
    if not _find_and_click(By.XPATH, commit_crime_button_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        print("FAILED: Could not click final 'Commit Crime' button for Torch.")
        return False

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event("Torch", selected_business_name, "Script Error (No Result Msg)", 0)
        return True

    if "managed to set ablaze" in result_text:
        try:
            print(f"Torch success result_text: {result_text}")

            business_name_re_match = re.search(r'managed to set ablaze the (.+?)!', result_text)
            torched_business_name = selected_business_name
            if business_name_re_match:
                extracted_name = business_name_re_match.group(1).strip()
                torched_business_name = f"{player_data.get('Location', '')} {extracted_name}".strip()
                torched_business_name = torched_business_name.lower()
            else:
                print(f"Could not parse torched business name from success message. Using selected_business_name: {selected_business_name}")
                torched_business_name = selected_business_name

            cost_match = re.search(r'\$(\d[\d,]*)(?:\s|\.|!)', result_text)
            extracted_cost = 0
            if cost_match:
                extracted_cost = int(cost_match.group(1).replace(',', ''))
            else:
                print(f"Could not parse torched cost from success message. Defaulting to 0.")

            print(f"Successfully torched {torched_business_name} at a cost of ${extracted_cost}.")
            log_aggravated_event("Torch", torched_business_name, "Success", extracted_cost)
            global_vars.torch_amount_for_repay = extracted_cost
            global_vars.torch_business_name_for_repay = torched_business_name
            global_vars.torch_successful = True

            if torch_repay and extracted_cost > 0:
                print(f"Torch - Repaying ${extracted_cost} to {torched_business_name}.")
                _get_business_owner_and_repay(torched_business_name, extracted_cost, player_data)
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                print(f"Torch repayment for {torched_business_name} queued.")
            else:
                print(f"Torch successful, but repayment is turned OFF. Skipping repayment.")
            return True

        except Exception as e:
            print(f"Error parsing successful Torch result: {e}")
            log_aggravated_event("Torch", selected_business_name, "Script Error (Parse Success)", 0)
            global_vars.torch_successful = False
            return True # An attempt was made, but parsing failed

    elif "recently survived" in result_text or "not yet repaired" in result_text:
        print(f"Business '{selected_business_name}' recently torched or not repaired. This will trigger a short re-check cooldown.")
        log_aggravated_event("Torch", selected_business_name, "Target Cooldown (No Repair/Recent Torching)", 0)
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(1, 3))
        global_vars.torch_successful = False
        return True

    elif "That business is your own" in result_text:
        print(f"Attempted to torch own business: {selected_business_name}. Setting long cooldown for this target.")
        log_aggravated_event("Torch", selected_business_name, "Own Business", 0)
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(days=1)
        global_vars.torch_successful = False
        return True

    # Failed too many
    elif "as you have failed too many" in result_text:
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        now = get_current_game_time()
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return False

    elif "failed" in result_text or "ran off" in result_text:
        print(f"Torch attempt at {selected_business_name} failed.")
        log_aggravated_event("Torch", selected_business_name, "Failed", 0)
        global_vars.torch_successful = False
        return True
    else:
        print(f"Unexpected result for Torch: {result_text}. This counts as an attempt.")
        log_aggravated_event("Torch", selected_business_name, "Unexpected Result", 0)
        global_vars.torch_successful = False
        return True