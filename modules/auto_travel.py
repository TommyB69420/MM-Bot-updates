import re
import time
from urllib.parse import urlparse, urljoin

from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import global_vars
from comms_journals import send_discord_notification
from helper_functions import _get_current_url, _navigate_to_page_via_menu, _get_element_text
from timer_functions import get_all_active_game_timers

def execute_travel_to_city(target_city: str, current_city: str = "", discord_user_id: str | None = None, timeout: int = 12):
    """
    Travel flow:
      1) Reads warrants via Police Station
      2) Validates current location provided by caller (no DOM scrape)
      3) Checks travel timer via timer_functions (seconds remaining)
      4) Attempts travel via /travel/depart.asp?destination=<City>

    Discord notifications are sent via send_discord_notification(...).
    Returns True only if the page shows "You have travelled successfully".
    """
    # --- small local helpers (no global side effects) ---
    def _digits_first_int(text, default=0):
        m = re.search(r"\d+", text or "")
        return int(m.group(0)) if m else default

    def _origin_from_current(driver):
        try:
            u = urlparse(driver.current_url or "")
            return f"{u.scheme}://{u.netloc}/"
        except Exception:
            return ""

    def _build_url(driver, path):
        base = _origin_from_current(driver)
        return urljoin(base, path.lstrip("/")) if base else path

    # Resolve and validate target city via global aliases
    valid_map = getattr(global_vars, "CITY_ALIASES", {}) or {}
    key = (target_city or "").strip().lower()
    if key not in valid_map:
        allowed = ", ".join(sorted(set(valid_map.values()))) or "Unknown"
        send_discord_notification(f"City must be one of: {allowed}.")
        return False
    target_city = valid_map[key]

    # acquire driver and common objects
    driver = getattr(global_vars, "driver", getattr(global_vars, "DRIVER", None))
    if driver is None:
        print("[TRAVEL] No webdriver instance available.")
        send_discord_notification("Travel failed: internal browser not available.")
        return False

    wait = WebDriverWait(driver, timeout)
    initial_url = _get_current_url()

    # Check warrants
    if not _navigate_to_page_via_menu(
            "//span[@class='city']",
            "//a[@class='business police_station']",
            "Police Station"
    ):
        send_discord_notification("Travel failed: unable to navigate to Police Station.")
        try:
            if initial_url: driver.get(initial_url)
        except Exception:
            pass
        return False

    warrants_text = _get_element_text(By.XPATH, "//*[@id='holder_content']/div/span[9]/strong")
    warrants = _digits_first_int(warrants_text, 0)
    if warrants > 0:
        plural = "conviction" if warrants == 1 else "convictions"
        send_discord_notification(f"You have {warrants} {plural} and can't travel.")
        try:
            if initial_url: driver.get(initial_url)
        except Exception:
            pass
        return False

    # Get your current location provided by caller
    if current_city and current_city.strip().lower() == target_city.lower():
        send_discord_notification(f"You are already in {target_city}.")
        try:
            if initial_url: driver.get(initial_url)
        except Exception:
            pass
        return False

    # Check travel timer
    timers = get_all_active_game_timers()
    remaining = int(max(0, timers.get("travel_time_remaining", 0)))
    if remaining > 0:
        send_discord_notification(f"Travel timer is not ready ({remaining}s).")
        try:
            if initial_url: driver.get(initial_url)
        except Exception:
            pass
        return False

    # Attempt to travel
    try:
        travel_url = _build_url(driver, f"/travel/depart.asp?destination={target_city}")
        driver.get(travel_url)
        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 0.5)

        page = (driver.page_source or "").lower()

        # Result messages
        if "you dont have enough money on you!" in page:
            send_discord_notification("You dont have enough money on you!")
            return False

        if "you have travelled successfully" in page:
            send_discord_notification(f"You are now in {target_city}.")
            return True

        # Fallback if content changed
        send_discord_notification("Travel attempted but outcome was unclear.")
        return False

    except Exception as e:
        print(f"[TRAVEL] Travel attempt failed: {e}")
        send_discord_notification("Travel failed due to an internal error.")
        return False

    finally:
        # Restore previous page
        try:
            if initial_url:
                driver.get(initial_url)
                time.sleep(global_vars.ACTION_PAUSE_SECONDS * 0.5)
        except Exception:
            print("[TRAVEL] WARNING: Could not return to previous page after travel.")