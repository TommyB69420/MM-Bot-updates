import datetime
import random
import time

from boto3.dynamodb.conditions import Attr
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select

import global_vars
from aws_players import upsert_player_home_city
from helper_functions import _get_current_url, _navigate_to_page_via_menu, _find_element, _find_and_click, _find_and_send_keys, _get_element_attribute, _find_elements

def banker_laundering():
    """
    Manages and performs money laundering services as a banker for other players.
    Assumes the bot is playing as a Banker and is accepting laundering requests.
    Returns True on a successful process, False otherwise.
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

        # Click a name — guard pattern to avoid “unreachable” diagnostics
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