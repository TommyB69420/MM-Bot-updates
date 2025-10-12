import datetime, time, random

from selenium.webdriver.common.by import By

import global_vars
from comms_journals import send_discord_notification
from database_functions import _set_last_timestamp
from global_vars import cfg_int, cfg_bool, cfg_list
from helper_functions import _navigate_to_page_via_menu, _get_element_text, _find_and_click, _find_element
from modules.money_handling import withdraw_money

def check_bionics_shop(initial_player_data):
    """
    Checks the Bionics Shop for stock, notifies Discord if enabled,
    and attempts auto-buy if enabled and affordable.
    """

    print("\n--- Beginning Bionics Shop Operation ---")

    # Settings (Dynamo-backed)
    min_check        = cfg_int ('Bionics Shop', 'MinBiosCheck', 11)
    max_check        = cfg_int ('Bionics Shop', 'MaxBiosCheck', 13)
    notify_stock     = cfg_bool('Bionics Shop', 'NotifyBSStock', True)
    auto_buy_enabled = cfg_bool('Bionics Shop', 'DoAutoBuyBios', False)
    priority_bionics = [b.strip() for b in cfg_list('Bionics Shop', 'AutoBuyBios')]

    # sanity guard
    if min_check > max_check:
        min_check, max_check = max_check, min_check

    # Navigation
    if not _navigate_to_page_via_menu("//span[@class='city']",
                                      "//a[@class='business bionics']",
                                      "Bionics Shop"):
        print("FAILED: Could not navigate to Bionics Shop.")
        next_check = datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(30, 90))
        _set_last_timestamp(global_vars.BIONICS_SHOP_NEXT_CHECK_FILE, next_check)
        return False

    print("Checking Bionics Shop for available stock...")
    time.sleep(global_vars.ACTION_PAUSE_SECONDS)

    found_bionics_in_stock = False
    bionic_data = {}

    try:
        rows = global_vars.driver.find_elements(By.XPATH, "//table//tr[td/input[@type='radio']]")
        for row in rows:
            try:
                radio = row.find_element(By.XPATH, ".//input[@type='radio']")
                radio_id = radio.get_attribute("value")
                name = row.find_element(By.TAG_NAME, "label").text.strip().split("\n")[0]
                print(f"[DEBUG] Parsed: {name} | Value: {radio.get_attribute('value')} | ID: {radio.get_attribute('id')}")
                price = int(row.find_elements(By.TAG_NAME, "td")[2].text.strip().replace("$", "").replace(",", ""))
                stock = int(row.find_elements(By.TAG_NAME, "td")[3].text.strip())
            except Exception as e:
                print(f"Skipping row due to parse error: {e}")
                continue

            if stock > 0:
                found_bionics_in_stock = True
                print(f"{name} is in stock! Stock: {stock}")
                if notify_stock and name in priority_bionics:
                    send_discord_notification(f"@here {name} is in stock! Stock: {stock}")
                bionic_data[name] = {"stock": stock, "price": price, "id": radio_id}
            else:
                print(f"{name} is out of stock.")

        if found_bionics_in_stock and auto_buy_enabled:
            for bionic in priority_bionics:
                data = bionic_data.get(bionic)
                if not data or data["stock"] <= 0:
                    continue

                price = data["price"]
                clean_money_text = _get_element_text(By.XPATH, "//div[@id='nav_right']//form[contains(., '$')]")
                clean_money = int(''.join(filter(str.isdigit, clean_money_text))) if clean_money_text else 0

                if clean_money < price:
                    amount_needed = price - clean_money
                    print(f"Not enough clean money to buy {bionic}. Withdrawing ${amount_needed:,}.")
                    withdraw_money(amount_needed)

                auto_buy_bionic(bionic, data["id"])
                break

        if not found_bionics_in_stock:
            print("No bionics found in stock.")

    except Exception as e:
        print(f"Error during Bionics Shop check: {e}")
        send_discord_notification(f"Error: Failed during Bionics Shop check. At max views {e}")
        next_check = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(10, 13))
        _set_last_timestamp(global_vars.BIONICS_SHOP_NEXT_CHECK_FILE, next_check)
        return False

    next_check = datetime.datetime.now() + datetime.timedelta(minutes=random.uniform(min_check, max_check))
    _set_last_timestamp(global_vars.BIONICS_SHOP_NEXT_CHECK_FILE, next_check)
    print(f"Bionics Shop check complete. Next check at {next_check.strftime('%Y-%m-%d %H:%M:%S')}.")
    return True

def auto_buy_bionic(item_name: str, item_id: str):
    """
    Attempts to buy a bionic if it's allowed by settings.
    """
    auto_buy_enabled = cfg_bool('Bionics Shop', 'DoAutoBuyBios', False)
    allowed_items    = [b.strip() for b in cfg_list('Bionics Shop', 'AutoBuyBios')]

    if not auto_buy_enabled:
        print(f"[AutoBuy] Skipping {item_name} - AutoBuy is disabled in settings.")
        return

    if item_name not in allowed_items:
        print(f"[AutoBuy] Skipping {item_name} - Not in allowed list.")
        return

    print(f"[AutoBuy] Attempting to buy: {item_name}")
    radio_xpath     = f"//input[@type='radio' and @value='{item_id}']"
    purchase_xpath  = "//input[@name='B1']"

    if not _find_and_click(By.XPATH, radio_xpath):
        print(f"[AutoBuy] Failed to select {item_name}. XPath attempted: {radio_xpath}")
        return

    if not _find_and_click(By.XPATH, purchase_xpath):
        print(f"[AutoBuy] Failed to click purchase for {item_name}.")
        return

    time.sleep(global_vars.ACTION_PAUSE_SECONDS * 2)

    success = _find_element(By.XPATH, "//div[@id='success']")
    if success:
        print(f"[AutoBuy] SUCCESS: Purchased {item_name}.")
        send_discord_notification(f"Successfully bought {item_name} from Bionics Shop!")
    else:
        print(f"[AutoBuy] FAILED: No confirmation for {item_name}.")
        send_discord_notification(
            f"Failed to purchase {item_name}. It might be gone, you may not have free hands, or funds were insufficient."
        )