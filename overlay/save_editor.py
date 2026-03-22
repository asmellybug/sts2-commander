#!/usr/bin/env python3
"""
STS2 Save Editor
Usage:
  sts2_edit.py hp [<value>]        — set current HP (default: max HP)
  sts2_edit.py gold <amount>       — add gold (use negative to subtract)
  sts2_edit.py gold set <value>    — set gold to exact value
  sts2_edit.py status              — show current HP and gold
"""

import json, os, sys, shutil

LOCAL_SAVE   = os.path.expanduser("~/Library/Application Support/SlayTheSpire2/steam/76561198314080932/profile1/saves/current_run.save")
LOCAL_BACKUP = LOCAL_SAVE + ".backup"
CLOUD_SAVE   = os.path.expanduser("~/Library/Application Support/Steam/userdata/353815204/2868840/remote/profile1/saves/current_run.save")

FILES = [LOCAL_SAVE, LOCAL_BACKUP, CLOUD_SAVE]

def load(path):
    with open(path, "r") as f:
        return json.load(f)

def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())

def patch_all(fn):
    """Apply fn(data) -> (old_val, new_val, label) to all save files."""
    results = []
    for path in FILES:
        if not os.path.exists(path):
            results.append(f"⚠️  {os.path.basename(path)}: not found, skipped")
            continue
        try:
            data = load(path)
            old, new, label = fn(data)
            save(path, data)
            results.append(f"✅ {os.path.basename(path)} ({os.path.basename(os.path.dirname(os.path.dirname(path)))}): {label}: {old} → {new}")
        except Exception as e:
            results.append(f"❌ {os.path.basename(path)}: {e}")
    return results

def cmd_status():
    data = load(LOCAL_SAVE)
    p = data["players"][0]
    print(f"HP:   {p['current_hp']} / {p['max_hp']}")
    print(f"Gold: {p['gold']}")

def cmd_hp(value=None):
    def fn(data):
        p = data["players"][0]
        old = p["current_hp"]
        new = int(value) if value is not None else p["max_hp"]
        p["current_hp"] = new
        return old, new, "HP"
    for line in patch_all(fn):
        print(line)

def cmd_gold(args):
    if not args:
        print("Usage: sts2_edit.py gold <amount> | gold set <value>")
        sys.exit(1)
    if args[0] == "set":
        value = int(args[1])
        def fn(data):
            p = data["players"][0]
            old = p["gold"]
            p["gold"] = value
            return old, value, "gold"
    else:
        amount = int(args[0])
        def fn(data):
            p = data["players"][0]
            old = p["gold"]
            p["gold"] = max(0, old + amount)
            return old, p["gold"], "gold"
    for line in patch_all(fn):
        print(line)

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "status":
        cmd_status()
    elif args[0] == "hp":
        cmd_hp(args[1] if len(args) > 1 else None)
    elif args[0] == "gold":
        cmd_gold(args[1:])
    else:
        print(__doc__)
        sys.exit(1)
