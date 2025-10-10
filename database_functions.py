import os
import json
import datetime as dt
import time

from global_vars import (
    COOLDOWN_DATA_DIR, AGGRAVATED_CRIMES_LOG_FILE, PLAYER_HOME_CITY_KEY, ALL_DEGREES_FILE,
    WEAPON_SHOP_NEXT_CHECK_FILE, POLICE_911_NEXT_POST_FILE, PENDING_FORENSICS_FILE,
    FORENSICS_TRAINING_DONE_FILE, POLICE_TRAINING_DONE_FILE, COMBAT_TRAINING_DONE, CUSTOMS_TRAINING_DONE_FILE,
    FIRE_TRAINING_DONE_FILE, BLIND_EYE_QUEUE_FILE, COMMUNITY_SERVICE_QUEUE_FILE, DRUGS_LAST_CONSUMED_FILE,
    FUNERAL_SMUGGLE_QUEUE_FILE, CASINO_NEXT_CHECK_FILE, get_timers_table, BOT_ID, MINOR_CRIME_COOLDOWN_KEY,
    MAJOR_CRIME_COOLDOWN_KEY, get_players_table, DDB_PLAYER_PK
)
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

# -----------------------
# Shared DynamoDB Timers
# -----------------------

TIMER_NAME_FUNERAL_YELLOW = "Funeral/Yellow"

def _now_epoch() -> int:
    return int(time.time())

def _iso_utc(ts: int) -> str:
    # Use module-style datetime consistently
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()

def acquire_distributed_timer(timer_name: str, interval_seconds: int, lease_seconds: int = 600, bot_id: str | None = None) -> bool:
    """
    Try to acquire the timer lock if due. Returns True if this bot acquired it.
    Creates the item if missing. Succeeds only if:
      NextEligibleEpoch <= now AND (no lease OR lease expired).
    """
    tbl = get_timers_table()
    now = _now_epoch()
    lease_until = now + int(lease_seconds)
    bot = bot_id or BOT_ID

    try:
        tbl.update_item(
            Key={"Timer": timer_name},
            UpdateExpression=(
                "SET IntervalSeconds = if_not_exists(IntervalSeconds, :ival), "
                "Holder = :bot, "
                "LeaseUntilEpoch = :lease, "
                "LeaseUntilUtc = :lease_utc, "
                "LastAttemptEpoch = :now, "
                "LastAttemptUtc = :now_utc, "
                "NextEligibleEpoch = if_not_exists(NextEligibleEpoch, :now), "
                "NextEligibleUtc = if_not_exists(NextEligibleUtc, :now_utc)"
            ),
            ConditionExpression=(
                "attribute_not_exists(#T) OR "
                "((attribute_not_exists(#N) OR #N <= :now) AND "
                " (attribute_not_exists(#L) OR #L <= :now))"
            ),
            ExpressionAttributeValues={
                ":ival": int(interval_seconds),
                ":bot": bot,
                ":lease": lease_until,
                ":lease_utc": _iso_utc(lease_until),
                ":now": now,
                ":now_utc": _iso_utc(now),
            },
            ExpressionAttributeNames={
                "#T": "Timer",
                "#N": "NextEligibleEpoch",
                "#L": "LeaseUntilEpoch",
            },
            ReturnValues="NONE",
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        print(f"[DDB] acquire_distributed_timer error for '{timer_name}': {e}")
        return False

def complete_distributed_timer(timer_name: str, interval_seconds: int) -> None:
    """
    Mark the timer as successfully run now; schedule next run after interval.
    Clears the lease/holder.
    """
    tbl = get_timers_table()
    now = _now_epoch()
    next_due = now + int(interval_seconds)
    try:
        tbl.update_item(
            Key={"Timer": timer_name},
            UpdateExpression=(
                "SET LastRunEpoch = :now, LastRunUtc = :now_utc, "
                "    NextEligibleEpoch = :next, NextEligibleUtc = :next_utc "
                "REMOVE Holder, LeaseUntilEpoch, LeaseUntilUtc"
            ),
            ExpressionAttributeValues={
                ":now": now,
                ":now_utc": _iso_utc(now),
                ":next": next_due,
                ":next_utc": _iso_utc(next_due),
            },
        )
    except ClientError as e:
        print(f"[DDB] complete_distributed_timer error for '{timer_name}': {e}")

def reschedule_distributed_timer(timer_name: str, seconds_from_now: int) -> None:
    """
    Don’t mark as success—just set next eligible time to N seconds in the future.
    Clears the lease/holder so any bot can try at that time.
    """
    tbl = get_timers_table()
    next_due = _now_epoch() + int(seconds_from_now)
    try:
        tbl.update_item(
            Key={"Timer": timer_name},
            UpdateExpression=(
                "SET NextEligibleEpoch = :next, NextEligibleUtc = :next_utc "
                "REMOVE Holder, LeaseUntilEpoch, LeaseUntilUtc"
            ),
            ExpressionAttributeValues={
                ":next": next_due,
                ":next_utc": _iso_utc(next_due),
            },
        )
    except ClientError as e:
        print(f"[DDB] reschedule_distributed_timer error for '{timer_name}': {e}")

def get_timer_remaining_seconds(timer_name: str) -> int:
    """Return seconds until due (0 if due or missing)."""
    tbl = get_timers_table()
    try:
        resp = tbl.get_item(Key={"Timer": timer_name}, ProjectionExpression="NextEligibleEpoch")
        item = resp.get("Item") or {}
        next_due = int(item.get("NextEligibleEpoch", 0))
    except Exception:
        return 0
    now = _now_epoch()
    return max(0, next_due - now)

# -----------------------
# Local JSON helpers (kept for non-player data)
# -----------------------

def init_local_db():
    """Ensures the cooldown data directory and necessary JSON/text files exist."""
    try:
        os.makedirs(COOLDOWN_DATA_DIR, exist_ok=True)

        files_to_initialize = {
            AGGRAVATED_CRIMES_LOG_FILE: lambda f: f.write("--- Aggravated Crimes Log ---\n"),
            ALL_DEGREES_FILE: lambda f: json.dump(False, f),
            WEAPON_SHOP_NEXT_CHECK_FILE: lambda f: f.write(""),
            POLICE_911_NEXT_POST_FILE: lambda f: f.write(""),
            PENDING_FORENSICS_FILE: lambda f: json.dump([], f),
            FORENSICS_TRAINING_DONE_FILE: lambda f: json.dump(False, f),
            POLICE_TRAINING_DONE_FILE: lambda f: json.dump(False, f),
            COMBAT_TRAINING_DONE: lambda f: json.dump(False, f),
            CUSTOMS_TRAINING_DONE_FILE: lambda f: json.dump(False, f),
            FIRE_TRAINING_DONE_FILE: lambda f: json.dump(False, f),
            BLIND_EYE_QUEUE_FILE: lambda f: json.dump([], f),
            FUNERAL_SMUGGLE_QUEUE_FILE: lambda f: json.dump([], f),
            COMMUNITY_SERVICE_QUEUE_FILE: lambda f: json.dump([], f),
            DRUGS_LAST_CONSUMED_FILE: lambda f: f.write(""),
            CASINO_NEXT_CHECK_FILE: lambda f: f.write(""),
        }

        for file_path, init_func in files_to_initialize.items():
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    init_func(f)
                print(f"Created new local file: {file_path}")
        return True
    except Exception as e:
        print(f"Error initializing local database: {e}")
        return False

def _read_json_file(file_path):
    """Reads JSON data from a file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File not found: {file_path}. Initializing empty data.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}. Initializing empty data.")
        return {}
    except Exception as e:
        print(f"Error reading JSON data from {file_path}: {e}")
        return {}

def _write_json_file(file_path, data):
    """Writes JSON data to a file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing JSON data to {file_path}: {e}")

def _read_text_file(file_path):
    """Reads text data from a file."""
    try:
        with open(file_path, 'r') as f:
            timestamp_str = f.read().strip()
            if timestamp_str:
                return timestamp_str
    except FileNotFoundError:
        return None
    except ValueError:
        return None
    except Exception as e:
        print(f"Error reading text data from {file_path}: {e}")
        return None
    return None

# -----------------------
# Player cooldown in DynamoDB
# -----------------------

def _cooldown_attr_name(cooldown_type: str) -> str:
    """
        Sets the name of the cooldown types.
        Minor = Personal Agg
        Major = Hack
    """
    if cooldown_type == MINOR_CRIME_COOLDOWN_KEY:
        return "MinorCooldown"
    if cooldown_type == MAJOR_CRIME_COOLDOWN_KEY:
        return "MajorCooldown"
    # Fallback so we don't explode if something odd is passed
    return cooldown_type

def get_player_cooldown(player_id: str, cooldown_type: str):
    """
    Retrieves a player's cooldown end time from DynamoDB Player table.
    Returns a datetime or None.
    """
    if not player_id or not cooldown_type:
        return None

    table = get_players_table()
    pk = DDB_PLAYER_PK
    attr = _cooldown_attr_name(cooldown_type)

    try:
        resp = table.get_item(
            Key={pk: player_id},
            ProjectionExpression=f"{pk}, {attr}"
        )
        item = resp.get("Item") or {}
        raw = item.get(attr)
        if not raw:
            return None

        # Accept both with and without microseconds for backward compatibility
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return dt.datetime.strptime(raw, fmt)
            except ValueError:
                continue

        raise ValueError(f"Unrecognized cooldown datetime format: {raw}")

    except Exception as e:
        print(f"[DDB] get_player_cooldown error for {player_id}/{attr}: {e}")
        return None

def set_player_data(player_id: str, cooldown_type: str | None = None, cooldown_end_time: dt.datetime | None = None, home_city: str | None = None, apartment: str | None = None):
    """
    Writes cooldown/home_city/apartment to DynamoDB.
    - cooldown_type -> MinorCooldown/MajorCooldown (ISO string)
    - home_city     -> HomeCity
    - apartment     -> Apartment (Title-cased)
    """
    if not player_id:
        return False

    table = get_players_table()
    pk = DDB_PLAYER_PK

    update_expr_parts = []
    eav = {}

    if cooldown_type and cooldown_end_time is not None:
        attr = _cooldown_attr_name(cooldown_type)
        update_expr_parts.append(f"{attr} = :cd")
        eav[":cd"] = cooldown_end_time.strftime("%Y-%m-%d %H:%M:%S")

    if home_city is not None:
        update_expr_parts.append("HomeCity = :hc")
        eav[":hc"] = home_city

    if apartment is not None:
        normalized = (apartment or "").strip().title()
        update_expr_parts.append("Apartment = :apt")
        eav[":apt"] = normalized

    if not update_expr_parts:
        return True  # nothing to update

    update_expr = "SET " + ", ".join(update_expr_parts)

    try:
        # Build a human-readable updates string
        updates = []
        if ":cd" in eav:
            updates.append(f"{update_expr.split('=')[0].strip()} → {eav[':cd']}")
        if ":hc" in eav:
            updates.append(f"HomeCity → {eav[':hc']}")
        if ":apt" in eav:
            updates.append(f"Apartment → {eav[':apt']}")

        print(f"[DDB] Player '{player_id}' updated with {', '.join(updates)}")
        table.update_item(
            Key={pk: player_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=eav,
        )
        return True
    except Exception as e:
        print(f"[DDB] set_player_data error for {player_id}: {e}")
        return False

def get_crime_targets_from_ddb(my_home_city: str | None, cooldown_key: str):
    """
    Returns (player_name, info_dict) pairs from DynamoDB for crime selection.
    info_dict contains at least {"HomeCity": str, "Apartment": str or None}.
    - If cooldown_key == MAJOR: only return players in my_home_city
    - If cooldown_key == MINOR: return everyone (city-agnostic)
    """
    table = get_players_table()
    pk = DDB_PLAYER_PK  # usually "PlayerName"

    # Read both HomeCity and Apartment
    projection = f"{pk}, HomeCity, Apartment"

    # If we’re doing a major crime, filter to same-city players
    filter_expr = Attr("HomeCity").eq(my_home_city) if (
        cooldown_key == MAJOR_CRIME_COOLDOWN_KEY and my_home_city
    ) else None

    scan_kwargs = {"ProjectionExpression": projection}
    if filter_expr:
        scan_kwargs["FilterExpression"] = filter_expr

    last_key = None
    while True:
        if last_key:
            scan_kwargs["ExclusiveStartKey"] = last_key
        resp = table.scan(**scan_kwargs)

        # Yield back each row’s (player_name, {"HomeCity": ..., "Apartment": ...})
        for item in resp.get("Items", []):
            yield item.get(pk), {
                "HomeCity": item.get("HomeCity") or "",
                "Apartment": item.get("Apartment") or "",
            }

        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break

# -----------------------
# DynamoDB Player helpers
# -----------------------

def remove_player_cooldown(player_id: str, cooldown_type: str | None = None) -> bool:
    """Delete the player item from DynamoDB Player table (cooldown_type ignored)."""
    table = get_players_table()
    pk = DDB_PLAYER_PK
    try:
        table.delete_item(
            Key={pk: player_id},
            ConditionExpression=Attr(pk).exists(),
        )
        print(f"[DDB] Deleted player: {player_id}")
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            print(f"[DDB] No player found to delete: {player_id}")
            return False
        print(f"[DDB] Delete error for {player_id}: {e}")
        return False

def rename_player_in_players_table(old_name: str, new_name: str) -> bool:
    """Copy item to new key then delete old key (overwrites if new already exists)."""
    table = get_players_table()
    pk = DDB_PLAYER_PK
    try:
        resp = table.get_item(Key={pk: old_name}, ConsistentRead=True)
        item = resp.get("Item")
        if not item:
            print(f"[DDB] Cannot rename; not found: {old_name}")
            return False

        item[pk] = new_name
        table.put_item(Item=item)              # upsert new
        table.delete_item(Key={pk: old_name})  # remove old
        print(f"[DDB] Renamed {old_name} → {new_name}")
        return True
    except ClientError as e:
        print(f"[DDB] Rename error {old_name} → {new_name}: {e}")
        return False

# -----------------------
# Time stamp helpers (text files) still in use for some features
# -----------------------

def _get_last_timestamp(file_path):
    """Reads a timestamp from a given file (format: %Y-%m-%d %H:%M:%S.%f)."""
    try:
        with open(file_path, 'r') as f:
            timestamp_str = f.read().strip()
            if timestamp_str:
                return dt.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
    except FileNotFoundError:
        return None
    except ValueError:
        return None
    except Exception as e:
        print(f"Error reading text data from {file_path}: {e}")
        return None
    return None

def _set_last_timestamp(file_path, timestamp):
    """Writes a timestamp to a given file (format: %Y-%m-%d %H:%M:%S.%f)."""
    try:
        with open(file_path, 'w') as f:
            f.write(timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"))
    except Exception as e:
        print(f"Error writing text data to {file_path}: {e}")

# -----------------------
# All-degrees JSON helpers
# -----------------------

def get_all_degrees_status():
    """Reads the status of all degrees from all_degrees.json in game_data."""
    try:
        with open(ALL_DEGREES_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File not found: {ALL_DEGREES_FILE}. Initializing to False.")
        set_all_degrees_status(False)
        return False
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {ALL_DEGREES_FILE}: {e}. Initializing to False.")
        set_all_degrees_status(False)
        return False
    except Exception as e:
        print(f"Error reading all degrees status from {ALL_DEGREES_FILE}: {e}")
        return False

def set_all_degrees_status(status):
    """Writes the status of all degrees to all_degrees.json."""
    try:
        with open(ALL_DEGREES_FILE, 'w') as f:
            json.dump(status, f, indent=4)
    except Exception as e:
        print(f"Error writing all degrees status to {ALL_DEGREES_FILE}: {e}")

