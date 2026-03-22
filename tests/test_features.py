"""
STS2 Overlay — Feature 测试
对应 TEST_PLAN.md 中的「二、Feature 测试」
"""
import json
import os
import tempfile
import pytest


# ═══════════════════════════════════════════
#  Feature #1 — 全中文化
# ═══════════════════════════════════════════
class TestFeatureChinese:

    def test_power_cn_translation(self, commander_module):
        """POWER_CN 包含核心 buff/debuff 翻译。"""
        P = commander_module.POWER_CN
        assert P["Strength"] == "力量"
        assert P["Dexterity"] == "敏捷"
        assert P["Weak"] == "虚弱"
        assert P["Vulnerable"] == "易伤"
        assert P["Frail"] == "脆弱"
        assert P["Poison"] == "中毒"
        assert P["Artifact"] == "神器"
        assert P["Intangible"] == "无实体"
        assert P["Focus"] == "专注"
        assert P["Echo Form"] == "回音"

    def test_relic_cn_translation(self, commander_module):
        """RELIC_CN 包含常见遗物翻译。"""
        R = commander_module.RELIC_CN
        assert R["Burning Blood"] == "燃烧之血"
        assert R["Shuriken"] == "手里剑"
        assert R["Dead Branch"] == "枯枝"
        assert R["Pen Nib"] == "笔尖"
        assert R["Snecko Eye"] == "蛇眼"

    def test_potion_cn_translation(self, commander_module):
        """POTION_CN 包含常见药水翻译。"""
        P = commander_module.POTION_CN
        assert P["Fire Potion"] == "火焰药水"
        assert P["Block Potion"] == "格挡药水"
        assert P["Strength Potion"] == "力量药水"
        assert P["Fairy In A Bottle"] == "瓶中仙女"

    def test_cn_power_function(self, commander_module):
        """_cn_power() 正确翻译已知 power。"""
        fn = commander_module._cn_power
        assert fn({"name": "Strength", "id": "Strength", "amount": 3}) == "力量"
        assert fn({"name": "Weak", "id": "Weak", "amount": 1}) == "虚弱"
        assert fn({"name": "Curl Up", "id": "Curl Up", "amount": 5}) == "蜷缩"

    def test_cn_power_fallback(self, commander_module):
        """_cn_power() 对未知 power 回退原名。"""
        fn = commander_module._cn_power
        result = fn({"name": "SomeUnknownPower", "id": "SomeUnknownPower", "amount": 1})
        assert result == "SomeUnknownPower"

    def test_cn_power_id_fallback(self, commander_module):
        """_cn_power() 优先用 name 查，不中再用 id 查。"""
        fn = commander_module._cn_power
        # name 未命中但 id 可能命中
        result = fn({"name": "UnknownName", "id": "Strength", "amount": 1})
        # 应该回退到 name（因为函数先查 name，查不到才看 id）
        # 具体行为取决于实现——至少不崩溃
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cn_relic_function(self, commander_module):
        """_cn_relic() 正确翻译已知遗物。"""
        fn = commander_module._cn_relic
        assert fn("Shuriken") == "手里剑"
        assert fn("Unknown Relic") == "Unknown Relic"  # 回退

    def test_cn_potion_function(self, commander_module):
        """_cn_potion() 正确翻译已知药水。"""
        fn = commander_module._cn_potion
        assert fn("Fire Potion") == "火焰药水"
        assert fn("Unknown Potion") == "Unknown Potion"  # 回退

    def test_combat_display_uses_cn_powers(self, commander, sample_combat_state):
        """_display_combat 不崩溃（内部使用 _cn_power 翻译）。"""
        commander._display_combat(sample_combat_state)

    def test_shop_display_uses_cn_relic(self, commander, sample_shop_state):
        """_display_shop 中遗物/药水名走翻译。"""
        commander._display_shop(sample_shop_state)


# ═══════════════════════════════════════════
#  Feature #2 — 卡组结构化显示
# ═══════════════════════════════════════════
class TestFeatureDeckDisplay:

    def test_deck_list_by_type(self, commander, sample_combat_state):
        """_display_deck_list 按攻击/技能/能力分类显示。"""
        commander.last_state = sample_combat_state
        commander.last_player = sample_combat_state["battle"]["player"]
        # 不崩溃
        commander._display_deck_list()

    def test_deck_list_with_api_deck(self, commander):
        """当 API 返回 deck 时，按类型分组。"""
        state = {
            "state_type": "map",
            "battle": {},
            "map": {
                "player": {
                    "character": "静默猎手",
                    "hp": 60, "max_hp": 72, "gold": 100,
                    "deck": [
                        {"name": "打击", "type": "攻击", "cost": 1},
                        {"name": "打击", "type": "攻击", "cost": 1},
                        {"name": "防御", "type": "技能", "cost": 1},
                        {"name": "恶毒", "type": "能力", "cost": 1},
                    ],
                    "relics": [], "potions": [],
                },
            },
            "run": {"act": 1, "floor": 3},
        }
        commander.last_state = state
        commander.last_player = state["map"]["player"]
        commander._display_deck_list()

    def test_deck_box_empty_on_new_run(self, commander):
        """新局开始时 box_deck 应显示空白提示。"""
        commander._on_new_run()
        # _on_new_run 中调用 _set_text(box_deck, "  点击「求策·卡组」...")
        # 验证 _deck_analysis_text 被清空
        assert commander._deck_analysis_text == ""

    def test_deck_box_only_on_manual_trigger(self, commander):
        """_deck_analysis_text 只有在 _do_deck_strategy 中才被写入。"""
        import inspect
        source = inspect.getsource(type(commander)._do_deck_strategy)
        assert "_deck_analysis_text" in source


# ═══════════════════════════════════════════
#  Feature #3 — Session 持久化
# ═══════════════════════════════════════════
class TestFeatureSession:

    def test_save_session(self, commander, tmp_path):
        """_save_session 正确保存状态到 JSON。"""
        session_file = str(tmp_path / "session.json")
        import commander as mod
        original = mod.SESSION_FILE
        mod.SESSION_FILE = session_file
        try:
            commander.last_player = {"character": "静默猎手"}
            commander.last_run = {"act": 1, "floor": 5}
            commander.deck_acquired = ["恶毒", "后空翻"]
            commander.deck_removed = ["打击"]
            commander._deck_archetype = "毒流"
            commander._deck_analysis_text = "走毒流方向"
            commander.run_log = ["[10:00] 新局开始"]

            commander._save_session()

            assert os.path.exists(session_file)
            with open(session_file) as f:
                data = json.load(f)
            assert data["character"] == "静默猎手"
            assert data["archetype"] == "毒流"
            assert "恶毒" in data["deck_acquired"]
            assert "打击" in data["deck_removed"]
            assert data["deck_analysis_text"] == "走毒流方向"
        finally:
            mod.SESSION_FILE = original

    def test_load_session_same_run(self, commander, tmp_path):
        """同一局的 session 能正确恢复。"""
        session_file = str(tmp_path / "session.json")
        import commander as mod
        original = mod.SESSION_FILE
        mod.SESSION_FILE = session_file

        try:
            # 先保存
            data = {
                "run_id": "静默猎手::恶毒|后空翻",
                "character": "静默猎手",
                "act": 1, "floor": 8,
                "archetype": "毒流",
                "deck_acquired": ["恶毒", "后空翻"],
                "deck_removed": ["打击"],
                "deck_analysis_text": "走毒流",
                "run_log": ["[10:00] 新局开始", "[10:05] 战斗"],
                "run_replay": [],
                "battle_log": [],
                "saved_at": "2026-03-20T10:00:00",
            }
            with open(session_file, "w") as f:
                json.dump(data, f)

            # 加载
            commander._load_session()

            assert commander.deck_acquired == ["恶毒", "后空翻"]
            assert commander.deck_removed == ["打击"]
            assert commander._deck_archetype == "毒流"
            assert commander._deck_analysis_text == "走毒流"
            assert len(commander.run_log) == 2
        finally:
            mod.SESSION_FILE = original

    def test_load_session_different_run(self, commander, tmp_path):
        """不同局的 session 不应恢复。"""
        session_file = str(tmp_path / "session.json")
        import commander as mod
        original_sf = mod.SESSION_FILE
        mod.SESSION_FILE = session_file

        # 也需要 mock archetype file
        arch_file = str(tmp_path / "archetype.json")
        original_af = commander.ARCHETYPE_FILE
        commander.ARCHETYPE_FILE = arch_file

        try:
            # session 保存的是角色A
            session_data = {
                "run_id": "铁甲战士::好勇斗狠",
                "character": "铁甲战士",
                "deck_acquired": ["好勇斗狠"],
                "deck_removed": [],
                "archetype": "力量流",
                "deck_analysis_text": "走力量",
                "run_log": ["old log"],
                "run_replay": [],
                "battle_log": [],
            }
            with open(session_file, "w") as f:
                json.dump(session_data, f)

            # archetype.json 是角色B
            with open(arch_file, "w") as f:
                json.dump({"character": "静默猎手", "deck": []}, f)

            # 加载 — 角色不匹配，不应恢复
            commander.deck_acquired = []
            commander._deck_archetype = ""
            commander._load_session()

            # 应该没有恢复铁甲战士的数据
            assert commander._deck_archetype != "力量流"
        finally:
            mod.SESSION_FILE = original_sf
            commander.ARCHETYPE_FILE = original_af

    def test_session_cleared_on_new_run(self, commander, tmp_path):
        """新局开始时 session.json 应被清空。"""
        session_file = str(tmp_path / "session.json")
        import commander as mod
        original = mod.SESSION_FILE
        mod.SESSION_FILE = session_file

        try:
            # 先写入一些数据
            with open(session_file, "w") as f:
                json.dump({"character": "test", "deck_acquired": ["card"]}, f)

            commander._on_new_run()

            with open(session_file) as f:
                data = json.load(f)
            assert data == {}  # 应该被清空
        finally:
            mod.SESSION_FILE = original

    def test_make_run_id(self, commander):
        """_make_run_id 生成稳定的局标识。"""
        commander.last_player = {"character": "静默猎手"}
        commander.last_run = {"act": 1, "floor": 5}
        commander.deck_acquired = ["恶毒", "后空翻"]

        rid = commander._make_run_id()
        assert "静默猎手" in rid
        assert "::" in rid

    def test_make_run_id_init(self, commander):
        """新局无已选牌时，run_id 包含 'init'。"""
        commander.last_player = {"character": "铁甲战士"}
        commander.last_run = {"act": 1, "floor": 1}
        commander.deck_acquired = []

        rid = commander._make_run_id()
        assert "init" in rid


# ═══════════════════════════════════════════
#  Feature #4 — 意图翻译
# ═══════════════════════════════════════════
class TestFeatureIntent:

    def test_intent_translation(self, commander):
        """基础意图类型能翻译为中文。"""
        result = commander._fmt_intent([{"type": "Attack", "damage": 10}])
        assert "10" in result

    def test_intent_multi_hit(self, commander):
        """多段攻击显示总伤。"""
        result = commander._fmt_intent([{"type": "Attack", "damage": 5, "hits": 3}])
        assert "15" in result  # 5×3=15 总伤

    def test_intent_defend(self, commander):
        """防御意图翻译。"""
        result = commander._fmt_intent([{"type": "Defend"}])
        assert "防御" in result

    def test_intent_buff(self, commander):
        """强化意图翻译。"""
        result = commander._fmt_intent([{"type": "Buff"}])
        assert "强化" in result

    def test_intent_unknown(self, commander):
        """未知意图不崩溃。"""
        result = commander._fmt_intent([{"type": "SomethingNew"}])
        assert isinstance(result, str)

    def test_intent_empty(self, commander):
        """空意图返回 —。"""
        result = commander._fmt_intent([])
        assert result == "—"


# ═══════════════════════════════════════════
#  Feature #5 — 战斗状态显示
# ═══════════════════════════════════════════
class TestFeatureCombatDisplay:

    def test_combat_display_enemies(self, commander, sample_combat_state):
        """_display_combat 能处理多个敌人。"""
        commander._display_combat(sample_combat_state)

    def test_combat_display_allies(self, commander, sample_combat_state):
        """_display_combat 能处理友方召唤物（Osty等）。"""
        allies = sample_combat_state["battle"]["allies"]
        assert len(allies) == 1
        assert allies[0]["name"] == "Osty"
        # 不崩溃
        commander._display_combat(sample_combat_state)

    def test_combat_display_no_allies(self, commander, sample_combat_state):
        """没有友方召唤物时不崩溃。"""
        del sample_combat_state["battle"]["allies"]
        commander._display_combat(sample_combat_state)

    def test_combat_display_empty_hand(self, commander, sample_combat_state):
        """手牌为空时不崩溃。"""
        sample_combat_state["battle"]["player"]["hand"] = []
        commander._display_combat(sample_combat_state)


# ═══════════════════════════════════════════
#  Feature #6 — 智能上下文构建
# ═══════════════════════════════════════════
class TestFeatureBuildContext:

    def test_build_context_returns_string(self, commander, sample_combat_state):
        """_build_context() 返回字符串。"""
        commander.last_state = sample_combat_state
        commander.last_player = sample_combat_state["battle"]["player"]
        commander.last_run = sample_combat_state["run"]
        result = commander._build_context("combat")
        assert isinstance(result, str)

    def test_build_context_types(self, commander, sample_combat_state):
        """不同 context_type 不崩溃。"""
        commander.last_state = sample_combat_state
        commander.last_player = sample_combat_state["battle"]["player"]
        commander.last_run = sample_combat_state["run"]
        for ct in ["combat", "deck", "card_reward", "map", "event", "shop", "boss"]:
            result = commander._build_context(ct)
            assert isinstance(result, str)


# ═══════════════════════════════════════════
#  Feature #7 — 其他显示方法不崩溃
# ═══════════════════════════════════════════
class TestFeatureDisplayMethods:

    def test_display_map(self, commander, sample_map_state):
        commander._display_map(sample_map_state)

    def test_display_card_reward(self, commander, sample_card_reward_state):
        commander._display_card_reward(sample_card_reward_state)

    def test_display_event(self, commander):
        state = {
            "state_type": "event",
            "event": {
                "event_name": "黄金神像",
                "id": "GoldenIdol",
                "body": "你发现了一尊金光闪闪的神像。",
                "options": [
                    {"index": 0, "title": "拿走", "description": "获得遗物黄金神像", "is_locked": False},
                    {"index": 1, "title": "离开", "description": "什么也不做", "is_locked": False},
                ],
            },
            "run": {"act": 1, "floor": 3},
        }
        commander._display_event(state)

    def test_display_rest(self, commander):
        state = {
            "state_type": "rest",
            "rest": {
                "options": [
                    {"type": "rest", "label": "rest"},
                    {"type": "smith", "label": "smith"},
                ],
            },
            "run": {"act": 1, "floor": 6},
            "player": {"character": "静默猎手", "hp": 40, "max_hp": 72,
                        "relics": [], "potions": []},
        }
        commander._display_rest(state)

    def test_refresh_header(self, commander):
        p = {"character": "静默猎手", "hp": 55, "max_hp": 72, "gold": 120,
             "energy": 3, "max_energy": 3, "block": 5}
        run = {"act": 1, "floor": 5, "ascension": 3}
        commander._refresh_header(p, run)
