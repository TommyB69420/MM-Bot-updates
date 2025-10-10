# config_diagnostics.py
from typing import Dict, Any, Tuple, List
import global_vars as gv

# Keys your main loop actually uses to decide what to run:
FEATURE_KEYS: Dict[str, List[str]] = {
    # high-impact feature switches
    "EarnsSettings": ["DoEarns", "UseDilly", "UseDillyOn", "WhichEarn", "MakeShank", "DigTunnel"],
    "ActionsSettings": ["CommunityService", "ForeignCommunityService", "ManufactureDrugs", "StudyDegrees", "Training"],
    "Misc": ["MinsBetweenAggs", "MoneyOnHand", "ExcessMoneyOnHand", "AcceptLawyerReps", "GymTrains",
             "DoEvent", "TakePromo", "PromoSpam", "DoSlots"],
    "Drugs": ["BuyDrugs", "UseClean", "Marijuana", "Cocaine", "Ecstasy", "Heroin", "Acid", "Speed",
              "ConsumeCocaine", "ConsumeLimit"],
    "Drug Store": ["CheckDrugStore", "NotifyDSStock", "AutoBuyDS"],
    "Weapon Shop": ["CheckWeaponShop", "NotifyWSStock", "AutoBuyWS", "AutoBuyWeapons", "MinWSCheck", "MaxWSCheck"],
    "Bionics Shop": ["CheckBionicsShop", "NotifyBSStock", "DoAutoBuyBios", "AutoBuyBios", "MinBiosCheck", "MaxBiosCheck"],
    "Launder": ["DoLaunders", "Reserve", "Preferred"],
    "Hack": ["DoHack", "Repay", "min_amount", "max_amount"],
    "PickPocket": ["DoPickPocket", "Repay", "min_amount", "max_amount"],
    "Mugging": ["DoMugging", "Repay", "min_amount", "max_amount"],
    "BnE": ["DoBnE", "Repay", "BnETarget", "CSNotToRemoveBnE"],
    "Armed Robbery": ["DoArmedRobbery", "Repay"],
    "Torch": ["DoTorch", "Repay", "Blacklist"],
    "Police": ["Post911", "911Thread", "DoCases", "DoForensics"],
    "Judge": ["Do_Cases", "Skip_Cases_On_Player", "Pickpocket", "MUGGING", "Hacking", "Breaking & Entering",
              "GTA", "Armed Robbery", "Torch", "GBH", "Whacking"],
    "Fire": ["DoFireDuties"],
    "Bank": ["AddClients"],
    "Funeral": ["DoSmuggle"],
    # auth/discord (used by login / discord bridge)
    "Auth": ["ChromePath", "RestingPage"],
    "LoginCredentials": ["UserName", "Password"],
    "DiscordBot": ["bot_token", "listen_channel_id", "command_prefix"],
    "DiscordWebhooks": ["DiscordID", "Messages"],
    "JournalSettings": ["JournalSendToDiscord", "RequestsOffersSendToDiscord"],
}

# backward-compat section aliases (same as gv._SECTION_ALIASES)
ALIASES = {
    "Login Credentials": "LoginCredentials",
    "Discord Webhooks":  "DiscordWebhooks",
    "Earns Settings":    "EarnsSettings",
    "Actions Settings":  "ActionsSettings",
    "Journal Settings":  "JournalSettings",
}

def _get_section_dict(section: str) -> Tuple[Dict[str, Any] | None, str]:
    """Return the dict for the section from gv.SET trying alias too, and the actual name used."""
    # exact
    s = gv.SET.get(section)
    if isinstance(s, dict):
        return s, section
    # alias
    alias = ALIASES.get(section, section)
    if alias != section:
        s = gv.SET.get(alias)
        if isinstance(s, dict):
            return s, alias
    return None, section

def validate_remote_settings(verbose: bool = True):
    """Report missing sections/keys or blank values in the remote settings (gv.SET)."""
    missing_sections: List[str] = []
    missing_keys: List[Tuple[str, str]] = []
    blank_keys: List[Tuple[str, str]] = []

    # scan only what matters to the bot (FEATURE_KEYS)
    for section, keys in FEATURE_KEYS.items():
        sec_dict, actual = _get_section_dict(section)
        if sec_dict is None:
            missing_sections.append(f"{section} (expected; not found in SET)")
            continue
        for key in keys:
            if key not in sec_dict:
                missing_keys.append((actual, key))
            else:
                val = sec_dict.get(key)
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    blank_keys.append((actual, key))

    if verbose:
        print("\n=== Remote Settings Diagnostics ===")
        print(f"SET sections present: {list(gv.SET.keys())}")
        if missing_sections:
            print("\n[MISSING SECTIONS]")
            for s in missing_sections:
                print(" -", s)
        if missing_keys:
            print("\n[MISSING KEYS]")
            for sec, key in missing_keys:
                print(f" - {sec}.{key}")
        if blank_keys:
            print("\n[BLANK/EMPTY VALUES]")
            for sec, key in blank_keys:
                print(f" - {sec}.{key}")
        if not (missing_sections or missing_keys or blank_keys):
            print("All expected sections/keys are present and non-empty (for the features list).")
        print("===================================\n")

    return {
        "missing_sections": missing_sections,
        "missing_keys": missing_keys,
        "blank_keys": blank_keys,
    }

def dump_feature_drivers():
    """Print the boolean/int/string values that drive enablement, as parsed by cfg_*."""
    # Use cfg_* so we see how the bot will *actually* read them
    def b(sec, key, d=False): return gv.cfg_bool(sec, key, d)
    def i(sec, key, d=0):    return gv.cfg_int(sec, key, d)
    def s(sec, key, d=""):   return gv.cfg_get(sec, key, d)

    print("\n--- Feature Driver Values (parsed) ---")
    drivers = {
        "EarnsSettings.DoEarns": b("EarnsSettings", "DoEarns"),
        "EarnsSettings.UseDilly": b("EarnsSettings", "UseDilly"),
        "ActionsSettings.CommunityService": b("ActionsSettings", "CommunityService"),
        "ActionsSettings.ForeignCommunityService": b("ActionsSettings", "ForeignCommunityService"),
        "ActionsSettings.ManufactureDrugs": b("ActionsSettings", "ManufactureDrugs"),
        "ActionsSettings.StudyDegrees": b("ActionsSettings", "StudyDegrees"),
        "ActionsSettings.Training": s("ActionsSettings", "Training"),
        "Misc.MinsBetweenAggs": i("Misc", "MinsBetweenAggs"),
        "Misc.DoEvent": b("Misc", "DoEvent"),
        "Misc.GymTrains": b("Misc", "GymTrains"),
        "Misc.DoSlots": b("Misc", "DoSlots"),
        "Misc.TakePromo": b("Misc", "TakePromo", True),
        "Launder.DoLaunders": b("Launder", "DoLaunders"),
        "Drugs.BuyDrugs": b("Drugs", "BuyDrugs"),
        "Drugs.ConsumeCocaine": b("Drugs", "ConsumeCocaine"),
        "Weapon Shop.CheckWeaponShop": b("Weapon Shop", "CheckWeaponShop"),
        "Drug Store.CheckDrugStore": b("Drug Store", "CheckDrugStore"),
        "Bionics Shop.CheckBionicsShop": b("Bionics Shop", "CheckBionicsShop"),
        "Police.Post911": b("Police", "Post911"),
        "Police.DoCases": b("Police", "DoCases"),
        "Police.DoForensics": b("Police", "DoForensics"),
        "Judge.Do_Cases": b("Judge", "Do_Cases"),
        "Fire.DoFireDuties": b("Fire", "DoFireDuties"),
        "Bank.AddClients": b("Bank", "AddClients"),
        "Hack.DoHack": b("Hack", "DoHack"),
        "PickPocket.DoPickPocket": b("PickPocket", "DoPickPocket"),
        "Mugging.DoMugging": b("Mugging", "DoMugging"),
        "BnE.DoBnE": b("BnE", "DoBnE"),
        "Armed Robbery.DoArmedRobbery": b("Armed Robbery", "DoArmedRobbery"),
        "Torch.DoTorch": b("Torch", "DoTorch"),
    }
    for k, v in drivers.items():
        print(f"{k:32} = {v}")
    print("--------------------------------------\n")

if __name__ == "__main__":
    validate_remote_settings(verbose=True)
    dump_feature_drivers()
