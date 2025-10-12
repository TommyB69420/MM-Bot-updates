from selenium.webdriver.common.by import By

import global_vars
from helper_functions import _find_and_click

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
                make_shank = global_vars.cfg_bool('EarnsSettings', 'MakeShank', False)
                dig_tunnel = global_vars.cfg_bool('EarnsSettings', 'DigTunnel', False)


                # Find all duties radio buttons
                all_jobs = global_vars.driver.find_elements(By.XPATH, "//input[@type='radio' and @name='job']")

                # Filter the duties into a list, excluding makeshank and dig tunnel unless enabled. Jailappeal will always be off
                valid_jobs = [
                    job for job in all_jobs
                    if job.get_attribute("id") not in {"makeshank", "digtunnel", "jailappeal"}
                       or (job.get_attribute("id") == "makeshank" and make_shank)
                       or (job.get_attribute("id") == "digtunnel" and dig_tunnel)
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