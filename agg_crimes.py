import datetime
import random
import re
import time
from urllib.parse import urlsplit
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from database_functions import get_player_cooldown, set_player_data, _set_last_timestamp, get_crime_targets_from_ddb
import global_vars
from helper_functions import _navigate_to_page_via_menu, _find_and_click, _find_and_send_keys, _get_element_text, _find_element, community_service_queue_count, _get_element_text_quiet, enqueue_community_services
from misc_functions import transfer_money
from timer_functions import parse_game_datetime, get_current_game_time
from comms_journals import send_discord_notification
from aws_players import upsert_player_home_city, mark_top_job
from database_functions import acquire_distributed_timer, complete_distributed_timer, reschedule_distributed_timer, TIMER_NAME_FUNERAL_YELLOW, remove_player_cooldown, rename_player_in_players_table
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
from global_vars import cfg_get, cfg_bool, cfg_int, cfg_float, cfg_list, cfg_int_nested

try:
    import requests  # pip install requests
except Exception:
    requests = None

def execute_funeral_parlour_scan():

    PROFILE_NEWNAME_XPATH = "//*[@id='profile_quote']/div[2]/span/strong/span[2]/a"
    OBITUARIES_TABLE_XPATH = "/html/body/div[4]/div[4]/div[1]/div[2]/div/table"
    VIEW_DAILY_OBITS_XPATH = "//a[normalize-space()='View Daily Obituaries']"
    DEATH_TYPES_TO_DELETE = {"suicide", "murdered", "admin whack"}  # case-insensitive
    INTERVAL_SECONDS = 3600   # shared once-per-hour cadence across all bots
    LEASE_SECONDS = 600       # 10-min lease while one bot is working
    RETRY_SECONDS = 600       # retry in 10 minutes on soft failures

    NAME_CHANGE_WEBHOOK = "https://discord.com/api/webhooks/1422121451007508510/Gc2gbdY0LeFajfGAtLMGHkf0u3vS6wOzlNqrYZRZOV0KVVUdflYD6HV-lxSajreGrJLr"
    try:
        import requests  # ensure installed
    except Exception:
        requests = None

    def _post_name_change_discord(old_name: str, new_name: str):
        msg = f"🪦 **Obituaries** — Name Change: `{old_name}` → `{new_name}`"
        if not requests:
            print(f"[Discord skipped] {msg}")
            return
        try:
            resp = requests.post(NAME_CHANGE_WEBHOOK, json={"content": msg}, timeout=10)
            if resp.status_code not in (200, 201, 202, 204):
                print(f"[Discord webhook error] HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[Discord webhook exception] {e}")

    def _ensure_obituaries_visible():
        """Ensure the Obituaries table is visible; re-navigate if needed."""
        if _find_element(By.XPATH, OBITUARIES_TABLE_XPATH):
            return True
        if not _navigate_to_page_via_menu("//span[@class='city']",
                                          "//a[@class='business funeral_parlour']",
                                          "Funeral Parlour"):
            return False
        if not _find_and_click(By.XPATH, VIEW_DAILY_OBITS_XPATH, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
            return False
        global_vars.wait.until(ec.presence_of_element_located((By.XPATH, OBITUARIES_TABLE_XPATH)))
        return True

    print("\n--- Starting Funeral Parlour Scan for Deceased Players ---")
    initial_url = global_vars.driver.current_url

    # Acquire shared timer/lease; skip if another bot owns it or it's not due yet
    got_lock = acquire_distributed_timer(
        TIMER_NAME_FUNERAL_YELLOW,
        interval_seconds=INTERVAL_SECONDS,
        lease_seconds=LEASE_SECONDS,
    )
    if not got_lock:
        print("Shared timer not due or leased by another bot. Skipping.")
        return True

    # Navigate to Funeral Parlour
    if not _navigate_to_page_via_menu("//span[@class='city']",
                                      "//a[@class='business funeral_parlour']",
                                      "Funeral Parlour"):
        print("Navigation to Funeral Parlour failed. Rescheduling in 10 minutes.")
        reschedule_distributed_timer(TIMER_NAME_FUNERAL_YELLOW, RETRY_SECONDS)
        try:
            global_vars.driver.get(initial_url)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception:
            pass
        return True

    # “Under going repairs” short-circuit (NO Yellow Pages on failure)
    closed_message_element = _get_element_text_quiet(
        By.XPATH, "//*[contains(text(), 'while under going repairs')]",
        global_vars.EXPLICIT_WAIT_SECONDS
    )
    if closed_message_element:
        print("Funeral Parlour is under repairs. Next attempt in 60 minutes.")
        reschedule_distributed_timer(TIMER_NAME_FUNERAL_YELLOW, 3600)
        try:
            global_vars.driver.get(initial_url)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception:
            pass
        return True

    # Open Daily Obituaries (NO Yellow Pages on failure)
    if not _find_and_click(By.XPATH, VIEW_DAILY_OBITS_XPATH, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        print("Could not open Daily Obituaries. Rescheduling in 10 minutes.")
        reschedule_distributed_timer(TIMER_NAME_FUNERAL_YELLOW, RETRY_SECONDS)
        try:
            global_vars.driver.get(initial_url)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception:
            pass
        return True

    # Ensure table is present (NO Yellow Pages on failure)
    if not _ensure_obituaries_visible():
        print("Failed to load obituaries table. Rescheduling in 10 minutes.")
        reschedule_distributed_timer(TIMER_NAME_FUNERAL_YELLOW, RETRY_SECONDS)
        try:
            global_vars.driver.get(initial_url)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception:
            pass
        return True

    obituary_table = _find_element(By.XPATH, OBITUARIES_TABLE_XPATH)
    if not obituary_table:
        print("Obituary table not found. Rescheduling in 10 minutes.")
        reschedule_distributed_timer(TIMER_NAME_FUNERAL_YELLOW, RETRY_SECONDS)
        try:
            global_vars.driver.get(initial_url)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception:
            pass
        return True

    # Snapshot entries so we can navigate away and return safely
    rows = obituary_table.find_elements(By.TAG_NAME, "tr")[1:]  # skip header
    entries = []
    for row in rows:
        name_links = row.find_elements(By.XPATH, ".//td[1]/a")
        if not name_links:
            continue
        original_name = name_links[0].text.strip()
        profile_href = name_links[0].get_attribute("href") or ""
        death_type_elems = row.find_elements(By.XPATH, ".//td[5]")
        death_type = death_type_elems[0].text.strip() if death_type_elems else ""
        if original_name:
            entries.append({
                "original_name": original_name,
                "profile_href": profile_href,
                "death_type": death_type
            })

    # 1) Process Name Changes first
    for e in [x for x in entries if x["death_type"].strip().lower() == "name change"]:
        try:
            if e["profile_href"]:
                global_vars.driver.get(e["profile_href"])
            else:
                link = _find_element(By.XPATH, f"//a[normalize-space()='{e['original_name']}']")
                if not link:
                    print(f"Could not open profile for {e['original_name']}; skipping rename.")
                    continue
                link.click()

            global_vars.wait.until(ec.presence_of_element_located((By.XPATH, PROFILE_NEWNAME_XPATH)))
            new_name_el = _find_element(By.XPATH, PROFILE_NEWNAME_XPATH)
            if not new_name_el:
                print(f"New name element not found for {e['original_name']}; skipping.")
            else:
                new_name = new_name_el.text.strip()
                if new_name and new_name.lower() != e["original_name"].lower():
                    if rename_player_in_players_table(e["original_name"], new_name):
                        _post_name_change_discord(e["original_name"], new_name)
                else:
                    print(f"No change detected for {e['original_name']} (new='{new_name}').")
        except Exception as ex:
            print(f"Error while processing Name Change for {e['original_name']}: {ex}")

        # Return to obituaries and re-ensure table after each profile visit
        try:
            global_vars.driver.back()
            _ensure_obituaries_visible()
        except Exception as e:
            print(f"Return to obits failed after rename: {e}")

    # 2) Delete entries for target death types
    for e in entries:
        dt = e["death_type"].strip().lower()
        if dt in DEATH_TYPES_TO_DELETE:
            try:
                remove_player_cooldown(e["original_name"])  # DynamoDB delete
            except Exception as e_del:
                print(f"Delete error for {e['original_name']}: {e_del}")

    # Success: set next window, return to initial page, and THEN run Yellow Pages
    complete_distributed_timer(TIMER_NAME_FUNERAL_YELLOW, INTERVAL_SECONDS)
    try:
        global_vars.driver.get(initial_url)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    except Exception:
        pass

    # Only run Yellow Pages after a successful Funeral Parlour run
    try:
        execute_yellow_pages_scan()
    except Exception as e:
        print(f"Yellow Pages chain error (final): {e}")

    print("--- Funeral Parlour Scan Completed ---")
    return True

def execute_yellow_pages_scan():

    print("\n--- Starting Yellow Pages Scan ---")
    initial_url = global_vars.driver.current_url

    # ---- Local, hard-coded Discord webhook poster (no send_discord_notification used) ----
    DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1422078249957068891/czUdlKjeDUixsymugsCJ91uWfDsSe9i9T3K5bOoQLenayfAKicQUOtnGcPeiQhSQANkP"

    def _post_to_discord(message: str):
        """Post a simple message to the hard-coded webhook.
        Falls back to print if requests isn't available or the call fails."""
        payload = {"content": message}
        if not requests:
            print(f"[Discord webhook skipped] {message}")
            return
        try:
            resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            # Discord webhooks usually return 204 No Content on success
            if resp.status_code not in (200, 201, 202, 204):
                print(f"[Discord webhook error] HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[Discord webhook exception] {e}")

    # Navigate to Yellow Pages
    if not _navigate_to_page_via_menu(
            "//*[@id='nav_left']/div[3]/a[2]",
            "//*[@id='city_holder']//a[contains(@class, 'business') and contains(@class, 'yellow_pages')]",
            "Yellow Pages"):
        print("FAILED: Navigation to Yellow Pages failed. Skipping scan.")
        return False

    occupations = [
        "UNEMPLOYED", "MAYOR", "BANK", "HOSPITAL", "ENGINEERING",
        "FUNERAL", "FIRE", "LAW", "CUSTOMS", "POLICE", "GANGSTER"
    ]

    search_input_xpath = "//*[@id='content']/center/div/div[2]/form/p[2]/input"
    search_button_xpath = "/html/body/div[4]/div[4]/center/div/div[2]/form/p[3]/input"
    results_table_xpath = "//*[@id='content']/center/div/div[2]/table"

    total_players_scanned = 0

    for occupation in occupations:
        print(f"Scanning occupation: {occupation}...")
        try:
            # Ensure we're still on Yellow Pages
            if "yellowpages.asp" not in global_vars.driver.current_url:
                if not _navigate_to_page_via_menu(
                        "//*[@id='nav_left']/div[3]/a[2]",
                        "//*[@id='city_holder']//a[contains(@class, 'business') and contains(@class, 'yellow_pages')]",
                        "Yellow Pages"):
                    print(f"CRITICAL FAILED: Failed to re-navigate for {occupation}. Skipping.")
                    continue

            # Enter occupation and search
            if not _find_and_send_keys(By.XPATH, search_input_xpath, occupation):
                print(f"FAILED: Failed to enter occupation '{occupation}'. Skipping.")
                continue
            if not _find_and_click(By.XPATH, search_button_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
                print(f"FAILED: Failed to click search button for '{occupation}'. Skipping.")
                continue

            # Parse results table
            results_table = _find_element(By.XPATH, results_table_xpath)
            if not results_table:
                print(f"No results table found for occupation '{occupation}'.")
                # Try to go back to the search screen anyway
                global_vars.driver.back()
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                global_vars.wait.until(ec.presence_of_element_located((By.XPATH, search_input_xpath)))
                continue

            player_rows = results_table.find_elements(By.TAG_NAME, "tr")
            data_rows = [
                row for row in player_rows
                if row.find_elements(By.XPATH, ".//a[contains(@href, 'userprofile.asp')]")
            ]

            players_found_in_occupation = 0

            for row in data_rows:
                # Player name (required)
                name_links = row.find_elements(By.XPATH, ".//td[1]/a")
                if not name_links:
                    print(f"WARNING: Missing player name link for {occupation}. Skipping row.")
                    continue
                player_name = name_links[0].text.strip()

                # Occupation can be in td[2] (normal) or td[3] (Commissioner / Commissioner-General)
                occ2_elems = row.find_elements(By.XPATH, ".//td[2]")
                occupation_td2 = occ2_elems[0].text.strip() if occ2_elems else ""

                occ3_elems = row.find_elements(By.XPATH, ".//td[3]")
                occupation_td3 = occ3_elems[0].text.strip() if occ3_elems else ""

                # Home City (td[4])
                city_elems = row.find_elements(By.XPATH, ".//td[4]")
                if not city_elems:
                    print(f"WARNING: Missing Home City cell for {player_name}. Skipping row.")
                    continue
                player_city = city_elems[0].text.strip()

                # --- DynamoDB: HomeCity upsert + notify on change (FirstSeen handled on new) ---
                upsert_player_home_city(
                    player_name=player_name,
                    home_city=player_city,
                    notify=_post_to_discord
                )

                # --- DynamoDB: Mark top job if applicable (check both td[2] and td[3]) ---
                mark_top_job(player_name, occupation_td2)
                mark_top_job(player_name, occupation_td3)

                total_players_scanned += 1
                players_found_in_occupation += 1

            print(f"Scanned {players_found_in_occupation} players in {occupation}.")

            # Go back to the search page and wait until it's ready
            global_vars.driver.back()
            time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
            global_vars.wait.until(ec.presence_of_element_located((By.XPATH, search_input_xpath)))

        except Exception as e:
            print(f"Error during scan for occupation '{occupation}': {e}. Attempting recovery.")
            if not _navigate_to_page_via_menu(
                    "//*[@id='nav_left']/div[3]/a[2]",
                    "//*[@id='city_holder']//a[contains(@class, 'business') and contains(@class, 'yellow_pages')]",
                    "Yellow Pages"):
                print(f"CRITICAL FAILED: Failed to recover navigation for {occupation}. Stopping scan.")
                return False

    # Timestamp + return to initial page
    print(f"Yellow Pages Scan Completed. Total players scanned: {total_players_scanned}.")
    global_vars.driver.get(initial_url)
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Increment OnlineHours (+1) for players currently online at the bottom panel
    print(f"Adding ONLINE HOURS to players online.")
    try:
        player_online_hours()
    except Exception as e:
        print(f"[OnlineHours] Error: {e}")

    return True

def player_online_hours():

    # Open the online list
    if not _find_and_click(
        By.XPATH,
        "/html/body/div[5]/div[1]/div[2]/div[1]/span[1]",
        pause=global_vars.ACTION_PAUSE_SECONDS * 2
    ):
        print("[OnlineHours] Could not open online list; skipping.")
        return False

    container = _find_element(By.XPATH, "/html/body/div[5]/div[3]/div[2]")
    if not container:
        print("[OnlineHours] Online players container not found; skipping.")
        # still go to /localcity/local.asp to leave the page in a good state
        try:
            cur = urlsplit(global_vars.driver.current_url)
            target = f"{cur.scheme}://{cur.netloc}/localcity/local.asp"
            global_vars.driver.get(target)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception as e:
            print(f"[OnlineHours] Navigation error to /localcity/local.asp: {e}")
        return False

    # Collect player names from <a id="profileLink:<name>:" ...>
    names = set()
    for link in container.find_elements(By.TAG_NAME, "a"):
        id_attr = link.get_attribute("id") or ""
        m = re.search(r'^profileLink:([^:]+):', id_attr)
        if m:
            names.add(m.group(1))

    if not names:
        print("[OnlineHours] No online players detected.")
        # Navigate to /localcity/local.asp before returning
        try:
            cur = urlsplit(global_vars.driver.current_url)
            target = f"{cur.scheme}://{cur.netloc}/localcity/local.asp"
            global_vars.driver.get(target)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception as e:
            print(f"[OnlineHours] Navigation error to /localcity/local.asp: {e}")
        return True

    # Increment OnlineHours in DynamoDB (only if the item exists)
    table = global_vars.get_players_table()
    pk = global_vars.DDB_PLAYER_PK

    updated = 0
    skipped_missing = 0
    for player_name in names:
        try:
            table.update_item(
                Key={pk: player_name},
                UpdateExpression="SET OnlineHours = if_not_exists(OnlineHours, :zero) + :one",
                ExpressionAttributeValues={":zero": 0, ":one": 1},
                ConditionExpression=Attr(pk).exists(),  # only update existing items
            )
            updated += 1
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                skipped_missing += 1
            else:
                print(f"[OnlineHours] Update error for {player_name}: {e}")

    print(f"[OnlineHours] +1 for {updated} players (skipped missing: {skipped_missing}).")

    # Go to /localcity/local.asp at the end
    try:
        cur = urlsplit(global_vars.driver.current_url)
        target = f"{cur.scheme}://{cur.netloc}/localcity/local.asp"
        global_vars.driver.get(target)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    except Exception as e:
        print(f"[OnlineHours] Navigation error to /localcity/local.asp: {e}")

    return True

def log_aggravated_event(crime_type, target, status, amount):
    """Logs an aggravated crime event."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"{timestamp} - Crime: {crime_type}, Target: {target}, Status: {status}, Amount: {amount}\n"
    print(f"LOG: {log_message.strip()}")
    try:
        with open(global_vars.AGGRAVATED_CRIMES_LOG_FILE, 'a') as f:
            f.write(log_message)
    except Exception as e:
        print(f"Error writing to aggravated crimes log file: {e}")

def _open_aggravated_crime_page(crime_type):
    """
    Navigates to the specified aggravated crime page (Hack, Pickpocket, Armed Robbery, or Torch).
    The process is skipped if the current URL is already on the Aggrivated Crime page
    """
    if "income/agcrime.asp" not in global_vars.driver.current_url:
        if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//a[@href='/income/agcrime.asp'][normalize-space()='Aggravated Crimes']",
            "Aggravated Crime Page"):
            return False

        # check the page-level fail box before touching any radio <<<
        fail_text = _get_element_text_quiet(By.XPATH, "//div[@id='fail']")
        if fail_text:
            # Example text: "You cannot commit an aggravated crime until you have completed another 1 Services to your community!"
            m = re.search(r"another\s+(\d+)\s+Services", (fail_text or ""), re.IGNORECASE)
            if m:
                needed = int(m.group(1))
                if needed > 0:
                    enqueue_community_services(needed)
                    print(f"Aggravated Crime gate requires {needed} Community Service(s). Queued them.")
                    return False  # Bail out here; Main will process the CS queue.

    radio_button_xpath = {
        "Hack": "//input[@type='radio' and @value='hack' and @name='agcrime']",
        "Pickpocket": "//input[@type='radio' and @value='pickpocket' and @name='agcrime']",
        "Mugging": "//input[@id='mugging']",
        "BnE": "//input[@id='breaking']",
        "Torch": "//input[@type='radio' and @value='torchbusiness' and @name='agcrime']",
        "Armed Robbery": "//input[@type='radio' and @value='armed' and @name='agcrime']",
    }

    if not _find_and_click(By.XPATH, radio_button_xpath[crime_type]):
        print(f"Failed to select {crime_type} radio button.")
        return False

    if not _find_and_click(By.XPATH, "//input[@type='submit' and @class='submit' and @value='Commit Crime']"):
        print(f"Failed to click initial 'Commit Crime' button for {crime_type}.")
        return False
    print(f"Successfully opened {crime_type}.")
    return True

def _repay_player(player_name, amount):
    """Navigates to the bank transfer page and repays the specified amount to the player."""
    print(f"Attempting to repay {player_name} with ${amount}.")
    if not _navigate_to_page_via_menu(
            "//span[@class='income']",
            "//td[@class='toolitem']//a[normalize-space()='Bank']",
            "Bank Page"):
        log_aggravated_event("Repay", player_name, "Failed (Navigate Bank)", amount)
        return False

    if not _find_and_click(By.XPATH, "//a[normalize-space()='Transfers']"):
        log_aggravated_event("Repay", player_name, "Failed (Navigate Transfers)", amount)
        return False

    if not _find_and_send_keys(By.XPATH, "//input[@name='transferamount']", str(amount)):
        log_aggravated_event("Repay", player_name, "Failed (Enter Amount)", amount)
        return False
    if not _find_and_send_keys(By.XPATH, "//input[@name='transfername']", player_name):
        log_aggravated_event("Repay", player_name, "Failed (Enter Recipient)", amount)
        return False

    if not _find_and_click(By.XPATH, "//input[@id='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        log_aggravated_event("Repay", player_name, "Failed (Click Transfer)", amount)
        return False

    confirmation_message = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if confirmation_message:
        log_aggravated_event("Repay", player_name, "Repaid Successfully", amount)
        return True
    else:
        log_aggravated_event("Repay", player_name, "Repaid Successfully (No Conf. Message)", amount)
        return True

def _get_suitable_crime_target(my_home_city, character_name, excluded_players, cooldown_key):
    """Retrieves a suitable player from DynamoDB for a crime."""
    game_now = get_current_game_time()  # use game clock

    # Pull candidates from DDB (prefiltered by city for major crimes)
    candidates = list(get_crime_targets_from_ddb(my_home_city, cooldown_key))
    random.shuffle(candidates)

    for player_id, target_home_city in candidates:
        if not player_id:
            continue
        if player_id == character_name or (excluded_players and player_id in excluded_players):
            continue

        # City rule: already enforced by get_crime_targets_from_ddb for Major;
        # for Minor, it's always allowed.
        cooldown_end_time = get_player_cooldown(player_id, cooldown_key)
        if cooldown_end_time is None or (game_now - cooldown_end_time).total_seconds() >= 0:
            return player_id

    return None

def _get_suitable_pickpocket_target_online(character_name, excluded_players):
    """Retrieves a suitable player for pickpocketing/mugging from the online list."""
    if not _find_and_click(By.XPATH, "/html/body/div[5]/div[1]/div[2]/div[1]/span[2]", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return None

    online_players_container = _find_element(By.XPATH, "/html/body/div[5]/div[3]/div[1]")
    if not online_players_container:
        return None

    online_player_links = online_players_container.find_elements(By.TAG_NAME, "a")
    available_players = []

    for link in online_player_links:
        player_id_attr = link.get_attribute("id")
        if player_id_attr and player_id_attr.startswith("profileLink:"):
            match = re.search(r'profileLink:([^:]+):', player_id_attr)
            if match:
                player_name = match.group(1)
                if player_name == character_name or (excluded_players and player_name in excluded_players):
                    continue

                cooldown_end_time = get_player_cooldown(player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY)
                game_now = get_current_game_time()

                if cooldown_end_time is None or (game_now - cooldown_end_time).total_seconds() >= 0:
                    available_players.append(player_name)

    if available_players:
        random.shuffle(available_players)
        return available_players[0]
    return None

def _get_business_owner_via_business_page(business_name):
    """
    Navigates directly to the Businesses page, finds the specified business, and extracts its owner.
    Returns owner name or None if not found or "Administrator".
    """
    print(f"Searching for owner of '{business_name}' via Businesses page.")

    if not _find_and_click(By.XPATH, "/html/body/div[4]/div[3]/div[4]/a[1]"):
        print("FAILED: Could not navigate directly to Businesses Page.")
        return None

    businesses_table_xpath = "//div[@id='biz_holder']//table"
    businesses_table = _find_element(By.XPATH, businesses_table_xpath)

    if not businesses_table:
        print("No businesses table found on Businesses page.")
        return None

    rows = businesses_table.find_elements(By.TAG_NAME, "tr")
    for row in rows[1:]:
        try:
            current_business_name_element = row.find_element(By.XPATH, ".//td[1]")
            current_business_name = current_business_name_element.text.strip()
            if current_business_name.lower() == business_name.lower():
                owner_element = row.find_element(By.XPATH, ".//td[2]/b/a")
                owner_name = owner_element.text.strip()
                if owner_name.lower() == "administrator":
                    print(f"Business '{business_name}' is owned by Administrator. No repayment needed.")
                    return None
                print(f"Found owner for '{business_name}': {owner_name}")
                return owner_name
        except NoSuchElementException:
            continue
        except Exception as e:
            print(f"Error parsing business row: {e}")
            continue

    print(f"Owner for business '{business_name}' not found on Businesses page.")
    return None

def _get_business_owner_and_repay(business_name, amount_stolen, player_data):
    """
    Determines the owner of a business based on its type.
    Utilises centralised business lists from global_vars.py.
    """
    owner_name = None
    current_location = player_data.get("Location")

    # Normalize business name: remove city prefix if present
    if current_location and business_name.lower().startswith(current_location.lower()):
        business_name = business_name[len(current_location):].strip()
        # Remove leading punctuation or space (e.g., 'Weapon Shop' from 'auckland weapon shop')
        business_name = re.sub(r"^[\s:,\.\-]+", "", business_name)

    # Check private businesses
    if any(business_name.lower() in [b.lower() for b in city_businesses] for city_businesses in global_vars.private_businesses.values()):
        print(f"Attempting to get owner for private business: {business_name}")
        owner_name = _get_business_owner_via_business_page(business_name)
    else:
        # Check public business via Yellow Pages
        search_occupation = global_vars.PUBLIC_BUSINESS_OCCUPATION_MAP.get(business_name.lower())
        if search_occupation and current_location:
            print(f"Attempting to find owner for public business '{business_name}' via Yellow Pages with occupation: {search_occupation}")
            owner_name = _search_yellow_pages_for_occupation(search_occupation, current_location)
        else:
            print(f"Business '{business_name}' not recognized for direct owner lookup or current location unknown. Skipping owner search.")

    if owner_name:
        print(f"Owner found for '{business_name}': {owner_name}. Attempting repayment.")
        if _repay_player(owner_name, amount_stolen):
            print(f"Successfully repaid ${amount_stolen} to {owner_name} for '{business_name}'.")
            return True
        else:
            print(f"FAILED to repay ${amount_stolen} to {owner_name} for '{business_name}'.")
            return False
    else:
        print(f"No owner found for '{business_name}' or repayment not applicable. Skipping repayment.")
        return False

def execute_aggravated_crime_logic(player_data):
    """Manages hacking, pickpocketing, mugging, armed robberies, and torch operations."""

    # Hard block: cannot attempt AgCrime while Services are queued
    if community_service_queue_count() > 0:
        print("Aggravated Crime blocked: mandatory Community Service queued. Skipping until queue is cleared.")
        global_vars._script_agg_crime_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
        return False

    do_hack      = cfg_bool('Hack', 'DoHack', False)
    hack_repay   = cfg_bool('Hack', 'Repay', False)
    hack_min     = cfg_int ('Hack', 'min_amount', 1)
    hack_max     = cfg_int ('Hack', 'max_amount', 100)

    do_pickpocket    = cfg_bool('PickPocket', 'DoPickPocket', False)
    pickpocket_repay = cfg_bool('PickPocket', 'Repay', False)
    pickpocket_min   = cfg_int ('PickPocket', 'min_amount', 1)
    pickpocket_max   = cfg_int ('PickPocket', 'max_amount', 100)

    do_mugging    = cfg_bool('Mugging', 'DoMugging', False)
    mugging_repay = cfg_bool('Mugging', 'Repay', False)
    mugging_min   = cfg_int ('Mugging', 'min_amount', 1)
    mugging_max   = cfg_int ('Mugging', 'max_amount', 100)

    do_bne     = cfg_bool('BnE', 'DoBnE', False)
    bne_repay  = cfg_bool('BnE', 'Repay', True)
    # Handles either a single value like "Flat" or a CSV like "Flat, Studio Unit"
    bne_target_apartments = [s.lower() for s in cfg_list('BnE', 'BnETarget')]

    do_armed_robbery = cfg_bool('Armed Robbery', 'DoArmedRobbery', False)
    do_torch         = cfg_bool('Torch', 'DoTorch', False)

    # --- PRIORITY: Torch over Armed Robbery when both are enabled ---
    if do_torch and do_armed_robbery:
        print("\n--- Aggravated Crimes (priority: Torch first, second Armed Robbery) ---")

        # 1) Try Torch first
        if _open_aggravated_crime_page("Torch"):
            if _perform_torch_attempt(player_data):
                _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
                print("Torch attempt initiated. Main Aggravated Crime cooldown set.")
                return True
        else:
            # If we couldn't even open the page, still consider AR fallback
            print("FAILED to open Torch page; considering Armed Robbery fallback.")

        # 2) Fallback to Armed Robbery if Torch wasn't viable
        print("Torch unavailable/no viable targets — trying Armed Robbery…")
        if _open_aggravated_crime_page("Armed Robbery") and _perform_armed_robbery_attempt(player_data):
            _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
            print("Armed Robbery attempt initiated. Main Aggravated Crime cooldown set.")
            return True

        # 3) Neither Torch nor AR could be initiated
        # (Short re-check timers may already be set by the subroutines.)
        print("No viable Torch or Armed Robbery targets right now.")
        return False


    enabled_crimes = [crime_type for crime_type, enabled_status in {
        'Hack': do_hack,
        'Pickpocket': do_pickpocket,
        'Mugging': do_mugging,
        'Armed Robbery': do_armed_robbery,
        'Torch': do_torch,
        'BnE': do_bne,
    }.items() if enabled_status]

    if not enabled_crimes:
        return False

    # Randomly select one of the enabled crimes
    crime_type = random.choice(enabled_crimes)

    # If Hack was selected but you're not in home city, switch to another enabled crime
    if crime_type == "Hack":
        current_city = player_data.get("Location")
        if current_city != player_data.get("Home City"):
            fallback_pool = [c for c in enabled_crimes if c != "Hack"]
            if not fallback_pool:
                print(f"Skipping Hack: not in home city ('{current_city}' vs '{player_data.get('Home City')}'), and no other crimes enabled.")
                return False
            crime_type = random.choice(fallback_pool)
            print(f"Skipping Hack outside home city. Switching to {crime_type}.")

    print(f"\n--- Beginning Aggravated Crime ({crime_type}) Operation ---")

    crime_attempt_initiated = False

    # Hacking
    if crime_type == "Hack":
        min_steal = hack_min
        max_steal = hack_max
        cooldown_key = global_vars.MAJOR_CRIME_COOLDOWN_KEY

        # Only hack if in home city
        current_city = player_data.get("Location")
        if current_city != player_data.get("Home City"):
            print(f"Skipping Hack: Current city '{current_city}' is not home city '{player_data.get('Home City')}'.")
            return False

        if not _open_aggravated_crime_page("Hack"):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()
        retried_no_money = set()

        while attempts_in_cycle < max_attempts_per_cycle:
            current_target_player = _get_suitable_crime_target(player_data['Home City'], player_data['Character Name'], tried_players_in_cycle, cooldown_key)
            if not current_target_player:
                print(f"No more suitable {crime_type} targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
                print(f"Will retry {crime_type} in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_hack_attempt(current_target_player, min_steal, max_steal, retried_no_money)

            if status == 'success':
                if hack_repay and global_vars.hacked_player_for_repay and global_vars.hacked_amount_for_repay:
                    if global_vars.hacked_player_for_repay in retried_no_money:
                        print(f"Skipping repay to {global_vars.hacked_player_for_repay} because we primed with $1 for the retry (looks botty otherwise).")
                    else:
                        _repay_player(global_vars.hacked_player_for_repay, global_vars.hacked_amount_for_repay)
                print(f"{crime_type} successful! Exiting attempts for this cycle.")
                break

            elif status in ['cooldown_target', 'not_online', 'no_money', 'non_existent_target', 'wrong_city']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page("Hack"):
                    print(f"FAILED: Failed to re-open {crime_type} page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break

            elif status in ['failed_password', 'failed_attempt', 'failed_proxy', 'general_error']:
                print(f"{crime_type} failed for {target_attempted} (status: {status}). Exiting attempts for this cycle.")
                break

    # Pickpocket
    elif crime_type == "Pickpocket":
        min_steal = pickpocket_min
        max_steal = pickpocket_max
        cooldown_key = global_vars.MINOR_CRIME_COOLDOWN_KEY

        if not _open_aggravated_crime_page(crime_type):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()

        while attempts_in_cycle < max_attempts_per_cycle:
            current_target_player = _get_suitable_pickpocket_target_online(player_data['Character Name'], tried_players_in_cycle)
            if not current_target_player:
                print(f"No more suitable {crime_type} targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
                print(f"Will retry {crime_type} in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_pickpocket_attempt(current_target_player, min_steal, max_steal)

            if status == 'success':
                if pickpocket_repay:
                    if global_vars.pickpocketed_player_for_repay and global_vars.pickpocketed_amount_for_repay:
                        _repay_player(global_vars.pickpocketed_player_for_repay, global_vars.pickpocketed_amount_for_repay)
                print(f"{crime_type} successful! Exiting attempts for this cycle.")
                break
            elif status in ['cooldown_target', 'not_online', 'no_money', 'failed_proxy', 'non_existent_target', 'wrong_city']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page(crime_type):
                    print(f"FAILED: Failed to re-open {crime_type} page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break


            elif status in ['failed_password', 'failed_attempt', 'general_error']:
                print(f"{crime_type} failed for {target_attempted} (status: {status}). Exiting attempts for this cycle.")
                break

    # Mugging
    elif crime_type == "Mugging":
        min_steal = mugging_min
        max_steal = mugging_max
        cooldown_key = global_vars.MINOR_CRIME_COOLDOWN_KEY

        if not _open_aggravated_crime_page(crime_type):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()

        while attempts_in_cycle < max_attempts_per_cycle:
            current_target_player = _get_suitable_pickpocket_target_online(player_data['Character Name'], tried_players_in_cycle)
            if not current_target_player:
                print(f"No more suitable {crime_type} targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
                print(f"Will retry {crime_type} in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_mugging_attempt(current_target_player, min_steal, max_steal)

            if status == 'success':
                if mugging_repay:
                    if global_vars.mugging_player_for_repay and global_vars.mugging_amount_for_repay:
                        _repay_player(global_vars.mugging_player_for_repay, global_vars.mugging_amount_for_repay)
                print(f"{crime_type} successful! Exiting attempts for this cycle.")
                break
            elif status in ['cooldown_target', 'not_online', 'no_money', 'failed_proxy', 'non_existent_target', 'wrong_city']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page(crime_type):
                    print(f"FAILED: Failed to re-open {crime_type} page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break

            elif status in ['failed_password', 'failed_attempt', 'general_error']:
                print(f"{crime_type} failed for {target_attempted} (status: {status}). Exiting attempts for this cycle.")
                break

    # BnE
    elif crime_type == "BnE":
        if not _open_aggravated_crime_page("BnE"):
            return False

        attempts_in_cycle = 0
        max_attempts_per_cycle = 60
        tried_players_in_cycle = set()

        current_city = player_data.get("Location")
        character_name = player_data.get("Character Name")

        while attempts_in_cycle < max_attempts_per_cycle:
            # First try with the configured apartment filter (if any)
            current_target_player = _get_suitable_bne_target(
                current_city, character_name, tried_players_in_cycle, apartment_filters=bne_target_apartments)

            # Fallback to anyone if a filter was set but no target found
            if not current_target_player and bne_target_apartments:
                print(f"No BnE targets with apartments {bne_target_apartments}. Falling back to any apartment.")
                current_target_player = _get_suitable_bne_target(current_city, character_name, tried_players_in_cycle, apartment_filters=None)

            if not current_target_player:
                print("No more suitable BnE targets found in the database for this cycle.")
                retry_minutes = random.randint(3, 5)
                global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(
                    minutes=retry_minutes)
                print(f"Will retry BnE in {retry_minutes} minutes.")
                break

            attempts_in_cycle += 1
            crime_attempt_initiated = True
            status, target_attempted, amount_stolen = _perform_bne_attempt(current_target_player, repay_enabled=bne_repay)

            if status == 'success':
                if bne_repay and global_vars.bne_player_for_repay and global_vars.bne_amount_for_repay:
                    _repay_player(global_vars.bne_player_for_repay, global_vars.bne_amount_for_repay)
                print("BnE successful! Exiting attempts for this cycle.")
                break

            elif status == 'failed_attempt':
                print("BnE attempt failed. Exiting attempts for this cycle.")
                break

            elif status in ['cooldown_target', 'no_apartment', 'general_error', 'wrong_city', 'non_existent_target']:
                tried_players_in_cycle.add(target_attempted)
                if not _open_aggravated_crime_page("BnE"):
                    print("FAILED: Failed to re-open BnE page. Cannot continue attempts for this cycle.")
                    break

            elif status == 'aggs_blocked':
                print(f"[{crime_type}] Blocked due to too many fails. Standing down for 30 minutes.")
                break

    # Armed Robbery
    elif crime_type == "Armed Robbery":
        if not _open_aggravated_crime_page("Armed Robbery"):
            return False
        if _perform_armed_robbery_attempt(player_data):
            crime_attempt_initiated = True
            _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
            print("Armed Robbery attempt initiated. Main Aggravated Crime cooldown set.")
            return True
        else:
            print("Armed Robbery attempt not initiated (e.g., no suitable targets found or pre-attempt failures).")
            return False

    # Torch
    elif crime_type == "Torch":
        if not _open_aggravated_crime_page("Torch"):
            return False
        if _perform_torch_attempt(player_data):
            crime_attempt_initiated = True
            _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
            print("Torch attempt initiated. Main Aggravated Crime cooldown set.")
            return True
        else:
            print("Torch: No eligible targets with asterisk found. Skipping general cooldown for now.")
            return False

    # --- Final cooldown handling ---
    short_retry_set = (global_vars._script_aggravated_crime_recheck_cooldown_end_time and global_vars._script_aggravated_crime_recheck_cooldown_end_time > datetime.datetime.now())

    if crime_attempt_initiated and not short_retry_set:
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, datetime.datetime.now())
        print(f"Finished {crime_type} attempts for this cycle. Aggravated Crime cooldown set.")
        return True
    elif not short_retry_set:
        retry_minutes = random.randint(3, 5)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_minutes)
        print(f"Finished {crime_type} attempts for this cycle. No crime attempt initiated. Will retry in {retry_minutes} minutes.")
        return False
    else:
        print(f"Short retry cooldown already set for {crime_type}. Skipping long cooldown.")
        return False

def _perform_pickpocket_attempt(target_player_name, min_steal, max_steal):
    """Performs a pickpocketing attempt."""

    global_vars.pickpocketed_player_for_repay = None
    global_vars.pickpocketed_amount_for_repay = None
    global_vars.pickpocket_successful = False

    steal_amount = random.randint(min_steal, max_steal)
    crime_type = "Pickpocket"

    if not _find_and_send_keys(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form/p[2]/span/input[2]", target_player_name):
        return 'general_error', target_player_name, None
    if not _find_and_send_keys(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form/p[4]/input", str(steal_amount)):
        return 'general_error', target_player_name, None

    if not _find_and_click(By.XPATH, "/html/body/div[4]/div[4]/div[2]/div[2]/form/p[5]/input", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return 'general_error', target_player_name, None

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event(crime_type, target_player_name, "Script Error (No Result Msg)", 0)
        return 'general_error', target_player_name, None

    now = get_current_game_time()

    if "try them again later" in result_text or "recently survived an aggravated crime" in result_text:
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=3))
        return 'cooldown_target', target_player_name, None

    if "must be online" in result_text:
        print(f"Target '{target_player_name}' is not online. Skipping pickpocketing.")
        return 'not_online', target_player_name, None

    if "The name you typed in doesn't exist" in result_text:
        print(f"INFO: Target '{target_player_name}' does not exist.")
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=15))
        return 'non_existent_target', target_player_name, None

    # FAILED TOO MANY RECENTLY
    if "as you have failed too many" in (result_text or "").lower():
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return 'aggs_blocked', None, None

    if "The victim must be in the same city as you" in result_text:
        print(f"INFO: Target '{target_player_name}' is not in the same city.")
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=30))
        return 'wrong_city', target_player_name, None

    if f"You pickpocketed" in result_text and "for $" in result_text:
        try:
            stolen_name_match = result_text.split("You pickpocketed ")[1].split(" for $")[0].strip()
            stolen_amount_str = result_text.split(" for $")[1].split("!")[0].strip()
            stolen_actual_amount = int(''.join(filter(str.isdigit, stolen_amount_str)))

            set_player_data(stolen_name_match, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1, minutes=10))
            global_vars.pickpocketed_player_for_repay = stolen_name_match
            global_vars.pickpocketed_amount_for_repay = stolen_actual_amount
            global_vars.pickpocket_successful = True
            log_aggravated_event(crime_type, stolen_name_match, "Success", stolen_actual_amount)
            return 'success', stolen_name_match, stolen_actual_amount
        except Exception:
            log_aggravated_event(crime_type, target_player_name, "Script Error (Parse Success)", 0)
            return 'general_error', target_player_name, None

    if "and failed" in result_text:
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1, minutes=10))
        log_aggravated_event(crime_type, target_player_name, "Failed", 0)
        return 'failed_attempt', target_player_name, None

    log_aggravated_event(crime_type, target_player_name, "Failed", 0)
    return 'general_error', target_player_name, None

def _perform_hack_attempt(target_player_name, min_steal, max_steal, retried_targets=None):
    """Performs a single hacking attempt."""

    if retried_targets is None:
        retried_targets = set()

    global_vars.hacked_player_for_repay = None
    global_vars.hacked_amount_for_repay = None
    global_vars.hacked_successful = False

    steal_amount = random.randint(min_steal, max_steal)
    crime_type = "Hack"

    if not _find_and_send_keys(By.XPATH, "//input[@name='hack']", target_player_name):
        return 'general_error', target_player_name, None
    if not _find_and_send_keys(By.XPATH, "//input[@name='cap']", str(steal_amount)):
        return 'general_error', target_player_name, None

    if not _find_and_click(By.XPATH, "//input[@name='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return 'general_error', target_player_name, None

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event(crime_type, target_player_name, "Script Error (No Result Msg)", 0)
        return 'general_error', target_player_name, None

    now = get_current_game_time()

    if "players account has increased security" in result_text:
        set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=3))
        return 'cooldown_target', target_player_name, None

    if "name you typed in" in result_text:
        print(f"INFO: Target '{target_player_name}' does not exist.")
        remove_player_cooldown(target_player_name)
        return 'non_existent_target', target_player_name, None

    if "as you have failed too many" in (result_text or "").lower():
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return 'aggs_blocked', None, None

    if "no money in their account" in result_text:
        # Allow the transfer+retry only once per target (for this cycle)
        if target_player_name in retried_targets:
            print(f"INFO: Target '{target_player_name}' still has no money and retry already used. Skipping further retries.")
            set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1))
            return 'no_money', target_player_name, None

        print(f"INFO: Target '{target_player_name}' has no money. Sending $1 and retrying once...")
        if transfer_money(1, target_player_name):
            retried_targets.add(target_player_name)
            print("Transfer successful. Retrying hack on same target using configured amount...")
            # Re-open Hack page after returning from Bank so the Hack form exists again
            if not _open_aggravated_crime_page("Hack"):
                print("FAILED: Could not re-open Hack page after transfer. Aborting retry.")
                return 'general_error', target_player_name, None
            # Re-enter details in the same way you already do (kept identical to your current flow)
            if not _find_and_send_keys(By.XPATH, "//input[@name='hack']", target_player_name):
                return 'general_error', target_player_name, None
            if not _find_and_send_keys(By.XPATH, "//input[@name='cap']", str(steal_amount)):
                return 'general_error', target_player_name, None
            if not _find_and_click(By.XPATH, "//input[@name='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
                return 'general_error', target_player_name, None
            # Read the new result and continue evaluation below
            result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]") or ""

            # If they still have no money after the $1 prime, park them for 24 hours and move on
            if "no money in their account" in (result_text or ""):
                print(f"INFO: Target '{target_player_name}' still has no money after $1 prime. Parking for 24h and moving on.")
                set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=24))
                return 'no_money', target_player_name, None
        else:
            print("Failed to transfer $1, skipping retry.")
            set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1))
            return 'no_money', target_player_name, None

    if f"You managed to {crime_type.lower()}" in result_text and "bank account" in result_text and "You transferred $" in result_text:
        try:
            stolen_name_match = \
                result_text.split(f"You managed to {crime_type.lower()} into ")[1].split("'s bank account")[0].strip()
            stolen_amount_str = result_text.split("You transferred $")[1].split(" to a fake account")[0].strip()
            stolen_actual_amount = int(''.join(filter(str.isdigit, stolen_amount_str)))

            set_player_data(stolen_name_match, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=12))
            global_vars.hacked_player_for_repay = stolen_name_match
            global_vars.hacked_amount_for_repay = stolen_actual_amount
            global_vars.hacked_successful = True
            log_aggravated_event(crime_type, stolen_name_match, "Success", stolen_actual_amount)
            return 'success', stolen_name_match, stolen_actual_amount
        except Exception:
            log_aggravated_event(crime_type, target_player_name, "Script Error (Parse Success)", 0)
            return 'general_error', target_player_name, None

    if "could not guess their password" in result_text:
        set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=12))
        log_aggravated_event(crime_type, target_player_name, "Failed", 0)
        return 'failed_password', target_player_name, None

    if "behind a proxy server" in result_text:
        set_player_data(target_player_name, global_vars.MAJOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=12))
        log_aggravated_event(crime_type, target_player_name, "Failed", 0)
        return 'failed_proxy', target_player_name, None

    log_aggravated_event(crime_type, target_player_name, "Failed", 0)
    return 'general_error', target_player_name, None

def _perform_armed_robbery_attempt(player_data, selected_business_name=None):
    """
    Performs an armed robbery attempt, including selecting a valid business and handling outcomes.
    Assumes the script is ALREADY on the Armed Robbery specific business selection page.
    Returns True on successful initiation of an attempt (even if it fails or yields no money),
    False otherwise (e.g., no eligible targets after retries).
    """
    global_vars.armed_robbery_amount_for_repay = None
    global_vars.armed_robbery_business_name_for_repay = None
    global_vars.armed_robbery_successful = False

    # --- Locate dropdown ---
    dropdown_xpath = "/html/body/div[4]/div[4]/div[2]/div[2]/form/p[2]/select"
    try:
        dropdown_element = global_vars.wait.until(ec.presence_of_element_located((By.XPATH, dropdown_xpath)))
    except TimeoutException:
        print("FAILED: Armed Robbery dropdown not found. Cannot proceed with armed robbery.")
        global_vars._script_armed_robbery_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(1, 3))
        return False

    select = Select(dropdown_element)
    options = select.options

    # --- Find eligible businesses ---
    eligible_businesses = []
    for option in options:
        business_text = option.text.strip()
        if business_text != "Please Select..." and "Drug House" not in business_text and "*" in business_text:
            business_name_for_value = business_text.replace('*', '').strip()
            eligible_businesses.append((business_name_for_value, business_text))

    if not eligible_businesses:
        print("No businesses with an asterisk (excluding Drug House) found for Armed Robbery. Setting short re-check timer.")
        global_vars._script_armed_robbery_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(45, 110))
        return False

    selected_business_name, selected_business_full_option_text = random.choice(eligible_businesses)
    print(f"Attempting Armed Robbery at: {selected_business_name} (Full option text: {selected_business_full_option_text})")

    # --- Select business ---
    try:
        select.select_by_visible_text(selected_business_full_option_text)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        print(f"Successfully selected business '{selected_business_name}' from dropdown.")
    except Exception as e:
        print(f"FAILED: Could not select business '{selected_business_name}' in dropdown using Select class: {e}")
        return False

    # --- Click 'Commit Crime' button ---
    commit_crime_button_xpath = "//input[@name='B1']"
    if not _find_and_click(By.XPATH, commit_crime_button_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        print("FAILED: Could not click final 'Commit Crime' button for Armed Robbery.")
        return False

    # --- Get result text ---
    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event("Armed Robbery", selected_business_name, "Script Error (No Result Msg)", 0)
        return True

    # --- Knockout handling ---
    knockout_text = _get_element_text(By.XPATH, "//span[@class='large']")
    if knockout_text and "It knocked you right out" in global_vars.driver.page_source:
        print(f"Knockout detected! Timer string: '{knockout_text}'")

        release_time = parse_game_datetime(knockout_text)
        current_game_time_text = _get_element_text(By.XPATH, "//*[@id='header_time']/div")
        current_game_time = parse_game_datetime(current_game_time_text)

        if release_time and current_game_time:
            seconds_remaining = (release_time - current_game_time).total_seconds()
            if 0 < seconds_remaining < 600:
                readable_minutes = int(seconds_remaining // 60)
                readable_seconds = int(seconds_remaining % 60)
                global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds_remaining + 5)

                print(f"Knocked out until {release_time}. Sleeping actions for {seconds_remaining:.0f} seconds.")
                send_discord_notification(
                    f"KO! You’ve been knocked out by debris during an armed robbery.\n"
                    f"Release in {readable_minutes}m {readable_seconds}s (at {release_time.strftime('%I:%M:%S %p')})"
                )
                return True

        else:
            print("Failed to parse knockout release time. Proceeding with default logic.")

    # --- Result cases ---

    now = get_current_game_time()

    # Failed too many
    if "as you have failed too many" in (result_text or "").lower():
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return False

    if "You managed to hold up the" in result_text:
        try:
            business_match = re.search(r'hold up the (.+?)(?: and| -| nothing|!| for \$|$)', result_text)
            stolen_business_name = business_match.group(1).strip() if business_match else selected_business_name or "Unknown Business"
            stolen_business_name = re.sub(r'[\`\n\r\t]', '', stolen_business_name).strip().lower()

            if " for $" in stolen_business_name:
                stolen_business_name = stolen_business_name.split(" for $")[0].strip()

            # Normalize to known business keys
            for known_business in global_vars.PUBLIC_BUSINESS_OCCUPATION_MAP:
                if known_business in stolen_business_name:
                    stolen_business_name = known_business
                    break

            amount_match = re.search(r'\$\d[\d,]*', result_text)
            stolen_actual_amount = int(amount_match.group(0).replace('$', '').replace(',', '')) if amount_match else 0

            print(f"Successfully robbed {stolen_business_name}. Stolen: ${stolen_actual_amount}")

            log_aggravated_event("Armed Robbery", stolen_business_name, "Success", stolen_actual_amount)
            global_vars.armed_robbery_amount_for_repay = stolen_actual_amount
            global_vars.armed_robbery_business_name_for_repay = stolen_business_name
            global_vars.armed_robbery_successful = True

            if stolen_actual_amount > 0 and cfg_bool('Armed Robbery', 'Repay', False):
                print(f"Repaying ${stolen_actual_amount} to {stolen_business_name}")
                _get_business_owner_and_repay(stolen_business_name, stolen_actual_amount, player_data)
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                print("Repayment completed.")
            else:
                print("No repayment needed (either 0 stolen or repay disabled).")

            return True

        except Exception as e:
            print(f"Error parsing success result: {e}")
            log_aggravated_event("Armed Robbery", selected_business_name or "Unknown Business", "Script Error (Success Parse)", 0)
            global_vars.armed_robbery_successful = False
            return True

    print("Armed Robbery failed. No success message found.")
    log_aggravated_event("Armed Robbery", selected_business_name or "Unknown Business", "Failed", 0)
    return True

def _perform_torch_attempt(player_data):
    """
    Performs a torch attempt, including selecting a valid business and handling outcomes.
    Assumes the script is ALREADY on the Torch specific business selection page.
    Returns True on successful initiation of an attempt (even if it fails or yields no money),
    False otherwise (e.g., no eligible targets after retries).
    """
    global_vars.torch_amount_for_repay = None
    global_vars.torch_business_name_for_repay = None
    global_vars.torch_successful = False

    torch_repay = cfg_bool('Torch', 'Repay', False)
    blacklist_raw = {s.lower() for s in cfg_list('Torch', 'Blacklist')}
    blacklist_items = {item.strip() for item in blacklist_raw.split(',') if item.strip()}
    blacklist_items.add("drug house") # Always blacklist drug house
    blacklist_items.add("fire station")  # Always blacklist fire station

    dropdown_xpath = "/html/body/div[4]/div[4]/div[2]/div[2]/form/p[2]/select"
    try:
        dropdown_element = global_vars.wait.until(ec.presence_of_element_located((By.XPATH, dropdown_xpath)))
    except TimeoutException:
        print("FAILED: Torch dropdown not found. Cannot proceed with torch.")
        # Setting a short re-check cooldown if the dropdown itself isn't found
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(1, 3))
        return False

    select = Select(dropdown_element)
    options = select.options

    eligible_businesses = []
    for option in options:
        business_text = option.text.strip()
        # Ensure it's not the default "Please Select..." option and contains an asterisk
        if business_text == "Please Select..." or "*" not in business_text:
            continue

        business_name_for_value = business_text.replace('*', '').strip()

        is_blacklisted = False
        if "public" in blacklist_items and business_name_for_value in global_vars.public_businesses:
            is_blacklisted = True
        if "private" in blacklist_items and business_name_for_value in global_vars.private_businesses:
            is_blacklisted = True
        for item in blacklist_items:
            if item != "public" and item != "private" and item in business_name_for_value.lower():
                is_blacklisted = True
                break

        if not is_blacklisted:
            eligible_businesses.append((business_name_for_value, business_text))
        else:
            print(f"Skipping blacklisted business for Torch: {business_name_for_value}")

    if not eligible_businesses:
        print(f"No eligible businesses found for Torch after applying blacklist. Setting short re-check cooldown.")
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(
            minutes=random.uniform(1, 3))
        return False

    selected_business_tuple = random.choice(eligible_businesses)
    selected_business_name = selected_business_tuple[0]
    selected_business_full_option_text = selected_business_tuple[1]

    print(f"Attempting Torch at: {selected_business_name}")

    try:
        select.select_by_visible_text(selected_business_full_option_text)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        print(f"Successfully selected business '{selected_business_name}' from dropdown.")
    except Exception as e:
        print(f"FAILED: Could not select business '{selected_business_name}' in dropdown: {e}")
        return False

    commit_crime_button_xpath = "//input[@name='B1']"
    if not _find_and_click(By.XPATH, commit_crime_button_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        print("FAILED: Could not click final 'Commit Crime' button for Torch.")
        return False

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event("Torch", selected_business_name, "Script Error (No Result Msg)", 0)
        return True

    if "managed to set ablaze" in result_text:
        try:
            print(f"Torch success result_text: {result_text}")

            business_name_re_match = re.search(r'managed to set ablaze the (.+?)!', result_text)
            torched_business_name = selected_business_name
            if business_name_re_match:
                extracted_name = business_name_re_match.group(1).strip()
                torched_business_name = f"{player_data.get('Location', '')} {extracted_name}".strip()
                torched_business_name = torched_business_name.lower()
            else:
                print(f"Could not parse torched business name from success message. Using selected_business_name: {selected_business_name}")
                torched_business_name = selected_business_name

            cost_match = re.search(r'\$(\d[\d,]*)(?:\s|\.|!)', result_text)
            extracted_cost = 0
            if cost_match:
                extracted_cost = int(cost_match.group(1).replace(',', ''))
            else:
                print(f"Could not parse torched cost from success message. Defaulting to 0.")

            print(f"Successfully torched {torched_business_name} at a cost of ${extracted_cost}.")
            log_aggravated_event("Torch", torched_business_name, "Success", extracted_cost)
            global_vars.torch_amount_for_repay = extracted_cost
            global_vars.torch_business_name_for_repay = torched_business_name
            global_vars.torch_successful = True

            if torch_repay and extracted_cost > 0:
                print(f"Torch - Repaying ${extracted_cost} to {torched_business_name}.")
                _get_business_owner_and_repay(torched_business_name, extracted_cost, player_data)
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
                print(f"Torch repayment for {torched_business_name} queued.")
            else:
                print(f"Torch successful, but repayment is turned OFF. Skipping repayment.")
            return True

        except Exception as e:
            print(f"Error parsing successful Torch result: {e}")
            log_aggravated_event("Torch", selected_business_name, "Script Error (Parse Success)", 0)
            global_vars.torch_successful = False
            return True # An attempt was made, but parsing failed

    elif "recently survived" in result_text or "not yet repaired" in result_text:
        print(f"Business '{selected_business_name}' recently torched or not repaired. This will trigger a short re-check cooldown.")
        log_aggravated_event("Torch", selected_business_name, "Target Cooldown (No Repair/Recent Torching)", 0)
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(1, 3))
        global_vars.torch_successful = False
        return True

    elif "That business is your own" in result_text:
        print(f"Attempted to torch own business: {selected_business_name}. Setting long cooldown for this target.")
        log_aggravated_event("Torch", selected_business_name, "Own Business", 0)
        global_vars._script_torch_recheck_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(days=1)
        global_vars.torch_successful = False
        return True

    # Failed too many
    elif "as you have failed too many" in result_text:
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        now = get_current_game_time()
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return False

    elif "failed" in result_text or "ran off" in result_text:
        print(f"Torch attempt at {selected_business_name} failed.")
        log_aggravated_event("Torch", selected_business_name, "Failed", 0)
        global_vars.torch_successful = False
        return True
    else:
        print(f"Unexpected result for Torch: {result_text}. This counts as an attempt.")
        log_aggravated_event("Torch", selected_business_name, "Unexpected Result", 0)
        global_vars.torch_successful = False
        return True

def _perform_mugging_attempt(target_player_name, min_steal, max_steal):
    """Performs a mugging attempt."""

    global_vars.mugging_player_for_repay = None
    global_vars.mugging_amount_for_repay = None
    global_vars.mugging_successful = False

    steal_amount = random.randint(min_steal, max_steal)
    crime_type = "Mugging"

    if not _find_and_send_keys(By.XPATH, "//input[@name='mugging']", target_player_name):
        return 'general_error', target_player_name, None
    if not _find_and_send_keys(By.XPATH, "//input[@name='cap']", str(steal_amount)):
        return 'general_error', target_player_name, None

    if not _find_and_click(By.XPATH, "//input[@name='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return 'general_error', target_player_name, None

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]")
    if not result_text:
        log_aggravated_event(crime_type, target_player_name, "Script Error (No Result Msg)", 0)
        return 'general_error', target_player_name, None

    now = get_current_game_time()

    if "try them again later" in result_text:
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=5))
        return 'cooldown_target', target_player_name, None

    if "must be online" in result_text:
        print(f"Target '{target_player_name}' is not online. Skipping pickpocketing.")
        return 'not_online', target_player_name, None

    if "The name you typed in" in result_text:
        print(f"INFO: Target '{target_player_name}' does not exist.")
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=15))
        return 'non_existent_target', target_player_name, None

    if "The victim must be in the same" in result_text:
        print(f"INFO: Target '{target_player_name}' is not in the same city.")
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(minutes=30))
        return 'wrong_city', target_player_name, None

    # Failed too many
    if "as you have failed too many" in result_text.lower():
        now = get_current_game_time()
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return 'aggs_blocked', None, None

    if f"You mugged" in result_text and "for $" in result_text:
        try:
            stolen_name_match = result_text.split("You mugged ")[1].split(" for $")[0].strip()
            stolen_amount_str = result_text.split(" for $")[1].split("!")[0].strip()
            stolen_actual_amount = int(''.join(filter(str.isdigit, stolen_amount_str)))

            set_player_data(stolen_name_match, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1, minutes=55))
            global_vars.mugging_player_for_repay = stolen_name_match
            global_vars.mugging_amount_for_repay = stolen_actual_amount
            global_vars.mugging_successful = True
            log_aggravated_event(crime_type, stolen_name_match, "Success", stolen_actual_amount)
            return 'success', stolen_name_match, stolen_actual_amount
        except Exception:
            log_aggravated_event(crime_type, target_player_name, "Script Error (Parse Success)", 0)
            return 'general_error', target_player_name, None

    if "and failed!" in result_text:
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, now + datetime.timedelta(hours=1, minutes=55))
        log_aggravated_event(crime_type, target_player_name, "Failed", 0)
        return 'failed_attempt', target_player_name, None

    log_aggravated_event(crime_type, target_player_name, "Failed", 0)
    return 'general_error', target_player_name, None

def _search_yellow_pages_for_occupation(occupation_search_term, current_city):
    """
    Navigates to Yellow Pages, searches for a specific occupation,
    and finds an owner matching the current city.
    Returns owner name or None for payback on public business'.
    """
    print(f"Searching Yellow Pages for '{occupation_search_term}' in '{current_city}'.")
    initial_url = global_vars.driver.current_url

    if not _navigate_to_page_via_menu(
            "//*[@id='nav_left']/div[3]/a[2]",
            "//*[@id='city_holder']//a[contains(@class, 'business') and contains(@class, 'yellow_pages')]",
            "Yellow Pages"
    ):
        print("FAILED: Navigation to Yellow Pages failed for specific occupation search.")
        return None

    search_input_xpath = "//*[@id='content']/center/div/div[2]/form/p[2]/input"
    search_button_xpath = "/html/body/div[4]/div[4]/center/div/div[2]/form/p[3]/input"
    results_table_xpath = "//*[@id='content']/center/div/div[2]/table"

    if not _find_and_send_keys(By.XPATH, search_input_xpath, occupation_search_term):
        print(f"FAILED: Failed to enter occupation '{occupation_search_term}'.")
        global_vars.driver.get(initial_url)
        return None
    if not _find_and_click(By.XPATH, search_button_xpath, pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        print(f"FAILED: Failed to click search button for '{occupation_search_term}'.")
        global_vars.driver.get(initial_url)
        return None

    results_table = _find_element(By.XPATH, results_table_xpath)
    if results_table:
        player_rows = results_table.find_elements(By.TAG_NAME, "tr")
        for row in player_rows:
            try:
                if row.find_elements(By.XPATH, ".//a[contains(@href, 'userprofile.asp')]"):
                    player_name = row.find_element(By.XPATH, ".//td[1]/a").text.strip()
                    player_occupation = row.find_element(By.XPATH, ".//td[2]").text.strip()
                    player_city = row.find_element(By.XPATH, ".//td[4]").text.strip()

                    if player_occupation.lower() == occupation_search_term.lower() and player_city.lower() == current_city.lower():
                        print(f"Found owner for '{occupation_search_term}' in '{current_city}': {player_name}")
                        global_vars.driver.get(initial_url)
                        return player_name
            except NoSuchElementException:
                continue
            except Exception as e:
                print(f"Error parsing Yellow Pages row: {e}")
                continue
    print(f"No owner found for '{occupation_search_term}' in '{current_city}' via Yellow Pages.")
    global_vars.driver.get(initial_url)
    return None

def _get_suitable_bne_target(current_location, character_name, excluded_players, apartment_filters=None):
    """
    Returns a player whose stored home_city == current_location,
    apartment is in apartment_filters (if provided), and whose
    minor_crime_cooldown is free/expired.
    """
    game_now = get_current_game_time()

    # Normalize filters once (lowercase for case-insensitive compare)
    filters = [f.strip().lower() for f in (apartment_filters or []) if f and f.strip()]

    # Pull candidates from DDB (already contains HomeCity + Apartment info)
    candidates = list(get_crime_targets_from_ddb(current_location, global_vars.MINOR_CRIME_COOLDOWN_KEY))
    random.shuffle(candidates)

    for player_id, target_home_city in candidates:
        if not player_id:
            continue
        if player_id == character_name or (excluded_players and player_id in excluded_players):
            continue

        # Apartment filter (if any)
        if filters:
            if isinstance(target_home_city, dict):
                apt = (target_home_city.get("Apartment") or "").strip().lower()
            else:
                apt = ""
            if apt not in filters:
                continue

        cooldown_end_time = get_player_cooldown(player_id, global_vars.MINOR_CRIME_COOLDOWN_KEY)
        if cooldown_end_time is None or (game_now - cooldown_end_time).total_seconds() >= 0:
            return player_id

    return None

def _perform_bne_attempt(target_player_name, repay_enabled=False):
    """
    Performs a single Breaking & Entering attempt.
    Assumes we are already on the BnE page (via _open_aggravated_crime_page("BnE")).
    Returns status, target_name, amount_or_None
      status in {'success','failed_attempt','cooldown_target','no_apartment','general_error'}
    """

    # Clear any previous “current crime” repay markers (guarded in case globals don’t exist yet)
    try:
        global_vars.bne_player_for_repay = None
        global_vars.bne_amount_for_repay = None
        global_vars.bne_successful = False
    except Exception:
        pass

    # Fill the form and submit
    if not _find_and_send_keys(By.XPATH, "//input[@name='breaking']", target_player_name):
        return 'general_error', target_player_name, None
    # Dismiss/accept the suggestion popup so it doesn't cover the button
    try:
        name_input = _find_element(By.XPATH, "//input[@name='breaking']")
        if name_input:
            # Try to select the first suggestion and accept it
            name_input.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.05)
            name_input.send_keys(Keys.ENTER)
            time.sleep(0.05)
    except Exception:
        pass

    # click a neutral area to blur the input (collapses popup)
    _find_and_click(By.XPATH, "//div[@id='content']", pause=0.1)

    if not _find_and_click(By.XPATH, "//input[@name='B1']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
        return 'general_error', target_player_name, None

    result_text = _get_element_text(By.XPATH, "/html/body/div[4]/div[4]/div[1]") or ""
    now = get_current_game_time()
    clean = result_text.lower()

    # SUCCESS CASE
    if "you managed to break" in clean:
        try:
            # Parse stolen amount
            amt_match = re.search(r"found yourself \$?([\d,]+)", result_text, re.IGNORECASE)
            stolen = int(amt_match.group(1).replace(',', '')) if amt_match else 0

            # Parse apartment type if present
            apt_match = re.search(r"(Flat|Studio Unit|Penthouse|Palace)", result_text, re.IGNORECASE)
            apt = apt_match.group(1) if apt_match else "Unknown"

            # Parse target name up to the apostrophe
            name_match = re.search(r"break[- ]?into (.+?)(?:'|`)", result_text, re.IGNORECASE)
            name = name_match.group(1).strip() if name_match else target_player_name

            # Success cooldown: 1h40m–2h10m
            cd = now + datetime.timedelta(seconds=random.uniform(100 * 60, 130 * 60))
            set_player_data(name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd, apartment=apt)

            if repay_enabled:
                global_vars.bne_player_for_repay = name
                global_vars.bne_amount_for_repay = stolen
                global_vars.bne_successful = True

            log_aggravated_event("BnE", name, "Success", stolen)
            print(f"[BnE] SUCCESS: {name} | {apt} | ${stolen:,}")

            # If an item was also stolen, push the full success string to Discord with the repay flag state
            if "you also managed" in result_text.lower():
                repay_flag = "ON" if repay_enabled else "OFF"
                send_discord_notification(f"[BnE] ITEM STOLEN — Repay {repay_flag}\n{result_text.strip()}")
            return 'success', name, stolen
        except Exception as e:
            print(f"[BnE] ERROR parsing success: {e}")
            return 'general_error', target_player_name, None

    # FAILED ATTEMPT
    if "attempted to break" in clean:
        try:
            apt_match = re.search(r"(Flat|Studio Unit|Penthouse|Palace)", result_text, re.IGNORECASE)
            apt = apt_match.group(1) if apt_match else "Unknown"

            name_match = re.search(r"into (.+?)(?:'|`)", result_text, re.IGNORECASE)
            name = name_match.group(1).strip() if name_match else target_player_name

            cd = now + datetime.timedelta(seconds=random.uniform(100 * 60, 130 * 60))  # 1h40m–2h10m
            set_player_data(name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd, apartment=apt)
            log_aggravated_event("BnE", name, "Failed", 0)
            print(f"[BnE] FAILED: {name} | {apt}. Cooldown until {cd.strftime('%H:%M:%S')}.")
            return 'failed_attempt', name, None
        except Exception as e:
            print(f"[BnE] ERROR parsing fail: {e}")
            return 'general_error', target_player_name, None

    # RECENTLY SURVIVED
    if "try them again later" in result_text.lower():
        cd = now + datetime.timedelta(minutes=5)
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd)
        print(f"[BnE] AGG PRO: {target_player_name}. Retry after {cd.strftime('%H:%M:%S')}.")
        return 'cooldown_target', target_player_name, None

    # NO APARTMENT
    if "have an apartment" in result_text.lower():
        cd = now + datetime.timedelta(hours=24)
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd, apartment="No Apartment")
        print(f"[BnE] NO APARTMENT: {target_player_name}. Cooldown set 24h.")
        return 'no_apartment', target_player_name, None

    # WRONG CITY (victim's apartment not in your city)
    if "city as your victim" in result_text.lower():
        cd = now + datetime.timedelta(hours=24)
        set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, cd)
        print(f"[BnE] WRONG CITY / MOVED APARTMENT: {target_player_name}. 24h minor cooldown set.")
        return 'wrong_city', target_player_name, None

    # NON-EXISTENT TARGET
    if "the name you typed in" in result_text.lower():
        print(f"[BnE] Target '{target_player_name}' does not exist. Removing from cooldown DB.")
        remove_player_cooldown(target_player_name)
        return 'non_existent_target', target_player_name, None

    # FAILED TOO MANY RECENTLY
    if "as you have failed too many" in result_text.lower():
        now = get_current_game_time()
        print("You cannot commit an aggravated crime as you have failed too many recently. Please try again shortly!")
        _set_last_timestamp(global_vars.AGGRAVATED_CRIME_LAST_ACTION_FILE, now)
        global_vars._script_aggravated_crime_recheck_cooldown_end_time = now + datetime.timedelta(minutes=30)
        return 'aggs_blocked', None, None

    # FALLBACK if unexpected result
    short_cd = now + datetime.timedelta(seconds=random.uniform(30, 60))
    set_player_data(target_player_name, global_vars.MINOR_CRIME_COOLDOWN_KEY, short_cd)
    log_aggravated_event("BnE", target_player_name, "Unexpected Result", 0)
    print(f"[BnE] Unrecognized result for '{target_player_name}'. Short cooldown applied.")
    return 'general_error', target_player_name, None
