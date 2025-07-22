import datetime
import random
import time
from selenium.webdriver.common.by import By
from global_vars import ACTION_PAUSE_SECONDS, config
from helper_functions import _find_and_click, _find_element, _navigate_to_page_via_menu
from timer_functions import get_game_timer_remaining


def _perform_earn_action(earn_name):
    """Clicks a specific earn option and then the 'Work' button."""
    if not _find_and_click(By.XPATH, f"//*[@id='earns_list']//span[normalize-space(text())='{earn_name}']"):
        print(f"FAILED: Could not click earn option '{earn_name}'.")
        return False

    work_button_xpaths = [
        "//*[@id='holder_content']/form/p/input",
        "//*[@id='holder_content']/form/p/button"
    ]

    for xpath in work_button_xpaths:
        if _find_and_click(By.XPATH, xpath):
            print(f"Earn '{earn_name}' completed successfully.")
            return True

    print(f"FAILED: Could not click 'Work' button for '{earn_name}'.")
    return False


def execute_earns_logic():
    """Manages the earn operation, trying quick earn first (via dropdown), then regular menu earn."""
    global _script_earn_cooldown_end_time
    print("\n--- Beginning Earn Operation ---")

    action_performed = False
    try:
        quick_earn_arrow_xpath = ".//*[@id='nav_left']/p[5]/a[2]/img"
        if _find_element(By.XPATH, quick_earn_arrow_xpath, timeout=1):
            if _find_and_click(By.XPATH, quick_earn_arrow_xpath):
                time.sleep(ACTION_PAUSE_SECONDS)
                if _find_and_click(By.NAME, "lastearn"):
                    print("Quick earn successful via dropdown.")
                    action_performed = True
                else:
                    print("Quick earn dropdown clicked but 'lastearn' still not found. Proceeding to regular menu.")
            else:
                print("Failed to click quick earn arrow. Proceeding to regular menu.")
        else:
            print("Quick earn arrow element not found. Proceeding to regular menu.")
    except Exception as e:
        print(f"Error during quick earn attempt: {e}. Proceeding to regular menu.")

    if not action_performed:
        if not _navigate_to_page_via_menu(
                "//*[@id='nav_left']/p[5]/a[1]/span",
                "//*[@id='admintoolstable']/tbody/tr[1]/td/a",
                "Earns Page"
        ):
            print("FAILED: Failed to open Earns menu.")
            _script_earn_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
            return False

        which_earn = config['Earns Settings'].get('WhichEarn')
        if not which_earn:
            print("ERROR: 'WhichEarn' setting not found in settings.ini under [Earns Settings].")
            _script_earn_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
            return False

        earns_holder_element = _find_element(By.XPATH, "//*[@id='content']/div[@id='earns_holder']/div[@id='holder_content']")
        earns_table_outer_html = earns_holder_element.get_attribute('outerHTML') if earns_holder_element else ""

        final_earn_to_click = which_earn
        if which_earn == "Law":
            if 'Parole sitting' in earns_table_outer_html:
                final_earn_to_click = 'Parole sitting'
            elif 'Judge' in earns_table_outer_html:
                final_earn_to_click = 'Judge'
            elif 'Lawyer' in earns_table_outer_html:
                final_earn_to_click = 'Lawyer'
            else:
                final_earn_to_click = 'Legal Secretary'

        elif which_earn == "Secrets":
            if 'Whore' in earns_table_outer_html:
                final_earn_to_click = 'Whore'
            elif 'Joyride' in earns_table_outer_html:
                final_earn_to_click = 'Joyride'
            elif 'Streetfight' in earns_table_outer_html:
                final_earn_to_click = 'Streetfight'
            else:
                final_earn_to_click = 'Pimp'

        elif which_earn == "Fire":
            if 'Fire Chief' in earns_table_outer_html:
                final_earn_to_click = 'Fire Chief'
            elif 'Fire Fighter' in earns_table_outer_html:
                final_earn_to_click = 'Fire Fighter'
            else:
                final_earn_to_click = 'Volunteer Firefighter'

        elif which_earn == "Gangster":
            if 'Scamming' in earns_table_outer_html:
                final_earn_to_click = 'Scamming'
            elif 'Hack' in earns_table_outer_html:
                final_earn_to_click = 'Hack'
            elif 'Compete at illegal drags' in earns_table_outer_html:
                final_earn_to_click = 'Compete at illegal drags'
            elif 'Steal cheques' in earns_table_outer_html:
                final_earn_to_click = 'Steal cheques'
            else:
                final_earn_to_click = 'Shoplift'

        elif which_earn == "Engineering":
            if 'Chief Engineer' in earns_table_outer_html:
                final_earn_to_click = 'Chief Engineer at local Construction Company'
            elif 'Engineer at local Construction Site' in earns_table_outer_html:
                final_earn_to_click = 'Engineer at local Construction Site'
            elif 'Technician at local vehicle yard' in earns_table_outer_html:
                final_earn_to_click = 'Technician at local vehicle yard'
            else:
                final_earn_to_click = 'Mechanic at local vehicle yard'

        elif which_earn == "Medical":
            if 'Hospital Director' in earns_table_outer_html:
                final_earn_to_click = 'Hospital Director'
            elif 'Surgeon at local hospital' in earns_table_outer_html:
                final_earn_to_click = 'Surgeon at local hospital'
            elif 'Doctor at local hospital' in earns_table_outer_html:
                final_earn_to_click = 'Doctor at local hospital'
            else:
                final_earn_to_click ='Nurse at local hospital'

        elif which_earn == "Bank":
            if 'Bank Manager' in earns_table_outer_html:
                final_earn_to_click = 'Bank Manager'
            elif 'Review loan requests' in earns_table_outer_html:
                final_earn_to_click = 'Review loan requests'
            else:
                final_earn_to_click ='Work at local bank'

        action_performed = _perform_earn_action(final_earn_to_click)

    if not action_performed:
        print("Earn failed. Applying fallback cooldown.")
        _script_earn_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))

    return action_performed