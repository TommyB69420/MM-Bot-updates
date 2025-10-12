import datetime
import random
import time

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from global_vars import cfg_bool
from helper_functions import _navigate_to_page_via_menu, _find_element, _get_element_text, _find_and_click
from modules.money_handling import withdraw_money

def check_drug_store(initial_player_data):
    """
    Checks the Drug Store for stock of Pseudoephedrine and Medipack.
    Withdraws money and purchases if AutoBuy is enabled.
    Sends a Discord alert if stock is found and sets a cooldown if not.
    """
    print("\n--- Beginning Drug Store Operation ---")

    notify_stock = cfg_bool('Drug Store', 'NotifyDSStock', True)

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
            withdraw_money(amount_needed)

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
    Attempts to auto-buy the specified drug store item if AutoBuyDS is enabled in settings.
    Sends a Discord notification only if a success message is detected.
    """
    # Toggle from Dynamo-backed settings
    auto_buy_enabled = cfg_bool('Drug Store', 'AutoBuyDS', False)

    if not auto_buy_enabled:
        print(f"[AutoBuy] Skipping {item_name} - AutoBuyDS is disabled in settings.")
        return

    print(f"[AutoBuy] Attempting to buy: {item_name}")
    item_radio_xpath      = f"//input[@id='{item_name}']"
    purchase_button_xpath = "//input[@name='B1']"
    success_message_xpath = "//div[@id='success']"

    # Try to select the radio button
    selected = _find_and_click(By.XPATH, item_radio_xpath)
    if not selected:
        print(f"[AutoBuy] Failed to select radio button for {item_name}")
        return

    # Try to click the purchase button
    purchased = _find_and_click(By.XPATH, purchase_button_xpath)
    if not purchased:
        print(f"[AutoBuy] Failed to click purchase button for {item_name}")
        return

    print(f"[AutoBuy] Clicked purchase button for {item_name}, waiting for success message...")
    time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

    # Look for the success message
    success_element = _find_element(By.XPATH, success_message_xpath)
    if success_element:
        success_text = (success_element.text or "").strip()
        print(f"[AutoBuy] SUCCESS: {success_text}")
        send_discord_notification(f"Purchased {item_name} from Drug Store.")

        # Set a cooldown after a successful purchase.
        global_vars._script_drug_store_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
        print(f"[AutoBuy] Drug Store cooldown set until {global_vars._script_drug_store_cooldown_end_time}")
    else:
        print(f"[AutoBuy] WARNING: No success message found after purchasing {item_name}.")
        global_vars._script_drug_store_cooldown_end_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
        send_discord_notification(f"Failed to purchase {item_name} from Drug Store. The item is gone, or insufficient funds.")