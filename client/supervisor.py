import os, sys, json, time, subprocess
from remote_config import RemoteConfig
from decimal import Decimal

def _json_default(o):
    if isinstance(o, Decimal):
        # keep integers as int, others as float
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError

POLL_SECONDS = int(os.getenv("SETTINGS_POLL_SECONDS", "10"))
ENTRYPOINT = os.getenv("WORKER_ENTRYPOINT", "main.py")  # change if your script name is different

def start_worker(env):
    print(f"[Supervisor] Starting worker: {ENTRYPOINT}")
    return subprocess.Popen([sys.executable, ENTRYPOINT], env=env)

def stop_worker(p, timeout=12):
    if p.poll() is None:
        print("[Supervisor] Stopping worker…")
        p.terminate()
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print("[Supervisor] Force kill.")
            p.kill()

def main():
    user_id = os.getenv("MM_USER_ID", "jamie")

    rc = RemoteConfig(user_id)
    settings, rev = rc.fetch(consistent=True)

    env = os.environ.copy()
    env["MM_USER_ID"] = user_id
    env["REMOTE_SETTINGS_JSON"] = json.dumps(settings, default=_json_default)
    env["REMOTE_SETTINGS_REV"] = str(rev)

    print(f"[Supervisor] MM_USER_ID={user_id} Rev={rev}")
    p = start_worker(env)
    last_rev = rev

    try:
        while True:
            time.sleep(POLL_SECONDS)

            # restart if worker died
            if p.poll() is not None:
                print("[Supervisor] Worker exited; restarting…")
                p = start_worker(env)
                continue

            # check for settings change
            _, cur_rev = rc.fetch(consistent=True)
            if cur_rev != last_rev:
                print(f"[Supervisor] Settings changed: {last_rev} -> {cur_rev}. Restarting worker…")
                env["REMOTE_SETTINGS_JSON"] = json.dumps(rc.settings, default=_json_default)
                env["REMOTE_SETTINGS_REV"] = str(cur_rev)
                stop_worker(p)
                p = start_worker(env)
                last_rev = cur_rev
    except KeyboardInterrupt:
        stop_worker(p)

if __name__ == "__main__":
    main()
