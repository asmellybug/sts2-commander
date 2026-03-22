#!/usr/bin/env python3.12
"""
STS2 Overlay 自动UI测试监控脚本
- 监控场景变化，每个新场景自动截图
- 对比reference图，报告排版/UI问题
- 不干预游戏，纯监控模式

用法: python3.12 scripts/auto_ui_test.py
"""
import json, time, subprocess, os, sys, urllib.request

API    = "http://localhost:15526/api/v1/singleplayer"
SHOTS  = os.path.expanduser("~/Projects/games/sts2/screenshots/ui_test")
WS     = "/Users/joy/.openclaw/workspace"
REFDIR = os.path.expanduser("~/Projects/games/sts2/tests/reference")
os.makedirs(SHOTS, exist_ok=True)

# 参考图映射
REFERENCE = {
    "monster":  "04_combat.png",
    "elite":    "04_combat.png",
    "boss":     "04_combat.png",
    "map":      "03_map.png",
    "shop":     "02_shop.png",
    "card_reward": "02_shop.png",   # 无专属，用closest
    "combat_rewards": "02_shop.png",
    "event":    "03_map.png",
    "rest_site":"03_map.png",
}

# 场景中文名
SCENE_CN = {
    "monster": "战斗",
    "elite": "精英战",
    "boss": "Boss战",
    "map": "地图",
    "shop": "商店",
    "card_reward": "选牌奖励",
    "card_select": "选牌",
    "combat_rewards": "战斗奖励",
    "event": "事件",
    "rest_site": "休息点",
    "treasure": "宝箱",
    "menu": "主菜单",
}

def api_get():
    try:
        with urllib.request.urlopen(API, timeout=5) as r:
            return json.loads(r.read())
    except:
        return {"state_type": "offline"}

def take_screenshot(label):
    path = f"{SHOTS}/{label}.png"
    ws   = f"{WS}/uicheck_{label}.png"
    # 截全屏（overlay应该可见）
    subprocess.run(["/usr/sbin/screencapture", "-x", path],
                   capture_output=True, timeout=5)
    subprocess.run(["cp", path, ws], capture_output=True, timeout=3)
    return ws

def check_player_info(state):
    """提取玩家信息用于显示验证"""
    issues = []
    p = {}
    if "battle" in state:
        p = state["battle"].get("player", {})
    elif "shop" in state:
        p = state["shop"].get("player", {})
    elif "event" in state:
        p = state["event"].get("player", {})
    elif "map" in state:
        p = state["map"].get("player", {})

    if p:
        hp   = p.get("hp")
        mhp  = p.get("max_hp")
        char = p.get("character", "?")
        gold = p.get("gold", "?")

    run = state.get("run", {})
    act   = run.get("act", "?")
    floor = run.get("floor", "?")
    asc   = run.get("ascension", 0)

    return {
        "char": char if p else "?",
        "hp": f"{hp}/{mhp}" if p and hp is not None else "?",
        "gold": str(gold) if p else "?",
        "act": act, "floor": floor, "asc": asc,
    }

def monitor():
    print("═" * 58)
    print("  STS2 Overlay 实时UI监控")
    print("  你打牌 → 我截图分析")
    print("  Ctrl+C 停止")
    print("═" * 58)
    print()

    last_type = None
    captured  = {}   # state_type → (path, game_info)
    TARGET    = {"monster", "map", "shop", "card_reward",
                 "combat_rewards", "event", "rest_site"}
    offline_warned = False
    scene_count = 0

    while True:
        d = api_get()
        st = d.get("state_type", "offline")

        if st == "offline":
            if not offline_warned:
                print("⚠  API离线（游戏未运行或未开局）")
                offline_warned = True
            time.sleep(3)
            continue
        else:
            offline_warned = False

        if st == last_type:
            time.sleep(1.5)
            continue

        # 场景切换！
        scene_count += 1
        cn = SCENE_CN.get(st, st)
        print(f"\n[{scene_count:03d}] 场景切换: {last_type} → {cn} ({st})")
        last_type = st

        if st == "menu":
            print("      主菜单，等待开局…")
            time.sleep(3)
            continue

        # 等overlay刷新
        time.sleep(3)

        # 截图
        label = f"{scene_count:03d}_{st}"
        ws_path = take_screenshot(label)
        info = check_player_info(d)
        captured[st] = (ws_path, info, label)

        print(f"      📸 {label}.png")
        print(f"      角色={info['char']} HP={info['hp']} 金币={info['gold']} 幕{info['act']}层{info['floor']}")

        # 已覆盖进度
        done = TARGET & set(captured.keys())
        left = TARGET - set(captured.keys())
        print(f"      覆盖进度: {len(done)}/{len(TARGET)} ({'✅' if not left else '还需: ' + str(left)})")

        if not left:
            print("\n✅ 所有目标场景已截图！生成报告中…")
            break

        time.sleep(1)

    # ── 生成截图对照报告 ──
    print()
    print("═" * 58)
    print("  截图总结（需人工对照reference检查）")
    print("═" * 58)
    for st2, (path, info, label) in sorted(captured.items()):
        ref = REFERENCE.get(st2, "—")
        ref_path = f"{REFDIR}/{ref}"
        ref_exists = "✅" if os.path.exists(ref_path) else "❌ 无reference"
        cn2 = SCENE_CN.get(st2, st2)
        print(f"\n  [{cn2}]")
        print(f"    截图: {label}.png")
        print(f"    角色: {info['char']}  HP:{info['hp']}  金:{info['gold']}")
        print(f"    参考: {ref}  {ref_exists}")

    print()
    print("截图目录:", SHOTS)
    print()
    print("等待继续打牌或 Ctrl+C 退出…")

    # 继续监控非目标场景
    try:
        while True:
            d = api_get()
            st = d.get("state_type", "offline")
            if st != last_type and st != "offline":
                cn = SCENE_CN.get(st, st)
                scene_count += 1
                label = f"{scene_count:03d}_{st}"
                time.sleep(3)
                ws_path = take_screenshot(label)
                print(f"[{scene_count:03d}] {cn} → {label}.png")
                last_type = st
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\n监控结束。")
        print(f"共截图 {scene_count} 张，保存在 {SHOTS}")

if __name__ == "__main__":
    monitor()
