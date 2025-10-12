import datetime
import random

from selenium.webdriver.common.by import By

import global_vars
from database_functions import _set_last_timestamp
from helper_functions import _navigate_to_page_via_menu, _get_dropdown_options, _select_dropdown_option, _find_and_click
from modules.money_handling import withdraw_money

def gym_training():
    """
    Attempts to perform gym training if 12h cooldown has passed.
    Buys membership card if required, withdraws funds if necessary.
    Updates cooldown file on success.
    """
    print("\n--- Beginning Gym Training Operation ---")

    now = datetime.datetime.now()

    # Navigate to Gym
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business gym']",
        "Gym"
    ):
        print("FAILED: Could not navigate to Gym.")
        return False

    dropdown_xpath = ".//*[@class='input']"
    dropdown_options = _get_dropdown_options(By.XPATH, dropdown_xpath)

    if not dropdown_options:
        print("FAILED: Could not find gym dropdown options.")
        return False

    if any("membership card" in option.lower() for option in dropdown_options):
        print("Membership required. Attempting to withdraw $10,000...")

        # Withdraw money for membership
        if not withdraw_money(10000):
            print("FAILED: Could not withdraw money for membership.")
            return False

        dropdown_options = _get_dropdown_options(By.XPATH, dropdown_xpath)
        if not dropdown_options or not any("membership card" in option.lower() for option in dropdown_options):
            print("FAILED: Gym membership option not present after returning.")
            return False

        if not _select_dropdown_option(By.XPATH, dropdown_xpath, "Purchase 1 week membership card"):
            print("FAILED: Could not select membership option.")
            return False
        if not _find_and_click(By.XPATH, "//form//input[@type='submit']"):
            print("FAILED: Could not submit membership purchase.")
            return False

        print("Successfully purchased gym membership.")
        return True  # Stop here, training will be available next cycle

    # Proceed with training
    print("Proceeding with gym training...")
    if not _select_dropdown_option(By.XPATH, dropdown_xpath, "Have a spa/sauna"):
        print("FAILED: Could not select training option.")
        return False
    if not _find_and_click(By.XPATH, "//form//input[@type='submit']"):
        print("FAILED: Could not submit gym training.")
        return False

    print("Gym training completed successfully.")
    cooldown = now + datetime.timedelta(hours=12, seconds=random.randint(60, 360))
    _set_last_timestamp(global_vars.GYM_TRAINING_FILE, cooldown)
    print(f"Next gym training available at {cooldown.strftime('%Y-%m-%d %H:%M:%S')}")
    return True