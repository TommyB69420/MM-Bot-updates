import datetime
import random
import time

from selenium.common import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
import global_vars
from comms_journals import send_discord_notification
from helper_functions import _find_and_click, _find_element, _navigate_to_page_via_menu, _get_element_text, _get_dropdown_options, _select_dropdown_option, _find_and_send_keys
from database_functions import set_all_degrees_status, get_all_degrees_status, _set_last_timestamp
from timer_functions import get_all_active_game_timers


def study_degrees():
    """
    Manages the process of studying university degrees.
    Checks a config setting to determine if a degree study should be attempted.
    Navigates to the university page, checks for available degrees, and attempts to study them.
    Updates a local file (game_data/all_degrees.json) when all degrees are completed.
    """
    print("\n--- Beginning Study Degrees Operation ---")

    # Check if all degrees are already completed based on a local file
    if get_all_degrees_status():
        print("All degrees already completed according to local data. Skipping operation.")
        return False

    # Navigate to the University Degree page
    if not _navigate_to_page_via_menu(
            "//*[@id='nav_left']/div[3]/a[2]", # Click the city page
            "//*[@id='city_holder']//a[contains(@class, 'business') and contains(@class, 'university')]", # Click University
            "University"
    ):
        print("FAILED: Failed to navigate to University Degree page.")
        # Set a cooldown before retrying, as navigation failed
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # Check if there are no more university studies to complete
    no_more_studies_element = _find_element(By.XPATH, "//*[@id='content']/div[@id='study_holder']/div[@id='holder_content']/p[@class='center']")
    if no_more_studies_element:
        results_text = _get_element_text(By.XPATH, "//*[@id='content']/div[@id='study_holder']/div[@id='holder_content']/p[@class='center']")
        if 'no more university studies to complete' in results_text:
            print("Detected 'no more university studies to complete'. Updating all_degrees.json to True.")
            set_all_degrees_status(True) # Set status to True
            # Set a long cooldown as there's nothing more to do
            global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(days=365)
            return True # Successfully determined all degrees are done

    # Get available dropdown options for degrees
    dropdown_options = _get_dropdown_options(By.XPATH, ".//*[@id='study_holder']/div[@id='holder_content']/form/select")

    degree_selected = False
    if "Yes, I would like to study" in dropdown_options:
        print(f"Dropdown options: {dropdown_options}")
        if _select_dropdown_option(By.XPATH, ".//*[@id='study_holder']/div[@id='holder_content']/form/select", "Yes, I would like to study"):
            if _find_and_click(By.XPATH, "//form//input[@type='submit']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
                print("Clicked submit to start studying.")
                degree_selected = True
            else:
                print("FAILED: Could not click submit button for 'Yes, I would like to study'.")
        else:
            print("FAILED: Could not select 'Yes, I would like to study' from dropdown.")
    else:
        # Prioritise specific degrees if 'study' is not an option
        degrees_to_check = ["Business", "Science", "Engineering", "Medicine", "Law"]
        for degree in degrees_to_check:
            if degree in dropdown_options:
                if _select_dropdown_option(By.XPATH, ".//*[@id='study_holder']/div[@id='holder_content']/form/select", degree):
                    print(f"Selected '{degree}' degree.")
                    if _find_and_click(By.XPATH, "//form//input[@type='submit']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
                        print(f"Clicked submit for '{degree}'.")
                        # Confirm the degree study
                        confirm_text = f"Yes, I would like to study for a {degree.lower()} degree"
                        if _select_dropdown_option(By.XPATH, ".//*[@id='study_holder']/div[@id='holder_content']/form/select", confirm_text):
                            print(f"Confirmed study for '{degree}'.")
                            if _find_and_click(By.XPATH, "//form//input[@type='submit']", pause=global_vars.ACTION_PAUSE_SECONDS * 2):
                                print(f"Successfully started studying '{degree}'.")
                                degree_selected = True
                                break # Exit loop after successfully starting a degree
                            else:
                                print(f"FAILED: Could not click final submit button for '{degree}'.")
                        else:
                            print(f"FAILED: Could not confirm study for '{degree}'.")
                else:
                    print(f"FAILED: Could not select '{degree}' from dropdown.")
            if degree_selected:
                break # Break the outer loop if a degree was successfully selected and initiated

    if degree_selected:
        print("Successfully initiated degree study.")
        return True
    else:
        print("No suitable degree options found or could not initiate study.")
        # If no degree was selected, set a slightly longer cooldown before re-checking
        global_vars._script_action_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(300, 600))
        return False

def clean_money_on_hand_logic(initial_player_data):
    """
    Manages clean money: deposits excess using quick deposit and withdraws desired amount from bank.
    Returns True if an action was performed, False otherwise.
    """
    action_performed = False
    clean_money = initial_player_data.get("Clean Money", 0)

    excess_money_on_hand_limit = global_vars.config.getint('Misc', 'ExcessMoneyOnHand', fallback=100000)
    desired_money_on_hand = global_vars.config.getint('Misc', 'MoneyOnHand', fallback=50000)

    # --- Deposit excess money ---
    if clean_money > excess_money_on_hand_limit:
        print(f"Clean money (${clean_money:,}) is above the excess limit (${excess_money_on_hand_limit:,}). Attempting quick deposit.")
        quick_deposit_xpath = "//form[@name='autodepositM']"

        if _find_and_click(By.XPATH, quick_deposit_xpath):
            print("Successfully initiated quick deposit for excess money.")
            action_performed = True
            time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
        else:
            print("Failed to click the quick deposit element.")

    # Withdraw money if under target
    if clean_money < desired_money_on_hand:
        withdraw_amount = desired_money_on_hand - clean_money
        print(f"Clean money (${clean_money:,}) is below desired amount (${desired_money_on_hand:,}). Will attempt to withdraw ${withdraw_amount:,}.")
        if withdraw_amount > 0 and withdraw_money(withdraw_amount):
            action_performed = True

    return action_performed

def withdraw_money(amount: int) -> bool:
    """
    Withdraws the specified amount of money from the bank.
    Returns True if the withdrawal was successful, False otherwise.
    """
    print(f"Attempting to withdraw ${amount:,} from the bank.")

    # Navigate to Bank page
    if not _navigate_to_page_via_menu(
        "//span[@class='income']",
        "//a[normalize-space()='Bank']",
        "Bank"
    ):
        print("Failed to navigate to the Bank page.")
        return False

    if not _find_and_click(By.XPATH, "//a[normalize-space()='Withdrawal']"):
        print("Failed to click withdrawal button.")
        return False

    if not _find_and_send_keys(By.XPATH, "//input[@name='withdrawal']", str(amount)):
        print("Failed to enter withdrawal amount.")
        return False

    if not _find_and_click(By.XPATH, "//input[@name='B1']"):
        print("Failed to click withdraw submit button.")
        return False

    print(f"Successfully withdrew ${amount:,}.")
    time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)
    return True

def do_events():
    """
    Checks for and attempts the in the game event based on settings.ini.
    Returns True if an action was performed (attacked or cooldown set), False otherwise.
    """

    print("\n--- Beginning Event Operation ---")

    # Click the logo to go to the game home page
    if not _find_and_click(By.XPATH, "//*[@id='logo_hit']"):
        print("Failed to click game logo to navigate to home page.")
        return False
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Click the button to navigate to the event page
    event_page_button_xpath = "//a[@class='easterboss acceptbutton' and contains(text(), 'help defend your local city')]"
    if not _find_and_click(By.XPATH, event_page_button_xpath):
        print("Event button 'help defend your local city' not found or not clickable.")
        # If the event button is not available, set a cooldown and return. It prevents constant re-checking when no event is active
        print("Setting event re-check cooldown for 5-7 minutes.")
        global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(5, 7))
        return False

    time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

    # Check for the 'ATTACK' button
    attack_button_xpath = "//a[@class='declinebutton' and contains(text(), 'ATTACK')]"
    if _find_and_click(By.XPATH, attack_button_xpath):
        print("Successfully clicked 'ATTACK' button for the event!")
        # If attacked, read the event_time_remaining from timer_functions.py
        all_timers = get_all_active_game_timers()
        event_time_remaining = all_timers.get('event_time_remaining', float('inf'))

        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

        if event_time_remaining > 0 and event_time_remaining != float('inf'):
            print(f"Event attack successful. Next event action available in {event_time_remaining:.2f} seconds.")
        else:
            print("Event attack successful, but could not determine event cooldown from game timers. Will re-evaluate soon.")
            # Set a fallback cooldown if the game timer is not immediately available
            global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(60, 120))
        return True
    else:
        print("ATTACK button not available on the event page. Event might be on cooldown or completed.")
        # If attack button not available, set a cooldown of 5-7 minutes
        print("Setting event re-check cooldown for 5-7 minutes.")
        global_vars._script_event_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(5, 7))
        return False

def check_weapon_shop(initial_player_data):
    """
    Checks the weapons shop for stock, message discord with results,
    Withdraws money if required and automatically buy top weapons if enabled in settings.ini.
    """
    print("\n--- Beginning Weapon Shop Operation ---")
    initial_url = global_vars.driver.current_url

    # The main loop has already determined this timer is ready, so no need to check again
    print("Timer was marked ready by main loop. Proceeding with Weapon Shop check.")

    # Read settings
    min_check = global_vars.config['Weapon Shop'].getint('MinWSCheck', 13)
    max_check = global_vars.config['Weapon Shop'].getint('MaxWSCheck', 18)
    notify_stock = global_vars.config['Weapon Shop'].getboolean('NotifyWSStock', fallback=True)
    auto_buy_enabled = global_vars.config['Weapon Shop'].getboolean('AutoBuyWS', fallback=False)
    priority_weapons = [w.strip() for w in global_vars.config['Weapon Shop'].get('AutoBuyWeapons', fallback='').split(',')]

    # Navigate to Weapon Shop
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//p[@class='weapon_shop']",
        "Weapon Shop"
    ):
        print("FAILED: Failed to navigate to Weapon Shop page.")
        global_vars._script_weapon_shop_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    print("Checking weapon shop for available stock...")
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    found_weapons_in_stock = False
    weapon_data = {}

    # Check for stock
    try:
        table = global_vars.driver.find_element(By.TAG_NAME, "table")
        rows = table.find_elements(By.TAG_NAME, "tr")

        for row in rows:
            try:
                # Skip header and description rows
                if row.find_elements(By.CLASS_NAME, "column_title"):
                    continue
                if "display_description" in row.get_attribute("class"):
                    continue

                td_elements = row.find_elements(By.TAG_NAME, "td")
                if len(td_elements) < 4:
                    continue  # Not a valid row

                try:
                    item_name_element = td_elements[1].find_element(By.TAG_NAME, "label")
                    item_name = item_name_element.text.strip().split("\n")[0]
                except NoSuchElementException:
                    print("Warning: Couldn't find label element in second column. Skipping row.")
                    continue

                stock_str = td_elements[3].text.strip()
                try:
                    price_str = td_elements[2].text.strip().replace("$", "").replace(",", "")
                    price = int(price_str)
                    stock = int(stock_str)
                except ValueError:
                    print(f"Warning: Could not parse stock value '{stock_str}' for item '{item_name}'. Skipping.")
                    continue

                # Confirm stock level
                if stock >= 1:
                    found_weapons_in_stock = True
                    print(f"{item_name} is in stock! Stock: {stock}")
                    if notify_stock and item_name in priority_weapons:
                        send_discord_notification("@here " f"{item_name} is in stock! Stock: {stock}")
                    weapon_data[item_name] = {"stock": stock, "price": price}
                else:
                    print(f"Item: {item_name}, Stock: {stock} (out of stock)")

            except (StaleElementReferenceException, Exception) as e:
                print(f"Skipping row due to DOM or unknown error: {e}")
                continue

        # Attempt auto-buy if a priortised weapon is in stock
        if found_weapons_in_stock and auto_buy_enabled and priority_weapons:
            for weapon in priority_weapons:
                data = weapon_data.get(weapon)
                if not data or data["stock"] <= 0:
                    continue

                price = data["price"]
                clean_money_text = _get_element_text(By.XPATH, "//div[@id='nav_right']//form[contains(., '$')]")
                clean_money = int(''.join(filter(lambda c: c.isdigit(), clean_money_text))) if clean_money_text else 0

                if clean_money < price:
                    amount_needed = price - clean_money
                    print(f"Not enough clean money to buy {weapon}. Withdrawing ${amount_needed:,}.")
                    if withdraw_money(amount_needed):
                        # Navigate back to Weapon Shop after withdrawal
                        _navigate_to_page_via_menu(
                            "//span[@class='city']",
                            "//p[@class='weapon_shop']",
                            "Weapon Shop"
                        )
                        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

                auto_buy_weapon(weapon)
                break # Remove this break to buy all weapons in the priority list if multiple is in stock.

        if not found_weapons_in_stock:
            print("No weapons found in stock at the shop currently.")

    # Unable to find the weapon shop table, meaning at max views or page structure has changed.
    except NoSuchElementException:
        print("Error: Could not find the weapon shop table on the page. Page structure might have changed.")
        send_discord_notification("Error: Failed to locate weapon shop table. At max views.")
        global_vars._script_weapon_shop_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(15, 17))
        return False
    except Exception as e:
        print(f"An unexpected error occurred during weapon shop check: {e}")
        send_discord_notification(f"Error during weapon shop check: {e}")
        global_vars._script_weapon_shop_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    # Set the next cooldown timestamp (randomized range from settings.ini)
    next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(min_check, max_check))
    _set_last_timestamp(global_vars.WEAPON_SHOP_NEXT_CHECK_FILE, next_check_time)
    global_vars._script_weapon_shop_cooldown_end_time = next_check_time
    print(f"Weapon Shop check completed. Next check scheduled for {global_vars._script_weapon_shop_cooldown_end_time.strftime('%Y-%m-%d %H:%M:%S')}.")

    # Return to the original page
    global_vars.driver.get(initial_url)
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)
    return True


def auto_buy_weapon(item_name: str):
    """
    Attempts to auto-buy the specified weapon if auto-buy is enabled and the weapon is whitelisted.
    """
    config = global_vars.config['Weapon Shop']
    auto_buy_enabled = config.getboolean('AutoBuyWS', fallback=False)
    allowed_weapons = [w.strip() for w in config.get('AutoBuyWeapons', fallback='').split(',')]

    if not auto_buy_enabled:
        print(f"[AutoBuy] Skipping {item_name} - AutoBuy is disabled.")
        return

    if item_name not in allowed_weapons:
        print(f"[AutoBuy] Skipping {item_name} - Not in allowed weapons list.")
        return

    print(f"[AutoBuy] Attempting to buy: {item_name}")
    weapon_radio_xpath = f"//input[@id='{item_name}']"
    purchase_button_xpath = "//input[@name='B1']"

    # Try to select the weapon radio button
    selected = _find_and_click(By.XPATH, weapon_radio_xpath)
    if not selected:
        print(f"[AutoBuy] Failed to select radio button for {item_name}")
        return

    # Try to click the purchase button
    purchased = _find_and_click(By.XPATH, purchase_button_xpath)
    if purchased:
        print(f"[AutoBuy] Purchase attempt submitted for {item_name}")
        send_discord_notification(f"Attempting to buy {item_name} from Weapon Shop!")
        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

        # Check for success message in div#success
        success_xpath = "//div[@id='success']"
        success_element = _find_element(By.XPATH, success_xpath)

        if success_element:
            print(f"[AutoBuy] SUCCESS: {item_name} purchase confirmed.")
            send_discord_notification(f"Successfully purchased {item_name} from Weapon Shop!")
        else:
            print(f"[AutoBuy] FAILED: No confirmation message found for {item_name}.")
            send_discord_notification(f"Attempted to purchase {item_name}, but failed. The item is gone, no available hands, or insufficient funds.")


def check_drug_store(initial_player_data):
    """
    Checks the Drug Store for stock of Pseudoephedrine and Medipack.
    Withdraws money and purchases if AutoBuy is enabled.
    Sends a Discord alert if stock is found and sets a cooldown if not.
    """
    print("\n--- Beginning Drug Store Operation ---")

    notify_stock = global_vars.config.getboolean('Drug Store', 'NotifyDSStock', fallback=True)

    # Cooldown Check
    if not hasattr(global_vars, '_script_drug_store_cooldown_end_time'):
        global_vars._script_drug_store_cooldown_end_time = datetime.datetime.min

    now = datetime.datetime.now()
    if now < global_vars._script_drug_store_cooldown_end_time:
        minutes_left = (global_vars._script_drug_store_cooldown_end_time - now).total_seconds() / 60
        print(f"Drug Store check on cooldown. Next check in {minutes_left:.2f} minutes.")
        return False

    # Navigation
    if not _navigate_to_page_via_menu(
        "//span[@class='city']",
        "//a[@class='business drug_store']",
        "Drug Store"
    ):
        print("FAILED: Could not navigate to Drug Store.")
        global_vars._script_drug_store_cooldown_end_time = now + datetime.timedelta(seconds=random.uniform(30, 90))
        return False

    print("Checking Drug Store for Pseudoephedrine and Medipack stock...")
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    # Extract stock and price for both items
    items_to_check = {
        "Pseudoephedrine": "//label[normalize-space()='Pseudoephedrine']/ancestor::tr",
        "Medipack": "//td[normalize-space()='Medipack']/parent::tr"
    }

    item_data = {}
    found_stock = False

    for name, row_xpath in items_to_check.items():
        row_element = _find_element(By.XPATH, row_xpath)
        if not row_element:
            print(f"{name} row not found on the page.")
            continue

        td_elements = row_element.find_elements(By.TAG_NAME, "td")
        if len(td_elements) < 4:
            print(f"Not enough columns in row for {name}.")
            continue

        price_str = td_elements[2].text.strip().replace("$", "").replace(",", "")
        stock_str = td_elements[3].text.strip()

        try:
            price = int(price_str)
            stock = int(stock_str)
            item_data[name] = {"price": price, "stock": stock}

            if stock > 0:
                print(f"DRUG STORE ALERT: {name} is in stock! Stock: {stock}")
                if notify_stock:
                    send_discord_notification(f"{name} is in stock! Stock: {stock}")
                found_stock = True
            else:
                print(f"{name} is out of stock.")
        except ValueError:
            print(f"Warning: Could not parse price or stock for {name}. Raw values: price='{price_str}', stock='{stock_str}'")

    # Attempt to buy, priortising Medipack over Pseudoephedrine
    for name in ["Medipack", "Pseudoephedrine"]:
        data = item_data.get(name)
        if not data or data["stock"] <= 0:
            continue

        clean_money_text = _get_element_text(By.XPATH, "//div[@id='nav_right']//form[contains(., '$')]")
        clean_money = int(''.join(filter(lambda c: c.isdigit(), clean_money_text))) if clean_money_text else 0
        price = data["price"]

        if clean_money < price:
            amount_needed = price - clean_money
            print(f"Not enough clean money to buy {name}. Withdrawing ${amount_needed:,}.")
            if withdraw_money(amount_needed):
                # Navigate back to Drug Store after withdrawal
                _navigate_to_page_via_menu(
                    "//span[@class='city']",
                    "//a[@class='business drug_store']",
                    "Drug Store"
                )
                time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        auto_buy_drug_store_item(name)

    if not found_stock:
        print("No stock found for Pseudoephedrine or Medipack.")
        global_vars._script_drug_store_cooldown_end_time = now + datetime.timedelta(minutes=random.uniform(5, 8))
    else:
        print("Stock was found, no cooldown set for Drug Store check.")

    print(f"Drug Store check complete.")
    return True

def auto_buy_drug_store_item(item_name: str):
    """
    Attempts to auto-buy the specified drug store item if AutoBuyDS is enabled in settings.ini.
    Sends Discord notification only if a success message is detected.
    """
    config = global_vars.config['Drug Store']
    auto_buy_enabled = config.getboolean('AutoBuyDS', fallback=False)

    if not auto_buy_enabled:
        print(f"[AutoBuy] Skipping {item_name} - AutoBuyDS is disabled in settings.ini.")
        return

    print(f"[AutoBuy] Attempting to buy: {item_name}")
    item_radio_xpath = f"//input[@id='{item_name}']"
    purchase_button_xpath = "//input[@name='B1']"
    success_message_xpath = "//div[@id='success' and (contains(text(), 'You keep') or contains(text(), 'something special'))]"

    # Try to select the radio button
    selected = _find_and_click(By.XPATH, item_radio_xpath)
    if not selected:
        print(f"[AutoBuy] Failed to select radio button for {item_name}")
        return

    # Try to click the purchase button
    purchased = _find_and_click(By.XPATH, purchase_button_xpath)
    send_discord_notification(f"Attempting to buy {item_name} from Drug Store.")
    if not purchased:
        print(f"[AutoBuy] Failed to click purchase button for {item_name}")
        return

    print(f"[AutoBuy] Clicked purchase button for {item_name}, waiting for success message...")
    time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

    # Look for the success message
    success_element = _find_element(By.XPATH, success_message_xpath)
    if success_element:
        success_text = success_element.text.strip()
        print(f"[AutoBuy] SUCCESS: {success_text}")
        send_discord_notification(f"Purchased {item_name} from Drug Store.")

        # Set a cooldown after a successful purchase.
        global_vars._script_drug_store_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
        print(f"[AutoBuy] Drug Store cooldown set until {global_vars._script_drug_store_cooldown_end_time}")
    else:
        print(f"[AutoBuy] WARNING: No success message found after purchasing {item_name}.")
        send_discord_notification(f"Failed to purchase {item_name} from Drug Store. The item is gone, or insufficient funds.")

def jail_work():
    """
    Executes jail earn jobs and gym workout, obeying earn/action timers.
    Picks the last available job (except 'makeshank', unless enabled in settings.ini).
    """
    print("\n--- Jail Detected: Executing Jail Work ---")

    # --- EARN JOB SELECTION ---
    if global_vars.jail_timers.get("earn_time_remaining", 999) <= 0:
        print("Earn timer ready. Attempting jail earn job.")

        if _find_and_click(By.XPATH, "//span[@class='income']"):
            try:
                # Check Settings.ini to determine if making a shank is enabled
                make_shank = global_vars.config.getboolean("Earns Settings", "MakeShank", fallback=False)
                dig_tunnel = global_vars.config.getboolean("Earns Settings", "DigTunnel", fallback=False)

                # Find all duties radio buttons
                all_jobs = global_vars.driver.find_elements(By.XPATH, "//input[@type='radio' and @name='job']")

                # Filter the duties into a list, excluding makeshank and digtunnel unless enabled
                valid_jobs = [
                    job for job in all_jobs
                    if (job.get_attribute("id") != "makeshank" or make_shank) and
                       (job.get_attribute("id") != "digtunnel" or dig_tunnel)
                ]

                if valid_jobs:
                    # Select the last valid duty
                    last_job = valid_jobs[-1]
                    job_id = last_job.get_attribute("id")
                    print(f"Selecting job: {job_id}")
                    last_job.click()

                    # Click submit
                    if _find_and_click(By.XPATH, "//input[@name='B1']"):
                        print(f"Successfully completed jail job: {job_id}")
                    else:
                        print("FAILED: Couldn't click 'Work' button.")
                else:
                    print("No valid jobs found (MakeShank disabled?).")
            except Exception as e:
                print(f"ERROR: Exception while processing earn jobs: {e}")
        else:
            print("FAILED: Couldn't open Earn (income) tab.")
    else:
        print(f"Earn timer not ready ({global_vars.jail_timers['earn_time_remaining']:.1f} sec left)")

    # --- GYM WORKOUT (action timer) ---
    if global_vars.jail_timers.get("action_time_remaining", 999) <= 0:
        print("Action timer ready. Attempting Gym Workout.")
        if _find_and_click(By.XPATH, "//span[@class='family']"):
            if _find_and_click(By.XPATH, "//input[@id='gym']"):
                if _find_and_click(By.XPATH, "//input[@name='B1']"):
                    print("Successfully completed Gym Workout.")
                else:
                    print("FAILED: Couldn't click 'Submit' button.")
            else:
                print("FAILED: Couldn't click 'Gym' radio.")
    else:
        print(f"Action timer not ready ({global_vars.jail_timers['action_time_remaining']:.1f} sec left)")




