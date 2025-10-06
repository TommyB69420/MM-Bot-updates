import boto3
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime, timezone
from global_vars import DDB_PLAYER_PK, get_players_table

# --- Configure your AWS creds/region (consider using env vars/instance roles in prod) ---
PLAYER_TABLE = get_players_table()

# --- Top job flags ---
TOP_JOBS = {
    "Fire Chief": "FireChief",
    "Hospital Director": "HospitalDirector",
    "Funeral Director": "FuneralDirector",
    "Mayor": "Mayor",
    "Chief Engineer": "ChiefEngineer",
    "Supreme Court Judge": "SupremeCourtJudge",
    "Commissioner": "Commissioner",
    "Commissioner-General": "CommissionerGeneral",
    "Bank Manager": "BankManager",
}

def mark_top_job(player_name: str, occupation: str) -> bool:
    """
    If the player's occupation is one of the TOP_JOBS, set that attribute to 'YES' on their Player record.
    """
    attr = TOP_JOBS.get(occupation)
    if not attr or not player_name:
        return False

    try:
        PLAYER_TABLE.update_item(
            Key={DDB_PLAYER_PK: player_name},
            UpdateExpression=f"SET {attr} = :yes",
            ExpressionAttributeValues={":yes": "YES"},
        )

        return True
    except Exception as e:
        print(f"[DynamoDB] Failed to set {attr} for {player_name}: {e}")
        return False

def upsert_player_home_city(player_name: str, home_city: str, notify=None) -> bool:
    """
    Upserts the player's Home City and First Seen attribute in the Player table on DDB.
    Ensures FirstSeen is always set for new players.
    """
    if not player_name:
        return False

    today_utc = datetime.now(timezone.utc).date().isoformat()

    try:
        resp = PLAYER_TABLE.get_item(
            Key={DDB_PLAYER_PK: player_name},
            ProjectionExpression=f"{DDB_PLAYER_PK}, HomeCity, FirstSeen",
        )
        item = resp.get("Item")

        # always include HomeCity + FirstSeen
        if not item:
            PLAYER_TABLE.put_item(Item={
                DDB_PLAYER_PK: player_name,
                "HomeCity": home_city,
                "FirstSeen": today_utc,
            })
            return True

        old_city = item.get("HomeCity")

        # Backfill FirstSeen if missing
        if not item.get("FirstSeen"):
            try:
                PLAYER_TABLE.update_item(
                    Key={DDB_PLAYER_PK: player_name},
                    UpdateExpression="SET FirstSeen = if_not_exists(FirstSeen, :fs)",
                    ExpressionAttributeValues={":fs": today_utc},
                )
            except Exception:
                pass

        # Update HomeCity if changed
        if old_city != home_city:
            if notify:
                try:
                    notify(f"HomeCity change for **{player_name}**: `{old_city or 'Unknown'}` → `{home_city}`")
                except Exception:
                    pass

            PLAYER_TABLE.update_item(
                Key={DDB_PLAYER_PK: player_name},
                UpdateExpression="SET HomeCity = :hc",
                ExpressionAttributeValues={":hc": home_city},
            )

        return True

    except (BotoCoreError, ClientError) as e:
        print(f"[DynamoDB] Upsert failed for {player_name}: {e}")
        return False

def upsert_player_apartment(player_name: str, apartment: str) -> bool:
    """
    Upserts the player's Apartment attribute in the Player table on DDB.
    """
    if not player_name or not apartment:
        return False

    normalized = (apartment or "").strip().title()

    try:
        PLAYER_TABLE.update_item(
            Key={DDB_PLAYER_PK: player_name},
            UpdateExpression="SET Apartment = :apt",
            ExpressionAttributeValues={":apt": normalized},
        )
        return True
    except Exception as e:
        print(f"[DynamoDB] Failed to set Apartment for {player_name}: {e}")
        return False

def get_players_with_other_home_cities(current_home_city: str) -> list[str]:
    """
    Return a list of player names whose HomeCity is present and different from current_home_city.
    Excludes 'Hell' and 'Heaven'. Case-insensitive compare.
    """
    if not current_home_city:
        return []

    try:
        target = (current_home_city or "").strip().lower()
        names: list[str] = []

        scan_kwargs = {
            "ProjectionExpression": f"{DDB_PLAYER_PK}, HomeCity",
        }

        resp = PLAYER_TABLE.scan(**scan_kwargs)
        items = resp.get("Items", []) or []
        while True:
            for it in items:
                name = (it.get(DDB_PLAYER_PK) or "").strip()
                city = (it.get("HomeCity") or "").strip()
                if not name or not city:
                    continue
                lc = city.lower()
                if lc == target:
                    continue
                if lc in {"hell", "heaven"}:
                    continue
                names.append(name)

            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            resp = PLAYER_TABLE.scan(ExclusiveStartKey=lek, **scan_kwargs)
            items = resp.get("Items", []) or []

        return names
    except Exception as e:
        print(f"[DynamoDB] scan failed in get_players_with_other_home_cities: {e}")
        return []
