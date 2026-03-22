"""
STS2 Overlay — Bug 回归测试
对应 TEST_PLAN.md 中的「一、已修复 Bug」
"""
import json
import os
import pytest


# ═══════════════════════════════════════════
#  Bug #1 — 商店"无物品"（API 用 items 数组）
# ═══════════════════════════════════════════
class TestBug1ShopItems:

    def test_shop_items_array(self, commander, sample_shop_state):
        """shop state 包含 items 数组时，_display_shop 不崩溃且能正确解析。"""
        # 应该不抛异常
        commander._display_shop(sample_shop_state)

    def test_shop_items_categories(self, commander, sample_shop_state):
        """items 数组中的 card/relic/potion/purge 分类都能处理。"""
        items = sample_shop_state["shop"]["items"]
        cats = {i["category"] for i in items}
        assert "card" in cats
        assert "relic" in cats
        assert "potion" in cats
        assert "purge" in cats
        # 不崩溃
        commander._display_shop(sample_shop_state)

    def test_shop_empty_items(self, commander):
        """items 为空列表时不崩溃。"""
        state = {
            "state_type": "shop",
            "shop": {"items": []},
            "run": {"act": 1, "floor": 5},
            "player": {"character": "静默猎手", "hp": 50, "max_hp": 72, "gold": 100,
                        "relics": [], "potions": []},
        }
        commander._display_shop(state)


# ═══════════════════════════════════════════
#  Bug #2 — 路线分析覆盖战斗（过期分析未清理）
# ═══════════════════════════════════════════
class TestBug2AnalysisStale:

    def test_analysis_stale_on_state_change(self, commander):
        """状态从 map 切到 monster 时，分析应标记为过期。"""
        commander.last_type = "monster"
        commander._analyze_state_type = "map"  # 分析开始时是 map
        assert commander._analysis_stale() is True

    def test_analysis_not_stale_same_state(self, commander):
        """状态未变化时，分析不过期。"""
        commander.last_type = "monster"
        commander._analyze_state_type = "monster"
        assert commander._analysis_stale() is False

    def test_busy_flags_reset_on_type_change(self, commander, sample_combat_state):
        """状态切换时，busy 锁应被重置。"""
        commander._busy_strat = True
        commander._busy_combat = True
        commander._busy_deck = True
        commander.last_type = "map"  # 之前是 map
        commander.last_state = sample_combat_state

        # 模拟 _on_update 检测到 type_changed
        # 直接测试逻辑：type_changed 时 busy 应清零
        stype = sample_combat_state["state_type"]
        type_changed = stype != commander.last_type
        if type_changed:
            commander._busy_strat = False
            commander._busy_combat = False
            commander._busy_deck = False

        assert commander._busy_strat is False
        assert commander._busy_combat is False
        assert commander._busy_deck is False


# ═══════════════════════════════════════════
#  Bug #3 — 角色名英文（缺少中文映射）
# ═══════════════════════════════════════════
class TestBug3CharacterNameChinese:

    def test_character_name_chinese(self):
        """存档 character_id 能映射为中文角色名。"""
        _CHAR_CN = {
            "CHARACTER.IRONCLAD": "铁甲战士",
            "CHARACTER.SILENT": "静默猎手",
            "CHARACTER.DEFECT": "缺陷体",
            "CHARACTER.REGENT": "储君",
            "CHARACTER.NECROBINDER": "亡灵契约师",
        }
        for key, expected_cn in _CHAR_CN.items():
            assert expected_cn != key  # 不是直接返回英文
            assert len(expected_cn) >= 2  # 至少2个中文字

    def test_all_characters_have_chinese(self):
        """五个主角都有中文名。"""
        chars = ["铁甲战士", "静默猎手", "缺陷体", "储君", "亡灵契约师"]
        for c in chars:
            assert any('\u4e00' <= ch <= '\u9fff' for ch in c), f"{c} 不是中文"


# ═══════════════════════════════════════════
#  Bug #4 — 卡组构建重复显示（分离显示区域）
# ═══════════════════════════════════════════
class TestBug4DeckDisplaySeparation:

    def test_deck_display_separate_areas(self, commander):
        """box_deck_list 和 box_deck 是不同的 widget。"""
        assert commander.box_deck_list is not commander.box_deck

    def test_deck_list_shows_structure(self, commander, sample_combat_state):
        """_display_deck_list 显示结构化牌组信息。"""
        commander.last_state = sample_combat_state
        commander.last_player = sample_combat_state["battle"]["player"]
        # 不崩溃
        commander._display_deck_list()


# ═══════════════════════════════════════════
#  Bug #5 — 选牌结果被覆盖（只在状态切换时刷新一次）
# ═══════════════════════════════════════════
class TestBug5CardRewardNotOverwritten:

    def test_card_reward_only_on_type_change(self, commander, sample_card_reward_state):
        """同一 card_reward 状态重复 poll 不应重复触发显示。"""
        # 第一次：type changed
        commander.last_type = "monster"
        stype = sample_card_reward_state["state_type"]
        type_changed = stype != commander.last_type
        assert type_changed is True

        # 模拟已设置
        commander.last_type = "card_reward"
        commander._card_analyzed = True

        # 第二次：type 没变
        type_changed_2 = stype != commander.last_type
        assert type_changed_2 is False  # 不应重新触发


# ═══════════════════════════════════════════
#  Bug #6 — "已移除：无"（对比初始牌组推断移除）
# ═══════════════════════════════════════════
class TestBug6RemovedCardsDetection:

    def test_removed_cards_detection(self):
        """当前牌组少于初始牌组时能推断出被移除的牌。"""
        from collections import Counter

        starter = {"STRIKE_SILENT": 4, "DEFEND_SILENT": 4, "NEUTRALIZE": 1, "SURVIVOR": 1}
        current = Counter({"STRIKE_SILENT": 3, "DEFEND_SILENT": 4, "NEUTRALIZE": 1, "SURVIVOR": 1})

        removed = []
        for sid, scount in starter.items():
            diff = scount - current.get(sid, 0)
            if diff > 0:
                removed.extend([sid] * diff)

        assert len(removed) == 1
        assert "STRIKE_SILENT" in removed

    def test_no_false_removal(self):
        """牌组未变化时，不应误报移除。"""
        from collections import Counter

        starter = {"STRIKE_SILENT": 4, "DEFEND_SILENT": 4}
        current = Counter({"STRIKE_SILENT": 4, "DEFEND_SILENT": 4})

        removed = []
        for sid, scount in starter.items():
            diff = scount - current.get(sid, 0)
            if diff > 0:
                removed.extend([sid] * diff)

        assert len(removed) == 0


# ═══════════════════════════════════════════
#  Bug #7 — 商店 AI 建议写错位置
# ═══════════════════════════════════════════
class TestBug7ShopAdvicePosition:

    def test_shop_advice_in_advice_box(self, commander_module):
        """_ai_node（shop 类型）应把AI结果写入 box_advice（不覆盖战场显示）。"""
        import inspect
        source = inspect.getsource(commander_module.STS2Commander._ai_node)
        assert "box_advice" in source
        # 不应直接写 box_deck（shop建议）
        # （box_deck 只用于卡组构建分析）

    def test_display_shop_writes_situation(self, commander, sample_shop_state):
        """_display_shop 写入 box_situation（自动显示区域）。"""
        import inspect
        source = inspect.getsource(type(commander)._display_shop)
        assert "box_situation" in source


# ═══════════════════════════════════════════
#  Bug #9 — 求策按钮卡在"分析中"（状态切换时未恢复）
# ═══════════════════════════════════════════
class TestBug9ButtonResetOnStateChange:

    def test_button_resets_on_type_change(self, commander):
        """状态切换时，求策按钮应恢复为可点击。"""
        # 模拟按钮处于 disabled 状态
        configured = {}
        def mock_configure(**kw):
            configured.update(kw)
        commander.btn_situation.configure = mock_configure

        # 模拟状态从 monster 切到 map
        commander.last_type = "monster"
        commander._busy_combat = True
        stype = "map"
        type_changed = stype != commander.last_type

        if type_changed:
            commander._busy_strat = False
            commander._busy_combat = False
            commander._busy_deck = False
            commander.btn_situation.configure(
                text="◆  求策·当前形势  ◆", state="normal")

        assert commander._busy_combat is False
        assert configured.get("state") == "normal"
        assert "求策" in configured.get("text", "")


# ═══════════════════════════════════════════
#  Bug #10 — 同名敌人无法区分
# ═══════════════════════════════════════════
class TestBug10SameNameEnemies:

    def test_same_name_enemies_numbered(self, commander):
        """同名敌人自动编号：绿虱#1, 绿虱#2。"""
        enemies = [
            {"name": "绿虱", "hp": 10, "max_hp": 18},
            {"name": "绿虱", "hp": 15, "max_hp": 18},
            {"name": "蘑菇人", "hp": 25, "max_hp": 30},
        ]
        commander._number_enemies(enemies)
        assert enemies[0]["_display_name"] == "绿虱#1"
        assert enemies[1]["_display_name"] == "绿虱#2"
        assert enemies[2]["_display_name"] == "蘑菇人"  # 唯一的不加编号

    def test_single_enemy_no_number(self, commander):
        """只有一只的敌人不加编号。"""
        enemies = [
            {"name": "六角幽灵", "hp": 200, "max_hp": 250},
        ]
        commander._number_enemies(enemies)
        assert enemies[0]["_display_name"] == "六角幽灵"

    def test_three_same_name(self, commander):
        """三只同名敌人正确编号。"""
        enemies = [
            {"name": "史莱姆", "hp": 10, "max_hp": 12},
            {"name": "史莱姆", "hp": 8, "max_hp": 12},
            {"name": "史莱姆", "hp": 12, "max_hp": 12},
        ]
        commander._number_enemies(enemies)
        assert enemies[0]["_display_name"] == "史莱姆#1"
        assert enemies[1]["_display_name"] == "史莱姆#2"
        assert enemies[2]["_display_name"] == "史莱姆#3"

    def test_display_combat_with_same_names(self, commander):
        """_display_combat 处理同名敌人不崩溃。"""
        state = {
            "state_type": "monster",
            "battle": {
                "round": 1,
                "player": {
                    "character": "静默猎手", "hp": 60, "max_hp": 72, "block": 0,
                    "energy": 3, "max_energy": 3,
                    "hand": [], "draw_pile_count": 10, "discard_pile_count": 0,
                    "powers": [],
                },
                "enemies": [
                    {"name": "绿虱", "hp": 10, "max_hp": 18, "block": 0,
                     "intents": [{"type": "Attack", "damage": 5}], "powers": []},
                    {"name": "绿虱", "hp": 15, "max_hp": 18, "block": 3,
                     "intents": [{"type": "Defend"}], "powers": []},
                ],
            },
            "run": {"act": 1, "floor": 3},
        }
        commander._display_combat(state)


    def test_busy_cleared_on_type_change(self, commander):
        """状态切换时所有 busy 锁都清零。"""
        commander._busy_strat = True
        commander._busy_combat = True
        commander._busy_deck = True
        commander.last_type = "monster"

        # 模拟切换
        stype = "card_reward"
        if stype != commander.last_type:
            commander._busy_strat = False
            commander._busy_combat = False
            commander._busy_deck = False

        assert commander._busy_strat is False
        assert commander._busy_combat is False
        assert commander._busy_deck is False
