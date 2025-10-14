import datetime
import random
import os, platform
import shutil
import requests
import configparser
import subprocess
import boto3
import time
import threading
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

# The supervisor sets this env var with the full item (includes Settings, Rev, etc.)
_REMOTE_SETTINGS_RAW = os.getenv("REMOTE_SETTINGS_JSON", "")

# Public globals you can inspect/log
SET: dict = {}           # The actual settings payload (dict of sections)
SET_REV: int = 0         # Monotonic revision from DynamoDB
SET_UPDATED_AT: str|None = None
SET_USER_ID: str|None = os.getenv("BOT_USER_ID") or os.getenv("USER_ID")

# Map old INI-style section names to new JSON keys
_SECTION_ALIASES = {
    "Login Credentials": "LoginCredentials",
    "Discord Webhooks":  "DiscordWebhooks",
    "Earns Settings":    "EarnsSettings",
    "Actions Settings":  "ActionsSettings",
    "Journal Settings":  "JournalSettings",
}

def _norm_section(name: str) -> str:
    return _SECTION_ALIASES.get(name, name)

def _load_remote_settings_from_env():
    """Populate SET/SET_REV/SET_UPDATED_AT from REMOTE_SETTINGS_JSON."""
    global SET, SET_REV, SET_UPDATED_AT
    if not _REMOTE_SETTINGS_RAW:
        SET, SET_REV, SET_UPDATED_AT = {}, 0, None
        print("[cfg] REMOTE_SETTINGS_JSON missing; using empty settings.")
        return
    try:
        data = json.loads(_REMOTE_SETTINGS_RAW)
        if isinstance(data, dict) and "Settings" in data:
            SET = data.get("Settings") or {}
            SET_REV = int(data.get("Rev") or 0)
            SET_UPDATED_AT = data.get("UpdatedAt")
        else:
            # allow passing just the Settings dict
            SET = data if isinstance(data, dict) else {}
            SET_REV = 0
            SET_UPDATED_AT = None
        if not isinstance(SET, dict):
            SET = {}
        print(f"[cfg] Loaded settings: sections={list(SET.keys())} rev={SET_REV}")
    except Exception as e:
        print(f"[cfg] Failed to parse REMOTE_SETTINGS_JSON: {e}")
        SET, SET_REV, SET_UPDATED_AT = {}, 0, None

_load_remote_settings_from_env()

# --- Nested lookups (e.g., Judge -> Fines -> <crime>) ---

def cfg_subdict(section: str, field: str) -> dict:
    """Return a dict from a nested field (case-insensitive)."""
    s = _section_dict(section) or {}
    if isinstance(s.get(field), dict):
        return s[field]
    # case-insensitive fallback
    for k, v in s.items():
        if isinstance(k, str) and k.lower() == field.lower() and isinstance(v, dict):
            return v
    return {}

def cfg_int_nested(section: str, nested_field: str, key: str, default: int = 0) -> int:
    """
    Try int at section[key]; if missing, try section[nested_field][key] (both case-insensitive).
    """
    # 1) direct (top-level in section)
    v = cfg_int(section, key, None)  # returns None if missing
    if v is not None:
        return v

    # 2) nested dict
    sub = cfg_subdict(section, nested_field)
    # exact key
    if key in sub:
        try:
            return int(str(sub[key]).replace(",", "").strip())
        except Exception:
            return default
    # case-insensitive match
    for k, val in sub.items():
        if isinstance(k, str) and k.lower() == key.lower():
            try:
                return int(str(val).replace(",", "").strip())
            except Exception:
                return default
    return default

def _section_dict(section: str) -> dict|None:
    """Return the section dict if present, trying alias names too."""
    s = SET.get(section)
    if isinstance(s, dict):
        return s
    s = SET.get(_norm_section(section))
    return s if isinstance(s, dict) else None

# ---------------- value accessors ----------------

def cfg_get(section: str, key: str, default=None):
    s = _section_dict(section)
    if not s:
        return default
    # exact key first
    if key in s:
        v = s[key]
    else:
        # case-insensitive fallback
        v = next((s[k] for k in s.keys() if isinstance(k, str) and k.lower()==key.lower()), default)
    # Normalize empty string to default (optional; keeps old INI semantics)
    if v == "" or v is None:
        return default
    return v

def cfg_bool(section: str, key: str, default: bool=False) -> bool:
    v = cfg_get(section, key, None)
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in {"1","true","t","yes","y","on"}:  return True
    if s in {"0","false","f","no","n","off"}: return False
    return default

def cfg_int(section: str, key: str, default: int=0) -> int:
    v = cfg_get(section, key, None)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if v is None:
        return default
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return default

def cfg_float(section: str, key: str, default: float=0.0) -> float:
    v = cfg_get(section, key, None)
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return default
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default

def cfg_list(section: str, key: str) -> list:
    """Return a list; supports JSON arrays or CSV strings."""
    v = cfg_get(section, key, None)
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if x not in ("", None)]
    s = str(v).strip()
    # JSON array support
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            return [x for x in arr if x not in ("", None)] if isinstance(arr, list) else [s]
        except Exception:
            pass
    # CSV fallback
    return [p.strip() for p in s.split(",") if p.strip()]

# -------- OPTIONAL: SectionProxy if some code still uses INI-like access -----
class SectionProxy:
    def __init__(self, section: str):
        self._section = section
        self._data = _section_dict(section) or {}
    def get(self, k: str, fallback=None):
        return cfg_get(self._section, k, fallback)
    def getboolean(self, k: str, fallback: bool=False) -> bool:
        return cfg_bool(self._section, k, fallback)
    def getint(self, k: str, fallback: int=0) -> int:
        return cfg_int(self._section, k, fallback)
    def getlist(self, k: str) -> list:
        return cfg_list(self._section, k)
    def __contains__(self, k: str) -> bool:
        return k in self._data

def cfg_section(section: str) -> SectionProxy|None:
    return SectionProxy(section) if _section_dict(section) else None

# --- Load Settings from Settings.ini ---
config = configparser.ConfigParser()
try:
    config.read('settings.ini')
    print("Settings loaded successfully from Settings.ini")
except Exception as e:
    print(f"Error loading settings from Settings.ini: {e}")
    exit()

# --- Connect to Chrome Window ---
chrome_path = cfg_get('Auth', 'ChromePath') or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
user_data_dir = r"C:\Temp\MMBotProfile"
debug_url = "http://127.0.0.1:9222/json/version"

# Utility: Check if Chrome debugger is already running
def is_debugger_running():
    try:
        res = requests.get(debug_url, timeout=2)
        return res.ok
    except Exception:
        return False

# Utility: Check if profile folder is corrupted
def is_profile_corrupted(path):
    try:
        test_file = os.path.join(path, "test.txt")
        os.makedirs(path, exist_ok=True)
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return False
    except Exception:
        return True

# Handle corrupted profile recovery
if is_profile_corrupted(user_data_dir):
    print(f"Profile folder appears corrupted. Resetting: {user_data_dir}")
    try:
        shutil.rmtree(user_data_dir, ignore_errors=True)
        os.makedirs(user_data_dir, exist_ok=True)
    except Exception as e:
        print(f"Failed to reset corrupted profile: {e}")
        exit()

# Start Chrome if it's not already running
if not is_debugger_running():
    print("Chrome not running. Launching it...")
    try:
        subprocess.Popen([
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            #"--disable-blink-features=AutomationControlled"
        ])
    except Exception as e:
        print(f"Failed to launch Chrome: {e}")
        exit()

    # Wait until debugger is available
    for _ in range(10):
        if is_debugger_running():
            print("Chrome debugger is now up.")
            break
        time.sleep(1)
    else:
        print("Chrome debugger not reachable after 10 seconds. Exiting.")
        exit()
else:
    print("Chrome debugger already running. Reusing open window.")

# Connect to Chrome via Selenium
chrome_options = Options()
chrome_options.debugger_address = "127.0.0.1:9222"

try:
    driver = webdriver.Chrome(options=chrome_options)
    current_url = driver.current_url.lower()
    if not current_url.startswith("https://mafiamatrix.net"):
        driver.get("https://mafiamatrix.net/default.asp")
        print("Navigated to https://mafiamatrix.net/default.asp")
    else:
        print(f"Already on MafiaMatrix: {current_url}")
        driver.refresh()
        time.sleep(2)
except Exception as e:
    print(f"Failed to connect to Chrome debugger instance: {e}")
    exit()

# --- Global Configurations ---
EXPLICIT_WAIT_SECONDS = random.uniform(2, 3) # This is a wait for specific elements to appear, preventing TimeoutException when elements load dynamically.
ACTION_PAUSE_SECONDS = random.uniform(0.3, 0.4) # This is an unconditional sleep between actions, primarily for pacing and simulating human interaction.
wait = WebDriverWait(driver, EXPLICIT_WAIT_SECONDS)
MIN_POLLING_INTERVAL_LOWER = 30
MIN_POLLING_INTERVAL_UPPER = 35
startup_login_ping_sent = False # One time Discord ping on startup (guard)

# --- Script Version ---
SCRIPT_VERSION = "15/10/2025"

# Directory for game data and logs
COOLDOWN_DATA_DIR = 'game_data'
AGGRAVATED_CRIMES_LOG_FILE = os.path.join(COOLDOWN_DATA_DIR, 'aggravated_crimes_log.txt')
AGGRAVATED_CRIME_LAST_ACTION_FILE = os.path.join(COOLDOWN_DATA_DIR, 'aggravated_crimes_last_action.txt')
ALL_DEGREES_FILE = os.path.join(COOLDOWN_DATA_DIR, 'all_degrees.json')
WEAPON_SHOP_NEXT_CHECK_FILE = os.path.join(COOLDOWN_DATA_DIR, "weapon_shop_next_check.txt")
GYM_TRAINING_FILE = os.path.join("game_data", "gym_timer.txt")
BIONICS_SHOP_NEXT_CHECK_FILE = os.path.join(COOLDOWN_DATA_DIR, "bionics_shop_next_check.txt")
POLICE_911_NEXT_POST_FILE = os.path.join(COOLDOWN_DATA_DIR, "police_911_next_post.txt")
PENDING_FORENSICS_FILE = os.path.join(COOLDOWN_DATA_DIR, "pending_forensics.json")
FORENSICS_TRAINING_DONE_FILE = os.path.join(COOLDOWN_DATA_DIR, "forensics_training_done.json")
POLICE_TRAINING_DONE_FILE = os.path.join(COOLDOWN_DATA_DIR, "police_training_done.json")
COMBAT_TRAINING_DONE = os.path.join(COOLDOWN_DATA_DIR, "combat_training_completed.json")
CUSTOMS_TRAINING_DONE_FILE = os.path.join(COOLDOWN_DATA_DIR, "customs_training_done.json")
FIRE_TRAINING_DONE_FILE = os.path.join(COOLDOWN_DATA_DIR, "fire_training_done.json")
BLIND_EYE_QUEUE_FILE = os.path.join(COOLDOWN_DATA_DIR, "blind_eye_queue.json")
COMMUNITY_SERVICE_QUEUE_FILE = os.path.join(COOLDOWN_DATA_DIR, "community_service_queue.json")
DRUGS_LAST_CONSUMED_FILE =  os.path.join(COOLDOWN_DATA_DIR, "drugs_last_consumed.txt")
FUNERAL_SMUGGLE_QUEUE_FILE = os.path.join(COOLDOWN_DATA_DIR, "funeral_smuggle_queue.json")
CASINO_NEXT_CHECK_FILE = os.path.join(COOLDOWN_DATA_DIR, "casino_next_check.txt")
SEX_CHANGE_NEXT_CHECK_FILE = os.path.join(COOLDOWN_DATA_DIR, "sex_change_next_check.txt")

# Define keys for database (aggravated_crime_cooldowns.json) entries
MINOR_CRIME_COOLDOWN_KEY = 'minor_crime_cooldown'
MAJOR_CRIME_COOLDOWN_KEY = 'major_crime_cooldown'
PLAYER_HOME_CITY_KEY = 'home_city'
LAST_KNOWN_CITY = ""

# Global variables for script's internal cooldowns
# Game timers
_script_earn_cooldown_end_time = datetime.datetime.now()
_script_action_cooldown_end_time = datetime.datetime.now()
_script_launder_cooldown_end_time = datetime.datetime.now()
_script_case_cooldown_end_time = datetime.datetime.now()
_script_trafficking_cooldown_end_time = datetime.datetime.now()
_script_event_cooldown_end_time = datetime.datetime.now()
_script_skill_cooldown_end_time = datetime.datetime.now()
# Career-specific timers
_script_bank_add_clients_cooldown_end_time = datetime.datetime.now()
_script_post_911_cooldown_end_time = datetime.datetime.min
_cases_pending_forensics = set()
# Aggravated crime timers
_script_armed_robbery_recheck_cooldown_end_time = datetime.datetime.now()
_script_torch_recheck_cooldown_end_time = datetime.datetime.now()
_script_aggravated_crime_recheck_cooldown_end_time = None
# Misc timers
_script_gym_train_cooldown_end_time = datetime.datetime.now()
_script_bionics_shop_cooldown_end_time = datetime.datetime.now()
_script_weapon_shop_cooldown_end_time = datetime.datetime.now()
_script_drug_store_cooldown_end_time = datetime.datetime.now()
_script_promo_check_cooldown_end_time = datetime.datetime.now()
_script_consume_drugs_cooldown_end_time = datetime.datetime.now()
_script_casino_slots_cooldown_end_time = datetime.datetime.now()
jail_timers = {}

# Global variable to store the last known unread message and journal count
_last_unread_message_count = 0
_last_unread_journal_count = 0

# Global variable to store the initial URL. This will be replaced once the driver is established in Main.py
initial_game_url = None

# Global Variable to store if the script needs to reselect an earn after taking a promotion.
force_reselect_earn = False

# Promo "unable to take promo" Discord rate-limit (runtime memory only)
_promo_unable_notify_count = 0
_promo_unable_last_name = None

# Global Variable that tells Main.py to pause while Discord uses Selenium
DRIVER_LOCK = threading.RLock()

# Discord-triggered smuggle state
_smuggle_request_active = threading.Event()     # Set by Discord; consumed by Main loop
_smuggle_request_target = None                  # String: player name requested from Discord

# Global variables to store hacked player and amount for repayment
hacked_player_for_repay = None
hacked_amount_for_repay = None
hacked_successful = False

# Global variables to store BnE players and amount for repayment
bne_player_for_repay = None
bne_amount_for_repay = None
bne_successful = False

# Global variables to store pickpocketed player and amount for repayment
pickpocketed_player_for_repay = None
pickpocketed_amount_for_repay = None
pickpocket_successful = False

# Global variables to store mugging player and amount for repayment
mugging_player_for_repay = None
mugging_amount_for_repay = None
mugging_successful = False

# Global variables for Armed Robbery repayment
armed_robbery_amount_for_repay = None
armed_robbery_business_name_for_repay = None
armed_robbery_successful = False

# Global variables for Torch repayment
torch_amount_for_repay = None
torch_business_name_for_repay = None
torch_successful = False

# Global lists for businesses for repayment logic
public_businesses = [
    "Bank Tills", "Hospital", "Fire Station", "Town Hall", "Airport", "Construction Company",
]

private_businesses = {
    "Auckland": ["Bar", "Underground Auction", "Weapon Shop", "Dog Fights", "Eden Park", "Drug Store", "Tattoo Parlour"],
    "Beirut": ["Bar", "Clothing Shop", "Hotel", "Horse Racing", "Casino", "Dog Pound", "Vehicle Yard"],
    "Chicago": ["Bar", "Brothel", "Boxing", "Bionics", "Dog Pound", "Gym", "Parking Lot", "Funeral Parlour"]
}

PUBLIC_BUSINESS_OCCUPATION_MAP = {
    "funeral parlour": "Funeral Director",
    "banks tills": "Bank Manager",
    "hospital": "Hospital Director",
    "fire station": "Fire Chief",
    "town hall": "Mayor",
    "airport": "Commissioner-General",
    "construction company": "Chief Engineer"
}

# Auto-Promotion Map
PROMO_MAP = {
    # Hospital
    "nurse": "one",
    "doctor": "two",
    "surgeon": "two",
    "hospital director": "one",
    "hosptal director": "one",

    # Bank
    "bank teller": "one",
    "loan officer": "two",
    "bank manager": "one",

    # Engineering
    "mechanic": "two",
    "technician": "one",
    "engineer": "one",
    "chief engineer": "two",

    # Funeral
    "mortician assistant": "one",
    "mortician": "one",
    "undertaker": "two",
    "funeral director": "one",

    # Fire
    "fire fighter": "one",
    "fire chief": "one",

    # Customs
    "inspector": "two",
    "supervisor": "one",
    "superintendent": "one",
    "commissioner-general": "two",
    "commissioner general": "two",

    # Law (manual for judge/SCJ)
    "legal secretary": "one",
    "lawyer": "one",

    # Gangster (manual for Gio/Godfather/Capi)
    "dealer": "two",
    "enforcer": "one",
    "piciotto": "two",
    "sgarrista": "one",
    "capodecima": "one",
    "caporegime": "one",
    "boss": "two",
    "don": "one",

    # Police (manual for commissioner)
    "sergeant": "two",
    "senior sergeant": "two",
    "detective": "one",

    # Crossroads - always pick career
    "Career Crossroad": "one"
}

# Cities / travel canonicalization (left = inputs we accept; right = canonical name used by MM URLs/UI)
CITY_ALIASES = {
    "auckland": "Auckland",
    "ak": "Auckland",
    "chicago": "Chicago",
    "cago": "Chicago",
    "beirut": "Beirut",
    "rut": "Beirut",
}

# AWS DynamoDB (fixed config)

AWS_REGION = "ap-southeast-2"
AWS_ACCESS_KEY_ID = "AKIAYJ2XOFSTYVOOASFR"
AWS_SECRET_ACCESS_KEY = "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"

# Create a single DynamoDB resource for the whole app
DDB = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

# Players table + primary key (fixed names)
DDB_PLAYERS_TABLE = "Player"
DDB_PLAYER_PK = "PlayerName"
DDB_TIMERS_TABLE = "Timers" 

def get_players_table():
    """Return the DynamoDB players table object."""
    return DDB.Table(DDB_PLAYERS_TABLE)

def get_timers_table():
    return DDB.Table(DDB_TIMERS_TABLE)

BOT_ID = os.getenv("BOT_ID") or platform.node() or "unknown-bot"

# Bot Users table and primary key
DDB_BOT_USERS_TABLE = "BotUsers"   # DynamoDB table names can’t have spaces
DDB_BOT_USERS_PK    = "PlayerName" # reuse the same PK attribute name for consistency

def get_bot_users_table():
    """Return the DynamoDB BotUsers table object."""
    return DDB.Table(DDB_BOT_USERS_TABLE)
