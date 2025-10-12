import datetime
import random

from selenium.webdriver.common.by import By

import global_vars
from database_functions import get_all_degrees_status, set_all_degrees_status
from helper_functions import _navigate_to_page_via_menu, _find_element, _get_element_text, _get_dropdown_options, _select_dropdown_option, _find_and_click
from modules.money_handling import withdraw_money

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
            "University"):
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
                print(f"Starting a new degree ('{degree}') — withdrawing $10,000 first.")
                if not withdraw_money(10000):
                    print("FAILED: Could not withdraw $10,000 for new degree.")
                    return False
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