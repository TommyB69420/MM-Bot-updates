import datetime
import random
import time

from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _find_and_click, _find_element, _find_elements_quiet, _navigate_to_page_via_menu, _get_element_text, _find_and_send_keys

def lawyer_casework():
    """
    Manages and processes lawyer cases.
    Only works if occupation is 'Lawyer'.
    """
    print("\n--- Beginning Lawyer Casework Operation ---")

    # Navigate to Court page
    court_menu_xpath = "//span[@class='court']"
    if not _find_and_click(By.XPATH, court_menu_xpath):
        print("FAILED: Navigation to Court menu for Lawyer Cases failed. Setting short cooldown.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    print("Successfully navigated to Lawyer Cases Page. Checking for cases...")

    # Read cases table
    cases_table_xpath = "/html/body/div[4]/div[4]/div[1]/div[2]/center/form/table"
    cases_table = _find_element(By.XPATH, cases_table_xpath)

    if cases_table:
        case_rows = cases_table.find_elements(By.TAG_NAME, "tr")[1:]
        for i, row in enumerate(case_rows):
            try:
                defend_button_xpath = ".//td[6]/a[@class='box green' and text()='DEFEND']"
                defend_button = _find_elements_quiet(By.XPATH, defend_button_xpath)
                if defend_button and _find_and_click(By.XPATH, defend_button_xpath):
                    print("Successfully clicked DEFEND for a lawyer case.")
                    return True
            except NoSuchElementException:
                pass
            except Exception as e:
                print(f"ERROR: Error processing a lawyer case row: {e}")

    # No defendable cases found — set standard back-off.
    wait_time = random.uniform(120, 180)
    global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_time)
    print(f"No lawyer cases found. Next check in {wait_time:.2f} seconds.")
    return False

def judge_casework(player_data):
    """Manages and processes judge cases."""
    print("\n--- Beginning Judge Casework Operation ---")

    # Navigate to judge page
    if not _navigate_to_page_via_menu(
            "//span[@class='court']",
            "//strong[normalize-space()='Assign sentences to pending cases']",
            "Judge Page"
    ):
        print("FAILED: Navigation to Judge Cases Page failed.")
        return False

    print("Successfully navigated to Judge Cases Page. Checking for cases...")

    # Read the case table
    cases_table = _find_element(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form/table")
    if not cases_table:
        cooldown = random.uniform(60, 120)
        print(f"FAILED: No cases table found. Setting cooldown of {cooldown:.2f} seconds.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=cooldown)
        return False

    # Process the table
    case_rows = cases_table.find_elements(By.TAG_NAME, "tr")[1:]
    processed_any_case = False

    # Read settings.ini for who to skip cases on
    skip_players = {
    s.strip().lower()
    for s in global_vars.cfg_list('Judge', 'Skip_Cases_On_Player')
    if isinstance(s, str) and s.strip()
    }

    # Define the rows to look at in the judge table
    for row in case_rows:
        try:
            suspect_name = row.find_element(By.XPATH, ".//td[3]//a").text.strip()
            victim_name = row.find_element(By.XPATH, ".//td[4]//a").text.strip()

            # Skip cases on yourself
            if player_data['Character Name'] in [suspect_name, victim_name]:
                print(f"Skipping case for self (Suspect: {suspect_name}, Victim: {victim_name}).")
                continue
            # Skip names listed in settings.ini
            if suspect_name.lower() in skip_players:
                print(f"Skipping case due to player in skip list (Suspect: {suspect_name}.")
                continue

            row.find_element(By.XPATH, ".//td[5]/input[@type='radio']").click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)

            if not _find_and_click(By.XPATH, "//input[@name='B1']"):
                continue

            # Read the crime type
            crime_committed = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[3]/div/table/tbody/tr[1]/td[4]")
            if not crime_committed:
                global_vars.driver.get("javascript:history.go(-2)")
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                continue

            if not _find_and_click(By.XPATH, "//input[@value='Submit']"):
                continue

            if process_judge_case_verdict(crime_committed, player_data['Character Name']):
                print(f"Successfully processed a case for {suspect_name}.")
                processed_any_case = True
                return True
            else:
                global_vars.driver.get("javascript:history.go(-2)")
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                continue

        except Exception as e:
            print(f"Exception during case processing: {e}")
            continue

    # Set cooldown if no judge cases
    if not processed_any_case:
        cooldown = random.uniform(60, 120)
        print(f"No valid judge cases processed. Waiting {cooldown:.2f} seconds before retry.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=cooldown)

    return False

def process_judge_case_verdict(crime_committed, character_name):
    """Applies fine, sets no community service/jail time, and submits verdict."""
    from selenium.common.exceptions import NoSuchElementException

    # --- Fine amount: prefer new nested map Judge.Fines, fallback to legacy flat keys ---
    crime_key = (crime_committed or "").strip().lower()
    fine_amount = None

    fines_map = global_vars.cfg_get('Judge', 'Fines', {})
    if isinstance(fines_map, dict):
        # case-insensitive lookup
        for k, v in fines_map.items():
            if isinstance(k, str) and k.strip().lower() == crime_key:
                try:
                    fine_amount = int(v)
                except Exception:
                    fine_amount = None
                break

    if fine_amount is None:
        # legacy fallback: value directly under [Judge] section
        fine_amount = global_vars.cfg_int('Judge', crime_committed, 1000)

    if not isinstance(fine_amount, int):
        fine_amount = 1000

    if fine_amount == 1000:
        print(f"Warning: Fine amount for crime '{crime_committed}' not found or invalid in settings. Defaulting to 1000.")

    # --- Fill fine and select 'No community service' (keeps your original XPaths) ---
    if not _find_and_send_keys(By.XPATH, "//input[@name='fine']", str(fine_amount)):
        return False

    if not _find_and_click(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div/center/form/p[4]/select/option[2]"):
        return False

    # --- Set jail time: prefer explicit 'no jail' option, else pick the smallest positive ---
    jail_time_dropdown = _find_element(By.XPATH, "//select[@name='sentence']")
    if jail_time_dropdown:
        try:
            no_jail_time_option = jail_time_dropdown.find_element(By.XPATH, "./option[2]")
            no_jail_time_option.click()
        except NoSuchElementException:
            options = jail_time_dropdown.find_elements(By.TAG_NAME, "option")
            min_jail_time_value = float('inf')
            min_jail_time_option = None
            for option in options:
                try:
                    value = int(option.get_attribute('value'))
                    if value > 0 and value < min_jail_time_value:
                        min_jail_time_value = value
                        min_jail_time_option = option
                except ValueError:
                    pass
            if min_jail_time_option:
                min_jail_time_option.click()
            else:
                return False
    else:
        return False

    # --- Submit verdict ---
    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        return False
    return True