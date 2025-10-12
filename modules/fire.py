import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _navigate_to_page_via_menu, _find_and_click, _find_elements_quiet, _find_elements

def fire_casework(initial_player_data):
    """
    Executes firefighting logic (Attend Fires, Fire Investigations, and Fire Safety Inspections).
    """
    print("\n--- Beginning Fire Station Logic ---")

    # Navigate to Fire Station via city menu
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business fire_station']",
        "Fire Station"
    ):
        print("FAILED: Could not navigate to Fire Station via menu.")
        return False

    print("SUCCESS: Navigated to Fire Station. Opening 'Fires' tab...")

    # Click the "Fires" button before checking for work
    if not _find_and_click(By.XPATH, "//a[contains(text(),'Fires')]"):
        print("FAILED: Could not click 'Fires' tab. Aborting fire casework.")
        return False
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    print("SUCCESS: Opened 'Fires' tab. Checking for active fires...")

    # Attend Fire
    attend_fire_links = _find_elements_quiet(By.XPATH, "//tbody/tr[2]/td[4]/a[1]")
    if attend_fire_links:
        print("Found active fire. Attending...")
        try:
            attend_fire_links[0].click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
            return True
        except Exception as e:
            print(f"WARNING: Could not click Attend Fire link: {e}")

    # Fire Investigation
    print("No active fires found. Checking for Fire Investigations...")
    investigate_links = _find_elements_quiet(By.XPATH, "//a[normalize-space()='Investigate']")
    if investigate_links:
        print("Found Fire Investigation. Investigating...")
        try:
            investigate_links[0].click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
            return True
        except Exception as e:
            print(f"WARNING: Could not click Investigate link: {e}")

    # Fire Safety Inspections
    print("No investigations found. Checking for Fire Safety Inspections...")
    if _find_and_click(By.XPATH, "//a[normalize-space()='Fire safety inspections']"):
        print("Opened Fire Safety Inspections page.")
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        inspect_links = _find_elements_quiet(By.XPATH, "//a[contains(text(),'Inspect')]")
        if inspect_links:
            print("Found Fire Safety Inspection. Commencing inspection...")
            try:
                inspect_links[0].click()
                time.sleep(global_vars.ACTION_PAUSE_SECONDS)
                return True
            except Exception as e:
                print(f"WARNING: Could not click inspection link: {e}")
        else:
            print("No inspection opportunities found on Fire Safety Inspections page.")
    else:
        print("No 'Fire safety inspections' button found.")

    print("No active fires or investigations available. Setting fallback cooldown.")
    global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
    return False

def fire_duties():
    """
    Navigates to firefighter Duties, selects the last available duty, and trains.
    """
    print("\n--- Beginning Fire Fighter Duties ---")

    # Navigate to the Fire Duties page
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[normalize-space()='Fire Fighter Duties']",
        "Fire Fighter Duties"
    ):
        print("FAILED: Could not navigate to Fire Fighter Duties page.")
        return False

    # Find all available radio buttons
    radio_buttons = _find_elements(By.XPATH, "//input[@type='radio' and @name='comservice']")
    if not radio_buttons:
        print("No Fire Duty options found.")
        return False

    # Select the last available option
    last_radio = radio_buttons[-1]
    try:
        last_radio.click()
        print(f"Selected last available duty: {last_radio.get_attribute('value')}")
    except Exception as e:
        print(f"ERROR: Could not click last radio button. {e}")
        return False

    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Click the Train button
    train_buttons = _find_elements(By.XPATH, "//input[@name='B2']")
    if train_buttons:
        train_buttons[0].click()
        print("Clicked Train button.")
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        return True
    else:
        print("Train button not found.")
        return False