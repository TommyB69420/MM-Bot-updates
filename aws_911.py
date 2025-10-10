import boto3
from botocore.exceptions import BotoCoreError, ClientError
from boto3.dynamodb.conditions import Key
from typing import List, Dict, Optional
from global_vars import cfg_get, cfg_bool, cfg_int, cfg_float, cfg_list, cfg_int_nested

# Configure creds/region (use env vars / IAM roles in prod)
DDB = boto3.resource(
    "dynamodb",
    region_name="ap-southeast-2",
    aws_access_key_id="AKIAYJ2XOFSTYVOOASFR",            # TODO: replace or use env vars
    aws_secret_access_key="lRbICs6T28cwPpRu2zc9NQHZBpVX5LW8JXcWj2cI",        # TODO: replace or use env vars
)

# DynamoDB table name EXACTLY as created in AWS
# Schema REQUIRED:
#   - Partition key: Time   (String)
#   - Sort key:      Victim (String)
TABLE_911 = DDB.Table("911")


def _row_to_item(row: Dict) -> Dict:
    """
    Map your parsed row to a DynamoDB item.
    Expected row keys: time, crime, victim, suspect, online_users (list)
    """
    return {
        "Time": row.get("time", ""),                  # PK
        "Victim": row.get("victim", ""),              # SK
        "Crime": row.get("crime", ""),
        "Suspect": row.get("suspect", ""),
        "OnlineUsers": row.get("online_users", []),   # list of usernames
    }

def bulk_upsert_911(rows: List[Dict]) -> int:
    """
    Upserts all provided 911 rows into the DynamoDB table '911'.
    Uniqueness is (Time, Victim). Existing items are overwritten (idempotent).
    Returns the count of items successfully queued for write.
    """
    if not rows:
        return 0

    ok = 0
    try:
        # NOTE: overwrite_by_pkeys must include BOTH keys
        with TABLE_911.batch_writer(overwrite_by_pkeys=["Time", "Victim"]) as batch:
            for row in rows:
                time_key = (row or {}).get("time")
                victim_key = (row or {}).get("victim")
                if not time_key or not victim_key:
                    continue  # skip malformed rows
                batch.put_item(Item=_row_to_item(row))
                ok += 1
    except (BotoCoreError, ClientError) as e:
        print(f"[DynamoDB] bulk_upsert_911 failed: {e}")
    return ok

def get_911_item_by_time_victim(time_str: str, victim_str: str) -> Optional[Dict]:
    """
    Fetch a single 911 row by composite key (Time, Victim).
    Falls back to a Time-only query and case-insensitive victim match if exact get_item misses.
    """
    if not time_str or not victim_str:
        return None
    try:
        # Primary: exact composite-key lookup
        resp = TABLE_911.get_item(
            Key={"Time": time_str, "Victim": victim_str},
            ExpressionAttributeNames={"#T": "Time"},
            ProjectionExpression="#T, Victim, Crime, Suspect, OnlineUsers",
        )
        item = resp.get("Item")
        if item:
            return item

        # Fallback: if victim casing/spaces differ, query by Time and match victim loosely
        q = TABLE_911.query(
            KeyConditionExpression=Key("Time").eq(time_str),
            ExpressionAttributeNames={"#T": "Time"},
            ProjectionExpression="#T, Victim, Crime, Suspect, OnlineUsers",
        )
        v_norm = victim_str.strip().lower()
        for it in q.get("Items", []):
            if (it.get("Victim", "").strip().lower() == v_norm):
                return it

        return None
    except (BotoCoreError, ClientError) as e:
        print(f"[DynamoDB] get_911_item_by_time_victim failed for {time_str}/{victim_str}: {e}")
        return None
