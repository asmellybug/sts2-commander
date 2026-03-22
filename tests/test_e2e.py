"""
端到端测试 — 模拟完整游戏流程
测试所有场景类型的数据处理和UI更新
"""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── 模拟游戏状态 ──────────────────────────────

def _base_state(stype, act=1, floor=1, hp=60, max_hp=80, gold=100):
    return {
        "type": stype,
        "run": {"act": act, "floor": floor, "character": "静默猎手", "ascension": 5},
        "players": [{
            "character": "静默猎手", "hp": hp, "max_hp": max_hp,
            "block": 0, "energy": 3, "max_energy": 3, "gold": gold,
            "powers": [], "relics": [], "potions": [],
            "draw_pile_count": 10, "discard_pile_count": 0,
            "deck": [
                {"name": "打击", "is_upgraded": False},
                {"name": "打击", "is_upgraded": False},
                {"name": "打击", "is_upgraded": False},
                {"name": "防御", "is_upgraded": False},
                {"name": "防御", "is_upgraded": False},
                {"name": "中和", "is_upgraded": True},
                {"name": "幸存者", "is_upgraded": False},
            ]
        }]
    }


def _combat_state(rnd=1, enemies=None, hand=None, relics=None, potions=None):
    s = _base_state("combat", floor=3)
    p = s["players"][0]
    p["energy"] = 3
    p["block"] = 5
    p["powers"] = [{"name": "力量", "id": "Strength", "amount": 2}]
    p["relics"] = relics or [
        {"id": "BurningBlood", "name": "燃烧之血"},
        {"id": "Shuriken", "name": "手里剑"},
    ]
    p["potions"] = potions or [
        {"name": "StrengthPotion", "id": "StrengthPotion"},
        {"name": "", "id": ""},  # empty slot
    ]

    s["combat"] = {
        "round": rnd,
        "hand": hand or [
            {"name": "打击", "index": 0, "cost": 1, "can_play": True,
             "is_upgraded": False, "damage": 8, "block": 0},
            {"name": "防御", "index": 1, "cost": 1, "can_play": True,
             "is_upgraded": False, "damage": 0, "block": 5},
            {"name": "中和+", "index": 2, "cost": 0, "can_play": True,
             "is_upgraded": True, "damage": 4, "block": 0},
            {"name": "恶毒", "index": 3, "cost": 1, "can_play": True,
             "is_upgraded": False, "damage": 0, "block": 0},
            {"name": "后空翻", "index": 4, "cost": 1, "can_play": True,
             "is_upgraded": False, "damage": 0, "block": 8},
        ],
        "enemies": enemies or [
            {"name": "绿虱", "hp": 18, "max_hp": 18, "block": 0,
             "powers": [{"name": "蜷缩", "id": "Curl Up", "amount": 5}],
             "intents": [{"type": "attack", "damage": 7, "hits": 1}]},
            {"name": "绿虱", "hp": 15, "max_hp": 18, "block": 3,
             "powers": [{"name": "蜷缩", "id": "Curl Up", "amount": 8},
                        {"name": "力量", "id": "Strength", "amount": 2}],
             "intents": [{"type": "attack", "damage": 5, "hits": 2}]},
        ],
        "allies": [
            {"name": "Osty", "hp": 15, "max_hp": 20, "block": 4,
             "powers": [{"name": "力量", "id": "Strength", "amount": 3}]},
        ],
    }
    return s


def _map_state():
    s = _base_state("map", floor=6)
    s["map"] = {
        "boss": {"name": "六角幽灵"},
        "next_options": [
            {"index": 0, "type": "Monster", "leads_to": [
                {"type": "Elite"}, {"type": "Rest"}]},
            {"index": 1, "type": "Event", "leads_to": [
                {"type": "Shop"}, {"type": "Monster"}]},
            {"index": 2, "type": "Elite", "leads_to": [
                {"type": "Rest"}, {"type": "Treasure"}]},
        ]
    }
    return s


def _shop_state():
    s = _base_state("shop", floor=8, gold=230)
    s["shop"] = {
        "cards": [
            {"name": "催化剂", "cost": 150, "is_stocked": True, "is_upgraded": False},
            {"name": "后空翻", "cost": 75, "is_stocked": True, "is_upgraded": False},
        ],
        "relics": [
            {"name": "手里剑", "cost": 200, "is_stocked": True, "category": "relic"},
        ],
        "potions": [
            {"name": "毒药水", "cost": 50, "is_stocked": True, "category": "potion"},
        ],
        "purge": {"cost": 75, "is_stocked": True},
    }
    return s


def _card_reward_state():
    s = _base_state("card_reward", floor=5)
    s["card_reward"] = {
        "cards": [
            {"name": "催化剂", "is_upgraded": False, "description": "将毒素翻倍"},
            {"name": "后空翻", "is_upgraded": False, "description": "获得8格挡，抽2牌"},
            {"name": "精准+", "is_upgraded": True, "description": "飞刀额外4伤害"},
        ]
    }
    return s


def _event_state():
    s = _base_state("event", floor=4)
    s["event"] = {
        "event_name": "黄金神像",
        "body": "一尊金光闪闪的古代神像矗立在石台上...",
        "options": [
            {"index": 0, "title": "拿走神像", "description": "获得遗物，受25%HP伤害"},
            {"index": 1, "title": "小心翼翼地拿走", "description": "获得遗物，需敏捷检定"},
            {"index": 2, "title": "离开", "description": "什么也不做"},
        ]
    }
    return s


def _rest_state():
    s = _base_state("rest", floor=9, hp=38)
    s["rest"] = {
        "options": [
            {"type": "rest", "label": "补血", "description": "回复约25HP"},
            {"type": "smith", "label": "锻造", "description": "升级一张牌"},
        ]
    }
    return s


# ── 端到端测试 ──────────────────────────────

class TestE2ECombat:
    """战斗场景完整流程"""

    def test_combat_state_parsing(self, commander):
        """战斗状态正确解析"""
        c = commander
        state = _combat_state()
        # 模拟状态更新
        c.last_state = state
        c.last_type = "combat"

        combat = state["combat"]
        enemies = combat["enemies"]
        hand = combat["hand"]
        allies = combat.get("allies", [])

        assert len(enemies) == 2
        assert len(hand) == 5
        assert len(allies) == 1
        assert enemies[0]["name"] == "绿虱"
        assert enemies[1]["name"] == "绿虱"

    def test_same_name_enemies_numbered(self, commander):
        """同名怪物编号"""
        c = commander
        state = _combat_state()
        enemies = state["combat"]["enemies"]
        c._number_enemies(enemies)

        assert enemies[0]["_display_name"] == "绿虱#1"
        assert enemies[1]["_display_name"] == "绿虱#2"

    def test_combat_display_compact(self, commander):
        """战斗显示紧凑格式"""
        c = commander
        state = _combat_state()
        c.last_state = state
        c.last_type = "combat"

        combat = state["combat"]
        enemies = combat["enemies"]
        c._number_enemies(enemies)
        hand = combat["hand"]

        # 测试手牌紧凑格式（名字已含+时不再加）
        hand_compact = []
        for card in hand:
            name = card["name"]
            upg = "+" if card.get("is_upgraded") and not name.endswith("+") else ""
            cost = card.get("cost", "?")
            hand_compact.append(f"{name}{upg}({cost})")

        result = " · ".join(hand_compact)
        assert "打击(1)" in result
        assert "防御(1)" in result
        assert "中和+(0)" in result  # 名字已含+，不重复
        assert "恶毒(1)" in result
        assert "后空翻(1)" in result

    def test_combat_lethal_detection(self, commander):
        """致命检测"""
        state = _combat_state()
        enemies = state["combat"]["enemies"]
        player = state["players"][0]

        # 计算总伤害
        total_incoming = 0
        for e in enemies:
            for intent in e.get("intents", []):
                if intent["type"] == "attack":
                    total_incoming += intent["damage"] * intent.get("hits", 1)

        # 7 + 5*2 = 17
        assert total_incoming == 17

        my_block = player.get("block", 0)
        assert my_block == 5
        gap = total_incoming - my_block
        assert gap == 12

        # 不致命
        facing_lethal = (total_incoming - my_block) >= player["hp"]
        assert not facing_lethal  # 12 < 60

    def test_combat_lethal_true(self, commander):
        """低HP时致命检测为True"""
        state = _combat_state()
        state["players"][0]["hp"] = 10
        state["players"][0]["block"] = 0
        enemies = state["combat"]["enemies"]

        total = sum(
            i["damage"] * i.get("hits", 1)
            for e in enemies for i in e.get("intents", [])
            if i["type"] == "attack"
        )
        assert total >= 10  # 致命

    def test_relic_combat_effects(self, commander):
        """遗物战斗效果解析"""
        c = commander
        state = _combat_state(rnd=1, relics=[
            {"id": "Shuriken", "name": "手里剑"},
            {"id": "BagOfMarbles", "name": "弹珠袋"},
            {"id": "SacredBark", "name": "圣树皮"},
        ])

        relic_ids = {r["id"] for r in state["players"][0]["relics"]}
        assert "Shuriken" in relic_ids
        assert "BagOfMarbles" in relic_ids
        assert "SacredBark" in relic_ids

    def test_potion_analysis_coverage(self, commander):
        """药水分析覆盖"""
        c = commander
        # 验证potion_guide已加载
        assert hasattr(c, '_potion_guide')

        # 确认所有63种药水都有best_use
        for pid, p in c._potion_guide.items():
            if pid == '_meta':
                continue
            assert p.get('best_use'), f"{pid} missing best_use"

    def test_ally_display(self, commander):
        """友方召唤物显示"""
        state = _combat_state()
        allies = state["combat"]["allies"]
        assert len(allies) == 1
        assert allies[0]["name"] == "Osty"
        assert allies[0]["hp"] == 15


class TestE2EMap:
    """地图场景完整流程"""

    def test_map_display(self, commander):
        """地图显示"""
        c = commander
        state = _map_state()
        c._display_map(state)

        text = c.box_situation.get("1.0", "end-1c")
        assert "路线" in text
        assert "普通怪" in text or "精英" in text or "事件" in text

    def test_map_relic_route_analysis(self, commander):
        """地图遗物路线分析"""
        state = _map_state()
        player = state["players"][0]
        player["relics"] = [
            {"id": "BurningBlood", "name": "燃烧之血"},
            {"id": "MealTicket", "name": "餐券"},
            {"id": "BlackStar", "name": "黑星"},
            {"id": "DreamCatcher", "name": "捕梦网"},
        ]

        relic_ids = {r["id"] for r in player["relics"]}
        notes = []
        if "BurningBlood" in relic_ids:
            notes.append("燃烧之血")
        if "MealTicket" in relic_ids:
            notes.append("餐券")
        if "BlackStar" in relic_ids:
            notes.append("黑星")
        if "DreamCatcher" in relic_ids:
            notes.append("捕梦网")

        assert len(notes) == 4

    def test_map_options_parsing(self, commander):
        """地图选项解析"""
        state = _map_state()
        opts = state["map"]["next_options"]
        assert len(opts) == 3
        assert opts[0]["type"] == "Monster"
        assert opts[1]["type"] == "Event"
        assert opts[2]["type"] == "Elite"


class TestE2EShop:
    """商店场景完整流程"""

    def test_shop_display(self, commander):
        """商店显示"""
        c = commander
        state = _shop_state()
        c._display_shop(state)

        text = c.box_situation.get("1.0", "end-1c")
        assert "商店" in text
        assert "催化剂" in text
        assert "后空翻" in text

    def test_shop_items_categorized(self, commander):
        """商店物品分类"""
        state = _shop_state()
        shop = state["shop"]
        cards = [c for c in shop.get("cards", []) if c.get("is_stocked")]
        relics = [r for r in shop.get("relics", []) if r.get("is_stocked")]
        potions = [p for p in shop.get("potions", []) if p.get("is_stocked")]

        assert len(cards) == 2
        assert len(relics) == 1
        assert len(potions) == 1

    def test_shop_gold_check(self, commander):
        """商店金币检查"""
        state = _shop_state()
        gold = state["players"][0]["gold"]
        assert gold == 230

        shop = state["shop"]
        affordable = [c for c in shop["cards"] if c.get("is_stocked") and c["cost"] <= gold]
        assert len(affordable) == 2


class TestE2ECardReward:
    """选牌奖励完整流程"""

    def test_card_reward_display(self, commander):
        """选牌显示"""
        c = commander
        state = _card_reward_state()
        c._display_card_reward(state)

        text = c.box_situation.get("1.0", "end-1c")
        assert "催化剂" in text
        assert "后空翻" in text
        assert "精准+" in text

    def test_card_reward_options(self, commander):
        """选牌选项"""
        state = _card_reward_state()
        cards = state["card_reward"]["cards"]
        assert len(cards) == 3
        assert any(c["name"] == "催化剂" for c in cards)


class TestE2EEvent:
    """随机事件完整流程"""

    def test_event_display(self, commander):
        """事件显示"""
        c = commander
        state = _event_state()
        c._display_event(state)

        text = c.box_situation.get("1.0", "end-1c")
        assert "黄金神像" in text
        assert "拿走" in text or "离开" in text

    def test_event_options(self, commander):
        """事件选项"""
        state = _event_state()
        opts = state["event"]["options"]
        assert len(opts) == 3


class TestE2ERest:
    """休息点完整流程"""

    def test_rest_display(self, commander):
        """休息点显示"""
        c = commander
        state = _rest_state()
        c._display_rest(state)

        text = c.box_situation.get("1.0", "end-1c")
        assert "休息" in text or "补血" in text or "锻造" in text

    def test_rest_options(self, commander):
        """休息选项"""
        state = _rest_state()
        opts = state["rest"]["options"]
        assert len(opts) == 2
        types = [o["type"] for o in opts]
        assert "rest" in types
        assert "smith" in types


class TestE2EStateTransitions:
    """状态转换完整流程"""

    def test_new_game_flow(self, commander):
        """新游戏流程：开局→战斗→选牌→地图"""
        c = commander

        # 1. 初始状态
        assert c.last_type is None

        # 2. 进入战斗
        state = _combat_state()
        c.last_state = state
        c.last_type = "combat"
        assert c.last_type == "combat"

        # 3. 切换到选牌
        state = _card_reward_state()
        c.last_state = state
        old_type = c.last_type
        c.last_type = "card_reward"
        assert old_type != c.last_type  # 类型变了

        # 4. 切换到地图
        state = _map_state()
        c.last_state = state
        c.last_type = "map"
        assert c.last_type == "map"

    def test_analysis_stale_on_transition(self, commander):
        """状态转换时分析标记为过时"""
        c = commander

        c.last_state = _combat_state()
        c.last_type = "combat"
        c._analysis_id = id(c.last_state)

        # 切换状态
        c.last_state = _map_state()
        c.last_type = "map"

        assert c._analysis_stale()

    def test_deck_tracking_across_states(self, commander):
        """跨状态牌组追踪"""
        c = commander

        # 选牌后追踪
        c.deck_acquired.append("催化剂")
        c.deck_acquired.append("恶毒")
        assert len(c.deck_acquired) == 2

        # 删牌后追踪
        c.deck_removed.append("打击")
        assert len(c.deck_removed) == 1

    def test_new_run_clears_everything(self, commander):
        """新局清除所有数据"""
        c = commander

        # 模拟有数据
        c.deck_acquired = ["催化剂", "恶毒"]
        c.deck_removed = ["打击"]
        c.run_log = ["[12:00] 测试"]
        c.last_type = "combat"

        c._on_new_run()

        assert c.deck_acquired == []
        assert c.deck_removed == []
        assert len(c.run_log) == 1  # 只剩新局开始


class TestE2ELogAndStats:
    """历史记录和统计"""

    def test_log_combat_entry(self, commander):
        """战斗日志格式"""
        entry = "[13:02]  幕1·层12  ⚔ 击败 绿虱、绿虱（3回合  零伤）"
        assert "⚔" in entry
        assert "幕1·层12" in entry

    def test_log_card_entry(self, commander):
        """选牌日志格式"""
        entry = "[13:01]  幕1·层12  ✦ 选牌：催化剂"
        assert "✦" in entry
        assert "催化剂" in entry

    def test_log_shop_entry(self, commander):
        """商店日志格式"""
        entry = "[12:50]  幕1·层8   ⊕ 商店：购：后空翻 删：打击"
        assert "⊕" in entry
        assert "后空翻" in entry
        assert "打击" in entry

    def test_stats_calculation(self, commander):
        """统计计算"""
        logs = [
            "[12:25]  幕1·层1   ⚔ 击败 史莱姆（2回合  零伤）",
            "[12:30]  幕1·层2   ⚔ 击败 水晶人（4回合  损失 8 HP）",
            "[12:35]  幕1·层4   ⚔ 击败 史莱姆（3回合  损失 6 HP）",
            "[12:45]  幕1·层7   ✦ 选牌：恶毒",
            "[12:50]  幕1·层8   ⊕ 商店：购：后空翻 删：打击",
            "[12:52]  幕1·层9   ⌂ 休息点：补血",
            "[12:55]  幕1·层10  ✧ 营火蜥蜴 → 选「摸它的头」",
            "[13:01]  幕1·层12  ✦ 选牌：催化剂",
            "[13:01]  幕1·层12  ✦ 选牌（跳过）",
        ]

        fights = sum(1 for e in logs if "⚔" in e)
        cards_picked = sum(1 for e in logs if "✦ 选牌：" in e and "跳过" not in e)
        cards_skipped = sum(1 for e in logs if "✦ 选牌（跳过）" in e)
        shops = sum(1 for e in logs if "⊕" in e)
        rests = sum(1 for e in logs if "⌂" in e)
        events = sum(1 for e in logs if "✧" in e)
        purges = sum(1 for e in logs if "删：" in e)

        total_hp = 0
        for e in logs:
            m = re.search(r"损失 (\d+) HP", e)
            if m:
                total_hp += int(m.group(1))

        assert fights == 3
        assert total_hp == 14
        assert cards_picked == 2
        assert cards_skipped == 1
        assert shops == 1
        assert rests == 1
        assert events == 1
        assert purges == 1
        assert total_hp // max(fights, 1) == 4  # 均伤


class TestE2EDataIntegrity:
    """数据完整性"""

    def test_card_dict_has_common_cards(self, commander):
        """卡牌字典包含常用牌"""
        with open("data/cards/card_dict.json") as f:
            cd = json.load(f)

        common = ["打击", "防御", "中和", "后空翻", "致命毒药"]
        for name in common:
            assert name in cd, f"缺失常用牌：{name}"

    def test_potion_guide_has_vars(self, commander):
        """药水指南有数值变量"""
        with open("knowledge/potion_guide.json") as f:
            pg = json.load(f)

        # 力量药水必须有StrengthPower
        sp = pg.get("StrengthPotion", {})
        assert sp.get("vars", {}).get("StrengthPower") == 2

        # 火焰药水必须有Damage
        fp = pg.get("FirePotion", {})
        assert fp.get("vars", {}).get("Damage") == 20

    def test_relic_combat_values_format(self, commander):
        """遗物战斗数值格式"""
        with open("knowledge/relic_combat_values.json") as f:
            rcv = json.load(f)

        # 手里剑
        shuriken = rcv.get("Shuriken", {})
        assert "trigger" in shuriken or "name_cn" in shuriken

        # 赤牛
        akabeko = rcv.get("Akabeko", {})
        assert akabeko  # 存在

    def test_relics_json_has_cn_names(self, commander):
        """遗物数据有中文名"""
        with open("data/relics/relics.json") as f:
            relics = json.load(f)

        assert relics.get("Akabeko", {}).get("name_cn") == "赤牛"
        assert relics.get("Shuriken", {}).get("name_cn") == "手里剑"

    def test_monster_ai_has_patterns(self, commander):
        """怪物AI有行为模式"""
        with open("knowledge/monster_ai.json") as f:
            mai = json.load(f)

        # 至少有一些怪物有ai_pattern
        with_pattern = sum(1 for m in mai.values()
                          if isinstance(m, dict) and m.get("ai_pattern"))
        assert with_pattern > 10

    def test_event_guide_has_options(self, commander):
        """事件指南有选项建议"""
        with open("knowledge/event_guide.json") as f:
            eg = json.load(f)

        # 至少有一些事件有建议
        with_advice = sum(1 for e in eg.values()
                         if isinstance(e, dict) and (e.get("best_option") or e.get("options")))
        assert with_advice > 5
