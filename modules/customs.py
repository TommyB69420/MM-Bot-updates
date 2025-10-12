import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from helper_functions import blind_eye_queue_count, _navigate_to_page_via_menu, _find_and_click, _get_dropdown_options, _select_dropdown_option, dequeue_blind_eye

def customs_blind_eyes():
    """
    Executes ONE 'Turn a Blind Eye' if anything is queued and returns True on success.
    Assumes the *caller* only invokes this when the Trafficking/AgCrime timer is ready (<= 0).
    """
    if blind_eye_queue_count() <= 0:
        return False

    # Navigate to the aggravated crime menu
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[@href='/income/agcrime.asp'][normalize-space()='Aggravated Crimes']",
        "Aggravated Crimes"):
        print("FAILED: navigate to Aggravated Crimes")
        return False

    # Select radio value 'blindeye', then submit
    if not _find_and_click(By.XPATH, "//input[@type='radio' and @name='agcrime' and @value='blindeye']"):
        print("FAILED: blindeye radio not found")
        return False

    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        print("FAILED: Commit Crime button not found/clickable")
        return False

    # On blindeye.asp, select a target from the dropdown, then submit
    select_xpath = ("//form[@action='blindeye.asp']//select[@name='gangster'] | "
                    "//div[@id='holder_content']//form//select[@name='gangster']")

    # Get all options
    options = _get_dropdown_options(By.XPATH, select_xpath) or []
    # Filter out placeholders
    valid = [t.strip() for t in options if t and not t.lower().startswith(("please", "select", "choose", "—", "-", "–"))]

    if not valid:
        print(f"No valid Blind Eye targets available. Raw options: {options}")
        global_vars._script_trafficking_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
        return False

    print(f"Valid Blind Eye targets found: {valid}")

    choice = valid[0]
    if not _select_dropdown_option(By.XPATH, select_xpath, choice):
        print(f"FAILED: Could not select '{choice}' from dropdown.")
        return False

    print(f"Selected '{choice}' from Blind Eye dropdown.")
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Submit button or fallback
    if not _find_and_click(By.XPATH, "//input[@type='submit' and (@name='B1' or contains(@value,'Turn a Blind Eye'))]"):
        print("FAILED: 'Turn a Blind Eye' submit not found/clickable")
        return False

    print(f"Submitted Blind Eye request for '{choice}'.")

    # if blind eye is success, consume 1 success token from the JSON file.
    if dequeue_blind_eye():
        remaining = blind_eye_queue_count()
        send_discord_notification(f"Turned a Blind Eye for '{choice}'. Remaining queued: {remaining}")
        print(f"Turned a Blind Eye for '{choice}'. Remaining queued: {remaining}")
    else:
        print("WARNING: Action done but queue could not be decremented (file read/write issue?)")

    return True