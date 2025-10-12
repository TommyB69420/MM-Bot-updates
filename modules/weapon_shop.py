import datetime
import random
import time

from selenium.common import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from database_functions import _set_last_timestamp
from global_vars import cfg_int, cfg_bool, cfg_list
from helper_functions import _navigate_to_page_via_menu, _get_element_text, _find_and_click, _find_element
from modules.money_handling import withdraw_money

def check_weapon_shop(initial_player_data):
    """
    Checks the weapons shop for stock, message discord with results,
    Withdraws money if required and automatically buy top weapons if enabled in settings.ini.
    """
    print("\n--- Beginning Weapon Shop Operation ---")

    # The main loop has already determined this timer is ready, so no need to check again
    print("Timer was marked ready by main loop. Proceeding with Weapon Shop check.")

    # Read settings
    min_check        = cfg_int ('Weapon Shop', 'MinWSCheck', 13)
    max_check        = cfg_int ('Weapon Shop', 'MaxWSCheck', 18)
    notify_stock     = cfg_bool('Weapon Shop', 'NotifyWSStock', True)
    auto_buy_enabled = cfg_bool('Weapon Shop', 'AutoBuyWS', False)
    priority_weapons = [w.strip() for w in cfg_list('Weapon Shop', 'AutoBuyWeapons')]


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
                    withdraw_money(amount_needed)

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
    return True

def auto_buy_weapon(item_name: str):
    """
    Attempts to auto-buy the specified weapon if auto-buy is enabled and the weapon is whitelisted.
    """
    auto_buy_enabled = cfg_bool('Weapon Shop', 'AutoBuyWS', False)
    allowed_weapons  = [w.strip() for w in cfg_list('Weapon Shop', 'AutoBuyWeapons')]

    if not auto_buy_enabled:
        print(f"[AutoBuy] Skipping {item_name} - AutoBuy is disabled.")
        return

    if item_name not in allowed_weapons:
        print(f"[AutoBuy] Skipping {item_name} - Not in allowed weapons list.")
        return

    print(f"[AutoBuy] Attempting to buy: {item_name}")
    weapon_radio_xpath   = f"//input[@id='{item_name}']"
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
        time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

        # Check for success message in div#success
        success_xpath = "//div[@id='success']"
        success_element = _find_element(By.XPATH, success_xpath)

        if success_element:
            print(f"[AutoBuy] SUCCESS: {item_name} purchase confirmed.")
            send_discord_notification(f"Successfully purchased {item_name} from Weapon Shop!")
        else:
            print(f"[AutoBuy] FAILED: No confirmation message found for {item_name}.")
            send_discord_notification(
                f"Attempted to purchase {item_name}, but failed. The item is gone, no available hands, or insufficient funds."
            )