import datetime
import random

from selenium.webdriver.common.by import By

import global_vars
from global_vars import cfg_bool
from helper_functions import _navigate_to_page_via_menu, _find_element, _find_and_click

def community_services(initial_player_data):
    """Manages and performs community service operations based on the player's location."""
    print("\n--- Beginning Community Service Operation ---")

    home_city = initial_player_data.get("Home City")

    # Only do CS if Jail Break is visible in Aggravated Crimes, and CSNotToRemoveBnE is enabled in settings.ini
    try:
        cs_guard = cfg_bool('BnE', 'CSNotToRemoveBnE', False)
    except Exception:
        cs_guard = False

    if cs_guard:
        # Open Aggravated Crimes to inspect radios
        if not _navigate_to_page_via_menu(
                "//span[@class='income']",
                "//a[@href='/income/agcrime.asp'][normalize-space()='Aggravated Crimes']",
                "Aggravated Crimes Page"):
            print("FAILED: Could not open Aggravated Crimes to check Jail Break. Short cooldown.")
            global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
            return False

        # Look for Jail Break radio
        jail_break_radio = _find_element(By.XPATH, "//input[@id='jailbreak']", timeout=1.5)
        if not jail_break_radio:
            print("Jail Break not present. Skipping Community Service to preserve BnE/JB mix.")
            global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(5, 8))
            return False
        else:
            print("Jail Break present; proceeding with Community Service.")

    if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//a[normalize-space()='Community Service']",
            "Community Services Page"
    ):
        print("FAILED: Failed to open Community Services menu.")
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    service_clicked = False

    print(f"In home city ({home_city}). Attempting regular community services.")
    community_service_options = [
        "reading", "suspect", "football", "delivery", "pamphlets",
        "kids", "weeding", "tags", "gum"
    ]
    try:
        # Get all matching visible elements in one go
        service_elements = global_vars.driver.find_elements(By.XPATH, "//input[@type='radio' and @id]")

        # Filter by only the known IDs in order
        filtered_services = [elem for elem in service_elements if elem.get_attribute("id") in community_service_options and elem.is_displayed()]

        if filtered_services:
            # Click the last one available (bottom-most)
            filtered_services[-1].click()
            selected_id = filtered_services[-1].get_attribute("id")
            print(f"Clicked community service: {selected_id}")
            service_clicked = True
        else:
            print("No regular community service option could be selected.")
    except Exception as e:
        print(f"ERROR while trying to find community services: {e}")
    if not service_clicked:
        print("No regular community service option could be selected.")

    if service_clicked:
        if _find_and_click(By.XPATH, "//input[@name='B1']"):
            print("Community Service commenced successfully.")
            return True
        else:
            print("FAILED: Failed to click 'Commence Service' button.")
    else:
        print("No community service option could be selected or commenced.")
    global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
    return False

def community_service_foreign(initial_player_data):
    """
    Performs Community Service when not in your home city.
    Does NOT check Jail Break guard.
    """
    print("\n--- Beginning Foreign Community Service Operation ---")

    # Navigate to CS page
    if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//a[normalize-space()='Community Service']",
            "Community Services Page"):
        print("FAILED: Could not open Community Services menu.")
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # Click the foreign CS option
    if _find_and_click(By.NAME, "csinothercities"):
        print("Clicked 'CS in other cities'.")
        if _find_and_click(By.XPATH, "//input[@name='B1']"):
            print("Foreign Community Service commenced successfully.")
            return True
        else:
            print("FAILED: Could not click 'Commence Service' button (foreign).")
    else:
        print("FAILED: Could not find or click 'CS in other cities' option.")

    # Short cooldown if failed
    global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
    return False