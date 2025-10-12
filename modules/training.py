import os
import re
import time

from selenium.webdriver.common.by import By

import global_vars
from database_functions import _read_json_file, _write_json_file
from helper_functions import _navigate_to_page_via_menu, _find_element, _find_and_click, _get_element_text, _get_dropdown_options, _select_dropdown_option
from modules.money_handling import withdraw_money

def police_training():
    """
    Handles police training sign-up and progression.
    Dynamically stops after completing the required number of training sessions (e.g. 15, 30, etc.).
    """

    # Skip if already marked complete in game_data
    try:
        if _read_json_file(global_vars.POLICE_TRAINING_DONE_FILE) is True:
            print("Police training already marked complete — skipping.")
            return False
    except Exception as e:
        print(f"WARNING: Could not read police training flag: {e}")

    print("\n--- Starting Police Training Operation ---")

    # Navigate to the Police Recruitment page
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business police']",
        "Police Training"):
        return False

    success_box_xpath = "//div[@id='success']"

    # If the first-time option exists, click it; otherwise select "Yes" (continue)
    accept_opt = _find_element(By.XPATH, "//option[@value='acceptpolice']", timeout=1, suppress_logging=True)

    if accept_opt:
        print("Step: Signing up for Police Training.")
        if not _find_and_click(By.XPATH, "//option[@value='acceptpolice']"):
            print("FAILED: Could not click 'Yes, I would like to join' option.")
            return False
    else:
        print("Step: Continuing Police Training (subsequent training).")
        yes_option_xpath = "//select[@name='action']/option[@value='Yes']"

        # Try to click "Yes", with one retry after focusing the dropdown
        if not _find_and_click(By.XPATH, yes_option_xpath):
            _find_and_click(By.XPATH, "//select[@name='action']")
            if not _find_and_click(By.XPATH, yes_option_xpath):
                print("FAILED: Could not select 'Yes' from dropdown.")
                return False

    # Submit the form
    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        print("FAILED: Could not click Submit.")
        return False

    # Check training progress to determine how many trains left to do
    success_text = _get_element_text(By.XPATH, success_box_xpath)
    if success_text:
        print(f"Success Message: '{success_text}'")
        match = re.search(r"\((\d+)\s+of\s+(\d+)\s+studies\)", success_text)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            print(f"Training Progress: {current}/{total}")
        else:
            print("WARNING: Could not parse training progress.")
    else:
        print("No success box found — likely finished training.")
        #Check for completion paragraph
        final_text = _get_element_text(By.XPATH, "//div[@id='content']//p[1]") or ""
        if "your hard work" in final_text.lower():
            _write_json_file(global_vars.POLICE_TRAINING_DONE_FILE, True)
            print("FINAL SUCCESS: Police training is now fully complete.")
            return False

    print("Police training step completed successfully.")
    return True

def fire_training():
    """
    Handles fire training sign-up and progression.
    Dynamically stops after completing the required number of training sessions (e.g. 15, 30, etc.).
    """

    # Skip if already marked complete in game_data
    try:
        if _read_json_file(global_vars.FIRE_TRAINING_DONE_FILE) is True:
            print("Fire training already marked complete — skipping.")
            return False
    except Exception as e:
        print(f"WARNING: Could not read fire training flag: {e}")

    print("\n--- Starting Fire Training Operation ---")

    # Navigate to Fire Recruitment page
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business fire']",
        "Fire Training"):
        return False

    success_box_xpath = "//div[@id='success']"

    # If the first-time option exists, click it; otherwise select "Yes" (continue)
    accept_opt = _find_element(By.XPATH, "//option[@value='acceptfire']", timeout=1, suppress_logging=True)

    if accept_opt:
        print("Step: Signing up for Fire Training.")
        if not _find_and_click(By.XPATH, "//option[@value='acceptfire']"):
            print("FAILED: Could not click 'Yes, I would like to join' option.")
            return False
    else:
        print("Step: Continuing Fire Training (subsequent training).")
        yes_option_xpath = "//select[@name='action']/option[@value='Yes']"

        # Try to click "Yes", with one retry after focusing the dropdown
        if not _find_and_click(By.XPATH, yes_option_xpath):
            _find_and_click(By.XPATH, "//select[@name='action']")
            if not _find_and_click(By.XPATH, yes_option_xpath):
                print("FAILED: Could not select 'Yes' from dropdown.")
                return False

    # Submit the form
    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        print("FAILED: Could not click Submit.")
        return False

    # Check training progress to determine how many trains left to do
    success_text = _get_element_text(By.XPATH, success_box_xpath)
    if success_text:
        print(f"Success Message: '{success_text}'")
        match = re.search(r"\((\d+)\s+of\s+(\d+)\s+studies\)", success_text)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            print(f"Training Progress: {current}/{total}")
        else:
            print("WARNING: Could not parse training progress.")
    else:
        print("No success box found — likely finished training.")
        # Final fallback: Check for completion paragraph
        final_text = _get_element_text(By.XPATH, "//div[@id='content']//p[1]") or ""
        if "your hard work" in final_text.lower():
            _write_json_file(global_vars.FIRE_TRAINING_DONE_FILE, True)
            print("FINAL SUCCESS: Fire training is now fully complete.")
            return False

    print("Fire training step completed successfully.")
    return True

def customs_training():
    """
    Handles customs training sign-up and progression.
    Dynamically stops after completing the required number of training sessions (e.g. 15, 30, etc.).
    """

    # Skip if already marked complete in game_data
    try:
        if _read_json_file(global_vars.CUSTOMS_TRAINING_DONE_FILE) is True:
            print("Customs training already marked complete — skipping.")
            return False
    except Exception as e:
        print(f"WARNING: Could not read customs training flag: {e}")

    print("\n--- Starting Customs Training Operation ---")

    # Navigate to Customs Recruitment page
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business customs']",
        "Customs Training"):
        return False

    success_box_xpath = "//div[@id='success']"

    # If the first-time option exists, click it; otherwise select "Yes" (continue)
    accept_opt = _find_element(By.XPATH, "//option[@value='acceptcustoms']", timeout=1, suppress_logging=True)

    if accept_opt:
        print("Step: Signing up for Customs Training.")
        if not _find_and_click(By.XPATH, "//option[@value='acceptcustoms']"):
            print("FAILED: Could not click 'Yes, I would like to join' option.")
            return False
    else:
        print("Step: Continuing Customs Training (subsequent training).")
        yes_option_xpath = "//select[@name='action']/option[@value='Yes']"

        # Try to click "Yes", with one retry after focusing the dropdown
        if not _find_and_click(By.XPATH, yes_option_xpath):
            _find_and_click(By.XPATH, "//select[@name='action']")
            if not _find_and_click(By.XPATH, yes_option_xpath):
                print("FAILED: Could not select 'Yes' from dropdown.")
                return False

    # Submit the form
    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        print("FAILED: Could not click Submit.")
        return False

    # Check training progress to determine how many trains left to do
    success_text = _get_element_text(By.XPATH, success_box_xpath)
    if success_text:
        print(f"Success Message: '{success_text}'")
        match = re.search(r"\((\d+)\s+of\s+(\d+)\s+studies\)", success_text)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            print(f"Training Progress: {current}/{total}")
        else:
            print("WARNING: Could not parse training progress.")
    else:
        print("No success box found — likely the initial join step or a layout change.")
        # Final fallback: Check for completion paragraph
        final_text = _get_element_text(By.XPATH, "//div[@id='content']//p[1]") or ""
        if "your hard work" in final_text.lower():
            _write_json_file(global_vars.CUSTOMS_TRAINING_DONE_FILE, True)
            print("FINAL SUCCESS: Customs training is now fully complete.")
            return False

    print("Customs training step completed successfully.")
    return True

def combat_training():
    """
    Combat Training driver:
      - If already marked complete, skip.
      - Navigate: City -> Training Centre.
      - If dropdown shows a course (Karate/Muay Thai/Jui Jitsu/MMA):
          * Select configured course ([Actions Settings] Training)
          * Submit to show info paragraph; parse one-off $fee
          * Withdraw shortfall; reselect course; submit
          * On confirmation, select 'Yes...' and submit
          * Stop script for manual review (first run only)
      - Else if dropdown shows 'Yes, I would like to train':
          * Select 'Yes'; submit
          * Read progress from //p[@class='center'] e.g. "(3 of 15 studies)"
          * If complete, write game_data/combat_training_completed.json = true
    """

    # file to mark completion
    COMBAT_DONE_FILE = os.path.join(global_vars.COOLDOWN_DATA_DIR, "combat_training_completed.json")

    # Skip if already marked complete
    try:
        if _read_json_file(COMBAT_DONE_FILE) is True:
            print("Combat training already marked complete — skipping.")
            return False
    except Exception:
        pass

    print("\n--- Beginning Combat Training Operation ---")

    # Desired course from settings
    val = (global_vars.cfg_get('ActionsSettings', 'Training', '')
           or global_vars.cfg_get('Actions Settings', 'Training', '')
           or '')
    course_name = (val[0] if isinstance(val, list) else val).strip()

    if not course_name:
        print("FAILED: Set [Actions Settings] Training = (Jui Jitsu | Muay Thai | Karate | MMA)")
        return False

    # Navigate to Training Centre
    if not _navigate_to_page_via_menu("//span[@class='city']",
                                      "//a[@class='business training']",
                                      "Training Centre"):
        print("FAILED: Could not navigate to Training Centre.")
        return False

    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    dropdown_xpath = "//select[@name='action']"
    submit_xpath   = "//input[@name='B1']"

    # What options are currently shown?
    opts = _get_dropdown_options(By.XPATH, dropdown_xpath) or []
    opts_lower = [o.lower() for o in opts]

    # Subsequent trains (Yes/No)
    if any("yes" in o for o in opts_lower):
        # Select the "Yes" option and submit
        yes_text = next((o for o in opts if "yes" in o.lower()), "Yes")
        if not _select_dropdown_option(By.XPATH, dropdown_xpath, yes_text):
            print("FAILED: Could not select 'Yes' to continue training.")
            return False
        if not _find_and_click(By.XPATH, submit_xpath):
            print("FAILED: Could not click Submit to continue training.")
            return False

        # Check for final completion phrase in first paragraph
        final_p_xpath = "//div[@id='content']//p[1]"
        final_p_text = (_get_element_text(By.XPATH, final_p_xpath) or "").strip()
        print(f"Post-train message: {final_p_text!r}")

        if "proud to award you with bonus stats for your" in final_p_text.lower():
            print("Combat training complete (bonus stats message detected). Writing completion flag.")
            _write_json_file(COMBAT_DONE_FILE, True)
            return True

        print("Submitted subsequent combat training step.")
        return True

    # FIRST SIGN-UP - Validate configured course is present
    if course_name not in opts:
        print(f"FAILED: Desired course '{course_name}' not found. Options: {opts}")
        return False

    # Select course & submit
    if not _select_dropdown_option(By.XPATH, dropdown_xpath, course_name):
        print(f"FAILED: Could not select '{course_name}'.")
        return False
    if not _find_and_click(By.XPATH, submit_xpath):
        print("FAILED: Could not click initial Submit for course selection.")
        return False

    # Parse one-off price from info paragraph
    blurb = _get_element_text(By.XPATH, "//p[contains(text(),'The Training Centre in') and contains(text(),'offers')]")
    if not blurb:
        print("FAILED: Could not find the training info paragraph to parse price.")
        return False

    m = re.search(r"\$\s*([\d,]+)", blurb)
    if not m:
        print(f"FAILED: Could not parse price from paragraph: {blurb}")
        return False
    price = int(m.group(1).replace(",", ""))
    print(f"Parsed course fee: ${price:,}")

    # Determine clean cash (best effort) and withdraw shortfall
    current_clean = 0
    try:
        clean_text = _get_element_text(By.XPATH, "//div[@id='nav_right']//form")
        if clean_text:
            digits = "".join(ch for ch in clean_text if ch.isdigit())
            if digits:
                current_clean = int(digits)
    except Exception:
        pass

    need = max(0, price - current_clean)
    if need > 0:
        print(f"Withdrawing ${need:,} to cover fee.")
        if not withdraw_money(need):
            print("FAILED: Withdrawal failed.")
            return False
        # Back the Training Centre after withdraw_money()

    # Reselect course & submit again
    if not _select_dropdown_option(By.XPATH, dropdown_xpath, course_name):
        print(f"FAILED: Could not reselect '{course_name}' after withdrawal.")
        return False
    if not _find_and_click(By.XPATH, submit_xpath):
        print("FAILED: Could not click Submit after reselecting the course.")
        return False

    # Pick the 'Yes' option and submit
    confirm_opts = _get_dropdown_options(By.XPATH, dropdown_xpath) or []
    yes_text = next((o for o in confirm_opts if "yes" in o.lower()), None)
    picked = False
    if yes_text:
        picked = _select_dropdown_option(By.XPATH, dropdown_xpath, yes_text)
    if not picked:
        picked = _select_dropdown_option(By.CSS_SELECTOR, "select[name='action']", "accept", use_value=True)
    if not picked:
        print(f"FAILED: Could not select the 'Yes' confirmation option. Options: {confirm_opts}")
        return False

    if not _find_and_click(By.XPATH, submit_xpath):
        print("FAILED: Could not click final Submit on confirmation.")
        return False

    print("Combat training sign-up complete — will continue next cycle.")
    return True