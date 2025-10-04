import datetime
import random
import time
import sys
from selenium.webdriver.common.by import By
import global_vars
from aws_botusers import upsert_bot_user_snapshot, mark_stale_bot_users_offline
from discord_bridge import start_discord_bridge
from agg_crimes import execute_aggravated_crime_logic, execute_funeral_parlour_scan
from earn_functions import execute_earns_logic, diligent_worker
from occupations import judge_casework, lawyer_casework, medical_casework, community_services, laundering, \
    manufacture_drugs, banker_laundering, banker_add_clients, fire_casework, fire_duties, engineering_casework, \
    customs_blind_eyes, execute_smuggle_for_player, mortician_autopsy, community_service_foreign
from helper_functions import _get_element_text, _find_and_send_keys, _find_and_click, is_player_in_jail, blind_eye_queue_count, community_service_queue_count, dequeue_community_service, funeral_smuggle_queue_count
from database_functions import init_local_db
from police import police_911, prepare_police_cases, train_forensics
from timer_functions import get_all_active_game_timers
from comms_journals import send_discord_notification, get_unread_message_count, read_and_send_new_messages, get_unread_journal_count, process_unread_journal_entries
from misc_functions import study_degrees, do_events, check_weapon_shop, check_drug_store, jail_work, \
    clean_money_on_hand_logic, gym_training, check_bionics_shop, police_training, combat_training, fire_training, \
    customs_training, take_promotion, consume_drugs, casino_slots

# --- Initialize Local Cooldown Database ---
if not init_local_db():
    exit()

# Capture the initial state
global_vars.initial_game_url = global_vars.driver.current_url

# --- Initial Player Data Fetch ---
def fetch_initial_player_data():
    """Fetches and prints initial player data from the game UI."""
    player_data = {}

    data_elements = {
        "Character Name": {"xpath": "//div[@id='nav_right']/div[normalize-space(text())='Name']/following-sibling::div[1]/a", "kind": "text"},
        "Rank": {"xpath": "//div[@id='nav_right']/div[normalize-space(text())='Rank']/following-sibling::div[1]", "kind": "text"},
        "Occupation": {"xpath": "//div[@id='nav_right']//div[@id='display_top'][normalize-space(text())='Occupation']/following-sibling::div[@id='display_end']", "kind": "text"},
        "Clean Money": {"xpath": "//div[@id='nav_right']//form[contains(., '$')]", "kind": "money"},
        "Dirty Money": {"xpath": "//div[@id='nav_right']/div[normalize-space(text())='Dirty money']/following-sibling::div[1]", "kind": "money"},
        "Location": {"xpath": "//div[@id='nav_right']/div[contains(normalize-space(text()), 'Location')]/following-sibling::div[1]", "kind": "text", "strip_label": "Location:"},
        "Home City": {"xpath": "//div[contains(text(), 'Home City')]/following-sibling::div[1]", "kind": "text", "strip_label": "Home city:"},
        "Next Rank": {"xpath": "//div[@id='nav_right']//div[@role='progressbar' and contains(@class,'bg-rankprogress')]", "attr": "aria-valuenow", "kind": "percent"},
        "Consumables 24h": {"xpath": "//div[@id='nav_right']/div[normalize-space(text())='Consumables / 24h']/following-sibling::div[1]", "kind": "int"},
    }

    # parsers for each kind
    kind_parsers = {
        "money":   lambda s: int(''.join(ch for ch in s if ch.isdigit())) if any(ch.isdigit() for ch in s) else 0,
        "percent": lambda s: int(''.join(ch for ch in s if ch.isdigit())) if any(ch.isdigit() for ch in s) else None,
        "int":     lambda s: int(''.join(ch for ch in s if ch.isdigit())) if any(ch.isdigit() for ch in s) else 0,
        "text":    lambda s: s,
    }

    for key, details in data_elements.items():
        # pull raw text or attribute
        if "attr" in details:
            from helper_functions import _get_element_attribute
            raw = _get_element_attribute(By.XPATH, details["xpath"], details["attr"])
        else:
            raw = _get_element_text(By.XPATH, details["xpath"])

        if not raw:
            print(f"Warning: Could not fetch {key}.")
            player_data[key] = None
            continue

        text_content = raw.strip()
        if details.get("strip_label"):
            text_content = text_content.replace(details["strip_label"], "").strip()

        kind = details.get("kind", "text")
        player_data[key] = kind_parsers.get(kind, kind_parsers["text"])(text_content)

    return player_data

def message_discord_on_startup():
    """On process start (and first loop), if we're already in-game,
    send the 'Script started for character: …' Discord message once."""
    if getattr(global_vars, "startup_login_ping_sent", False):
        return

    try:
        # If we're actually in-game, this should succeed:
        initial_player_data = fetch_initial_player_data()
        character_name = initial_player_data.get("Character Name", "UNKNOWN")
        if character_name and character_name != "UNKNOWN":
            send_discord_notification(f"Script started for character: {character_name}. Version: {global_vars.SCRIPT_VERSION}")
            setattr(global_vars, "startup_login_ping_sent", True)
    except Exception as e:
        # Not in-game yet (or DOM not ready) — totally fine; we'll try again later.
        print(f"Startup ping not sent yet (HUD not ready): {e}")

def check_for_logout_and_login():
    """
    Handles bounce-back after logging in:
    - If on login screen (default.asp), enter username/password and click Sign in.
    - If redirected back to login, try again until logged in.
    - Once logged in, click Play Now.
    Returns True if a login attempt was made, False otherwise.
    """

    if "default.asp" not in (global_vars.driver.current_url or "").lower():
        return False  # Not on login screen

    username = global_vars.config['Login Credentials'].get('UserName')
    password = global_vars.config['Login Credentials'].get('Password')
    if not username or not password:
        print("ERROR: Missing UserName/Password in settings.ini.")
        send_discord_notification("Login credentials missing. Cannot log in.")
        return False

    send_discord_notification("Logged out — attempting to log in.")

    while True:
        print("Attempting login…")

        if not _find_and_send_keys(By.XPATH, "//form[@id='loginForm']//input[@id='email']", username):
            print("FAILED: Could not enter username.")
            return True
        if not _find_and_send_keys(By.XPATH, "//input[@id='pass']", password):
            print("FAILED: Could not enter password.")
            return True
        if not _find_and_click(By.XPATH, "//button[normalize-space()='Sign in']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
            print("FAILED: Could not click Sign In button.")
            return True

        # Wait briefly then check URL
        time.sleep(2)
        if "default.asp" not in (global_vars.driver.current_url or "").lower():
            if _find_and_click(By.XPATH, "//a[@title='Log in with the character!|Get inside the world of MafiaMatrix!']", pause=global_vars.ACTION_PAUSE_SECONDS * 3):
                print("Successfully logged in.")
                send_discord_notification("Logged in successfully!")

            else:
                print("Logged in, but Play Now click failed.")
                send_discord_notification("Logged in, but Play Now click failed.")
            return True

        print("Bounce back to login detected. Retrying…")
        time.sleep(1)  # small pause before retry

def check_for_gbh(character_name: str):
    """
    If current URL contains gbh.asp, alert Discord and terminate.
    Returns True if GBH was detected (process will exit).
    """
    try:
        url = (global_vars.driver.current_url or "").lower()
    except Exception:
        url = ""

    if "gbh.asp" in url:
        try:
            discord_id = global_vars.config['Discord Webhooks'].get('DiscordID', '').strip()
        except Exception:
            discord_id = '@discordID'

        # message discord
        msg = f"{discord_id} @here, {character_name} has been GBHd. OMGGG FUCCCKK"
        print("GBH DETECTED — sending Discord alert and stopping the bot.")
        send_discord_notification(msg)
        sys.exit(0)

    return False

def get_enabled_configs(location, occupation, home_city, rank, next_rank_pct):
    """
    Reads the settings from settings.ini to determine what functions to turn on
    """
    config = global_vars.config
    return {
    "do_earns_enabled": config.getboolean('Earns Settings', 'DoEarns', fallback=True),
    "do_diligent_worker_enabled": config.getboolean('Earns Settings', 'UseDilly', fallback=False),
    "do_community_services_enabled": config.getboolean('Actions Settings', 'CommunityService', fallback=False),
    "do_foreign_community_services_enabled": config.getboolean('Actions Settings', 'ForeignCommunityService', fallback=False) and location != home_city,
    "mins_between_aggs": config.getint('Misc', 'MinsBetweenAggs', fallback=30),
    "do_hack_enabled": config.getboolean('Hack', 'DoHack', fallback=False),
    "do_pickpocket_enabled": config.getboolean('PickPocket', 'DoPickPocket', fallback=False),
    "do_mugging_enabled": config.getboolean('Mugging', 'DoMugging', fallback=False),
    "do_bne_enabled": config.getboolean('BnE', 'DoBnE', fallback=False),
    "do_armed_robbery_enabled": config.getboolean('Armed Robbery', 'DoArmedRobbery', fallback=False),
    "do_torch_enabled": config.getboolean('Torch', 'DoTorch', fallback=False),
    "do_judge_cases_enabled": config.getboolean('Judge', 'Do_Cases', fallback=False) and occupation in ("Judge", "Supreme Court Judge") and location == home_city,
    "do_launders_enabled": config.getboolean('Launder', 'DoLaunders', fallback=False) and location != home_city,
    "do_manufacture_drugs_enabled": config.getboolean('Actions Settings', 'ManufactureDrugs', fallback=False) and occupation == "Gangster",
    "do_university_degrees_enabled": config.getboolean('Actions Settings', 'StudyDegrees', fallback=False) and location == home_city,
    "do_event_enabled": config.getboolean('Misc', 'DoEvent', fallback=False),
    "do_weapon_shop_check_enabled": config.getboolean('Weapon Shop', 'CheckWeaponShop', fallback=False) and any("Weapon Shop" in biz_list for city, biz_list in global_vars.private_businesses.items() if city == location),
    "do_drug_store_enabled": config.getboolean('Drug Store', 'CheckDrugStore', fallback=False) and any("Drug Store" in biz_list for city, biz_list in global_vars.private_businesses.items() if city == location),
    "do_firefighter_duties_enabled": config.getboolean('Fire', 'DoFireDuties', fallback=False) and location == home_city and occupation in ("Fire Chief", "Fire Fighter", "Volunteer Fire Fighter"),
    "do_gym_trains_enabled": config.getboolean('Misc', 'GymTrains', fallback=False) and any("Gym" in biz_list for city, biz_list in global_vars.private_businesses.items() if city == location),
    "do_bionics_shop_check_enabled": config.getboolean('Bionics Shop', 'CheckBionicsShop', fallback=False) and any("Bionics" in biz_list for city, biz_list in global_vars.private_businesses.items() if city == location),
    "do_training_enabled": config.get('Actions Settings', 'Training', fallback='').strip().lower() if location == home_city else "",
    "do_post_911_enabled": config.getboolean('Police', 'Post911', fallback=False) and occupation == "Police Officer" and location == home_city,
    "do_police_cases_enabled": config.getboolean('Police', 'DoCases', fallback=False) and occupation == "Police Officer" and location == home_city,
    "do_forensics_enabled": config.getboolean('Police', 'DoForensics', fallback=False) and occupation == "Police Officer" and location == home_city,
    "do_consume_drugs_enabled": config.getboolean('Drugs', 'ConsumeCocaine', fallback=False) and location == home_city,
    "do_slots_enabled": config.getboolean('Misc', 'DoSlots', fallback=False) and any("Casino" in biz_list for city, biz_list in global_vars.private_businesses.items() if city == location),
    "do_lawyer_cases_enabled": occupation == "Lawyer",
    "do_autopsy_work_enabled": occupation in ("Mortician", "Undertaker", "Funeral Director") and location == home_city,
    "do_engineering_work_enabled": occupation in ("Mechanic", "Technician", "Engineer", "Chief Engineer"),
    "do_fire_cases_enabled": occupation in ("Volunteer Fire Fighter", "Fire Fighter", "Fire Chief"),
    "do_medical_cases_enabled": occupation in ("Nurse", "Doctor", "Surgeon", "Hospital Director"),
    "do_bank_cases_enabled": occupation in ("Bank Teller", "Loan Officer", "Bank Manager") and location == home_city,
    "do_bank_add_clients_enabled": config.getboolean('Bank', 'AddClients',fallback=False) and location == home_city and occupation in ("Bank Teller", "Loan Officer", "Bank Manager"),
    "do_blind_eye_enabled": ('customs' in (occupation or '').lower()) and location == home_city and blind_eye_queue_count() > 0,
    "do_funeral_smuggle_enabled": getattr(global_vars, "_smuggle_request_active", None) and global_vars._smuggle_request_active.is_set() and funeral_smuggle_queue_count() > 0,
    "do_auto_promo_enabled": (config.getboolean('Misc', 'TakePromo', fallback=True) and occupation not in {"Fire Chief", "Bank Manager", "Chief Engineer", "Hospital Director", "Funeral Director", "Supreme Court Judge", "Mayor"}
    and rank not in {"Commissioner-General", "Caporegime", "Commissioner"} and ((isinstance(next_rank_pct, (int, float)) and next_rank_pct >= 95) or next_rank_pct is None or (isinstance(next_rank_pct, str) and next_rank_pct.strip().lower() == "unknown"))),
    }

def _determine_sleep_duration(action_performed_in_cycle, timers_data, enabled_configs):
    """
    Determines the optimal sleep duration based on enabled activities and cooldown timers.
    """
    print("\n--- Calculating Sleep Duration ---")

    # Extract timers
    get_timer = lambda key: timers_data.get(key, float('inf'))
    earn = get_timer('earn_time_remaining')
    action = get_timer('action_time_remaining')
    launder = get_timer('launder_time_remaining')
    case = get_timer('case_time_remaining')
    event = get_timer('event_time_remaining')
    skill = get_timer('skill_time_remaining')
    bank_add = get_timer('bank_add_clients_time_remaining')
    aggro = get_timer('aggravated_crime_time_remaining')
    rob_recheck = get_timer('armed_robbery_recheck_time_remaining')
    torch_recheck = get_timer('torch_recheck_time_remaining')
    yps = get_timer('yellow_pages_scan_time_remaining')
    fps = get_timer('funeral_parlour_scan_time_remaining')
    weapon = get_timer('check_weapon_shop_time_remaining')
    drug = get_timer('check_drug_store_time_remaining')
    gym = get_timer('gym_trains_time_remaining')
    bionics = get_timer('check_bionics_store_time_remaining')
    post_911 = get_timer('post_911_time_remaining')
    trafficking = get_timer('trafficking_time_remaining')
    auto_promo = get_timer('promo_check_time_remaining')
    consume_drugs = get_timer('consume_drugs_time_remaining')
    casino = get_timer('casino_slots_time_remaining')

    active = []

    # Add timers if enabled
    if enabled_configs.get('do_earns_enabled'):
        active.append(('Earn', earn))
    if enabled_configs.get('do_diligent_worker_enabled'):
        active.append(('Diligent Worker', skill))
    if enabled_configs.get('do_community_services_enabled'):
        active.append(('Community Service', action))
    if enabled_configs.get('do_foreign_community_services_enabled'):
        active.append(('Foreign Community Service', action))
    if enabled_configs.get('do_university_degrees_enabled'):
        active.append(('Study Degree', action))
    if enabled_configs.get('do_manufacture_drugs_enabled'):
        active.append(('Manufacture Drugs', action))
    if enabled_configs.get('do_event_enabled'):
        active.append(('Event', event))
    if enabled_configs.get('do_launders_enabled'):
        active.append(('Launder', launder))
    if enabled_configs.get('do_training_enabled'):
        active.append(('Training', action))
    if enabled_configs.get('do_auto_promo_enabled'):
        active.append(('Auto Promo', auto_promo))
    if enabled_configs.get ('do_judge_cases_enabled'):
        active.append(('Judge Casework', case))
    if enabled_configs.get ('do_lawyer_cases_enabled'):
        active.append(('Lawyer Casework', case))
    if enabled_configs.get ('do_autopsy_work_enabled'):
        active.append(('Autopsy Work', case))
    if enabled_configs.get ('do_engineering_work_enabled'):
        active.append(('Engineering Casework', case))
    if enabled_configs.get ('do_fire_cases_enabled'):
        active.append(('FireFighter Casework', case))
    if enabled_configs.get ('do_medical_cases_enabled'):
        active.append(('Medical Casework', case))
    if enabled_configs.get ('do_bank_cases_enabled'):
        active.append(('Bank Casework', case))
    if enabled_configs.get ('do_bank_add_clients_enabled'):
        active.append(('Bank add clients', bank_add))
    if enabled_configs.get ('do_firefighter_duties_enabled'):
        active.append(('Firefighter Duties', action))
    if enabled_configs.get ('do_post_911_enabled'):
        active.append(('Post 911', post_911))
    if enabled_configs.get ('do_police_cases_enabled'):
        active.append(('Do Cases', case))
    if enabled_configs.get ('do_forensics_enabled'):
        effective_forensics = max(action, case)
        active.append(('Forensics', effective_forensics))
    if enabled_configs.get ('do_weapon_shop_check_enabled'):
        active.append(('Check Weapon Shop', weapon))
    if enabled_configs.get ('do_drug_store_enabled'):
        active.append(('Check Drug Store', drug))
    if enabled_configs.get ('do_gym_trains_enabled'):
        active.append(('Gym Trains', gym))
    if enabled_configs.get ('do_slots_enabled'):
        active.append(('Casino Slots', casino))
    if enabled_configs.get ('do_bionics_shop_check_enabled'):
        active.append(('Check Bionics Shop', bionics))
    if enabled_configs.get('do_consume_drugs_enabled'):
        active.append(('Consume Drugs', consume_drugs))
    if enabled_configs.get ('do_blind_eye_enabled'):
        active.append(('Blind Eye', trafficking))
    if enabled_configs.get ('do_funeral_smuggle_enabled'):
        smuggle_tokens = funeral_smuggle_queue_count()
        active.append((f"Smuggle (queued {smuggle_tokens})", trafficking))

    active.append(('Funeral Parlour Scan', fps))

    # Aggravated Crime timers (use enabled_configs flags)
    if any([
        enabled_configs.get('do_hack_enabled'),
        enabled_configs.get('do_pickpocket_enabled'),
        enabled_configs.get('do_mugging_enabled'),
        enabled_configs.get('do_bne_enabled'),
    ]):
        active.append(('Aggravated Crime (General)', aggro))

    elif enabled_configs.get('do_armed_robbery_enabled'):
        if aggro > global_vars.ACTION_PAUSE_SECONDS:
            active.append(('Armed Robbery (General)', aggro))
        else:
            active += [('Armed Robbery (Re-check)', rob_recheck),
                       ('Armed Robbery (General)', aggro)]

    elif enabled_configs.get('do_torch_enabled'):
        if aggro > global_vars.ACTION_PAUSE_SECONDS:
            active.append(('Torch (General)', aggro))
        else:
            active += [('Torch (Re-check)', torch_recheck),
                       ('Torch (General)', aggro)]

    print("--- Timers Under Consideration for Sleep Duration ---")
    for name, timer_val in active:
        print(f"  {name}: {timer_val:.2f} seconds")
    print("----------------------------------------------------")

    # Sleep logic
    valid = [t for _, t in active if t is not None and t != float('inf')]
    sleep_reason = "No active timers found."
    sleep_duration = random.randint(global_vars.MIN_POLLING_INTERVAL_LOWER, global_vars.MIN_POLLING_INTERVAL_UPPER)

    if valid:
        ready = [t for t in valid if t <= global_vars.ACTION_PAUSE_SECONDS]
        if ready:
            min_ready = min(ready)
            sleep_reason = "One or more enabled tasks are immediately ready (timer <= 0)."
            sleep_duration = global_vars.ACTION_PAUSE_SECONDS if min_ready <= 0 else min_ready
        else:
            upcoming = [t for t in valid if t > global_vars.ACTION_PAUSE_SECONDS]
            if upcoming:
                next_time = min(upcoming)
                sleep_reason = f"Waiting for next task in {next_time:.2f}s."
                sleep_duration = max(global_vars.ACTION_PAUSE_SECONDS, next_time)
            else:
                sleep_reason = "All enabled timers are infinite or already processed."

    if not action_performed_in_cycle and sleep_duration > global_vars.MIN_POLLING_INTERVAL_UPPER:
        sleep_duration = random.randint(global_vars.MIN_POLLING_INTERVAL_LOWER, global_vars.MIN_POLLING_INTERVAL_UPPER)
    if action_performed_in_cycle:
        sleep_duration = global_vars.ACTION_PAUSE_SECONDS
        sleep_reason = "An action was just performed in this cycle, re-evaluating soon."

    print(f"Decision: {sleep_reason}")
    return sleep_duration

# --- Start Discord Bridge ---
start_discord_bridge()
print("[Main] Discord bridge started.")

# --- SCRIPT CHECK DETECTION & LOGOUT/LOGIN ---
def perform_critical_checks(character_name):
    """
    Fast, non-blocking check for logout, script check and GBH pages.
    Uses instant checks with no WebDriverWait, or delays.
    """
    # Ensure critical probes and any quick nav happen under the Selenium lock
    with global_vars.DRIVER_LOCK:
        # Check for logout
        try:
            # Look for login form field directly
            login_field = global_vars.driver.find_elements(By.XPATH, "//form[@id='loginForm']//input[@id='email']")
            if login_field:
                print("Logged out. Attempting to log in.")
                if check_for_logout_and_login():
                    global_vars.initial_game_url = global_vars.driver.current_url
                    return True
        except Exception:
            # fall back to URL check if DOM not ready
            if "default.asp" in global_vars.driver.current_url.lower():
                print("Likely logged out (default.asp detected). Attempting login.")
                if check_for_logout_and_login():
                    global_vars.initial_game_url = global_vars.driver.current_url
                    return True

        # GBH page detection
        if check_for_gbh(character_name):
            return True

        # --- Script Check Detection ---
        current_url = global_vars.driver.current_url.lower()
        script_check_found = False

        # Fastest check: by URL
        if "test.asp" in current_url or "activity" in current_url or "test" in current_url:
            script_check_found = True

        else:
            # look to add content-based probes when we next see a script check. the words will need to be specific to the script check page
            pass

        # If a script check is found — alert discord and send puzzle text
        if script_check_found:

            # Try to capture the puzzle prompt's innerHTML
            prompt_html = ""
            try:
                # Primary prompt node we’ve seen on Script checks
                el = global_vars.driver.find_element(By.XPATH, "/html/body/div[4]/div[4]/div[1]/div[2]/center/font[3]")
                prompt_html = el.get_attribute("innerHTML") or ""
            except Exception:
                # Fallback: grab a reasonable center/font block, else trim the page
                try:
                    el = global_vars.driver.find_element(By.XPATH, "(//center | //font)[last()]")
                    prompt_html = el.get_attribute("innerHTML") or ""
                except Exception:
                    prompt_html = (global_vars.driver.page_source or "")[:1800]

            # Trim for Discord and send
            safe_html = prompt_html.strip()
            if len(safe_html) > 1800:
                safe_html = safe_html[:1800] + "…"
            send_discord_notification(
                f"{character_name} @here ADMIN SCRIPT CHECK! ARGGGH FUCK\n"
                f"Paste your solution with `!scriptcheck <answer>`\n"
                f"```html\n{safe_html}\n```"
            )

            # Stay on the page and let the main loop tick; don’t hard-exit the process
            print("ADMIN SCRIPT CHECK detected — sent puzzle to Discord.")
            return True

    return False  # No critical issues


while True:
    if perform_critical_checks("UNKNOWN"):
        continue

    # Re-read settings.ini in case they've changed
    global_vars.config.read('settings.ini') # Re-read config in case it's changed
    action_performed_in_cycle = False

    # --- Fetch all timers first ---
    with global_vars.DRIVER_LOCK:
        all_timers = get_all_active_game_timers()
    global_vars.jail_timers = all_timers  # Store for jail logic access

    # Fetch the player data
    initial_player_data = fetch_initial_player_data()
    character_name = initial_player_data.get("Character Name", "UNKNOWN")
    message_discord_on_startup()

    # --- Jail Check ---
    if is_player_in_jail():
        print("Player is in jail. Entering jail work loop...")

        while True:
            with global_vars.DRIVER_LOCK:
                if not is_player_in_jail():
                    break
                if perform_critical_checks(character_name):
                    continue
                global_vars.jail_timers = get_all_active_game_timers()
                jail_work()
            time.sleep(2)  # sleep outside the lock

        print("Player released from jail. Resuming normal script.")
        continue  # Skip the rest of the main loop for this cycle

    # Critical checks are performed throughout the loop to ensure script checks and log-outs are captured quickly
    if perform_critical_checks(character_name):
        continue

    # Re-fetch player data after potential navigation or actions
    initial_player_data = fetch_initial_player_data()
    character_name = initial_player_data.get("Character Name", character_name)
    rank = initial_player_data.get("Rank")
    occupation = initial_player_data.get("Occupation")
    clean_money = initial_player_data.get("Clean Money")
    dirty_money = initial_player_data.get("Dirty Money")
    location = initial_player_data.get("Location")
    home_city = initial_player_data.get("Home City")
    next_rank_pct = initial_player_data.get("Next Rank")
    Consumables = initial_player_data.get("Consumables 24h")
    print(f"\nCurrent Character: {character_name}, Rank: {rank}, Occupation: {occupation}\nClean Money: {clean_money}, Dirty Money: {dirty_money}\nLocation: {location}. Home City: {home_city}. Next Rank: {next_rank_pct}. Consumables 24h: {Consumables}\n")

    upsert_bot_user_snapshot({
        "name": character_name,
        "rank": rank,
        "occupation": occupation,
        "location": location,
        "home_city": home_city,
        "clean_money": clean_money,
        "dirty_money": dirty_money,
        "next_rank_pct": next_rank_pct,
        "consumables_24h": Consumables,
    })

    # Periodically mark any stale users offline (no-op if called too soon)
    mark_stale_bot_users_offline(max_age_seconds=180)  # ~3 min online window


    # Read enabled configs.
    enabled_configs = get_enabled_configs(location, occupation, home_city, rank, next_rank_pct)


    if perform_critical_checks(character_name):
        continue

    # --- Fetch all game timers AFTER player data and BEFORE action logic ---
    with global_vars.DRIVER_LOCK:
        all_timers = get_all_active_game_timers()

    if perform_critical_checks(character_name):
        continue

    # Extract timers for easier use in conditions (from the freshly fetched all_timers)
    earn_time_remaining = all_timers.get('earn_time_remaining', float('inf'))
    action_time_remaining = all_timers.get('action_time_remaining', float('inf'))
    case_time_remaining = all_timers.get('case_time_remaining', float('inf'))
    launder_time_remaining = all_timers.get('launder_time_remaining', float('inf'))
    event_time_remaining = all_timers.get('event_time_remaining', float('inf'))
    trafficking_time_remaining = all_timers.get('trafficking_time_remaining', float('inf'))
    skill_time_remaining = all_timers.get('skill_time_remaining', float('inf'))

    # Aggravated crime timers
    aggravated_crime_time_remaining = all_timers.get('aggravated_crime_time_remaining', float('inf'))
    armed_robbery_recheck_time_remaining = (getattr(global_vars, "_script_armed_robbery_recheck_cooldown_end_time", datetime.datetime.min) - datetime.datetime.now()).total_seconds()
    torch_recheck_time_remaining = (getattr(global_vars, "_script_torch_recheck_cooldown_end_time", datetime.datetime.min) - datetime.datetime.now()).total_seconds()
    yellow_pages_scan_time_remaining = all_timers.get('yellow_pages_scan_time_remaining', float('inf'))
    funeral_parlour_scan_time_remaining = all_timers.get('funeral_parlour_scan_time_remaining', float('inf'))

    # Misc city timers
    check_weapon_shop_time_remaining = all_timers.get('check_weapon_shop_time_remaining', float('inf'))
    check_drug_store_time_remaining = all_timers.get('check_drug_store_time_remaining', float('inf'))
    gym_trains_time_remaining = all_timers.get('gym_trains_time_remaining', float('inf'))
    check_bionics_store_time_remaining = all_timers.get('check_bionics_store_time_remaining', float('inf'))
    promo_check_time_remaining = all_timers.get('promo_check_time_remaining', float('inf'))
    consume_drugs_time_remaining = all_timers.get('consume_drugs_time_remaining', float('inf'))
    casino_slots_time_remaining = all_timers.get('casino_slots_time_remaining', float('inf'))

    # Career specific timers
    bank_add_clients_time_remaining = all_timers.get('bank_add_clients_time_remaining', float('inf'))
    post_911_time_remaining = all_timers.get('post_911_time_remaining', float('inf'))

    if perform_critical_checks(character_name):
        continue

    with global_vars.DRIVER_LOCK:

        # Auto Promo logic
        if enabled_configs.get ('do_auto_promo_enabled') and promo_check_time_remaining <= 0:
            print(f"Auto Promo timer ({promo_check_time_remaining:.2f}s) is ready. Attempting auto-promotion...")
            if take_promotion():
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Diligent Worker Logic
        if enabled_configs.get ('do_diligent_worker_enabled') and skill_time_remaining <= 0:
            print(f"Skill timer ({skill_time_remaining:.2f}s) is ready. Attempting Diligent Worker.")
            if diligent_worker(character_name, which_player=None):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Earn logic
        if enabled_configs.get ('do_earns_enabled') and earn_time_remaining <= 0:
            print(f"Earn timer ({earn_time_remaining:.2f}s) is ready. Attempting earn.")
            if execute_earns_logic():
                action_performed_in_cycle = True
            else:
                print("Earns logic did not perform an action or failed. Setting fallback cooldown.")

        if perform_critical_checks(character_name):
            continue

        # Funeral Parlour & Yellow Pages scan logic
        if funeral_parlour_scan_time_remaining <= 0:
            print(f"Funeral Parlour Scan timer ({funeral_parlour_scan_time_remaining:.2f}s) is ready. Attempting scan.")
            if execute_funeral_parlour_scan():
                action_performed_in_cycle = True
            else:
                print("Funeral Parlour Scan logic did not perform an action or failed. No immediate cooldown from here.")

        if perform_critical_checks(character_name):
            continue

        # Mandatory Community Services (queued by AgCrime gate)
        queued_cs = community_service_queue_count()
        if queued_cs > 0 and action_time_remaining <= 0:
            print(f"Mandatory Community Service queued ({queued_cs}). Attempting 1 now.")
            if community_services(initial_player_data):
                if dequeue_community_service():
                    print(f"Completed 1 queued Community Service. Remaining: {community_service_queue_count()}")
                action_performed_in_cycle = True
            else:
                print("Queued Community Service attempt failed or could not start. Will retry next cycle.")

        # Community Service Logic
        if enabled_configs.get ('do_community_services_enabled') and action_time_remaining <= 0:
            print(f"Community Service timer ({action_time_remaining:.2f}s) is ready. Attempting CS.")
            if community_services(initial_player_data):
                action_performed_in_cycle = True
            else:
                print("Community Service logic did not perform an action or failed. Setting fallback cooldown.")

        # Foreign Community Service Logic
        if enabled_configs.get ('do_foreign_community_services_enabled') and action_time_remaining <= 0:
            print(f"Foreign Community Service timer ({action_time_remaining:.2f}s) is ready. Attempting Foreign CS.")
            if community_service_foreign(initial_player_data):
                action_performed_in_cycle = True
            else:
                print("Foreign Community Service logic did not perform an action or failed. Setting fallback cooldown.")

        if perform_critical_checks(character_name):
            continue

        # Firefighter duties Logic
        if enabled_configs.get ('do_firefighter_duties_enabled') and action_time_remaining <= 0:
            print(f"Firefighter duties timer ({action_time_remaining:.2f}s) is ready. Attempting to do duties.")
            if fire_duties():
                action_performed_in_cycle = True
            else:
                print("Firefighter duties logic did not perform an action or failed. Setting fallback cooldown.")

        if perform_critical_checks(character_name):
            continue

        # Study Degrees Logic
        if enabled_configs.get ('do_university_degrees_enabled') and action_time_remaining <= 0:
            print(f"Study Degree timer ({action_time_remaining:.2f}s) is ready. Attempting Study Degree.")
            if study_degrees():
                action_performed_in_cycle = True
            else:
                print("Study Degree logic did not perform an action or failed. Setting fallback cooldown.")

        if perform_critical_checks(character_name):
            continue

        # Training logic
        if enabled_configs.get ('do_training_enabled') and action_time_remaining <= 0:
            training_type = enabled_configs['do_training_enabled'].lower()

            training_map = {
                "police": police_training,
                "forensics": train_forensics,
                "fire": fire_training,
                "customs": customs_training,
                "jui jitsu": combat_training,
                "muay thai": combat_training,
                "karate": combat_training,
                "mma": combat_training,
            }

            func = training_map.get(training_type)
            if func:
                func()
                action_performed_in_cycle = True
            else:
                print(f"WARNING: Unknown training type '{training_type}' specified in settings.ini.")

        if perform_critical_checks(character_name):
            continue

        # Drug manufacturing logic
        if enabled_configs.get ('do_manufacture_drugs_enabled') and action_time_remaining <= 0:
            print(f"Manufacture Drugs timer ({action_time_remaining:.2f}s) is ready. Attempting manufacture.")
            if manufacture_drugs():
                action_performed_in_cycle = True
            else:
                print("Manufacture Drugs logic did not perform an action or failed. Setting fallback cooldown.")

        if perform_critical_checks(character_name):
            continue

        # Do Aggravated Crime Logic
        should_attempt_aggravated_crime = False

        # Check if any aggravated crime setting is enabled
        if any([
            enabled_configs.get ('do_hack_enabled'),
            enabled_configs.get ('do_pickpocket_enabled'),
            enabled_configs.get ('do_mugging_enabled'),
            enabled_configs.get ('do_bne_enabled'),
            enabled_configs.get ('do_armed_robbery_enabled'),
            enabled_configs.get ('do_torch_enabled'),
        ]):
            # Hack / Pickpocket / Mugging / BnE — only if no mandatory CS queued
            if any([
                enabled_configs.get ('do_hack_enabled'),
                enabled_configs.get ('do_pickpocket_enabled'),
                enabled_configs.get ('do_mugging_enabled'),
                enabled_configs.get ('do_bne_enabled'),
            ]) and aggravated_crime_time_remaining <= 0 and community_service_queue_count() == 0:
                should_attempt_aggravated_crime = True
                print(f"Aggravated Crime timer ({aggravated_crime_time_remaining:.2f}s) is ready. Attempting crime.")

            # Armed Robbery — only if no mandatory CS queued
            if enabled_configs.get ('do_armed_robbery_enabled'):
                if (aggravated_crime_time_remaining <= 0
                        and armed_robbery_recheck_time_remaining <= 0
                        and community_service_queue_count() == 0):
                    should_attempt_aggravated_crime = True
                    print("Armed Robbery timers are ready. Attempting crime.")

            # Torch — only if no mandatory CS queued
            if enabled_configs.get ('do_torch_enabled'):
                if (aggravated_crime_time_remaining <= 0
                        and torch_recheck_time_remaining <= 0
                        and community_service_queue_count() == 0):
                    should_attempt_aggravated_crime = True
                    print("Torch timers are ready. Attempting crime.")

            # Execute if any path above marked it ready
            if should_attempt_aggravated_crime:
                if execute_aggravated_crime_logic(initial_player_data):
                    action_performed_in_cycle = True
                else:
                    print("Aggravated Crime logic did not perform an action or failed. No immediate cooldown from here.")

        if perform_critical_checks(character_name):
            continue

        # Deposit and withdraw excess money logic
        if clean_money_on_hand_logic(initial_player_data):
            action_performed_in_cycle = True
        else:
            print("Checking clean money on hand - Amount is within limits.")

        if perform_critical_checks(character_name):
            continue

        # Do event logic
        if enabled_configs.get ('do_event_enabled') and event_time_remaining <= 0:
            print(f"Event timer ({event_time_remaining:.2f}s) is ready. Attempting the event.")
            if do_events():
                action_performed_in_cycle = True
            else:
                print("Event logic did not perform an action or failed.")

        if perform_critical_checks(character_name):
            continue

        # Do Weapon Shop Logic
        if enabled_configs.get ('do_weapon_shop_check_enabled') and check_weapon_shop_time_remaining <= 0:
            print(f"Weapon Shop timer ({check_weapon_shop_time_remaining:.2f}s) is ready. Attempting check now.")
            if check_weapon_shop(initial_player_data):
                action_performed_in_cycle = True

        # Consume Drugs Logic
        if enabled_configs.get ('do_consume_drugs_enabled') and consume_drugs_time_remaining <= 0:
            print(f"Consume Drugs timer ({consume_drugs_time_remaining:.2f}s) is ready. Attempting consume/earn loop now.")
            if consume_drugs():
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Bionics Shop Logic
        if enabled_configs.get ('do_bionics_shop_check_enabled') and check_bionics_store_time_remaining <= 0:
            print(f"Bionics Shop timer ({check_bionics_store_time_remaining:.2f}s) is ready. Attempting check now.")
            if check_bionics_shop(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Casino Slots logic
        if enabled_configs.get ('do_slots_enabled') and casino_slots_time_remaining <= 0:
            print("Casino Slots timer ready. Attempting to play until addiction warning.")
            if casino_slots():
                action_performed_in_cycle = True

        # Drug Store Check Logic
        if enabled_configs.get ('do_drug_store_enabled') and check_drug_store_time_remaining <= 0:
            print(f"Drug Store timer ({check_drug_store_time_remaining:.2f}s) is ready. Attempting to check Drug Store.")
            if check_drug_store(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Gym Train Logic
        if enabled_configs.get ('do_gym_trains_enabled') and gym_trains_time_remaining <= 0:
            print(f"Gym trains timer ({gym_trains_time_remaining:.2f}s) is ready. Attempting Gym trains.")
            if gym_training():
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Judge Casework Logic
        if enabled_configs.get ('do_judge_cases_enabled') and case_time_remaining <= 0:
            print(f"Judge Casework timer ({case_time_remaining:.2f}s) is ready. Attempting judge cases.")
            if judge_casework(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Lawyer case work logic
        if enabled_configs.get ('do_lawyer_cases_enabled') and case_time_remaining <= 0:
            print(f"Lawyer Casework timer ({case_time_remaining:.2f}s) is ready. Attempting lawyer cases.")
            if lawyer_casework():
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Medical Casework Logic
        if enabled_configs.get ('do_medical_cases_enabled') and case_time_remaining <= 0:
            print(f"Medical Casework timer ({case_time_remaining:.2f}s) is ready. Attempting medical cases.")
            if medical_casework(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Mortician Autopsy Logic
        if enabled_configs.get ('do_autopsy_work_enabled') and case_time_remaining <= 0:
            print(f"Autopsy timer is ready ({case_time_remaining:.2f}s) is ready. Attempting autopsy cases.")
            if mortician_autopsy():
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Police Casework Logic
        if enabled_configs.get ('do_police_cases_enabled') and case_time_remaining <= 0:
            print(f"Police case timer ({case_time_remaining:.2f}s) is ready. Attempting to do Police Cases")
            if prepare_police_cases(character_name):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Post 911 Logic
        if enabled_configs.get ('do_post_911_enabled') and post_911_time_remaining <= 0:
            print(f"Post 911 timer ({post_911_time_remaining:.2f}s) is ready. Attempting to post 911")
            if police_911():
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Firefighter Casework Logic
        if enabled_configs.get ('do_fire_cases_enabled') and case_time_remaining <= 0:
            print(f"Fire Fighter Casework timer ({case_time_remaining:.2f}s) is ready. Attempting Fire Fighter cases.")
            if fire_casework(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Bank Laundering Casework Logic
        if enabled_configs.get ('do_bank_cases_enabled') and case_time_remaining <= 0:
            if location == home_city:
                print(f"Bank Casework timer ({case_time_remaining:.2f}s) is ready. Attempting bank cases.")
                if banker_laundering():
                    action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Customs Blind Eye Logic
        if enabled_configs.get ('do_blind_eye_enabled') and trafficking_time_remaining <= 0:
            print(f"Blind Eye queued ({blind_eye_queue_count()}) and Trafficking timer ({trafficking_time_remaining:.2f}s) is ready. Attempting Blind Eye.")
            if customs_blind_eyes():
                action_performed_in_cycle = True

        # Funeral Smuggle Logic
        if enabled_configs.get ('do_funeral_smuggle_enabled') and trafficking_time_remaining <= 0:
            req_target = (global_vars._smuggle_request_target or "").strip()
            smuggle_tokens = funeral_smuggle_queue_count()
            if req_target:
                print(f"[Smuggle] Timer ready and {smuggle_tokens} token(s) available. Attempting smuggle for '{req_target}'.")
                if execute_smuggle_for_player(req_target):
                    global_vars._smuggle_request_active.clear()
                    action_performed_in_cycle = True

        # Bank Add Clients Logic
        if enabled_configs.get ('do_bank_add_clients_enabled') and bank_add_clients_time_remaining <= 0:
            print(f"Add Clients timer ({bank_add_clients_time_remaining:.2f}s) is ready. Attempting to add new clients.")
            if banker_add_clients(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Engineering Casework Logic
        if enabled_configs.get ('do_engineering_work_enabled') and case_time_remaining <= 0:
            print(f"Engineering Casework timer ({case_time_remaining:.2f}s) is ready. Attempting engineering cases.")
            if engineering_casework(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

        # Check messages logic
        current_unread_messages = get_unread_message_count()

        if current_unread_messages > 0:
            read_and_send_new_messages()
            global_vars._last_unread_message_count = get_unread_message_count()
            action_performed_in_cycle = True

        elif global_vars._last_unread_message_count > 0:
            global_vars._last_unread_message_count = 0

        # Check Journals logic
        current_unread_journals = get_unread_journal_count()

        if current_unread_journals > 0:
            if process_unread_journal_entries(initial_player_data):
                action_performed_in_cycle = True
            global_vars._last_unread_journal_count = get_unread_journal_count()

        elif global_vars._last_unread_journal_count > 0:
            global_vars._last_unread_journal_count = 0

        if perform_critical_checks(character_name):
            continue

        # Do Laundering logic (as a gangster, not a banker)
        if enabled_configs.get ('do_launders_enabled') and launder_time_remaining <= 0:
            print(f"Launder timer ({launder_time_remaining:.2f}s) is ready. Attempting launder.")
            if laundering(initial_player_data):
                action_performed_in_cycle = True

        if perform_critical_checks(character_name):
            continue

    # --- Re-fetch all game timers just before determining sleep duration ---
    with global_vars.DRIVER_LOCK:
        all_timers = get_all_active_game_timers()

    # --- Return to the resting page if drifted ---
    resting_page_url = global_vars.config.get('Auth', 'RestingPage', fallback='').strip()

    if resting_page_url:
        with global_vars.DRIVER_LOCK:
            if resting_page_url not in global_vars.driver.current_url:
                print(
                    f"Current URL is '{global_vars.driver.current_url}', expected to include '{resting_page_url}'. Navigating back...")
                try:
                    global_vars.driver.get(resting_page_url)
                    time.sleep(global_vars.ACTION_PAUSE_SECONDS)
                except Exception as e:
                    print(f"FAILED: Could not navigate to the resting page URL '{resting_page_url}'. Error: {e}")
                    continue

                if resting_page_url not in global_vars.driver.current_url:
                    print(f"Still not back on resting page. Current URL: {global_vars.driver.current_url}")
                    continue
    else:
        print("WARNING: No 'RestingPage' URL set in settings.ini under [Auth].")

    # --- Determine the total sleep duration ---
    total_sleep_duration = _determine_sleep_duration(action_performed_in_cycle, {**all_timers, 'occupation': occupation, 'location': location, 'home_city': home_city}, enabled_configs)

    print(f"Sleeping for {total_sleep_duration:.2f} seconds...")
    time.sleep(total_sleep_duration)


