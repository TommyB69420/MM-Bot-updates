import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from helper_functions import _click_quick_xpath, _get_current_url, _find_and_click, _find_element, \
    _navigate_to_page_via_menu, _find_and_send_keys

def map_promo_choice(promo_name: str):
    """
    Lookup-based promo choice against global_vars.PROMO_MAP.
    Returns 'one' or 'two' if a keyword matches, else None for manual.
    """
    key = (promo_name or "").lower().strip()
    for keyword, choice in global_vars.PROMO_MAP.items():
        if keyword in key:
            return choice
    return None

def _accept_promo_on_current_page() -> bool:
    """
    Shared core that assumes we're already on /promotion.
    Reads the promo, maps to choice 'one' or 'two', clicks it, and continues.
    Sets cooldowns and Discord notices on failure.
    """
    curr_url = (_get_current_url() or "").lower()
    if "promotion" not in curr_url:
        print("Promo: No promotion detected.")
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
        return False

    print("Promo page detected — parsing details...")

    header_el = _find_element(By.XPATH, "//*[@id='holder_top']/h1")
    promo_name = (header_el.text if header_el else "").strip()
    if not promo_name:
        print("Promo: Could not read promotion header.")
        return False

    print(f"Detected Promotion: {promo_name}")

    choice = map_promo_choice(promo_name)
    if choice not in {"one", "two"}:
        msg = f"Unable to auto-take promotion — manual action required: {promo_name}"
        print("Promo:", msg)
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))

        last_name = getattr(global_vars, "_promo_unable_last_name", None)
        if last_name != promo_name:
            setattr(global_vars, "_promo_unable_notify_count", 0)
            setattr(global_vars, "_promo_unable_last_name", promo_name)

        count = getattr(global_vars, "_promo_unable_notify_count", 0)
        if count < 5:
            try:
                send_discord_notification(msg)
            except Exception:
                pass
            setattr(global_vars, "_promo_unable_notify_count", count + 1)
        return False

    if not _find_and_click(By.ID, choice, pause=0):
        print(f"Promo: Could not click option '{choice}'.")
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
        return False

    if not _find_and_click(By.XPATH, "//*[@id='holder_content']/form/center/input", pause=0):
        print("Promo: Could not click Continue.")
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
        return False

    print("Promo: Continue clicked — promotion accepted.")
    try:
        send_discord_notification(f"Taking promotion: {promo_name}")
    except Exception:
        pass

    setattr(global_vars, "_promo_unable_notify_count", 0)
    setattr(global_vars, "_promo_unable_last_name", None)

    setattr(global_vars, "force_reselect_earn", True)
    print("Promo: Flag set to force re-selecting earn on next cycle.")
    return True

def check_and_take_promotion(player_ctx: dict | None = None) -> bool:
    """
    Single-shot promo check used by the periodic loop.
    Clicks the logo once, and if a promotion is present, accepts it.
    Returns True if a promotion was taken, else False (and sets a short cooldown).
    """
    print("\n--- Promotion Check ---")

    if not _find_and_click(By.XPATH, "//*[@id='logo_hit']", pause=0):
        print("Promo: Could not click logo.")
        return False
    time.sleep(0.2)

    # Will set cooldown and return False if not actually on a promo page.
    took = _accept_promo_on_current_page()

    # After we’ve checked (and possibly taken) the promo, check top-job vacancy
    try:
        auto_top_job_scan_and_spam(player_ctx)
    except Exception as e:
        print(f"[TopJob] Error during vacancy check: {e}")

    return took

def spam_for_promotion_and_take(max_minutes: float = 25.0) -> bool:
    """
    Aggressively spam-clicks the logo until a promotion page appears (or timeout),
    then accepts it on arrival. Mirrors prior PromoSpam behavior.
    Returns True on success; False if timed out or failed.
    """
    print("\n--- Promotion Check (spam) ---")
    print(f"PromoSpam enabled — spamming logo until promotion appears (max {int(max_minutes)} minutes).")

    start = time.monotonic()
    max_seconds = int(max_minutes * 60)
    while (time.monotonic() - start) < max_seconds:
        _click_quick_xpath(By.XPATH, "//*[@id='logo_hit']")
        time.sleep(0.15)
        curr_url = (_get_current_url() or "").lower()
        if "promotion" in curr_url:
            print("PromoSpam: promotion page detected — exiting spam loop.")
            break
    else:
        print(f"PromoSpam: No promotion detected after {int(max_minutes)} minutes. Backing off.")
        global_vars._script_promo_check_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(2, 4))
        return False

    return _accept_promo_on_current_page()

def take_promotion(player_ctx: dict | None = None) -> bool:
    """
    Backwards-compatible delegator.
    Uses [Misc] PromoSpam to choose between single-check and spam mode.
    """
    try:
        promo_spam_enabled = global_vars.cfg_bool('Misc', 'PromoSpam', False)
    except Exception:
        promo_spam_enabled = False

    if promo_spam_enabled:
        return spam_for_promotion_and_take()
    return check_and_take_promotion(player_ctx)

def auto_top_job_scan_and_spam(player_ctx: dict | None = None) -> bool:
    """
    If our Occupation is one of the target roles (Loan Officer, Surgeon, Engineer,
    Mortician/Undertaker, Fire Fighter) OR Rank is Superintendent, open City -> Yellow Pages,
    search the relevant occupation, and check whether the city's TOP job is present for OUR home city.
    If the top job is NOT present in our Home City, start promo spam for the top job immediately.

    Returns True if spam was triggered, else False.
    """
    # --- Read Occupation / Rank / City / Name directly from player_ctx ---
    occ = rank = my_city = player_name = ""

    if player_ctx:
        occ = (player_ctx.get("Occupation") or "").lower()
        rank = (player_ctx.get("Rank") or "").lower()
        my_city = (player_ctx.get("Home City") or "").strip()
        player_name = (player_ctx.get("Character Name") or "").strip()

    # If we can’t determine the minimum inputs, skip quietly
    if not (occ or rank):
        print("[TopJob] Unknown occupation/rank. Skipping vacancy check.")
        return False

    # Map occupation/rank -> (search_term, top_title we expect to see in results for our city)
    # Note: handle synonyms and the Superintendent rank -> Customs mapping
    target = None
    if "loan officer" in occ:
        target = ("Bank", "Bank Manager")
    elif "surgeon" in occ:
        target = ("Hospital", "Hospital Director")
    elif "engineer" in occ:
        target = ("Engineering", "Chief Engineer")
    elif "mortician" in occ or "undertaker" in occ:
        target = ("Funeral", "Funeral Director")
    elif "fire fighter" in occ or "firefighter" in occ:
        target = ("Fire", "Fire Chief")
    elif "superintendent" in rank:
        target = ("Customs", "Commissioner-General")

    if not target:
        print(f"[TopJob] Occupation '{occ}' / rank '{rank}' not in monitored set. Skipping.")
        return False

    search_term, top_title = target
    print(f"[TopJob] Checking vacancy for '{top_title}' in our city via Yellow Pages…")

    # Navigate: City → Yellow Pages
    if not _navigate_to_page_via_menu("//span[@class='city']",
                                      "//a[@class='business yellow_pages']",
                                      "Yellow Pages"):
        print("[TopJob] Navigation to Yellow Pages failed.")
        return False

    # Use the same style of selectors YP scanner relies on
    search_input_xpath = "//input[@type='text']"
    search_button_xpath = "//input[@name='B1']"
    results_table_xpath = "//*[@id='content']/center/div/div[2]/table"

    # Enter the occupation keyword and search
    if not _find_and_send_keys(By.XPATH, search_input_xpath, search_term, pause=0):
        print(f"[TopJob] Could not enter search term '{search_term}'.")
        return False
    if not _find_and_click(By.XPATH, search_button_xpath, pause=0):
        print("[TopJob] Could not click search.")
        return False

    # Wait briefly for Yellow Pages results table to render fully, then poll
    time.sleep(0.8)  # allow DOM to finish re-render after clicking Search

    data_rows = None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not data_rows:
        try:
            table = _find_element(By.XPATH, results_table_xpath)
            if not table:
                time.sleep(0.1)
                continue

            # Touch once to ensure the element is stable (prevents stale later)
            _ = table.get_attribute("outerHTML")

            rows = table.find_elements(By.TAG_NAME, "tr")
            cand = [r for r in rows if r.find_elements(By.XPATH, ".//a[contains(@href, 'userprofile.asp')]")]
            if cand:
                data_rows = cand
                break

            time.sleep(0.1)  # table present but not populated yet
        except Exception:
            # If the DOM is mid-refresh or briefly unavailable, retry quickly
            time.sleep(0.1)
            continue

    if not data_rows:
        print(f"[TopJob] No results table/rows for '{search_term}'.")
        return False

    # If we still don't know our city, try to infer from our own player row if we can
    if not my_city and player_name:
        try:
            for r in data_rows:
                name_links = r.find_elements(By.XPATH, ".//td[1]/a")
                city_elems = r.find_elements(By.XPATH, ".//td[4]")
                if name_links and city_elems:
                    if name_links[0].text.strip().lower() == player_name.lower():
                        my_city = city_elems[0].text.strip()
                        print(f"[TopJob] Inferred our Home City from table: {my_city}")
                        break
        except Exception:
            pass

    if not my_city:
        print("[TopJob] Unable to determine our Home City. Skipping vacancy check.")
        return False

    # Look for a row in OUR city with the TOP title (occupation is sometimes in td[2] or td[3])
    present_in_our_city = False
    for r in data_rows:
        occ2 = (r.find_elements(By.XPATH, ".//td[2]")[0].text.strip()
                if r.find_elements(By.XPATH, ".//td[2]") else "")
        occ3 = (r.find_elements(By.XPATH, ".//td[3]")[0].text.strip()
                if r.find_elements(By.XPATH, ".//td[3]") else "")
        city = (r.find_elements(By.XPATH, ".//td[4]")[0].text.strip()
                if r.find_elements(By.XPATH, ".//td[4]") else "")

        if city.lower() == my_city.lower() and (
                occ2.strip().lower() == top_title.lower() or
                occ3.strip().lower() == top_title.lower()
        ):
            present_in_our_city = True
            break

    if present_in_our_city:
        # Try to get the player name for whoever holds the top job in our city
        top_job_holder = "Unknown"
        try:
            for r in data_rows:
                occ2 = (r.find_elements(By.XPATH, ".//td[2]")[0].text.strip()
                        if r.find_elements(By.XPATH, ".//td[2]") else "")
                occ3 = (r.find_elements(By.XPATH, ".//td[3]")[0].text.strip()
                        if r.find_elements(By.XPATH, ".//td[3]") else "")
                city = (r.find_elements(By.XPATH, ".//td[4]")[0].text.strip()
                        if r.find_elements(By.XPATH, ".//td[4]") else "")
                if city.lower() == my_city.lower() and (
                        occ2.strip().lower() == top_title.lower() or
                        occ3.strip().lower() == top_title.lower()
                ):
                    name_links = r.find_elements(By.XPATH, ".//td[1]/a")
                    if name_links:
                        top_job_holder = name_links[0].text.strip()
                    break
        except Exception:
            pass

        print(f"[TopJob] '{top_title}' is already filled in {my_city} by {top_job_holder}. No action.")
        return False

    msg = f"{top_title}' is vacant in {my_city} — starting promo spam now."
    print(msg)
    try:
        send_discord_notification(msg)
    except Exception:
        pass

    # Kick off aggressive spam to capture the promotion when it appears
    return spam_for_promotion_and_take()

