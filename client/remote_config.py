# client/remote_config.py
"""
Remote settings fetcher for your bot.

Priority for AWS credentials:
1) Env var AWS_PROFILE (uses named profile)
2) global_vars.py (keys inside your codebase)
3) Default env/credential files (~/.aws/*)

Env you can set:
- AWS_REGION (default: ap-southeast-2)
- AWS_PROFILE (optional)
- USERSETTINGS_TABLE (default: UserSettings)
"""

from __future__ import annotations
import os
from typing import Any, Dict, Tuple, Optional
import boto3

DEFAULT_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
TABLE_NAME = os.getenv("USERSETTINGS_TABLE", "UserSettings")


# ---- credential/session helpers ------------------------------------------------

def _session_from_global_vars(default_region: str) -> Optional[boto3.Session]:
    """
    Try to build a boto3 Session from credentials defined in your global_vars.py
    Supported names:
      - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION
      - AWS_KEY / AWS_SECRET / AWS_REGION
      - AWS_ACCESS_KEY / AWS_SECRET_KEY / AWS_REGION
      - AWS = {'access_key_id'|'key', 'secret_access_key'|'secret', 'region'}
    """
    try:
        import global_vars as gv  # must be importable from your project root
    except Exception:
        return None

    pairs = [
        ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"),
        ("AWS_KEY",           "AWS_SECRET",           "AWS_REGION"),
        ("AWS_ACCESS_KEY",    "AWS_SECRET_KEY",       "AWS_REGION"),
    ]
    for kid, ksec, kreg in pairs:
        if hasattr(gv, kid) and hasattr(gv, ksec):
            return boto3.Session(
                aws_access_key_id=getattr(gv, kid),
                aws_secret_access_key=getattr(gv, ksec),
                region_name=getattr(gv, kreg, default_region) or default_region,
            )

    if hasattr(gv, "AWS") and isinstance(getattr(gv, "AWS"), dict):
        d = getattr(gv, "AWS")
        key = d.get("access_key_id") or d.get("key")
        sec = d.get("secret_access_key") or d.get("secret")
        reg = d.get("region") or default_region
        if key and sec:
            return boto3.Session(
                aws_access_key_id=key,
                aws_secret_access_key=sec,
                region_name=reg or default_region,
            )
    return None


def _build_session() -> boto3.Session:
    # 1) AWS_PROFILE takes precedence if set
    profile = os.getenv("AWS_PROFILE")
    if profile:
        return boto3.Session(profile_name=profile, region_name=DEFAULT_REGION)

    # 2) try global_vars.py
    sess = _session_from_global_vars(DEFAULT_REGION)
    if sess:
        return sess

    # 3) default env/credential files
    return boto3.Session(region_name=DEFAULT_REGION)


# ---- Dynamo resources -----------------------------------------------------------

_SESSION = _build_session()
_DDB = _SESSION.resource("dynamodb")
_TABLE = _DDB.Table(TABLE_NAME)


# ---- Public API ----------------------------------------------------------------

class RemoteConfig:
    def __init__(self, user_id: str, table_name: str = TABLE_NAME):
        self.user_id = user_id
        self.table_name = table_name
        self._settings: Dict[str, Any] = {}
        self._rev: int = 0

    def fetch(self, consistent: bool = True) -> Tuple[Dict[str, Any], int]:
        """Fetch settings + rev from DynamoDB and cache them on the instance."""
        resp = _TABLE.get_item(Key={"UserId": self.user_id}, ConsistentRead=consistent)
        item = resp.get("Item") or {}
        self._settings = item.get("Settings", {}) or {}
        self._rev = int(item.get("Rev", 0))
        return self._settings, self._rev

    @property
    def settings(self) -> Dict[str, Any]:
        return self._settings

    @property
    def rev(self) -> int:
        return self._rev

    def as_env(self) -> Dict[str, str]:
        """Handy helper for supervisor -> worker environment injection."""
        import json
        return {
            "MM_USER_ID": self.user_id,
            "REMOTE_SETTINGS_JSON": json.dumps(self._settings),
            "REMOTE_SETTINGS_REV": str(self._rev),
        }


# ---- CLI test ------------------------------------------------------------------

if __name__ == "__main__":
    # Quick manual test:
    uid = os.getenv("MM_USER_ID", "Bleeders")
    rc = RemoteConfig(uid)
    s, r = rc.fetch()
    print(f"UserId={uid} Rev={r}")
    # print a couple of examples safely
    misc = s.get("Misc", {})
    print("Misc.DoSlots =", misc.get("DoSlots"))
    print("WeaponShop.MinWSCheck =", (s.get("Weapon Shop", {}) or {}).get("MinWSCheck"))
