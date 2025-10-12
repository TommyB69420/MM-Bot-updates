import time

from selenium.webdriver.common.by import By
import global_vars
from comms_journals import _clean_amount
from helper_functions import _find_and_click, _find_element, _navigate_to_page_via_menu, _find_and_send_keys, _get_current_url
from global_vars import cfg_int

def clean_money_on_hand_logic(initial_player_data):
    """
    Manages clean money: deposits excess using quick deposit and withdraws desired amount from bank.
    Returns True if an action was performed, False otherwise.
    """
    action_performed = False
    clean_money = initial_player_data.get("Clean Money", 0)

    excess_money_on_hand_limit = cfg_int('Misc', 'ExcessMoneyOnHand', 100000)
    desired_money_on_hand      = cfg_int('Misc', 'MoneyOnHand', 50000)


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

def withdraw_money(amount: int):
    """
    Withdraws the specified amount of money from the bank.
    Returns True if the withdrawal was successful, False otherwise.
    """
    print(f"Attempting to withdraw ${amount:,} from the bank.")
    initial_url = _get_current_url()

    try:
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

    finally:
        # Safely return to the previous page
        try:
            if initial_url:
                global_vars.driver.get(initial_url)
                time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception:
            print("WARNING: Could not return to previous page after withdrawal.")

def transfer_money(amount, recipient):
    """
    Transfers a specified amount of money to another player.

    Args:
        amount (int or float): The amount of money to transfer.
        recipient (str): The exact name of the player receiving the money.

    Returns:
        bool: True if the transfer was successful, False otherwise.
    """
    print(f"\n--- Initiating Money Transfer: ${amount} to {recipient} ---")
    initial_url = _get_current_url()

    try:
        # Navigate to Bank via Income menu
        if not _navigate_to_page_via_menu("//span[@class='income']", "//td[@class='toolitem']//a[normalize-space()='Bank']", "Bank"):
            print("FAILED: Navigation to Bank failed.")
            return False

        # Go to Transfers page
        if not _find_and_click(By.XPATH, "//a[normalize-space()='Transfers']", pause=global_vars.ACTION_PAUSE_SECONDS):
            print("FAILED: Could not click Transfers link.")
            return False

        # Fill out the transfer page
        if not _find_and_send_keys(By.XPATH, "//input[@name='transferamount']", str(amount)):
            print("FAILED: Could not enter transfer amount.")
            return False

        if not _find_and_send_keys(By.XPATH, "//input[@name='transfername']", recipient):
            print("FAILED: Could not enter recipient name.")
            return False

        # Submit the transfer
        if not _find_and_click(By.XPATH, "//input[@id='B1']", pause=global_vars.ACTION_PAUSE_SECONDS):
            print("FAILED: Could not click Submit button.")
            return False

        # Verify transfer success
        success_message = _find_element(By.XPATH, "//div[@id='success']", timeout=3, suppress_logging=True)
        if success_message:
            print(f"SUCCESS: Transferred ${amount} to {recipient} successfully.")
            return True
        else:
            print("WARNING: Transfer may have failed (no success message detected).")
            return False

    except Exception as e:
        print(f"ERROR during money transfer: {e}")
        return False

    finally:
        # Safely return to the previous page
        try:
            if initial_url:
                global_vars.driver.get(initial_url)
                time.sleep(global_vars.ACTION_PAUSE_SECONDS)
        except Exception:
            print("WARNING: Could not return to previous page after transfer.")

def execute_sendmoney_to_player(target_player: str, amount_str: str) -> bool:
    try:
        target_player = (target_player or "").strip()
        amt = _clean_amount(amount_str)

        if not target_player:
            print("Incorrect player name for transfer")
            return False
        if amt is None:
            print("You have insufficient funds")  # or "Invalid amount"; using provided phrasing constraints
            return False

        # Navigate to Bank
        if not _navigate_to_page_via_menu(
                "//span[@class='income']",
                "//a[normalize-space()='Bank']",
                "Bank"):
            print("FAILED: Could not open Bank.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        # Click Transfers tab
        if not _find_and_click(By.XPATH, "//a[normalize-space()='Transfers']", pause=global_vars.ACTION_PAUSE_SECONDS):
            print("FAILED: Could not open Bank Transfers.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS / 2)

        # Fill amount and player
        amount_xpath = "//input[@name='transferamount']"
        name_xpath = "//input[@name='transfername']"
        transfer_btn_xpath = "//input[@id='B1']"

        amount_el = _find_element(By.XPATH, amount_xpath, timeout=5)
        name_el = _find_element(By.XPATH, name_xpath, timeout=5)
        if not amount_el or not name_el:
            print("FAILED: Transfer inputs not found.")
            return False

        # Clear and send keys to amount text box
        if not _find_and_send_keys(By.XPATH, amount_xpath, str(amt)):
            print("FAILED: Could not enter transfer amount.")
            return False

        if not _find_and_send_keys(By.XPATH, name_xpath, target_player):
            print("FAILED: Could not enter recipient name.")
            return False

        # Click Transfer
        if not _find_and_click(By.XPATH, transfer_btn_xpath):
            print("FAILED: Could not click Transfer.")
            return False

        time.sleep(global_vars.ACTION_PAUSE_SECONDS)

        # Fail checks on the result page
        src = (global_vars.driver.page_source or "")

        if "You have entered an incorrect name!" in src:
            print("Incorrect player name for transfer")
            return False

        if "You have insufficient funds to complete this transfer!" in src:
            print("You have insufficient funds")
            return False

        # If we reach here, assume success (no explicit success text provided)
        print(f"Transfer completed: ${amt:,} to '{target_player}'.")
        return True

    except Exception as e:
        print(f"ERROR during sendmoney flow: {e}")
        return False
