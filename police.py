import configparser
import datetime
import random
import time
from selenium.webdriver.common.by import By
import global_vars
import os, json, re
from selenium.webdriver.common.keys import Keys
from comms_journals import send_discord_notification
from database_functions import _set_last_timestamp
from helper_functions import _navigate_to_page_via_menu, _find_and_click, _find_elements, _find_element, \
    _find_and_send_keys, _get_element_text


def police_911():
    """
    Automates copying 911  list and posting it in the designated Interpol thread.
    """
    print("\n--- Starting Police 911 Automation ---")

    cfg = configparser.ConfigParser()
    cfg.read('settings.ini')

    thread_title = cfg.get('Police', '911Thread', fallback='').strip()
    if not thread_title:
        print("FAILED: No thread title defined in settings.ini under [Police] 911Thread.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

        # Ensure we're on the city page to access the Police menu
    if not _find_and_click(By.XPATH, "//span[@class='city']"):
        print("FAILED: Could not navigate to city page before Police menu.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Navigate to Police then Emergency Call Register
    if not _navigate_to_page_via_menu(
        "//a[normalize-space()='']//span[@class='police']",
        "//a[normalize-space()='Emergency call register']",
        "Emergency Call Register"
    ):
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Copy the 911 list
    print("Reading 911 table content...")

    rows = _find_elements(By.XPATH, "//table[@id='casestable']//tr")
    if not rows or len(rows) <= 1:
        print("FAILED: Could not find or parse 911 table rows.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Skip the header row
    table_data = []
    parsed_rows = []
    for row in rows[1:]:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) >= 4:
            time = cols[0].text.strip()
            crime = cols[1].text.strip()
            victim = cols[2].text.strip()
            suspect = cols[3].text.strip()
            table_data.append(f"{time} {crime} {victim} {suspect}")
            parsed_rows.append({"time": time, "crime": crime, "victim": victim, "suspect": suspect})

            # If whack appears, send to Discord
            if "whack" in crime.lower():
                send_discord_notification(f"911 Reported: {time} {crime} {victim} {suspect}")

    if not table_data:
        print("FAILED: 911 table had no valid entries.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    compiled_911_list = "\n".join(table_data)
    print(f"Successfully compiled {len(table_data)} 911 entries.")

    # Navigate to Interpol tab
    print("Navigating to Interpol tab...")
    if not _find_and_click(By.XPATH, "(//a[normalize-space()='Interpol'])[1]"):
        print("FAILED: Could not navigate to Interpol tab.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Open correct thread
    print(f"Searching for Interpol thread titled: '{thread_title}'...")
    thread_rows = _find_elements(By.XPATH, "//table[3]//tr[@class='thread']")
    if not thread_rows:
        print("FAILED: No thread rows found in table[3].")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    for row in thread_rows:
        try:
            thread_link = row.find_element(By.XPATH, ".//a")
            title = thread_link.text.strip()
            if title.lower() == thread_title.lower():
                print(f"Opening thread: {title}")
                thread_link.click()
                break
        except Exception as e:
            continue
    else:
        print(f"FAILED: Could not find thread titled '{thread_title}' in Interpol tab.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Click Post Reply
    print("Clicking Post Reply...")
    if not _find_and_click(By.XPATH, "//body[1]/div[4]/div[4]/form[1]/div[1]/div[2]/table[1]/tbody[1]/tr[1]/td[1]/a[1]"):
        print("FAILED: Could not click Post Reply button.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Paste copied 911 list into reply box
    print("Pasting 911 list into reply box...")
    if not _find_and_send_keys(By.XPATH, "//textarea[@id='body']", compiled_911_list):
        print("FAILED: Could not paste into text box.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Click "local" filter
    print("Clicking 'local' filter...")
    if not _find_and_click(By.XPATH, "//span[@class='list-show selected']"):
        print("FAILED: Could not click 'local' filter.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Copy the online list
    print("Clicking 'Copy online list'...")
    if not _find_and_click(By.XPATH, "//a[normalize-space()='Copy online list']"):
        print("FAILED: Could not click 'Copy online list'.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Append the online list to text area
    print("Appending online list to text box...")
    textarea_element = _find_element(By.XPATH, "//textarea[@id='body']")
    if textarea_element:
        existing_text = textarea_element.get_attribute("value")
        textarea_element.clear()
        textarea_element.send_keys(existing_text + "\n\n")  # Make sure there's spacing
        # Online list should now be in clipboard — paste it
        textarea_element.send_keys(Keys.CONTROL, 'v')
        # Get the pasted online list and parse it
        updated_text = textarea_element.get_attribute("value") or ""
        marker = (existing_text or "") + "\n\n"
        online_block = updated_text[len(marker):] if updated_text.startswith(marker) else updated_text
        online_users = _parse_online_usernames(online_block)
        print(f"Parsed {len(online_users)} online users.")

        # Attach online users to each parsed row
        for row_data in parsed_rows:
            row_data["online_users"] = online_users

        # Persist crimes + who-was-online in one JSON
        if parsed_rows:
            _append_911_cache(parsed_rows)
            print(f"Cached {len(parsed_rows)} 911 rows with online users to local JSON.")

    else:
        print("FAILED: Could not find textarea to append online list.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    # Post the reply
    print("Posting the reply...")
    if not _find_and_click(By.XPATH, "//input[@name='Submit']"):
        print("FAILED: Could not click Post Reply submit button.")
        next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
        _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
        global_vars._script_post_911_cooldown_end_time = next_check_time

        return False

    print("Successfully posted 911 list to Interpol thread.")
    next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(20, 25))
    _set_last_timestamp(global_vars.POLICE_911_NEXT_POST_FILE, next_check_time)
    global_vars._script_post_911_cooldown_end_time = next_check_time

    return True

def prepare_police_cases(character_name):
    """
    Main police case runner:
    - If an active case exists: collect evidence / solve it.
    - Else: try Intray; if none, pick a decent Reported Case and proceed.
    """
    import re, datetime, random, time
    from selenium.webdriver.common.by import By

    print("\n--- Preparing Police Case ---")

    # 1) Go to City → Police Current Case (keep your XPaths)
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[normalize-space()='']//span[@class='police']",
        "Police Current Case"
    ):
        return False

    # 2) If there's NO red fail box, we *do* have an active case
    fail_box = _find_element(By.XPATH, "//div[@id='fail']")
    if not fail_box:
        print("Active case detected. Proceeding to collect evidence / solve...")
        return solve_case(character_name)

    # 3) Open Unassigned Cases
    print("No active case. Checking Unassigned Cases…")
    if not _find_and_click(By.XPATH, "//a[contains(@href, 'display=unassigned') and contains(., 'UNASSIGNED CASES')]"):
        print("FAILED: Could not open Unassigned Cases.")
        return False

    # Respect the throttle + handle "no new cases"
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    fail_box = _find_element(By.XPATH, "//div[@id='fail']", timeout=2, suppress_logging=True)
    if fail_box:
        msg = (fail_box.text or "").strip().lower()
        if "you must wait at least 30 seconds" in msg:
            backoff = random.uniform(33, 42)
            print(f"Viewed Unassigned cases too quickly. Backing off for ~{backoff:.1f}s")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=backoff)
            return True
        if "there are currently no new cases" in msg:
            mins = random.uniform(10, 15)
            print(f"No new cases available — cool down for {mins:.1f} minutes.")
            global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=mins)
            return True

    # Helpers for color parsing
    def _cell_bg(td):
        style = (td.get_attribute("style") or "").lower()
        m = re.search(r"background(?:-color)?:\s*([^;]+)", style)
        return (m.group(1).strip() if m else "").lower().replace(" ", "")

    def _is_orange(c: str) -> bool:
        # Cover "orange" keyword, rgb, and nearby hexes (#e68f12, #e69a0c, etc.)
        c = (c or "")
        return (
            "orange" in c or
            "rgb(230,143,18)" in c or
            re.search(r"#e6(8|9)[0-9a-f]{3}", c) is not None
        )

    # 4) Try Intray first — pick the first row with NO orange boxes
    intray_rows = _find_elements(
        By.XPATH,
        "//table[contains(@style,'border-collapse')]//tr[td/input[@type='radio' and @name='case']]"
    )

    if intray_rows:
        picked = None
        for row in intray_rows:
            try:
                # Cols: 1 Case | 2 Crime | 3 Victim | 4 Witness | 5 DNA | 6 Prints | 7 Fire | 8 Autopsy | 9 Select
                w  = _cell_bg(row.find_element(By.XPATH, "./td[4]"))
                d  = _cell_bg(row.find_element(By.XPATH, "./td[5]"))
                fp = _cell_bg(row.find_element(By.XPATH, "./td[6]"))
                f  = _cell_bg(row.find_element(By.XPATH, "./td[7]"))
                a  = _cell_bg(row.find_element(By.XPATH, "./td[8]"))

                # (Optional) log to verify colors in practice
                case_no = (row.find_element(By.XPATH, "./td[1]").text or "").strip()
                print(f"INTRAY {case_no} -> W:{w} DNA:{d} FP:{fp} Fire:{f} Aut:{a}")

                # Skip any row with ANY orange indicator
                if any(_is_orange(x) for x in (w, d, fp, f, a)):
                    continue

                picked = row
                break
            except Exception:
                continue

        if picked:
            print("Selecting an intray case with no orange boxes and opening…")
            picked.find_element(By.XPATH, ".//input[@type='radio' and @name='case']").click()
            if not _find_and_click(By.XPATH, "//input[@name='result']"):
                print("FAILED: Could not click Open Case.")
                return False
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)

            # Witness-only safeguard
            if _is_witness_only_case():
                print("WITNESS-ONLY CASE: burying.")
                _bury_case()
                return True

            return solve_case(character_name)
        else:
            print("All intray cases have orange boxes — skipping intray and checking Reported Cases…")

    # 5) Reported Cases: pick best row with NO orange; prefer green/yellow DNA/Prints
    if not _navigate_to_page_via_menu("//span[@class='police']",
                                      "//a[normalize-space()='Reported cases']",
                                      "Reported Cases"):
        return False

    print("Scanning Reported Cases for eligible candidates (skip ORANGE)…")

    rows = _find_elements(
        By.XPATH,
        "//table[contains(@style,'border-collapse')]/tbody/tr[td/input[@type='radio' and @name='case']]"
    )

    def _score_row(row):
        # returns (score, has_orange)
        w  = _cell_bg(row.find_element(By.XPATH, "./td[4]"))
        d  = _cell_bg(row.find_element(By.XPATH, "./td[5]"))
        fp = _cell_bg(row.find_element(By.XPATH, "./td[6]"))
        f  = _cell_bg(row.find_element(By.XPATH, "./td[7]"))
        a  = _cell_bg(row.find_element(By.XPATH, "./td[8]"))

        has_orange = any(_is_orange(x) for x in (w, d, fp, f, a))

        # Prefer green, then yellow, on DNA/Prints
        score = 0
        for x in (d, fp):
            if "#4c8a23" in x or "rgb(76,138,35)" in x:   # green
                score += 2
            elif "#e8d71d" in x or "rgb(232,215,29)" in x:  # yellow
                score += 1
        return score, has_orange

    best_row, best_score = None, -1
    for row in rows:
        try:
            score, has_orange = _score_row(row)
            if has_orange:
                continue
            if score > best_score:
                best_row, best_score = row, score
        except Exception:
            continue

    if best_row:
        print(f"Eligible reported case chosen (score {best_score}). Opening…")
        try:
            best_row.find_element(By.XPATH, ".//input[@type='radio' and @name='case']").click()
            btn = _find_element(By.XPATH, "//input[@type='submit' and contains(@value,'Select Case')]")
            if btn:
                btn.click()
        except Exception:
            print("FAILED: Could not open the selected case row.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        if _is_witness_only_case():
            print("WITNESS-ONLY CASE: burying.")
            _bury_case()
            return True

        return solve_case(character_name)

    print("No eligible reported cases found.")
    return False


def _is_witness_only_case():
    """
    Returns True if the open case appears to be a witness case (no victim report yet).
    Old code keyed off '<i>Not reported yet' in the case body.
    We keep that signal and also prefer when there's a Witness Statement without a Victim Statement.
    """
    h = _case_body_html()
    if not h:
        return False
    # Original witness marker from legacy script:
    if "<i>Not reported yet" in h:
        return True
    # Extra guard: explicit witness statement but no victim statement
    if ("Witness Statement:" in h) and ("Victim Statement:" not in h):
        return True
    return False


def collect_evidence():
    """
    Ensure core evidence exists on the open case:
    - If torch: ensure Fire Investigation exists
    - Ensure Fingerprints & DNA exist
    - Ensure Travel is present
    If DNA was just requested, set a short backoff and stop.
    Then, if DNA/FP cells contain numbers, run them through Records database and come back to Intray.
    """
    print("\n--- Collecting Case Evidence ---")
    h = _case_body_html()
    if not h:
        print("FAILED: Could not read case contents for evidence check.")
        return False

    # Torch → Fire Investigation (only when the section exists and says 'None')
    if _is_torch() and "Fire Investigation:" in h and "None" in h:
        print("POLICE - FIRE INVESTIGATION REQUIRED")
        _find_and_click(By.XPATH, "//*[@id='pd']//div[@class='links']/input[5]")  # Fire investigation
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Fingerprints — only dust if the value cell is blank
    fp_value = _get_case_cell("Fingerprint Evidence:")
    if not fp_value:
        print("POLICE - FINGERPRINT EVIDENCE REQUIRED (cell blank)")
        idx = 6 if _is_torch() else 5
        if _find_and_click(By.XPATH, f"//*[@id='pd']//div[@class='links']/input[{idx}]"):
            # Give the page a moment to populate the FP cell, then re-read it
            time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
            fp_after = _get_case_cell("Fingerprint Evidence:") or ""
            if fp_after:
                print(f"Fingerprint log updated to: '{fp_after}'")
                fp_value = fp_after  # <-- IMPORTANT: use latest value for DB logic below
        else:
            print("FAILED: Could not click 'Dust for fingerprints'.")
    else:
        print(f"POLICE - Fingerprint evidence present ({fp_value}). Skipping dusting.")

    # DNA — only swab if the value cell is completely blank
    dna_content = _get_case_cell("DNA Log:")
    if not dna_content:
        print("POLICE - DNA cell blank → requesting swab now")
        idx = 7 if _is_torch() else 6
        if _find_and_click(By.XPATH, f"//*[@id='pd']//div[@class='links']/input[{idx}]"):
            # Give the page a moment to update, then re-read DNA Log
            time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
            dna_after = _get_case_cell("DNA Log:") or ""
            dna_after_l = dna_after.lower()

            if "awaiting results" in dna_after_l:
                print("DNA sample taken; awaiting results — RETURN case for hospital processing.")
                _return_case()
                return False

            elif dna_after.strip().lower() == "none" or not dna_after.strip():
                print(f"DNA swab returned immediately as None — continuing (no wait).")
                dna_content = dna_after  # update so later logic sees the latest value
            else:
                # Some other immediate text (rare), just log and continue
                print(f"DNA log updated to: '{dna_after}'. Continuing without wait.")
                dna_content = dna_after  # update so later logic sees the latest value

        else:
            print("FAILED: Could not click DNA swab button.")
    else:
        print(f"POLICE - DNA already requested (cell content: {dna_content}). Skipping swab.")

    # Travel — only add if the value cell is blank
    # NOTE: "No valid travel evidence found." counts as PRESENT (do not click again)
    travel_value = _get_case_cell("Travel Log:")
    if not travel_value:
        print("POLICE - TRAVEL EVIDENCE MISSING → adding travel evidence")
        _enter_travel_evidence()
    else:
        print(f"POLICE - Travel evidence present ({travel_value}). Skipping.")

    # --- Add results via Records database ONLY when numbers are present ---
    # "None" should NOT trigger DB search; blank cells were already handled above.
    dna_has_numbers = bool(re.fullmatch(r"\d[\d ]*", dna_content)) if dna_content else False
    fp_has_numbers  = bool(re.fullmatch(r"\d[\d ]*", fp_value))    if fp_value else False

    any_added = False
    went_to_records_db = False  # <-- track if we visited the DB

    if dna_has_numbers:
        print(f"DNA cell contains numbers ({dna_content}) → checking Records database…")
        if _records_database_add_if_results("DNA"):
            any_added = True
        went_to_records_db = True
    else:
        if dna_content:
            print(f"DNA cell not numeric ('{dna_content}') → skipping Records database for DNA.")

    if fp_has_numbers:
        print(f"FP cell contains numbers ({fp_value}) → checking Records database…")
        if _records_database_add_if_results("Fingerprints"):
            any_added = True
        went_to_records_db = True
    else:
        if fp_value:
            print(f"FP cell not numeric ('{fp_value}') → skipping Records database for FP.")

    # Only navigate back to In-tray if we actually went to Records Database
    if went_to_records_db:
        if not _find_and_click(By.XPATH, "//a[normalize-space()='In-tray']"):
            print("FAILED: Could not navigate back to 'In-tray'.")
            return False
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    print("Evidence present (none missing).")
    return True

def _choose_name_ending(cues):
    """Pick the longest reliable ending among victim/witness/fire/forensics."""
    candidates = [cues.get("victim_statement"), cues.get("witness_statement"), cues.get("fire"), cues.get("forensics")]
    candidates = [c for c in candidates if c]
    return max(candidates, key=len) if candidates else None


def _search_phonebook_by_ending(ending):
    """
    Search the Phone Book page and return (alive_matches, dead_matches) for names
    that END with `ending`. The page shows multiple sections:
      - "You found the following people accounts in the phonebook:"  (alive)
      - "You found the following forum accounts in the phonebook:"    (ignore)
      - "You found the following people in the obituaries:"           (dead-on-same-page)
    """
    alive, dead = [], []
    try:
        # Go to Phone Book and run the search
        if not _find_and_click(By.XPATH, "//span[@class='city']"):
            return alive, dead
        if not _find_and_click(By.XPATH, "//*[@class='business phone_book']"):
            return alive, dead

        _find_and_send_keys(By.XPATH, "//*[@id='AutoNumber4']/tbody/tr[5]/td[@class='s1'][2]/p/input", ending)
        if not _find_and_click(By.XPATH, "//*[@id='AutoNumber4']/tbody/tr[7]/td[@class='s1'][2]/p/input"):
            return alive, dead

        # The phonebook renders multiple repeated blocks:
        # <div id='holder_top'><h1>...</h1></div>
        # <div id='holder_content'> ...names... </div>
        headings = _find_elements(By.XPATH, "//div[@id='holder_top']/h1")
        for h1 in headings or []:
            title = (h1.text or "").lower()

            # get the *next* holder_content for this heading
            content = h1.find_element(By.XPATH, "../following-sibling::div[@id='holder_content'][1]")
            html = content.get_attribute("innerHTML") or ""

            # extract usernames and filter by ending
            names = re.findall(r'username=([^"&<]+)"', html)
            names = [n for n in names if n.endswith(ending)]

            if "obituar" in title:
                dead.extend(names)
            elif "people accounts in the phonebook" in title:
                alive.extend(names)
            else:
                # forum accounts or anything else → ignore
                pass

        # back to Police
        _find_and_click(By.XPATH, "//span[@class='police']")
        return alive, dead

    except Exception as e:
        print(f"Phonebook search failed: {e}")
        return alive, dead



def _enter_suspect(name):
    """Enter suspect into the input; bury if it’s actually you."""
    try:
        you = _get_element_text(By.XPATH, "//div[@id='nav_right']/div[normalize-space(text())='Name']/following-sibling::div[1]/a")
        if name and you and name.strip() == you.strip():
            print("YOU ARE THE SUSPECT - BURY")
            _bury_case()
            return False
        elem = _find_element(By.NAME, "suspect")
        if elem:
            elem.clear()
            elem.send_keys(name)
            time.sleep(global_vars.ACTION_PAUSE_SECONDS)
            return True
    except Exception as e:
        print(f"Failed to enter suspect '{name}': {e}")
    return False


def solve_case(character_name):
    """
    Solve the open case using:
    - Direct hits (DNA/fingerprint match/forensics)
    - Name-ending phonebook search (fallback)
    Conservative: if ambiguous → return/bury; do not guess.
    """
    print("\n--- Solving Case ---")

    if _is_witness_only_case():
        print("POLICE - WITNESS-ONLY CASE: burying (pre-solve).")
        _bury_case()
        return True

    # 1) Ensure evidence actions are done first (dust/swab/travel + Records DB if needed)
    if not collect_evidence():
        print("Evidence pending (e.g., DNA). Will try again later.")
        return False

    # 2) If DNA shows 'awaiting results', return for hospital processing
    dna_status = _get_case_cell("DNA Log:")
    if dna_status and "awaiting results" in dna_status.lower():
        print("DNA sample taken; awaiting results — RETURN case for hospital processing.")
        _return_case()
        return True

    # If fire investigation hasn't produced a suspect, return the case
    if _is_torch():
        fire_cell = _get_case_cell("Fire Investigation:")  # may be "", "None", "identity: XYZ", or other text
        fire_text = (fire_cell or "").strip().lower()
        # treat as pending if: blank, "none", or doesn't include the word "identity"
        if not fire_text or fire_text == "none" or ("identity" not in fire_text):
            print("Torch case: Fire Investigation pending — RETURN case until firefighters report back.")
            _return_case()
            return True

    # 3) Parse cues AFTER evidence work
    cues = _parse_case_for_signals()
    if not cues:
        print("Could not parse the case – returning for safety.")
        _return_case()
        return False

    suspect = cues.get("suspect")

    # 4) If still no suspect, and there are no leads at all, bury instead of return
    if not suspect:
        dna_val = _get_case_cell("DNA Log:")
        fp_val  = _get_case_cell("Fingerprint Evidence:")

        no_dna = (not dna_val) or (dna_val.strip().lower() == "none")
        no_fp  = (not fp_val)  or (fp_val.strip().lower() == "none")

        no_name_cues = not any([
            cues.get("victim_statement"),
            cues.get("witness_statement"),
            cues.get("forensics"),
            cues.get("fire"),
        ])

        if no_dna and no_fp and no_name_cues:
            # Try the 911 cache before burying
            infer = _try_infer_suspect_from_911(cues)
            if infer:
                print(f"911 cache identified suspect: {infer}")
                if not _enter_suspect(infer):
                    print("Failed to enter 911-resolved suspect; returning the case.")
                    _return_case()
                    return True

                is_torch = (cues.get("agg_type") == "Torch")
                if not _update_case(is_torch):
                    print("Failed to UPDATE case after 911 suspect; returning.")
                    _return_case()
                    return True

                fail_box = _find_element(By.XPATH, "//*[@id='fail']")
                if fail_box and "is now dead" in fail_box.get_attribute("innerText").lower():
                    print("Suspect is dead per banner – burying case.")
                    _bury_case()
                    return True

                if not _close_case():
                    print("Close failed after 911 suspect; bury as fallback.")
                    _bury_case()
                    return True

                print("Case closed successfully (via 911 cache).")
                send_discord_notification(f"Closed via 911: {cues.get('agg_time') or _get_case_cell('Time of Crime:')} | "f"{cues.get('victim') or _get_case_cell('Victim:')} → **{infer}**")
                return True

            # Cache gave nothing → proceed to bury
            print("No evidence or name cues – BURY case.")
            _bury_case()
            return True

    # 5) Fallback: phonebook via name ending, then close/return/bury as before
    if not suspect:
        ending = _choose_name_ending(cues)
        if ending:
            ending = ending.strip()[-3:] if hasattr(ending, "strip") else str(ending)[-3:]

        # Minimum 2 characters required for phone book search
        if ending and len(ending.strip()) == 1:
            print(f"Only 1-letter clue ('{ending}') — checking 911 cache before burying…")
            infer = _try_infer_suspect_from_911(cues)
            if infer:
                print(f"911 cache identified suspect: {infer}")
                if not _enter_suspect(infer):
                    print("Failed to enter 911-resolved suspect; returning the case.")
                    _return_case()
                    return True

                is_torch = (cues.get("agg_type") == "Torch")
                if not _update_case(is_torch):
                    print("Failed to UPDATE case after 911 suspect; returning.")
                    _return_case()
                    return True

                fail_box = _find_element(By.XPATH, "//*[@id='fail']")
                if fail_box and "is now dead" in fail_box.get_attribute("innerText").lower():
                    print("Suspect is dead per banner – burying case.")
                    _bury_case()
                    return True

                if not _close_case():
                    print("Close failed after 911 suspect; bury as fallback.")
                    _bury_case()
                    return True

                print("Case closed successfully (via 911 cache from 1-letter hint).")
                send_discord_notification(f"Closed via 911: {cues.get('agg_time') or _get_case_cell('Time of Crime:')} | "f"{cues.get('victim') or _get_case_cell('Victim:')} → **{infer}**")
                return True

            print("911 cache gave nothing. 1-letter clue is unusable → BURY.")
            _bury_case()
            return True

        if not ending or len(ending.strip()) < 2:
            # zero-length fallback (no letters at all)
            print("No usable clue (0 letters) → BURY case.")
            _bury_case()
            return True

        if ending:
            alive_matches, dead_matches = _search_phonebook_by_ending(ending)
            print(f"PHONEBOOK ALIVE MATCHES ({ending}): {alive_matches}")
            print(f"PHONEBOOK OBITUARY MATCHES ({ending}): {dead_matches}")

            # Prefer alive matches first
            if len(alive_matches) == 1:
                suspect = alive_matches[0]
            elif len(alive_matches) > 1 and cues.get("fingerprint"):
                fp = cues["fingerprint"]
                narrowed = [m for m in alive_matches if fp in m]
                if len(narrowed) == 1:
                    suspect = narrowed[0]
            elif len(alive_matches) > 1:
                print("Multiple alive phonebook matches – BURY case.")
                _bury_case()
                return True
            else:
                # No alive → check dead section
                if len(dead_matches) > 1:
                    print("Multiple obituary matches (phonebook bottom) – BURY case.")
                    _bury_case()
                    return True
                elif len(dead_matches) == 1:
                    suspect = dead_matches[0]

    if not suspect:
        # Try 911 cache here too before giving up
        infer = _try_infer_suspect_from_911(cues)
        if infer:
            print(f"911 cache identified suspect: {infer}")
            if _enter_suspect(infer):
                is_torch = (cues.get("agg_type") == "Torch")
                if _update_case(is_torch) and _close_case():
                    print("Case closed successfully (via 911 cache).")
                    send_discord_notification(f"Closed via 911: {cues.get('agg_time') or _get_case_cell('Time of Crime:')} | "f"{cues.get('victim') or _get_case_cell('Victim:')} → **{infer}**")
                    return True
            # If entering/updating/closing fails, just return to be safe
            print("Could not complete close after 911 suspect – RETURN case.")
            _return_case()
            return True

        if cues.get("forensics"):
            print("No decisive suspect and forensics already done – BURY.")
            _bury_case()
            return True
        print("No decisive suspect – RETURN case.")
        _return_case()
        return True

    print(f"POLICE - SOLVING CASE with suspect: {suspect}")

    # If suspect is the same as our character name, bury immediately
    if character_name and suspect and suspect.strip() == character_name.strip():
        print("Suspect matches our own name – BURY case.")
        _bury_case()
        return True

    if not _enter_suspect(suspect):
        print("Failed to enter suspect; returning the case.")
        _return_case()
        return False

    is_torch = (cues.get("agg_type") == "Torch")
    if not _update_case(is_torch):
        print("Failed to UPDATE case; returning.")
        _return_case()
        return False

    fail_box = _find_element(By.XPATH, "//*[@id='fail']")
    if fail_box and "is now dead" in fail_box.get_attribute("innerText").lower():
        print("Suspect is dead per banner – burying case.")
        _bury_case()
        return True

    if not _close_case():
        print("Close failed; bury as fallback.")
        _bury_case()
        return True

    print("Case closed successfully.")
    return True


def _parse_case_for_signals():
    """
    Parse case body for: agg type, victim, time, suspect via DNA/fingerprint/forensics/fire,
    and witness/victim name endings.
    """
    raw = _case_body_html()
    if not raw:
        return {}

    data = {
        "agg_type": None,
        "victim": None,
        "agg_time": None,
        "suspect": None,
        "fingerprint": None,
        "dna": None,
        "fire": None,
        "forensics": None,
        "victim_statement": None,
        "witness_statement": None,
    }

    # Agg type
    if "BIZ TORCH" in raw or "Torch" in raw:
        data["agg_type"] = "Torch"
    elif "HACK" in raw or "Hacking" in raw:
        data["agg_type"] = "Hack"
    elif "Armed Robbery" in raw:
        data["agg_type"] = "AR"
    elif "MUGGING" in raw or "Mugging" in raw:
        data["agg_type"] = "Mug"
    elif "Breaking" in raw:
        data["agg_type"] = "BnE"

    # Victim + time (best-effort extraction)
    m = re.search(r'Victim:\s*</td>\s*<td>.*?username=([^"&<]+)', raw)
    if m:
        data["victim"] = m.group(1)
    tm = re.search(r"Time of Crime:\s*</td>\s*<td>([^<]+)</td>", raw)
    if tm:
        data["agg_time"] = tm.group(1).strip()

    # DNA → hard suspect
    if "DNA Log:" in raw and "was at the crime scene" in raw:
        md = re.search(r'The DNA revealed\s+([^<]+)\s+was at the crime scene', raw)
        if md:
            data["dna"] = md.group(1).strip()
            data["suspect"] = data["dna"]

    # Fingerprints (owner could be …) → treat as usable suspect
    if "Fingerprint Evidence:" in raw:
        mf = re.search(r'owner could be,\s*([^.<]+)\.', raw, re.IGNORECASE)
        if mf:
            name = mf.group(1).strip()
            # clean any trailing punctuation/quotes
            name = re.sub(r'^[\'"]|[\'"]$', '', name).strip()
            data["fingerprint"] = name
            # Promote to suspect even without "match=" phrasing
            data["suspect"] = name

    # Forensics
    if "Forensic Log" in raw:
        mf = re.search(r'name is\s*([^!]+)!', raw)
        if mf:
            data["forensics"] = mf.group(1).strip()
            data["suspect"] = data["forensics"]
        else:
            mf2 = re.search(r'name ended with\s*([^!]+)!', raw)
            if mf2:
                data["forensics"] = mf2.group(1).strip()

    # Fire (torch identity)
    if _is_torch() and "Fire Investigation:" in raw and "identity:" in raw:
        mf = re.search(r'identity:\s*([^<]+)</td>', raw)
        if mf:
            data["fire"] = re.sub(r'[^a-zA-Z0-9_-]', '', mf.group(1))

    # Witness / Victim statements (name endings)
    mv = re.search(r'Victim Statement:', raw)
    if mv:
        mve = re.search(r'ended with[: ]\s*([^.<<]+)[\.<]', raw)
        if mve:
            data["victim_statement"] = mve.group(1).strip()

    mw = re.search(r'Witness Statement:', raw)
    if mw:
        mwe = re.search(r'name ended with\s*([^.<<]+)[\.<]', raw)
        if mwe:
            data["witness_statement"] = mwe.group(1).strip()

    return data



# -------------------------
# Evidence & solving helpers
# -------------------------

def _close_case():
    print("POLICE - CLOSE CASE")
    return _find_and_click(By.XPATH, "//*[@id='pd']//div[@class='links']/input[1]")  # Close


def _bury_case():
    print("POLICE - BURY CASE")
    return _find_and_click(By.XPATH, "//*[@id='pd']//div[@class='links']/input[2]")  # Bury


def _return_case():
    print("POLICE - RETURN CASE")
    result = _find_and_click(By.XPATH, "//*[@id='pd']//div[@class='links']/input[3]")  # Return
    if result:
        wait_s = random.uniform(30, 39)
        print(f"Waiting {wait_s:.1f} seconds before doing police casework again.")
        global_vars._script_case_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_s)
    return result



def _update_case(is_torch: bool):
    print("POLICE - UPDATE CASE")
    # Torch uses a different button index in this menu vs other aggs
    idx = 8 if is_torch else 7
    return _find_and_click(By.XPATH, f"//*[@id='pd']//div[@class='links']/input[{idx}]")


def _enter_travel_evidence():
    print("POLICE - ADD TRAVEL EVIDENCE")
    if not _find_and_click(By.XPATH, "//*[@id='pd']//div[@class='links']/input[4]"):
        print("FAILED: Travel Evidence open")
        return False
    if not _find_and_click(By.XPATH, "//*[@id='noevidence']"):
        print("FAILED: Travel - 'no evidence'")
        return False
    if not _find_and_click(By.XPATH, "//*[@id='pd']/div[@class='body']/p[3]/input[@class='submit']"):
        print("FAILED: Travel submit")
        return False
    return True


def _case_body_html():
    elem = _find_element(By.XPATH, "//*[@id='content']/div[@id='pd']/div[@id='shop_holder']/div[@id='holder_content']/div[@class='body']")
    return elem.get_attribute("innerHTML") if elem else None


def _is_torch():
    h = _case_body_html()
    return bool(h and ("BIZ TORCH" in h or "Torch" in h))


def _has_section(label):
    h = _case_body_html()
    return bool(h and (label in h))

def _get_case_cell(label_text: str) -> str:
    """
    Returns the stripped text inside the <td> cell that follows a label.
    Example: label_text="DNA Log:" -> inner text of the value cell.
    Empty string means the cell is present but blank.
    Handles <b>Label</b></td><td>Value</td> structures.
    """
    h = _case_body_html()
    if not h:
        return ""
    # Pattern 1: label inside <b>…</b>
    pat1 = rf"<b>\s*{re.escape(label_text)}\s*</b>\s*</td>\s*<td[^>]*>(.*?)</td>"
    m = re.search(pat1, h, re.IGNORECASE | re.DOTALL)
    if not m:
        # Pattern 2: looser fallback (allow anything until the label cell closes)
        pat2 = rf"{re.escape(label_text)}.*?</td>\s*<td[^>]*>(.*?)</td>"
        m = re.search(pat2, h, re.IGNORECASE | re.DOTALL)
        if not m:
            return ""
    # Strip tags & whitespace
    val = re.sub(r"<[^>]+>", "", m.group(1))
    return val.strip()


def _records_database_add_if_results(kind: str) -> bool:
    """
    From an open case, jump to 'Records database' and add results if available.

    Flows now match UI exactly:
      - DNA: click "Search DNA Records" → click "Add to Case Evidence"
      - Fingerprints: select 'fingerprint' → click "Add to Case Evidence"

    Returns True if evidence was added, False otherwise.
    """
    kind_lower = (kind or "").lower()
    print(f"RECORDS DB: Processing {kind} results…")

    # Open the Records database tab
    if not _find_and_click(By.XPATH, "//a[normalize-space()='Records database']"):
        print("FAILED: Could not open 'Records database'.")
        return False
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    if "dna" in kind_lower:
        # Search DNA records
        if not _find_and_click(By.XPATH, "//input[@type='submit' and @value='Search DNA Records']"):
            # Fallback (older markup sometimes uses name='b1')
            if not _find_and_click(By.XPATH, "//input[@name='b1']"):
                print("FAILED: Could not click 'Search DNA Records'.")
                return False
        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        # Add to case evidence
        if not _find_and_click(By.XPATH, "//input[@type='submit' and @value='Add to Case Evidence']"):
            # Fallback (older markup uses name='B1')
            if not _find_and_click(By.XPATH, "//input[@name='B1']"):
                fail_box = _find_element(By.XPATH, "//div[@id='fail']", timeout=2, suppress_logging=True)
                msg = (fail_box.text.strip() if fail_box and fail_box.text else "no fail message")
                print(f"RECORDS DB: DNA had no addable results ({msg}).")
                return False

        print("RECORDS DB: DNA added to case.")
        return True

    elif "finger" in kind_lower:
        # Select the fingerprint option (radio) then add
        if not _find_and_click(By.XPATH, "//input[@name='fingerprint']", pause=1):
            print("FAILED: Could not select 'fingerprint' option.")
            return False

        # Add to case evidence
        if not _find_and_click(By.XPATH, "//input[@type='submit' and @value='Add to Case Evidence']"):
            # Fallback for older markup
            if not _find_and_click(By.XPATH, "//input[@name='B1']"):
                fail_box = _find_element(By.XPATH, "//div[@id='fail']", timeout=2, suppress_logging=True)
                msg = (fail_box.text.strip() if fail_box and fail_box.text else "no fail message")
                print(f"RECORDS DB: Fingerprints had no addable results ({msg}).")
                return False

        print("RECORDS DB: Fingerprints added to case.")
        return True

    else:
        print(f"RECORDS DB: Unknown kind '{kind}'. Expected 'DNA' or 'Fingerprints'.")
        return False


def _append_911_cache(new_rows: list):
    """Merge new 911 rows into a local JSON cache (dedupe by time+crime+victim+suspect)."""
    path = global_vars.POLICE_911_CACHE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Lazy-init file if missing
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f)

    try:
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = []

    seen = {(r.get("time"), r.get("crime"), r.get("victim"), r.get("suspect")) for r in cache}

    for r in new_rows or []:
        key = (r.get("time"), r.get("crime"), r.get("victim"), r.get("suspect"))
        if key not in seen:
            entry = {
                "time": r.get("time") or "",
                "crime": r.get("crime") or "",
                "victim": r.get("victim") or "",
                "suspect": r.get("suspect") or "",
            }
            # keep the online snapshot if present
            if "online_users" in r and isinstance(r["online_users"], list):
                entry["online_users"] = ", ".join(r["online_users"])
            cache.append(entry)
            seen.add(key)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _parse_online_usernames(block: str) -> list[str]:
    """Convert raw pasted online list text into a clean username list."""
    if not block:
        return []
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    ignore_prefixes = ("online list", "players online", "local", "copy online list")
    users = []
    for l in lines:
        low = l.lower()
        if any(low.startswith(p) for p in ignore_prefixes):
            continue
        for token in [t.strip() for t in re.split(r'[,]+', l) if t.strip()]:
            token = re.sub(r'^[\-\•\*\u200b\s]+|[\s\)\]\.]+$', '', token)
            if token:
                users.append(token)
    seen = set()
    out = []
    for u in users:
        k = u.lower()
        if k not in seen:
            seen.add(k)
            out.append(u)
    return out

def _try_infer_suspect_from_911(cues) -> str | None:
    """
    If we have Time of Crime + Victim for the open case, look for an exact
    match in the 911 JSON. When found, take the 'suspect' suffix from
    that row and resolve it against the 'online_users'.
    Return a single username, or None if ambiguous/not found.
    """
    try:
        # prefer values already parsed from the case body
        time_of_crime = (cues or {}).get("agg_time") or _get_case_cell("Time of Crime:")
        victim = (cues or {}).get("victim") or _get_case_cell("Victim:")

        if not time_of_crime or not victim:
            return None

        path = global_vars.POLICE_911_CACHE_FILE
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            rows = json.load(f) or []

        for r in rows:
            if (r.get("time") == time_of_crime) and (r.get("victim", "").lower() == victim.lower()):
                suffix = (r.get("suspect") or "").strip()
                if len(suffix) < 2:
                    print(f"911 match found but suspect suffix too short ('{suffix}')")
                    return None

                # online_users is stored as a single comma-separated string in the cache
                online_raw = r.get("online_users", "") or ""
                users = [u.strip() for u in re.split(r"[,]+", online_raw) if u.strip()]

                candidates = [u for u in users if u.endswith(suffix)]
                print(f"911 MATCH: {time_of_crime} | {victim} → suffix '{suffix}' → candidates: {candidates}")

                if len(candidates) == 1:
                    return candidates[0]  # resolved suspect

                # ambiguous or none → don’t guess
                return None

        return None
    except Exception as e:
        print(f"911 infer failed: {e}")
        return None


