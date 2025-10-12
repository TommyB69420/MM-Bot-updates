import datetime
import random
import re
import time

from selenium.webdriver.common.by import By

import global_vars
from aws_botusers import get_bankers_by_city
from helper_functions import _navigate_to_page_via_menu, _find_and_click, _find_element, _get_element_text, _find_and_send_keys

def manufacture_drugs():
    """
    Manages and performs drug manufacturing operations.
    Only works if occupation is 'Gangster'.
    """
    print("\n--- Beginning Drug Manufacturing Operation ---")

    if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//a[normalize-space()='Drugs']",
            "Drugs Page"
    ):
        print("FAILED: Navigation to Drugs Page failed.")
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    if not _find_and_click(By.XPATH, "//strong[normalize-space()='Manufacture Drugs at the local Drug House']"):
        print("FAILED: Could not click 'Manufacture Drugs' link.")
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    select_dropdown_xpath = "//select[@name='action']"
    yes_option_xpath = "/html/body/div[4]/div[4]/div[1]/div[2]/form/select/option[2]"

    if not _find_and_click(By.XPATH, select_dropdown_xpath):
        print("FAILED: Could not click on the drug manufacturing dropdown.")
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    if not _find_and_click(By.XPATH, yes_option_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        print("FAILED: Could not select 'Yes, I want to work at the drug house'.")
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    submit_button_xpath = "//input[@name='B1']"
    if not _find_and_click(By.XPATH, submit_button_xpath):
        print("FAILED: Could not click 'Submit' for drug manufacturing.")
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    try:
        fail_element = global_vars.driver.find_element(By.XPATH, "//div[@id='fail']")
        fail_text = fail_element.text.strip()
        print(f"Manufacture Result: {fail_text}")

        if "can't manufacture at this" in fail_text:
            print("Drug house is overstocked. Setting 10-minute cooldown.")
            global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=10)
            return False

    except Exception:
        # No fail message found
        pass

    print("Successfully initiated drug manufacturing.")
    return True

def laundering(player_data):
    """Launder dirty money via Income menu. Can set preferred launder contacts in settings.ini"""

    print("\n--- Money Laundering ---")

    # Load player money + launder config
    dirty = int(player_data.get("Dirty Money", 0))
    reserve = global_vars.cfg_int('Launder', 'Reserve', 0)
    preferred_list = [s.strip() for s in global_vars.cfg_list('Launder', 'Preferred')]
    preferred_raw = ', '.join(preferred_list)
    preferred = {n.strip().lower() for n in preferred_raw.split(",") if n.strip()}

    # If dirty ≤ reserve: always trickle $5 (banker > preferred > fallback); skip only if dirty < $5
    if dirty <= reserve:
        print(f"Dirty money: ${dirty}. Reserve: ${reserve}. Trickling laundering $5")

    # Navigate via Income → Money Laundering
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[normalize-space()='Money Laundering']",
        "Money Laundering Page"):
        print("FAILED: open Money Laundering via menu.")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # Find laundering contacts table
    table = _find_element(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/table")
    if not table:
        print("No laundering contacts. Backing off 30m.")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
        return False

    # Gather all rows (excluding header)
    rows = table.find_elements(By.TAG_NAME, "tr")[1:]
    target_link = None
    fallback_link = None

    # Laundering Bot Users work: pick any bot user banker whose HomeCity == current city
    current_city = (player_data.get("Location") or "").strip()
    banker_priority = set()
    if current_city:
        banker_priority = get_bankers_by_city(current_city)
        if banker_priority:
            print(f"Laundering Bot Users Work is active in {current_city}: {sorted(list(banker_priority))}")
        else:
            print(f"No banker bot users in {current_city}; using normal preference order.")
    else:
        print("Unknown current city; skipping banker override.")

    # Scan rows for banker override, then preferred, then anyone
    for row in rows:
        try:
            link = row.find_element(By.XPATH, ".//td[1]/a")
            name = (link.text or "").strip()
            if not name:
                continue
            lname = name.lower()

            # 1) Launder with bot users first
            if lname in banker_priority:
                target_link = link
                print(f"[Launder] Choosing banker bot user in {current_city}: {name}")
                break

            # 2) Preferred launderer second
            if lname in preferred:
                target_link = link
                print(f"Preferred launderer: {name}")
                break

            # 3) First available fallback
            if fallback_link is None:
                fallback_link = link
                print(f"Set first available launderer as fallback: {name}")

        except Exception:
            continue

    # Use fallback if no preferred launderer was found
    if not target_link:
        if not fallback_link:
            print("No suitable launderers. Backing off 30m.")
            global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
            return False
        target_link = fallback_link
        print("No preferred launderer found, using first available.")

    # Click into chosen launderer
    try:
        target_link.click()
        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
    except Exception as e:
        print(f"FAILED: click launderer: {e}")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # Read max launderable amount from contact page
    max_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form[1]/p[1]/font")
    if not max_text:
        print("No 'max' text on contact page.")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    m = re.search(r"\$(\d[\d,]*)\s*max", max_text)
    if not m:
        print("Couldn't parse max amount.")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    max_amt = int(m.group(1).replace(",", ""))

    if dirty > reserve:
        # Normal laundering: clean as much as possible under reserve
        amt = min(max_amt, dirty - reserve)
    else:
        # If already at or below reserve: trickle $5 each time (only if dirty >= 5)
        amt = 5 if dirty >= 5 else 0

    if amt <= 0:
        print(f"Nothing to launder (dirty ${dirty}, reserve ${reserve}, max ${max_amt}).")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(300, 600))
        return False

    # Enter amount to launder
    if not _find_and_send_keys(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form[1]/p[1]/input", str(amt)):
        print("FAILED: enter amount.")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # Click submit
    if not _find_and_click(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form[1]/p[2]/input"):
        print("FAILED: click 'Launder'.")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    print(f"Successfully initiated laundering of ${amt}.")
    return True