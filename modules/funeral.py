import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from helper_functions import _navigate_to_page_via_menu, _find_and_click, _find_element, _select_dropdown_option, dequeue_funeral_smuggle, funeral_smuggle_queue_count

def execute_smuggle_for_player(target_player: str) -> bool:
    try:
        target_player = (target_player or "").strip()
        if not target_player:
            print("Smuggle not found for that player")
            return False

        # Open Aggravated Crimes page
        if not _navigate_to_page_via_menu(
                "//span[@class='income']",
                "//a[normalize-space()='Aggravated Crimes']",
                "Aggravated Crimes"):
            print("FAILED: Could not open Aggravated Crimes.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        # Select radio smuggle radio button from the aggravated crime page
        if not _find_and_click(By.XPATH, "//*[@id='smugglefuneral']"):
            print("FAILED: Could not select 'smugglefuneral' option.")
            return False

        # Click Commit Crime
        if not _find_and_click(By.XPATH, "//input[@name='B1']"):
            print("FAILED: Could not click 'Commit Crime'.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        # On smuggle funeral page: select player from dropdown, click Continue
        dropdown_xpath = "//*[@id='AutoNumber4']/tbody/tr[5]/td[2]/p/select"
        dropdown_el = _find_element(By.XPATH, dropdown_xpath, timeout=2)
        if not dropdown_el:
            print("Smuggle not found for that player")
            return False

        # Try direct select by visible text
        selected_ok = _select_dropdown_option(By.XPATH, dropdown_xpath, target_player)
        if not selected_ok:
            # Fallback: case-insensitive match over options
            try:
                options = dropdown_el.find_elements(By.TAG_NAME, "option")
                norm_target = target_player.strip().lower()
                matched_val = None
                for opt in options:
                    if (opt.text or "").strip().lower() == norm_target:
                        matched_val = opt.get_attribute("value")
                        break
                if matched_val:
                    # select by value with small JS
                    global_vars.driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));", dropdown_el, matched_val)
                    selected_ok = True
            except Exception:
                selected_ok = False

        if not selected_ok:
            print("Smuggle not found for that player")
            return False

        # Click Continue
        if not _find_and_click(By.XPATH, "//*[@id='AutoNumber4']/tbody/tr[7]/td[2]/p/input"):
            print("FAILED: Could not click Continue after selecting player.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        # Next page: select radio with value='smuggle' (label contains 'Smuggle the drugs into'). Prefer value match; a label text can vary slightly
        if not _find_and_click(By.XPATH, "//input[@type='radio' and @value='smuggle']"):
            # Secondary: try to find by nearby text
            radio_by_text = _find_element(By.XPATH, "//*[contains(normalize-space(.), 'Smuggle the drugs into')]/preceding::input[@type='radio'][1]", timeout=2)
            if radio_by_text:
                radio_by_text.click()
                time.sleep(global_vars.ACTION_PAUSE_SECONDS / 2)
            else:
                print("FAILED: Could not select 'Smuggle the drugs into' option.")
                return False

        # click Submit
        if not _find_and_click(By.XPATH, "//*[@id='AutoNumber4']/tbody/tr[8]/td[2]/p/input"):
            print("FAILED: Could not click Submit on final step.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS / 2)
        print(f"Smuggle flow completed for '{target_player}'.")
        # Consume 1 token and notify
        if dequeue_funeral_smuggle():
            remaining = funeral_smuggle_queue_count()
            send_discord_notification(f"Smuggled for '{target_player}'. Remaining smuggles remaining: {remaining}")
            print(f"Smuggled for '{target_player}'. Remaining smuggle tokens: {remaining}")
        else:
            print("WARNING: Smuggle done but queue could not be decremented (empty or file issue).")

        return True

    except Exception as e:
        print(f"ERROR during smuggle flow: {e}")
        return False

def mortician_autopsy():
    """
    Navigate to the income menu to Autopsy Work and, if available, do an autopsy.
    If no autopsy radio is present, set a short case cooldown (60–80s).
    """
    print("\n--- Beginning Mortician Autopsy ---")

    # Navigate to Autopsy page
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[normalize-space()='Autopsy Work']",
        "Autopsy Work"):
        print("FAILED: Could not open Autopsy Work.")
        # keep it lightweight; brief backoff like other flows
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
        return False

    # Look for an autopsy radio button
    radio = _find_element(By.NAME, "autopsynum", timeout=1)
    if radio:
        try:
            radio.click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS / 2)
        except Exception as e:
            print(f"ERROR: Could not click autopsy radio: {e}")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 80))
            return False

        # Click submit (unsure on xpath, so using a variety seen across MM)
        if _find_and_click(By.XPATH, "//input[@name='B1' or @type='submit' or @value='Continue']", pause=global_vars.ACTION_PAUSE_SECONDS):
            print("Autopsy commenced successfully.")
            return True
        else:
            print("FAILED: Continue/Submit button not found after selecting autopsy.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 80))
            return False

    # Set a cooldown if no autopsy found
    cooldown = random.uniform(31, 60)
    print(f"No autopsy available. Setting case cooldown for {cooldown:.2f}s.")
    global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=cooldown)
    return False