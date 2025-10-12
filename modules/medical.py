import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _navigate_to_page_via_menu, _get_element_attribute, _find_element, _find_and_click

def medical_casework(player_data):
    """
    Manages and processes hospital casework.
    Assumes caller only invokes this when occupation is appropriate.
    Navigates to the Hospital via the menu, opens PATIENTS, then performs available casework tasks.
    """
    print("\n--- Beginning Medical Casework Operation ---")

    # Filter your own name from rows
    your_character_name = (player_data or {}).get("Character Name", "")

    # Navigate to Hospital
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business hospital']",
        "Hospital"
    ):
        print("FAILED: Could not navigate to Hospital via menu. Setting cooldown.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
        return False

    # If the Hospital is torched/under repair, the page usually shows a #fail block.
    fail_el = _find_element(By.ID, "fail", timeout=1, suppress_logging=True)
    if fail_el:
        fail_html = _get_element_attribute(By.ID, "fail", "innerHTML") or ""
        if "under going repairs" in (fail_html or "").lower():
            print("Hospital is under repairs. Backing off.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
            return False

    # Click the PATIENTS tab before scanning for work
    if not _find_and_click(By.XPATH, "/html/body/div[4]/div[4]/center/div[1]/form/div/div/table/tbody/tr[1]/td[1]/a"):
        print("FAILED: Could not click 'PATIENTS' tab. Aborting medical casework.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
        return False
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    print("Clicked on Patients. Checking for casework...")

    # Ensure the table with casework options is visible
    table_xpath = "//*[@id='holder_table']/form/div[@id='holder_content']/center/table"
    table_html = _get_element_attribute(By.XPATH, table_xpath, "innerHTML")
    if not table_html:
        print("No hospital casework table found.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    task_clicked = False

    # Process task in order of priority
    for row in table_html.split("<tr>"):
        if "PROCESS SAMPLE" in row:
            task_clicked = _find_and_click(By.LINK_TEXT, "PROCESS SAMPLE")
            break
        elif "COMMENCE SURGERY" in row:
            if your_character_name and your_character_name not in row:
                task_clicked = _find_and_click(By.LINK_TEXT, "COMMENCE SURGERY", timeout=5)
                break
        elif "START TREATMENT" in row:
            if your_character_name and your_character_name not in row:
                task_clicked = _find_and_click(By.LINK_TEXT, "START TREATMENT", timeout=5)
                break
        elif "PROVIDE ASSISTANCE" in row:
            task_clicked = _find_and_click(By.LINK_TEXT, "PROVIDE ASSISTANCE")
            break

    if task_clicked:
        print("SUCCESS: Casework task initiated.")
        return True

    print("No casework tasks found. Setting fallback cooldown.")
    global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
    return False

def execute_sex_change_if_staff_online(initial_player_data: dict) -> bool:
    """
      - If a Surgeon or Hospital Director bot user is online in our current city,
        and our 12h cooldown has expired, navigate to Hospital and book a sex change.
      - Uses Clean Money from initial_player_data (already parsed to int by Main).
      - Ensures funds via money_handling.withdraw_money, selects "Yes", submits, and sets a 12h cooldown.
    Returns True if submitted; otherwise False.
    """
    # local imports to avoid circular import issues
    import re
    import datetime as dt
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select

    import global_vars
    from aws_botusers import get_hospital_staff_online_in_city
    from database_functions import _get_last_timestamp, _set_last_timestamp
    from helper_functions import _find_and_click, _find_element, _get_element_text
    from modules.money_handling import withdraw_money

    COOLDOWN_HOURS = 12

    # Cooldown gate
    now = dt.datetime.now()
    next_due = _get_last_timestamp(global_vars.SEX_CHANGE_NEXT_CHECK_FILE)
    if next_due and now < next_due:
        return False

    # Determine city and check for online hospital staff (Surgeon / Hospital Director)
    current_city = (initial_player_data.get("Location") or initial_player_data.get("Home City") or "").strip()
    if not current_city:
        print("[SexChange] Cannot determine current city.")
        return False

    staff = get_hospital_staff_online_in_city(current_city)
    if not staff:
        # Only proceed if a staffer is actually online in our city
        return False

    print(f"[SexChange] Staff online in {current_city}: {', '.join(sorted(staff))}")

    # Navigate to City page, Hospital, then apply for sex change page
    if not _navigate_to_page_via_menu("//span[@class='city']",
                                      "//a[@class='business hospital']",
                                      "Hospital"):
        print("[SexChange] Failed to navigate to Hospital via menu.")
        return False
    if not _find_and_click(By.XPATH, "//a[normalize-space()='APPLY FOR A SEX CHANGE']"):
        print("[SexChange] Apply link not found.")
        return False

    # Read price (parse first $ amount in the first row <td>)
    price_td_xpath = "//*[@id='holder_content']/center/table/tbody/tr[1]/td"
    price_text = _get_element_text(By.XPATH, price_td_xpath)
    m = re.search(r"\$[\s]*([0-9][0-9,]*)", price_text or "")
    if not m:
        print(f"[SexChange] Could not parse price from: {price_text!r}")
        return False
    price = int(m.group(1).replace(",", ""))

    # Use Clean Money from initial_player_data (already int)
    clean_money = int(initial_player_data.get("Clean Money") or 0)
    need = max(0, price - clean_money)
    if need > 0:
        print(f"[SexChange] Need ${need:,} more clean funds (price ${price:,}, have ${clean_money:,}). Withdrawing...")
        # This helper navigates to Bank and then returns you to the same page you called it from.
        if not withdraw_money(need):
            print("[SexChange] Could not ensure clean funds.")
            return False
        # After return, we should still be on the Apply page as desired.

    # Select 'Yes' in dropdown and submit
    select_el = _find_element(By.XPATH, "//select")
    if not select_el:
        print("[SexChange] Dropdown not found.")
        return False
    try:
        Select(select_el).select_by_visible_text("Yes")
    except Exception:
        try:
            Select(select_el).select_by_visible_text("yes")
        except Exception as e:
            print(f"[SexChange] Could not select 'Yes': {e}")
            return False

    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        print("[SexChange] Submit button not found.")
        return False

    # Success: set next eligible time (12h)
    _set_last_timestamp(global_vars.SEX_CHANGE_NEXT_CHECK_FILE, now + dt.timedelta(hours=COOLDOWN_HOURS))
    print(f"[SexChange] Submitted. Next eligible around {(now + dt.timedelta(hours=COOLDOWN_HOURS)).strftime('%Y-%m-%d %H:%M')}")
    return True
