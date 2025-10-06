import datetime
import random
import re
import time
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from boto3.dynamodb.conditions import Attr
import global_vars
from aws_botusers import get_bankers_by_city
from aws_players import upsert_player_home_city
from comms_journals import send_discord_notification
from helper_functions import _find_and_send_keys, _find_and_click, _find_element, _navigate_to_page_via_menu, \
    _get_element_text, _get_element_attribute, _find_elements, _get_current_url, blind_eye_queue_count, \
    _get_dropdown_options, _select_dropdown_option, dequeue_blind_eye, _find_elements_quiet, dequeue_funeral_smuggle, \
    funeral_smuggle_queue_count


def community_services(player_data):
    """Manages and performs community service operations based on the player's location."""
    print("\n--- Beginning Community Service Operation ---")

    current_location = player_data.get("Location")
    home_city = player_data.get("Home City")

    # Only do CS if Jail Break is visible in Aggravated Crimes, and CSNotToRemoveBnE is enabled in settings.ini
    try:
        cs_guard = global_vars.config.getboolean('BnE', 'CSNotToRemoveBnE', fallback=False)
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

def community_service_foreign(player_data):
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
    reserve = global_vars.config.getint("Launder", "Reserve", fallback=0)
    preferred_raw = global_vars.config.get("Launder", "Preferred", fallback="").strip()
    preferred = {n.strip().lower() for n in preferred_raw.split(",") if n.strip()}

    # Skip if dirty money is not above reserve
    if dirty <= reserve:
        print(f"Skip: dirty ${dirty} ≤ reserve ${reserve}.")
        global_vars._script_launder_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(300, 600))  # 5–10 min backoff
        return False

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

    # Laundering Boys Work: pick any bot user banker whose HomeCity == current city
    current_city = (player_data.get("Location") or player_data.get("Home City") or "").strip()
    banker_priority = set()
    if current_city:
        banker_priority = get_bankers_by_city(current_city)
        if banker_priority:
            print(f"Laundering Boys Work is active in {current_city}: {sorted(list(banker_priority))}")
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
        # Normal laundering: clean as much as possible under reserve and max
        amt = min(max_amt, dirty - reserve)
    else:
        # Already at or below reserve: trickle $5 each time (if dirty cash allows)
        amt = min(max_amt, 5)

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

def medical_casework(player_data):
    """
    Manages and processes hospital casework.
    Assumes caller only invokes this when occupation is appropriate.
    Navigates to the Hospital via menu, opens PATIENTS, then performs available casework tasks.
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

def engineering_casework(player_data):
    """
    Super-simple engineering: open Maintenance & Construction via Income menu,
    pick the first available job, submit. No prioritization.
    """

    print("\n--- Beginning Engineering Casework ---")

    # Navigate via menus
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[normalize-space()='Maintenance and Construction']",
        "Maintenance and Construction Page"):
        print("FAILED: Navigation to Maintenance and Construction page failed.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    print("On Maintenance & Construction. Looking for the first available task…")

    # Capture your own name for filtering
    your_character_name = (player_data or {}).get("Character Name", "")

    # Find all selectable tasks
    radios = _find_elements_quiet(By.XPATH, ".//*[@id='holder_content']//input[@type='radio']")
    if not radios:
        print("No selectable tasks (no radio inputs found). Short cooldown.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    # Prefer the Construction Site / Business Repairs form if present
    construction_radio = None
    try:
        form = _find_element(
            By.XPATH,
            "//form[input[@name='display' and @value='bus_repair'] "
            "      or .//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'start repairs')]]",
            timeout=1,
            suppress_logging=True
        )
        if form:
            construction_radio = form.find_element(By.XPATH, ".//input[@type='radio']")
    except Exception:
        construction_radio = None

    selected_radio = None
    if construction_radio:
        print("Found Construction Site / Business Repairs task. Selecting it even if owned by self.")
        selected_radio = construction_radio
    else:
        # Fallback – pick the last available task, skipping self-owned
        for candidate in reversed(radios):  # Select last most radio button
            try:
                container_text = candidate.find_element(By.XPATH, "./ancestor::tr[1]").text
                if your_character_name and your_character_name.lower() in container_text.lower():
                    print(f"Skipping self-owned engineering task ({your_character_name}).")
                    continue
                selected_radio = candidate
                break
            except Exception as e:
                print(f"Warning: could not read a task row: {e}")

    if not selected_radio:
        print("All available engineering tasks belong to you. Short cooldown.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    # Click the chosen radio
    try:
        selected_radio.click()
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    except Exception as e:
        print(f"FAILED: Could not click the selected radio: {e}")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    # Submit the nearest form for that radio (its ancestor form)
    try:
        form = selected_radio.find_element(By.XPATH, "./ancestor::form[1]")
        submit = form.find_element(By.XPATH, ".//input[@type='submit' or @class='submit']")
        submit.click()
        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
        print("Successfully started a non-self engineering task.")
        return True
    except Exception as e:
        print(f"FAILED: Could not submit the selected task: {e}")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

def judge_casework(player_data):
    """Manages and processes judge cases."""
    print("\n--- Beginning Judge Casework Operation ---")

    # Navigate to judge page
    if not _navigate_to_page_via_menu(
            "//span[@class='court']",
            "//strong[normalize-space()='Assign sentences to pending cases']",
            "Judge Page"
    ):
        print("FAILED: Navigation to Judge Cases Page failed.")
        return False

    print("Successfully navigated to Judge Cases Page. Checking for cases...")

    # Read the case table
    cases_table = _find_element(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form/table")
    if not cases_table:
        cooldown = random.uniform(60, 120)
        print(f"FAILED: No cases table found. Setting cooldown of {cooldown:.2f} seconds.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=cooldown)
        return False

    # Process the table
    case_rows = cases_table.find_elements(By.TAG_NAME, "tr")[1:]
    processed_any_case = False

    # Read settings.ini for who to skip cases on
    skip_players = {
        name.strip().lower()
        for name in global_vars.config.get('Judge', 'Skip_Cases_On_Player', fallback='').split(',')
        if name.strip()
    }

    # Define the rows to look at in the judge table
    for row in case_rows:
        try:
            suspect_name = row.find_element(By.XPATH, ".//td[3]//a").text.strip()
            victim_name = row.find_element(By.XPATH, ".//td[4]//a").text.strip()

            # Skip cases on yourself
            if player_data['Character Name'] in [suspect_name, victim_name]:
                print(f"Skipping case for self (Suspect: {suspect_name}, Victim: {victim_name}).")
                continue
            # Skip names listed in settings.ini
            if suspect_name.lower() in skip_players:
                print(f"Skipping case due to player in skip list (Suspect: {suspect_name}.")
                continue

            row.find_element(By.XPATH, ".//td[5]/input[@type='radio']").click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)

            if not _find_and_click(By.XPATH, "//input[@name='B1']"):
                continue

            # Read the crime type
            crime_committed = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[3]/div/table/tbody/tr[1]/td[4]")
            if not crime_committed:
                global_vars.driver.get("javascript:history.go(-2)")
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                continue

            if not _find_and_click(By.XPATH, "//input[@value='Submit']"):
                continue

            if process_judge_case_verdict(crime_committed, player_data['Character Name']):
                print(f"Successfully processed a case for {suspect_name}.")
                processed_any_case = True
                return True
            else:
                global_vars.driver.get("javascript:history.go(-2)")
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                continue

        except Exception as e:
            print(f"Exception during case processing: {e}")
            continue

    # Set cooldown if no judge cases
    if not processed_any_case:
        cooldown = random.uniform(60, 120)
        print(f"No valid judge cases processed. Waiting {cooldown:.2f} seconds before retry.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=cooldown)

    return False

def process_judge_case_verdict(crime_committed, character_name):
    """Applies fine, sets no community service/jail time, and submits verdict."""
    fine_amount = global_vars.config.getint('Judge', crime_committed, fallback=1000)
    if fine_amount == 1000:
        print(f"Warning: Fine amount for crime '{crime_committed}' not found or invalid in settings.ini. Defaulting to 1000.")

    if not _find_and_send_keys(By.XPATH, "//input[@name='fine']", str(fine_amount)):
        return False
    if not _find_and_click(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div/center/form/p[4]/select/option[2]"):
        return False

    jail_time_dropdown = _find_element(By.XPATH, "//select[@name='sentence']")
    if jail_time_dropdown:
        try:
            no_jail_time_option = jail_time_dropdown.find_element(By.XPATH, "./option[2]")
            no_jail_time_option.click()
        except NoSuchElementException:
            options = jail_time_dropdown.find_elements(By.TAG_NAME, "option")
            min_jail_time_value = float('inf')
            min_jail_time_option = None
            for option in options:
                try:
                    value = int(option.get_attribute('value'))
                    if value > 0 and value < min_jail_time_value:
                        min_jail_time_value = value
                        min_jail_time_option = option
                except ValueError:
                    pass
            if min_jail_time_option:
                min_jail_time_option.click()
            else:
                return False
    else:
        return False

    # Click Submit
    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        return False
    return True

def lawyer_casework():
    """
    Manages and processes lawyer cases.
    Only works if occupation is 'Lawyer'.
    """
    print("\n--- Beginning Lawyer Casework Operation ---")

    # Navigate to Court page
    court_menu_xpath = "//span[@class='court']"
    if not _find_and_click(By.XPATH, court_menu_xpath):
        print("FAILED: Navigation to Court menu for Lawyer Cases failed. Setting short cooldown.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
        return False

    print("Successfully navigated to Lawyer Cases Page. Checking for cases...")

    # Read cases table
    cases_table_xpath = "/html/body/div[4]/div[4]/div[1]/div[2]/center/form/table"
    cases_table = _find_element(By.XPATH, cases_table_xpath)

    if cases_table:
        case_rows = cases_table.find_elements(By.TAG_NAME, "tr")[1:]
        for i, row in enumerate(case_rows):
            try:
                defend_button_xpath = ".//td[6]/a[@class='box green' and text()='DEFEND']"
                defend_button = _find_elements_quiet(By.XPATH, defend_button_xpath)
                if defend_button and _find_and_click(By.XPATH, defend_button_xpath):
                    print("Successfully clicked DEFEND for a lawyer case.")
                    return True
            except NoSuchElementException:
                pass
            except Exception as e:
                print(f"ERROR: Error processing a lawyer case row: {e}")

    # No defendable cases found — set standard back-off.
    wait_time = random.uniform(120, 180)
    global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_time)
    print(f"No lawyer cases found. Next check in {wait_time:.2f} seconds.")
    return False

def banker_laundering():
    """
    Manages and performs money laundering services as a banker for other players.
    Assumes the bot is playing as a Banker and is accepting laundering requests.
    Returns True on successful process, False otherwise.
    """
    print("\n--- Beginning Banker Laundering Service Operation ---")

    # --- Navigate (skip if already there) ---
    curr_url = (_get_current_url() or "").lower()
    if "banklaunder.asp" not in curr_url:
        if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//a[normalize-space()='Convert Dirty Money']",
            "Banker Page"):
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
            return False
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    else:
        print("Already on Banker page, skipping navigation.")

    print("Successfully navigated to Banker Laundering Service page. Checking for requests...")

    # Find launder table
    requests_table = _find_element(By.XPATH, "//div[@id='holder_content']/table")
    if not requests_table:
        print("No banker laundering requests table found.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(180, 300))
        return False

    # Rows (skip header)
    rows = requests_table.find_elements(By.TAG_NAME, "tr")[1:]
    if not rows:
        print("No pending laundering requests from other players.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(180, 220))
        return False

    # Filter eligible (>= $5)
    eligible_rows = []
    small_count = 0

    for row in rows:
        try:
            client_cell = row.find_element(By.XPATH, ".//td[1]")
            amount_cell = row.find_element(By.XPATH, ".//td[3]")

            client_name = (client_cell.text or "").strip()
            amount_text = (amount_cell.text or "").strip()

            cleaned = amount_text.replace("$", "").replace(",", "").strip()
            try:
                amount = int(cleaned)
            except ValueError:
                print(f"WARNING: Could not parse amount '{amount_text}' for request from {client_name or '(unknown)'}; skipping.")
                continue

            if amount >= 5:
                eligible_rows.append(row)
            else:
                small_count += 1

        except NoSuchElementException:
            print("ERROR: Missing client or amount column in a request row; skipping row.")
        except Exception as e:
            print(f"ERROR: Unexpected error parsing a request row: {e}; skipping row.")

    if not eligible_rows:
        msg = "All laundering requests are less than $5." if small_count else "No eligible requests found."
        print(f"{msg} (sub-$5 count: {small_count})")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(180, 220))
        return False
    if small_count:
        print(f"Info: filtered out {small_count} sub-$5 request(s).")

    # Take first eligible
    selected = eligible_rows[0]
    try:
        # Name (link preferred)
        link_el = None
        try:
            link_el = selected.find_element(By.XPATH, ".//td[1]/a")
            client_name = (link_el.text or "").strip()
        except NoSuchElementException:
            client_name = (selected.find_element(By.XPATH, ".//td[1]").text or "").strip()

        amount_text = (selected.find_element(By.XPATH, ".//td[3]").text or "").strip()
        cleaned = amount_text.replace("$", "").replace(",", "").strip()
        try:
            amount_to_process = int(cleaned)
        except ValueError:
            print(f"WARNING: Could not parse amount '{amount_text}' for selected request from {client_name or '(unknown)'}; backing off.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
            return False

        print(f"Selected request from {client_name} for ${amount_to_process}.")

        # Click name — guard pattern to avoid “unreachable” diagnostics
        clicked_ok = False
        if link_el:
            try:
                link_el.click()
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                print(f"Successfully clicked player name '{client_name}'. Now on the transaction page.")
                clicked_ok = True
            except Exception as e:
                print(f"FAILED: Could not click player link for {client_name}: {e}")
        else:
            print("FAILED: Client name is not a link; cannot open transaction page.")

        if not clicked_ok:
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
            return False

        # Pick "Launder Money" in dropdown
        dropdown_el = _find_element(By.XPATH, "//select[@name='display']")
        if not dropdown_el:
            print("FAILED: Could not find the 'What do you wish to do?' dropdown.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
            return False

        try:
            Select(dropdown_el).select_by_value("result")
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
            print("Selected 'Launder Money'.")
        except NoSuchElementException:
            print("FAILED: 'Launder Money' option not present in dropdown.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
            return False
        except Exception as e:
            print(f"FAILED: Error selecting dropdown value: {e}")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
            return False

        # Auto Funds Transfer
        if not _find_and_click(By.XPATH, "//input[@name='B1']", timeout=global_vars.EXPLICIT_WAIT_SECONDS, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
            print("FAILED: Could not click first 'Submit' button after selecting 'Launder Money'.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
            return False

        print("Submitted transaction type. Proceeding to Auto Funds Transfer…")

        if not _find_and_click(By.XPATH, "//input[@name='B1']", timeout=global_vars.EXPLICIT_WAIT_SECONDS, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
            print("FAILED: Could not click 'Auto Funds Transfer' button.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
            return False

        print(f"SUCCESS: Completed laundering and auto-transferred funds for {client_name} (${amount_to_process}).")
        return True

    except NoSuchElementException:
        print("ERROR: Missing elements while processing the selected request. Backing off shortly.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
        return False
    except Exception as e:
        print(f"ERROR: Unexpected exception during laundering flow: {e}. Short cooldown set.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
        return False

def banker_add_clients(current_player_home_city=None):
    """
    Manages the process of adding new clients as a Banker.
    Reads the Players table in DynamoDB to find potential clients
    (players with a HomeCity different from the bot's Home City).
    Accepts either the full initial_player_data dict or just the Home City string.
    """
    print("\n--- Beginning Banker Add Clients Operation ---")

    # Normalise current_player_home_city (support dict or str)
    if isinstance(current_player_home_city, dict):
        current_player_home_city = current_player_home_city.get("Home City")
    if not isinstance(current_player_home_city, str) or not current_player_home_city.strip():
        print("ERROR: Could not determine current player's home city. Cannot filter clients.")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
        return False
    current_player_home_city = current_player_home_city.strip()

    # Get potential clients from DDB (players whose HomeCity differs from ours, excluding Hell/Heaven)
    potential_clients = []
    try:
        players_tbl = global_vars.get_players_table()

        filt = (
                Attr("HomeCity").exists() &
                Attr("HomeCity").ne(current_player_home_city) &
                Attr("HomeCity").ne("Hell") &
                Attr("HomeCity").ne("Heaven")
        )

        # Only need the Player name and HomeCity for filtering/reporting
        projection = "#pk, HomeCity"
        expr_names = {"#pk": global_vars.DDB_PLAYER_PK}

        scan_kwargs = {
            "FilterExpression": filt,
            "ProjectionExpression": projection,
            "ExpressionAttributeNames": expr_names,
        }

        # Paginated scan
        resp = players_tbl.scan(**scan_kwargs)
        items = resp.get("Items", [])
        for it in items:
            pk = it.get(global_vars.DDB_PLAYER_PK)
            city = (it.get("HomeCity") or "")
            if pk and city.lower() not in {"hell", "heaven"}:
                potential_clients.append(pk)

        while "LastEvaluatedKey" in resp:
            resp = players_tbl.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **scan_kwargs)
            items = resp.get("Items", [])
            for it in items:
                pk = it.get(global_vars.DDB_PLAYER_PK)
                city = (it.get("HomeCity") or "")
                if pk and city.lower() not in {"hell", "heaven"}:
                    potential_clients.append(pk)

    except Exception as e:
        print(f"ERROR: DynamoDB scan for Player table failed: {e}")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 180))
        return False

    if not potential_clients:
        print("No potential clients found with a different home city.")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(300, 600))
        return False

    print(f"Found {len(potential_clients)} potential clients to add: {potential_clients}")

    # Ensure we're on the Banker page before scraping existing clients
    curr_url = (_get_current_url() or "").lower()
    if "banklaunder.asp" not in curr_url:
        if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//a[normalize-space()='Convert Dirty Money']",
            "Banker Page"):
            global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
            return False
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    else:
        print("Already on Banker page, skipping navigation.")

    # Now it is safe to scrape who we already do business with
    existing_clients = get_existing_banker_clients()
    existing_lower = {ec.lower() for ec in existing_clients}

    # Case-insensitive filtering
    potential_clients = [c for c in potential_clients if c.lower() not in existing_lower]
    print(f"Filtered potential clients (excluding existing): {potential_clients}")

    if not potential_clients:
        print("All potential clients are already established. Nothing to do.")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(hours=random.uniform(7, 9))
        return False

    added_any_client = False

    # Navigate to the 'Establish New Deal' tab
    add_client_tab_xpath = "//a[text()='Establish New Deal']"
    add_client_link = _find_element(By.XPATH, add_client_tab_xpath)
    if not add_client_link:
        print("FAILED: Could not find 'Establish New Deal' link.")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
        return False

    try:
        add_client_link.click()
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    except Exception as e:
        print(f"ERROR: Failed to click 'Establish New Deal' link: {e}")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 90))
        return False

    for client_to_add in potential_clients:
        print(f"\n--- Attempting to add client: {client_to_add} ---")

        # Always navigate to 'Establish New Deal' tab before each client attempt
        add_client_link = _find_element(By.XPATH, add_client_tab_xpath)
        if not add_client_link:
            print("FAILED: Could not find 'Establish New Deal' link before adding next client.")
            break

        try:
            add_client_link.click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception as e:
            print(f"ERROR: Failed to click 'Establish New Deal' link before adding next client: {e}")
            break

        try:
            gangster_name_input_xpath = "//input[@name='gangster']"
            if not _find_and_send_keys(By.XPATH, gangster_name_input_xpath, client_to_add):
                print(f"FAILED: Could not enter client name '{client_to_add}'. Skipping.")
                continue

            submit_button_xpath = "//input[@type='submit' and @value='Establish Deal']"
            if not _find_and_click(By.XPATH, submit_button_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
                print(f"FAILED: Could not click submit button for client '{client_to_add}'. Skipping.")
                continue

            fail_element = _find_element(By.ID, "fail", timeout=1, suppress_logging=True)
            if fail_element:
                fail_results = _get_element_attribute(By.ID, "fail", "innerHTML") or ""
                fl = fail_results.lower()
                if 'appear to exist' in fl:
                    print(f"INFO: Client '{client_to_add}' does not appear to exist (dead/removed). Skipping.")
                elif 'from your home city' in fl:
                    print(f"INFO: Client '{client_to_add}' is from your home city. Upserting HomeCity in DDB and skipping.")
                    upsert_player_home_city(client_to_add, current_player_home_city)
                elif 'already do business' in fl:
                    print(f"INFO: You already do business with '{client_to_add}'. Skipping.")
                else:
                    print(f"WARNING: Unknown failure when adding client '{client_to_add}': {fail_results}")
            else:
                print(f"Successfully added client: {client_to_add}.")
                added_any_client = True

        except Exception as e:
            print(f"An unexpected error occurred while adding client '{client_to_add}': {e}. Skipping.")

    if added_any_client:
        print("Completed Banker Add Clients operation. Some clients were added.")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(hours=random.uniform(7, 9))
        return True
    else:
        print("No new clients were successfully added in this cycle.")
        global_vars._script_bank_add_clients_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(hours=random.uniform(7, 9))
        return False

def get_existing_banker_clients():
    """
    Scrapes the gangster names the banker already does business with
    from the Laundering Deals table under the 'Gangster' column.
    Ensures we're on the Banker page and the 'Deals' tab first.
    """
    try:
        # Ensure we're on the Banker page
        curr_url = (_get_current_url() or "").lower()
        if "banklaunder.asp" not in curr_url:
            if not _navigate_to_page_via_menu(
                "//span[@class='income']",
                "//a[normalize-space()='Convert Dirty Money']",
                "Banker Page"):
                print("FAILED: Could not navigate to Banker page before scraping existing clients.")
                return []
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        # Find all rows that have a gangster link (href contains 'display=gangster')
        rows = _find_elements(By.XPATH, "//div[@id='holder_content']//table//tr[.//a[contains(@href,'display=gangster')]]", timeout=2)

        if not rows:
            # Check for 'no deals' message
            holder = _find_element(By.XPATH, "//div[@id='holder_content']", timeout=1, suppress_logging=True)
            holder_html = (holder.get_attribute("innerHTML") if holder else "") or ""
            if "no deals" in holder_html.lower():
                print("No existing banker clients found.")
                return []
            print("No rows with gangster links found on Deals tab.")
            return []

        existing_clients = []
        for r in rows:
            try:
                a = r.find_element(By.XPATH, ".//a[contains(@href,'display=gangster')]")
                name = (a.text or "").strip()
                if name:
                    existing_clients.append(name)
            except Exception:
                continue

        print(f"Existing banker clients found: {existing_clients}")
        return existing_clients

    except Exception as e:
        print(f"ERROR: Could not fetch existing banker clients: {e}")
        return []

def fire_casework(initial_player_data):
    """
    Executes firefighting logic (Attend Fires, Fire Investigations, and Fire Safety Inspections).
    """
    print("\n--- Beginning Fire Station Logic ---")

    # Navigate to Fire Station via city menu
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business fire_station']",
        "Fire Station"
    ):
        print("FAILED: Could not navigate to Fire Station via menu.")
        return False

    print("SUCCESS: Navigated to Fire Station. Opening 'Fires' tab...")

    # Click the "Fires" button before checking for work
    if not _find_and_click(By.XPATH, "//a[contains(text(),'Fires')]"):
        print("FAILED: Could not click 'Fires' tab. Aborting fire casework.")
        return False
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    print("SUCCESS: Opened 'Fires' tab. Checking for active fires...")

    # Attend Fire
    attend_fire_links = _find_elements_quiet(By.XPATH, "//tbody/tr[2]/td[4]/a[1]")
    if attend_fire_links:
        print("Found active fire. Attending...")
        try:
            attend_fire_links[0].click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
            return True
        except Exception as e:
            print(f"WARNING: Could not click Attend Fire link: {e}")

    # Fire Investigation
    print("No active fires found. Checking for Fire Investigations...")
    investigate_links = _find_elements_quiet(By.XPATH, "//a[normalize-space()='Investigate']")
    if investigate_links:
        print("Found Fire Investigation. Investigating...")
        try:
            investigate_links[0].click()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
            return True
        except Exception as e:
            print(f"WARNING: Could not click Investigate link: {e}")

    print("No active fires or investigations available. Setting fallback cooldown.")
    global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(31, 32))
    return False

def fire_duties():
    """
    Navigates to firefighter Duties, selects the last available duty, and trains.
    """
    print("\n--- Beginning Fire Fighter Duties ---")

    # Navigate to the Fire Duties page
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[normalize-space()='Fire Fighter Duties']",
        "Fire Fighter Duties"
    ):
        print("FAILED: Could not navigate to Fire Fighter Duties page.")
        return False

    # Find all available radio buttons
    radio_buttons = _find_elements(By.XPATH, "//input[@type='radio' and @name='comservice']")
    if not radio_buttons:
        print("No Fire Duty options found.")
        return False

    # Select the last available option
    last_radio = radio_buttons[-1]
    try:
        last_radio.click()
        print(f"Selected last available duty: {last_radio.get_attribute('value')}")
    except Exception as e:
        print(f"ERROR: Could not click last radio button. {e}")
        return False

    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Click the Train button
    train_buttons = _find_elements(By.XPATH, "//input[@name='B2']")
    if train_buttons:
        train_buttons[0].click()
        print("Clicked Train button.")
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        return True
    else:
        print("Train button not found.")
        return False

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