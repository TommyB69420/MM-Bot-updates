import re

from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _navigate_to_page_via_menu, _find_and_click, _find_and_send_keys, _get_element_text, _find_element
from modules.agg_helpers import log_aggravated_event

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
    Uses a centralised business lists from global_vars.py.
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