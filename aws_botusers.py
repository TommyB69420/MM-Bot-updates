import datetime as dt
from typing import Dict, Any
from global_vars import BOT_ID, SCRIPT_VERSION, DDB_BOT_USERS_PK, get_bot_users_table

# Throttle the offline sweep so it doesn't scan too often
_last_bot_users_sweep_epoch = 0

def upsert_bot_user_snapshot(snap: Dict[str, Any]) -> bool:
    """
    Upserts the per-loop HUD fields for a bot user into the BotUsers table on DDB.
    Sets IsOnline = True each tick and stamps LastSeen.
    Expected keys in snap: name, rank, occupation, location, home_city, clean_money, dirty_money, next_rank_pct, consumables_24h
    """
    try:
        name = (snap.get("name") or "").strip()
        if not name:
            print("[DDB] upsert_bot_user_snapshot: missing name")
            return False

        now_epoch = int(dt.datetime.utcnow().timestamp())
        now_utc   = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"

        tbl = get_bot_users_table()
        pk  = DDB_BOT_USERS_PK

        # Base attributes written every loop
        update_parts = [
            "IsOnline = :on",
            "LastSeenSeconds = :ts",
            "LastSeenTime = :ts_utc",
            "BotId = :bot",
            "ScriptVersion = :ver",
        ]
        eav = {
            ":on": True,
            ":ts": now_epoch,
            ":ts_utc": now_utc,
            ":bot": BOT_ID,
            ":ver": SCRIPT_VERSION,
        }

        ean = {}  # ExpressionAttributeNames mapping

        def add(field: str, token: str, value):
            if value is not None:
                placeholder = f"#{field}"  # e.g. "#Rank"
                update_parts.append(f"{placeholder} = {token}")
                eav[token] = value
                ean[placeholder] = field  # map "#Rank" -> "Rank"

        # Optional fields will only set if present
        add("Rank", ":rk", snap.get("rank"))
        add("Occupation", ":occ", snap.get("occupation"))
        add("Location", ":loc", snap.get("location"))
        add("HomeCity", ":hc", snap.get("home_city"))
        add("CleanMoney", ":cm", int(snap.get("clean_money") or 0))
        add("DirtyMoney", ":dm", int(snap.get("dirty_money") or 0))
        add("NextRankPct", ":nr", snap.get("next_rank_pct"))
        add("Consumables24h", ":con", snap.get("consumables_24h"))

        update_expr = "SET " + ", ".join(update_parts)

        tbl.update_item(
            Key={pk: name},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=eav,
            ExpressionAttributeNames=ean if ean else None,
        )
        return True

    except Exception as e:
        print(f"[DDB] upsert_bot_user_snapshot error: {e}")
        return False

def mark_stale_bot_users_offline(max_age_seconds: int = 180) -> None:
    """
    Marks IsOnline = False for any BotUsers last seen > max_age_seconds ago.
    Throttled to run at most once every ~60 seconds per process.
    """
    global _last_bot_users_sweep_epoch
    now = int(dt.datetime.utcnow().timestamp())
    if now - _last_bot_users_sweep_epoch < 60:
        return  # throttle

    _last_bot_users_sweep_epoch = now

    try:
        tbl = get_bot_users_table()
        pk  = DDB_BOT_USERS_PK

        # Read minimal columns to keep scans cheap
        resp = tbl.scan(ProjectionExpression=f"{pk}, LastSeenSeconds, IsOnline")
        items = resp.get("Items", []) or []

        stale_before = now - max_age_seconds

        def mark_offline(name: str):
            try:
                tbl.update_item(
                    Key={pk: name},
                    UpdateExpression="SET IsOnline = :off",
                    ExpressionAttributeValues={":off": False},
                )
            except Exception as e:
                print(f"[DDB] Failed to mark offline {name}: {e}")

        # First page
        for item in items:
            name = item.get(pk)
            if not name:
                continue
            last_seen = int(item.get("LastSeenSeconds") or 0)
            is_online = bool(item.get("IsOnline", False))
            if last_seen < stale_before and is_online:
                mark_offline(name)

        # Sequence the order if needed
        while resp.get("LastEvaluatedKey"):
            resp = tbl.scan(
                ProjectionExpression=f"{pk}, LastSeenSeconds, IsOnline",
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            for item in (resp.get("Items", []) or []):
                name = item.get(pk)
                if not name:
                    continue
                last_seen = int(item.get("LastSeenSeconds") or 0)
                is_online = bool(item.get("IsOnline", False))
                if last_seen < stale_before and is_online:
                    mark_offline(name)

    except Exception as e:
        print(f"[DDB] BotUsers offline sweep error: {e}")
