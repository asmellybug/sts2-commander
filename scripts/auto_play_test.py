#!/usr/bin/env python3.12
"""
STS2 全自动打牌 + Overlay专属截图
- 只截overlay窗口（不截全屏）
- 更聪明的出牌策略（不会第2回合就死）
- 死亡后等待重新开局
"""
import json, time, subprocess, os, sys, urllib.request

API   = "http://localhost:15526/api/v1/singleplayer"
SHOTS = os.path.expanduser("~/Projects/games/sts2/screenshots/ui_test")
WS    = "/Users/joy/.openclaw/workspace"
os.makedirs(SHOTS, exist_ok=True)

# ── API ──────────────────────────────────────

def api(method="GET", data=None):
    try:
        if method == "POST":
            req = urllib.request.Request(API, json.dumps(data).encode(),
                  {"Content-Type": "application/json"}, method="POST")
        else:
            req = urllib.request.Request(API)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except:
        return {"state_type": "offline"}

def post(action, **kw):
    return api("POST", {"action": action, **kw})

def state():
    return api()

# ── 窗口截图（只截overlay）──────────────────

def _find_overlay_wid():
    """找到overlay窗口的CGWindowID"""
    try:
        r = subprocess.run(["python3.12", "-c", """
import Quartz
wl = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
for w in wl:
    name = str(w.get('kCGWindowOwnerName', ''))
    title = str(w.get('kCGWindowName', ''))
    if 'python' in name.lower() and ('STS2' in title or '战略' in title or 'commander' in title.lower()):
        print(w['kCGWindowNumber'])
        break
else:
    # fallback: any Python window
    for w in wl:
        name = str(w.get('kCGWindowOwnerName', ''))
        if 'python' in name.lower() and w.get('kCGWindowAlpha', 0) > 0:
            layer = w.get('kCGWindowLayer', 999)
            if layer == 0:  # normal window
                print(w['kCGWindowNumber'])
                break
"""], capture_output=True, text=True, timeout=5)
        wid = r.stdout.strip()
        return int(wid) if wid else None
    except:
        return None

def shot(label):
    """截图只截overlay窗口"""
    path = f"{SHOTS}/{label}.png"
    ws   = f"{WS}/uishot_{label}.png"

    wid = _find_overlay_wid()
    if wid:
        # -l <windowID> 只截指定窗口
        subprocess.run(["/usr/sbin/screencapture", "-x", "-l", str(wid), path],
                       capture_output=True, timeout=5)
    else:
        # fallback: 全屏
        subprocess.run(["/usr/sbin/screencapture", "-x", path],
                       capture_output=True, timeout=5)

    subprocess.run(["cp", path, ws], capture_output=True, timeout=3)
    print(f"  📸 {label}" + (" (窗口)" if wid else " (全屏)"))
    sys.stdout.flush()
    return ws

# ── 智能出牌 ─────────────────────────────────

def _card_priority(card, enemies, player):
    """给手牌评分 — STS2出牌顺序：buff/能力 → 0费 → 防御(低血时) → AOE → 高伤"""
    desc = card.get("description", "")
    name = card.get("name", "")
    ctype = card.get("type", "")
    score = 50
    hp_pct = player.get("hp", 50) / max(player.get("max_hp", 1), 1)

    try:
        cost = int(card.get("cost", "1"))
    except:
        cost = 0

    # 能力牌最先（永久buff）
    if ctype == "Power":
        score += 60

    # 0费牌优先
    if cost == 0:
        score += 40

    # buff类：力量/敏捷/灵体 先打 → 后续伤害更高
    if "力量" in desc or "敏捷" in desc or "灵体" in desc:
        score += 35

    # 召唤（嘲讽/输出帮手）
    if "召唤" in desc:
        score += 30

    # 抽牌（先抽再出）
    if "抽" in desc and ("牌" in desc or "张" in desc):
        score += 25

    # 低血时防御优先
    if hp_pct < 0.5:
        if "格挡" in desc or ctype == "Skill":
            score += 30
    elif "格挡" in desc:
        score += 10

    # AOE（多个敌人时）
    if len(enemies) > 1 and ("所有" in desc or "全体" in desc or "每个" in desc):
        score += 25

    # 虚弱/易伤debuff先打
    if "虚弱" in desc or "易伤" in desc:
        score += 20

    # 攻击牌
    if ctype == "Attack":
        # 高伤牌优先
        import re
        dmg = re.findall(r'造成(\d+)', desc)
        if dmg:
            score += min(int(dmg[0]), 30)
        else:
            score += 5

    # 诅咒/状态牌最后
    if ctype in ("Curse", "Status"):
        score -= 50

    return score

def play_combat():
    """智能出牌打战斗"""
    for turn in range(1, 35):
        d = state()
        st = d.get("state_type", "")
        if st not in ("monster", "elite", "boss", "card_select", "hand_select"):
            return d

        if st == "card_select":
            cs = d.get("card_select", {})
            post("select_card", index=0)
            time.sleep(0.5)
            if cs.get("screen_type") == "select":
                post("confirm_selection")
                time.sleep(0.5)
            continue

        if st == "hand_select":
            # 弃牌/选牌 — 用combat_select_card选第一张，然后confirm
            post("combat_select_card", card_index=0)
            time.sleep(0.5)
            post("combat_confirm_selection")
            time.sleep(0.5)
            continue

        b = d.get("battle", {})
        p = b.get("player", {})
        hand = p.get("hand", [])
        enemies = [e for e in b.get("enemies", [])
                   if e.get("name") and e.get("hp", 0) > 0]
        nrg = p.get("energy", 0)

        if not enemies:
            post("end_turn")
            time.sleep(1.5)
            continue

        # 按优先级排序手牌
        scored = [(i, c, _card_priority(c, enemies, p)) for i, c in enumerate(hand)]
        scored.sort(key=lambda x: -x[2])

        played = 0
        played_indices = set()
        for orig_idx, card, score in scored:
            # 刷新状态
            d2 = state()
            st2 = d2.get("state_type", "")
            if st2 not in ("monster", "elite", "boss", "hand_select", "card_select"):
                return d2
            if st2 == "card_select":
                cs2 = d2.get("card_select", {})
                post("select_card", index=0)
                time.sleep(0.3)
                if cs2.get("screen_type") == "select":
                    post("confirm_selection")
                    time.sleep(0.3)
                continue
            if st2 == "hand_select":
                post("combat_select_card", card_index=0)
                time.sleep(0.3)
                post("combat_confirm_selection")
                time.sleep(0.3)
                continue

            p2 = d2.get("battle", {}).get("player", {})
            h2 = p2.get("hand", [])
            nrg2 = p2.get("energy", 0)
            if not h2:
                break

            # 找这张牌在当前手牌中的位置（出牌后index会变）
            target_name = card.get("name", "")
            card_idx = None
            for ci, c in enumerate(h2):
                if c.get("name") == target_name and ci not in played_indices:
                    card_idx = ci
                    break
            if card_idx is None:
                continue

            try:
                cost = int(h2[card_idx].get("cost", "99"))
            except:
                cost = 0
            if cost > nrg2 and cost > 0:
                continue

            alive = [e for e in d2["battle"].get("enemies", [])
                     if e.get("name") and e.get("hp", 0) > 0]
            target = alive[0]["entity_id"] if alive else None

            r = post("play_card", card_index=card_idx, target=target)
            if "error" in r:
                r = post("play_card", card_index=card_idx)
            if "error" not in r:
                played += 1
            time.sleep(0.15)

        d3 = state()
        if d3.get("state_type") in ("monster", "elite", "boss"):
            post("end_turn")
            time.sleep(1.5)

        p3 = d3.get("battle", {}).get("player", {})
        hp = p3.get("hp", "?")
        print(f"    T{turn}: played {played}  HP={hp}")
        sys.stdout.flush()
    return state()

# ── Scene handlers ───────────────────────────

def handle(d):
    st = d.get("state_type", "")
    if st == "map":
        opts = d.get("map", {}).get("next_options", [])
        if opts:
            # 优先选休息/商店/未知，避免精英
            best = opts[0]
            for o in opts:
                t = o.get("type", "").lower()
                if t in ("rest", "restsite", "shop", "merchant"):
                    best = o
                    break
                elif t in ("unknown", "?"):
                    best = o
            post("choose_map_node", index=best["index"])
        else:
            post("proceed")
    elif st == "event":
        opts = d.get("event", {}).get("options", [])
        if opts:
            post("choose_event_option", index=opts[0]["index"])
        else:
            post("proceed")
    elif st == "card_reward":
        cards = d.get("card_reward", {}).get("cards", [])
        if cards:
            post("select_card_reward", index=0)
            time.sleep(0.3)
            post("proceed")
        else:
            post("proceed")
    elif st in ("combat_rewards", "treasure"):
        post("proceed")
    elif st == "rest_site":
        # 优先休息回血
        opts = d.get("rest_site", {}).get("options", [])
        rest_idx = 0
        for o in opts:
            if "休息" in o.get("label", "") or "rest" in o.get("label", "").lower():
                rest_idx = o.get("index", 0)
                break
        post("choose_rest_option", index=rest_idx)
    elif st == "shop":
        post("proceed")
    elif st == "card_select":
        cs = d.get("card_select", {})
        post("select_card", index=0)
        time.sleep(0.5)
        if cs.get("screen_type") == "select":
            post("confirm_selection")
    else:
        post("proceed")
    time.sleep(1)

COMBAT = {"monster", "elite", "boss", "hand_select"}
TARGET = {"monster", "map", "event", "card_reward", "combat_rewards", "rest_site", "shop"}
CN = {"monster":"战斗","elite":"精英战","boss":"Boss战","map":"地图","shop":"商店",
      "card_reward":"选牌奖励","combat_rewards":"战斗奖励","event":"事件",
      "rest_site":"休息点","treasure":"宝箱","card_select":"选牌","menu":"主菜单"}

# ── Main ─────────────────────────────────────

def run_one_game():
    """跑一局，返回覆盖的场景集合"""
    seen = set()
    shots = {}
    last = None

    for i in range(80):
        d = state()
        st = d.get("state_type", "unknown")

        if st in ("menu", "offline"):
            print(f"\n{'🏠 主菜单' if st == 'menu' else '📴 离线'}")
            return seen, shots

        if st != last:
            cn = CN.get(st, st)
            print(f"\n── [{i+1}] {cn} ({st}) ──")

            time.sleep(2.5)

            if st not in seen or st in COMBAT:
                label = f"{i+1:02d}_{st}"
                shot(label)
                shots[st] = label
                seen.add(st)

            last = st

        if st in COMBAT:
            d = play_combat()
            continue
        else:
            handle(d)
            d = state()

        if TARGET.issubset(seen):
            print(f"\n✅ 全部{len(TARGET)}种场景覆盖！")
            return seen, shots

    return seen, shots


def main():
    print("=" * 55)
    print("  STS2 全自动UI测试 v2")
    print("  只截overlay窗口 | 智能出牌 | 死亡等待重开")
    print("=" * 55)

    all_seen = set()
    all_shots = {}
    max_runs = 5

    for run_num in range(1, max_runs + 1):
        print(f"\n{'━' * 55}")
        print(f"  第 {run_num} 局")
        print(f"{'━' * 55}")

        # 等待游戏进入非menu状态
        print("等待游戏开局...")
        sys.stdout.flush()
        for _ in range(300):  # 等5分钟
            d = state()
            st = d.get("state_type", "")
            if st not in ("menu", "offline", ""):
                break
            time.sleep(1)
        else:
            print("⏰ 超时，退出")
            break

        d = state()
        if d.get("state_type") in ("menu", "offline"):
            print("游戏未开局，退出")
            break

        print(f"✅ 开始！当前: {d['state_type']}")

        seen, shots = run_one_game()
        all_seen.update(seen)
        all_shots.update(shots)

        if TARGET.issubset(all_seen):
            print(f"\n🎉 经过{run_num}局，全部场景覆盖！")
            break

        missing = TARGET - all_seen
        print(f"\n本局覆盖: {sorted(seen)}")
        print(f"累计覆盖: {sorted(all_seen)}")
        print(f"还缺: {sorted(missing)}")

        if run_num < max_runs:
            print("\n⏳ 等待下一局开始（请手动开局或等待自动重试）...")
            sys.stdout.flush()

    # Final report
    print("\n" + "=" * 55)
    print("  最终报告")
    print("=" * 55)
    for st2 in sorted(all_shots):
        print(f"  {CN.get(st2,st2):6s} → {all_shots[st2]}.png")
    miss = TARGET - all_seen
    if miss:
        print(f"\n  未覆盖: {sorted(miss)}")
    else:
        print("\n  ✅ 全部覆盖！")
    print(f"\n  截图目录: {SHOTS}")

if __name__ == "__main__":
    main()
