import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _navigate_to_page_via_menu, _find_elements_quiet, _find_element

def engineering_casework(player_data):
    """
    Super-simple engineering: open Maintenance & Construction via Income menu,
    pick the first available job, submit. No prioritization.
    """

    print("\n--- Beginning Engineering Casework ---")

    # Navigate via menus
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[normalize-space()='Maintenance and Construction']",
        "Maintenance and Construction Page"):
        print("FAILED: Navigation to Maintenance and Construction page failed.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    print("On Maintenance & Construction. Looking for the first available task…")

    # Capture your own name for filtering
    your_character_name = (player_data or {}).get("Character Name", "")

    # Find all selectable tasks
    radios = _find_elements_quiet(By.XPATH, ".//*[@id='holder_content']//input[@type='radio']")
    if not radios:
        print("No selectable tasks (no radio inputs found). Short cooldown.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    # Prefer the Construction Site / Business Repairs form if present
    construction_radio = None
    try:
        # strictly repair your own business's, nothing else
        form = _find_element(By.XPATH, "//form[input[@name='display' and @value='bus_repair']]", timeout=1, suppress_logging=True)

        if form:
            construction_radio = form.find_element(By.XPATH, ".//input[@type='radio']")
    except Exception:
        construction_radio = None

    selected_radio = None
    if construction_radio:
        print("Found Construction Site / Business Repairs task. Selecting it even if owned by self.")
        selected_radio = construction_radio
    else:
        # Fallback – pick the last available task, skipping self-owned
        for candidate in reversed(radios):  # Select last most radio button
            try:
                container_text = candidate.find_element(By.XPATH, "./ancestor::tr[1]").text
                if your_character_name and your_character_name.lower() in container_text.lower():
                    print(f"Skipping self-owned engineering task ({your_character_name}).")
                    continue
                selected_radio = candidate
                break
            except Exception as e:
                print(f"Warning: could not read a task row: {e}")

    if not selected_radio:
        print("All available engineering tasks belong to you. Short cooldown.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    # Click the chosen radio
    try:
        selected_radio.click()
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    except Exception as e:
        print(f"FAILED: Could not click the selected radio: {e}")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    # Submit the nearest form for that radio (its ancestor form)
    try:
        form = selected_radio.find_element(By.XPATH, "./ancestor::form[1]")
        submit = form.find_element(By.XPATH, ".//input[@type='submit' or @class='submit']")
        submit.click()
        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
        print("Successfully started a non-self engineering task.")
        return True
    except Exception as e:
        print(f"FAILED: Could not submit the selected task: {e}")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False