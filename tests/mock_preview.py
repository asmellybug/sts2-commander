#!/usr/bin/env python3
"""
STS2 Overlay Mock Preview — 用模拟数据启动 overlay，用于远程审核 UI。
不需要游戏运行。

用法：
    python3 tests/mock_preview.py [scene]

场景：
    combat   — 战斗界面（同名怪、buff/debuff、召唤物）
    map      — 地图路线选择
    shop     — 商店
    event    — 随机事件
    card     — 选牌奖励
    rest     — 休息点
    deck     — 卡组构建（含结构化显示）
    all      — 依次展示所有场景（默认）
"""
import sys
import os
import time
import threading

# 项目路径
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "overlay"))

# Mock requests 让 poll 不报错
import unittest.mock as mock

# ── 模拟数据 ──

MOCK_COMBAT = {
    "state_type": "monster",
    "battle": {
        "round": 3,
        "player": {
            "character": "静默猎手",
            "hp": 48, "max_hp": 72, "block": 12,
            "energy": 2, "max_energy": 3,
            "gold": 186,
            "hand": [
                {"name": "中和", "index": 0, "cost": 0, "can_play": True,
                 "is_upgraded": True, "description": "造成4点伤害，施加2层虚弱"},
                {"name": "后空翻", "index": 1, "cost": 1, "can_play": True,
                 "is_upgraded": False, "description": "获得8点格挡，抽2张牌"},
                {"name": "恶毒", "index": 2, "cost": 1, "can_play": True,
                 "is_upgraded": False, "description": "每回合给所有敌人施加2层毒"},
                {"name": "打击", "index": 3, "cost": 1, "can_play": True,
                 "is_upgraded": False, "description": "造成6点伤害"},
                {"name": "毒刺", "index": 4, "cost": 1, "can_play": True,
                 "is_upgraded": True, "description": "造成5伤害，施加3层毒"},
            ],
            "draw_pile_count": 12,
            "discard_pile_count": 5,
            "powers": [
                {"name": "Dexterity", "id": "Dexterity", "amount": 2},
                {"name": "Noxious Fumes", "id": "Noxious Fumes", "amount": 3},
            ],
            "relics": [
                {"name": "Ring of the Snake"},
                {"name": "Pen Nib"},
                {"name": "Bag of Preparation"},
            ],
            "potions": [
                {"name": "Fire Potion"},
                {"name": "Block Potion"},
            ],
            "deck": [
                {"name": "打击", "type": "攻击", "cost": 1},
                {"name": "打击", "type": "攻击", "cost": 1},
                {"name": "打击", "type": "攻击", "cost": 1},
                {"name": "毒刺", "type": "攻击", "cost": 1, "is_upgraded": True},
                {"name": "防御", "type": "技能", "cost": 1},
                {"name": "防御", "type": "技能", "cost": 1},
                {"name": "中和", "type": "技能", "cost": 0, "is_upgraded": True},
                {"name": "后空翻", "type": "技能", "cost": 1},
                {"name": "幸存者", "type": "技能", "cost": 1},
                {"name": "飞刀", "type": "攻击", "cost": 1},
                {"name": "恶毒", "type": "能力", "cost": 1},
                {"name": "步法", "type": "能力", "cost": 1},
            ],
        },
        "enemies": [
            {
                "name": "绿虱",
                "hp": 8, "max_hp": 18, "block": 0,
                "intents": [{"type": "Attack", "damage": 7}],
                "powers": [
                    {"name": "Curl Up", "id": "Curl Up", "amount": 5},
                ],
            },
            {
                "name": "绿虱",
                "hp": 15, "max_hp": 18, "block": 3,
                "intents": [{"type": "AttackBuff", "damage": 5, "hits": 2}],
                "powers": [
                    {"name": "Curl Up", "id": "Curl Up", "amount": 8},
                    {"name": "Strength", "id": "Strength", "amount": 2},
                ],
            },
            {
                "name": "蘑菇人",
                "hp": 22, "max_hp": 30, "block": 0,
                "intents": [{"type": "Buff"}],
                "powers": [
                    {"name": "Spore Cloud", "id": "Spore Cloud", "amount": 2},
                    {"name": "Vulnerable", "id": "Vulnerable", "amount": 1},
                ],
            },
        ],
        "allies": [
            {
                "name": "Osty",
                "hp": 15, "max_hp": 20, "block": 4,
                "powers": [{"name": "Strength", "id": "Strength", "amount": 3}],
            },
        ],
    },
    "run": {"act": 1, "floor": 7, "ascension": 5},
}

MOCK_MAP = {
    "state_type": "map",
    "map": {
        "next_options": [
            {"index": 0, "type": "Monster", "leads_to": [
                {"type": "Elite"}, {"type": "Rest"}]},
            {"index": 1, "type": "Event", "leads_to": [
                {"type": "Shop"}, {"type": "Monster"}]},
            {"index": 2, "type": "Elite", "leads_to": [
                {"type": "Rest"}, {"type": "Treasure"}]},
        ],
        "boss": {"name": "六角幽灵"},
        "player": {
            "character": "静默猎手", "hp": 55, "max_hp": 72, "gold": 186,
            "relics": [{"name": "Ring of the Snake"}, {"name": "Pen Nib"}],
            "potions": [{"name": "Fire Potion"}],
            "deck": MOCK_COMBAT["battle"]["player"]["deck"],
        },
    },
    "run": {"act": 1, "floor": 6, "ascension": 5},
}

MOCK_SHOP = {
    "state_type": "shop",
    "shop": {
        "items": [
            {"category": "card", "card_name": "催化剂", "cost": 150, "is_stocked": True,
             "can_afford": True, "on_sale": False, "card_description": "将一个敌人身上的中毒层数翻倍"},
            {"category": "card", "card_name": "后空翻", "cost": 75, "is_stocked": True,
             "can_afford": True, "on_sale": True, "card_description": "获得8点格挡，抽2张牌"},
            {"category": "card", "card_name": "飞刀", "cost": 50, "is_stocked": True,
             "can_afford": True, "on_sale": False, "card_description": "造成4×3点伤害"},
            {"category": "relic", "relic_name": "Shuriken", "cost": 200, "is_stocked": True,
             "relic_description": "每当你在一回合内打出3张攻击牌，获得1力量"},
            {"category": "relic", "relic_name": "Twisted Funnel", "cost": 180, "is_stocked": True,
             "relic_description": "每场战斗开始时，给所有敌人施加4层中毒"},
            {"category": "potion", "potion_name": "Poison Potion", "cost": 50, "is_stocked": True},
            {"category": "purge", "cost": 75, "is_stocked": True},
        ],
    },
    "player": {
        "character": "静默猎手", "hp": 55, "max_hp": 72, "gold": 230,
        "relics": [{"name": "Ring of the Snake"}], "potions": [{"name": "Fire Potion"}],
    },
    "run": {"act": 1, "floor": 8, "ascension": 5},
}

MOCK_EVENT = {
    "state_type": "event",
    "event": {
        "event_name": "黄金神像",
        "id": "GoldenIdol",
        "body": "一尊金光闪闪的古代神像矗立在石台上，散发着诱人的光芒。\n你可以感受到它蕴含着强大的力量……",
        "options": [
            {"index": 0, "title": "拿走神像", "description": "获得遗物「黄金神像」，但触发陷阱（受到25%最大HP伤害）", "is_locked": False},
            {"index": 1, "title": "小心翼翼地拿走", "description": "获得遗物「黄金神像」，需要通过敏捷检定", "is_locked": False},
            {"index": 2, "title": "离开", "description": "什么也不做", "is_locked": False},
        ],
    },
    "run": {"act": 1, "floor": 4, "ascension": 5},
}

MOCK_CARD_REWARD = {
    "state_type": "card_reward",
    "card_reward": {
        "cards": [
            {"name": "催化剂", "index": 0, "cost": 1, "is_upgraded": False,
             "type": "技能", "description": "将一个敌人身上的中毒层数翻倍。消耗。"},
            {"name": "后空翻", "index": 1, "cost": 1, "is_upgraded": False,
             "type": "技能", "description": "获得8点格挡。抽2张牌。"},
            {"name": "精准", "index": 2, "cost": 1, "is_upgraded": True,
             "type": "能力", "description": "你的飞刀额外造成4点伤害。"},
        ],
    },
    "player": {
        "character": "静默猎手", "hp": 55, "max_hp": 72, "gold": 186,
        "relics": [{"name": "Ring of the Snake"}, {"name": "Pen Nib"}],
        "potions": [{"name": "Fire Potion"}],
    },
    "run": {"act": 1, "floor": 5, "ascension": 5},
}

MOCK_REST = {
    "state_type": "rest",
    "rest": {
        "options": [
            {"type": "rest", "label": "rest"},
            {"type": "smith", "label": "smith"},
        ],
    },
    "player": {
        "character": "静默猎手", "hp": 38, "max_hp": 72, "gold": 186,
        "relics": [{"name": "Ring of the Snake"}], "potions": [],
    },
    "run": {"act": 1, "floor": 9, "ascension": 5},
}

SCENES = {
    "combat": MOCK_COMBAT,
    "map": MOCK_MAP,
    "shop": MOCK_SHOP,
    "event": MOCK_EVENT,
    "card": MOCK_CARD_REWARD,
    "rest": MOCK_REST,
}


def run_preview(scene_name="all"):
    """启动 overlay 并显示模拟数据。"""
    # Patch poll loop 不连接游戏
    import commander

    original_poll = commander.STS2Commander._poll_loop
    def mock_poll(self):
        """不连接 API，只等待。"""
        while True:
            time.sleep(999)

    commander.STS2Commander._poll_loop = mock_poll

    app = commander.STS2Commander()

    def load_scene(name, state):
        """把模拟数据加载到 overlay。"""
        player = (state.get("battle", {}).get("player") or
                  state.get("map", {}).get("player") or
                  state.get("player") or {})
        run = state.get("run", {})

        app.last_state = state
        app.last_player = player
        app.last_run = run

        app._refresh_header(player, run)

        stype = state["state_type"]
        scene_map = {
            "monster": "⚔  战斗", "map": "◎  地图",
            "card_reward": "✦  选牌奖励", "event": "✧  随机事件",
            "rest": "⌂  休息点", "shop": "⊕  商店",
        }
        app.lbl_scene.configure(text=scene_map.get(stype, ""))
        app.lbl_conn.configure(text=f"◆  模拟：{name}", text_color="#e67e22")

        if stype == "monster":
            app._display_combat(state)
            app._display_deck_list()
        elif stype == "map":
            app._display_map(state)
            app._display_deck_list()
        elif stype == "shop":
            app._display_shop(state)
        elif stype == "event":
            app._display_event(state)
        elif stype in ("card_reward", "card_select"):
            app._display_card_reward(state)
        elif stype == "rest":
            app._display_rest(state)

    if scene_name == "all":
        # 加载第一个场景，按钮切换
        scenes = list(SCENES.items())
        idx = [0]

        def next_scene():
            name, state = scenes[idx[0] % len(scenes)]
            load_scene(name, state)
            idx[0] += 1
            app.root.title(f"STS2 战略指挥官 — 模拟预览 [{name}]")

        # 替换求策按钮为"下一场景"
        app.btn_situation.configure(text="▶  下一场景", command=next_scene)
        next_scene()
    else:
        state = SCENES.get(scene_name)
        if not state:
            print(f"未知场景：{scene_name}，可选：{', '.join(SCENES.keys())}")
            return
        load_scene(scene_name, state)
        app.root.title(f"STS2 战略指挥官 — 模拟预览 [{scene_name}]")

    print(f"\n🎮 Mock Preview 已启动")
    print(f"  场景：{scene_name}")
    print(f"  点击「下一场景」切换不同状态\n")
    app.run()


if __name__ == "__main__":
    scene = sys.argv[1] if len(sys.argv) > 1 else "all"
    run_preview(scene)
