import time

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec

import global_vars
from aws_players import upsert_player_home_city, mark_top_job
from database_functions import acquire_distributed_timer, TIMER_NAME_FUNERAL_YELLOW, reschedule_distributed_timer, rename_player_in_players_table, remove_player_cooldown, complete_distributed_timer
from helper_functions import _find_element, _navigate_to_page_via_menu, _find_and_click, _get_element_text_quiet, _find_and_send_keys
from modules.agg_helpers import player_online_hours


def execute_funeral_parlour_scan():
    """
    Scans the Funeral Parlour’s Daily Obituaries for name changes or deaths.
    Updates player data in DynamoDB, posts Discord alerts for renames,
    deletes cooldowns for suicides/murders/admin whacks, and triggers a Yellow Pages scan.
    """

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

    # Snapshot the entries so we can navigate away and return safely
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
    """
    Scans Yellow Pages for all occupations, updates player Home Cities and top jobs in DynamoDB,
    and optionally notifies Discord on city changes.
    """

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