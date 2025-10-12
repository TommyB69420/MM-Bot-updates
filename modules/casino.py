import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from database_functions import _set_last_timestamp
from helper_functions import _get_element_text_quiet, _find_and_click, _find_and_send_keys, _navigate_to_page_via_menu

def casino_slots():
    """
    Plays $100 slots repeatedly until the game warns about addiction, then sets a 25h cooldown.
    """
    print("\n--- Beginning Casino Slots Operation ---")

    now = datetime.datetime.now()

    # Navigate to City page then Casino
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business casino']",
        "Casino"
    ):
        print("FAILED: Could not navigate to Casino.")
        # short, randomised recheck to avoid hammering when torched
        global_vars._script_casino_slots_cooldown_end_time = now + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # Select Slots radio button, click submit
    if not _find_and_click(By.XPATH, "//input[@id='slot']"):
        print("FAILED: Could not select 'Slots' radio.")
        global_vars._script_casino_slots_cooldown_end_time = now + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        print("FAILED: Could not click initial submit to enter Slots.")
        global_vars._script_casino_slots_cooldown_end_time = now + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # After entering Slots, immediately check if the page already shows the addiction fail box.
    early_fail_msg = _get_element_text_quiet(By.XPATH, "//div[@id='fail']", timeout=0.5)
    if early_fail_msg and 'get an addiction' in early_fail_msg.lower():
        print("Addiction warning detected immediately after entering Slots — setting 25h cooldown.")
        next_time = datetime.datetime.now() + datetime.timedelta(hours=25)
        _set_last_timestamp(global_vars.CASINO_NEXT_CHECK_FILE, next_time)
        global_vars._script_casino_slots_cooldown_end_time = next_time
        print(f"Casino Slots cooldown set until {next_time.strftime('%Y-%m-%d %H:%M:%S')}.")
        return True

    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # On the Slots page: enter $100, then submit repeatedly until 'get an addiction' shows in //div[@id='fail']
    if not _find_and_send_keys(By.XPATH, "//input[@name='bet']", "100"):
        print("FAILED: Could not enter $100 bet.")
        global_vars._script_casino_slots_cooldown_end_time = now + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    print("Starting $100 spins. Will stop when addiction warning appears...")

    submit_xpath = "//input[@name='B1']"
    fail_xpath = "//div[@id='fail']"

    spins = 0
    while True:
        # Check for the addiction message
        msg = _get_element_text_quiet(By.XPATH, fail_xpath, timeout=0.25)
        if msg and 'get an addiction' in msg.lower():
            print("Addiction warning detected — stopping slots.")
            # Set 25h cooldown in file and script timer
            next_time = datetime.datetime.now() + datetime.timedelta(hours=25)
            _set_last_timestamp(global_vars.CASINO_NEXT_CHECK_FILE, next_time)
            global_vars._script_casino_slots_cooldown_end_time = next_time
            print(f"Casino Slots cooldown set until {next_time.strftime('%Y-%m-%d %H:%M:%S')}.")
            return True

        # Otherwise, click submit again
        if not _find_and_click(By.XPATH, submit_xpath):
            print("FAILED: Could not click spin submit button.")
            # Short fallback cooldown; we’ll try again shortly
            global_vars._script_casino_slots_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 60))
            return False

        spins += 1
        if spins % 10 == 0:
            print(f"Spins so far: {spins}")