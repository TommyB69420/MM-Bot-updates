import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _find_and_click
from timer_functions import get_all_active_game_timers

def do_events():
    """
    Checks for and attempts the in the game event based on settings.ini.
    Returns True if an action was performed (attacked or cooldown set), False otherwise.
    """

    print("\n--- Beginning Event Operation ---")

    # Click the logo to go to the game home page
    if not _find_and_click(By.XPATH, "//*[@id='logo_hit']"):
        print("Failed to click game logo to navigate to home page.")
        return False
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Click the button to navigate to the event page
    event_page_button_xpath = "//*[self::a or self::button][contains(text(), 'help defend your local city')]"
    if not _find_and_click(By.XPATH, event_page_button_xpath):
        print("Event button 'help defend your local city' not found or not clickable.")
        # If the event button is not available, set a cooldown and return. It prevents constant re-checking when no event is active
        print("Setting event re-check cooldown for 5-7 minutes.")
        global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(5, 7))
        return False

    time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

    # Check for the 'ATTACK' button
    attack_button_xpath = "//a[@class='declinebutton' and contains(text(), 'ATTACK')]"
    if _find_and_click(By.XPATH, attack_button_xpath):
        print("Successfully clicked 'ATTACK' button for the event!")
        # If attacked, read the event_time_remaining from timer_functions.py
        all_timers = get_all_active_game_timers()
        event_time_remaining = all_timers.get('event_time_remaining', float('inf'))

        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

        if event_time_remaining > 0 and event_time_remaining != float('inf'):
            print(f"Event attack successful. Next event action available in {event_time_remaining:.2f} seconds.")
        else:
            print("Event attack successful, but could not determine event cooldown from game timers. Will re-evaluate soon.")
            # Set a fallback cooldown if the game timer is not immediately available
            global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
        return True
    else:
        print("ATTACK button not available on the event page. Event might be on cooldown or completed.")
        # If attack button not available, set a cooldown of 5-7 minutes
        print("Setting event re-check cooldown for 5-7 minutes.")
        global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(5, 7))
        return False