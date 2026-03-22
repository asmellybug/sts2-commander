"""
STS2 Overlay — 数据完整性测试
对应 TEST_PLAN.md 中的「三、数据完整性测试」
"""
import json
import os
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════
#  翻译字典覆盖率
# ═══════════════════════════════════════════
class TestTranslationCoverage:

    def test_power_cn_minimum_coverage(self, commander_module):
        """POWER_CN 至少包含 50 个翻译。"""
        assert len(commander_module.POWER_CN) >= 50

    def test_relic_cn_minimum_coverage(self, commander_module):
        """RELIC_CN 至少包含 80 个翻译。"""
        assert len(commander_module.RELIC_CN) >= 80

    def test_potion_cn_minimum_coverage(self, commander_module):
        """POTION_CN 至少包含 25 个翻译。"""
        assert len(commander_module.POTION_CN) >= 25

    def test_power_cn_values_are_chinese(self, commander_module):
        """POWER_CN 的值应该全是中文。"""
        for key, val in commander_module.POWER_CN.items():
            # 至少有一个中文字符
            has_cn = any('\u4e00' <= ch <= '\u9fff' for ch in val)
            assert has_cn, f"POWER_CN['{key}'] = '{val}' 不含中文"

    def test_intent_cn_coverage(self, commander_module):
        """INTENT_CN 至少包含基础意图类型。"""
        I = commander_module.INTENT_CN
        for key in ["Attack", "Defend", "Buff", "Debuff", "Escape", "Unknown"]:
            assert key in I, f"INTENT_CN 缺少 '{key}'"


# ═══════════════════════════════════════════
#  知识库文件完整性
# ═══════════════════════════════════════════
KNOWLEDGE_FILES = [
    "knowledge/archetype_matrix.json",
    "knowledge/boss_counter_guide.json",
    "knowledge/card_synergy_index.json",
    "knowledge/card_tier_list.json",
    "knowledge/combat_rules.json",
    "knowledge/event_guide.json",
    "knowledge/monster_ai.json",
    "knowledge/potion_guide.json",
    "knowledge/relic_pivot_rules.json",
]

class TestKnowledgeFiles:

    @pytest.mark.parametrize("relpath", KNOWLEDGE_FILES)
    def test_knowledge_files_exist(self, relpath):
        """知识库 JSON 文件存在。"""
        fpath = os.path.join(PROJECT_DIR, relpath)
        assert os.path.exists(fpath), f"缺少文件：{relpath}"

    @pytest.mark.parametrize("relpath", KNOWLEDGE_FILES)
    def test_knowledge_files_valid_json(self, relpath):
        """知识库 JSON 文件可正常解析。"""
        fpath = os.path.join(PROJECT_DIR, relpath)
        if not os.path.exists(fpath):
            pytest.skip(f"文件不存在：{relpath}")
        with open(fpath) as f:
            data = json.load(f)
        assert isinstance(data, (dict, list)), f"{relpath} 不是 dict/list"

    @pytest.mark.parametrize("relpath", KNOWLEDGE_FILES)
    def test_knowledge_files_not_empty(self, relpath):
        """知识库 JSON 文件非空。"""
        fpath = os.path.join(PROJECT_DIR, relpath)
        if not os.path.exists(fpath):
            pytest.skip(f"文件不存在：{relpath}")
        assert os.path.getsize(fpath) > 100, f"{relpath} 文件太小"


# ═══════════════════════════════════════════
#  卡牌数据库
# ═══════════════════════════════════════════
class TestCardDatabase:

    def test_card_dict_file_exists(self):
        """card_dict.json 存在。"""
        fpath = os.path.join(PROJECT_DIR, "data", "cards", "card_dict.json")
        assert os.path.exists(fpath)

    def test_card_dict_not_empty(self):
        """card_dict.json 包含数据。"""
        fpath = os.path.join(PROJECT_DIR, "data", "cards", "card_dict.json")
        if not os.path.exists(fpath):
            pytest.skip("card_dict.json 不存在")
        with open(fpath) as f:
            data = json.load(f)
        assert len(data) >= 100, f"card_dict 只有 {len(data)} 条（预期 >= 100）"

    def test_character_cards_file_exists(self):
        """character_cards.json 存在。"""
        fpath = os.path.join(PROJECT_DIR, "data", "cards", "character_cards.json")
        assert os.path.exists(fpath)

    def test_character_cards_all_have_names(self):
        """character_cards.json 中每张牌都有 name 字段。"""
        fpath = os.path.join(PROJECT_DIR, "data", "cards", "character_cards.json")
        if not os.path.exists(fpath):
            pytest.skip("character_cards.json 不存在")
        with open(fpath) as f:
            data = json.load(f)
        for char, cards in data.items():
            for card in cards:
                assert "name" in card, f"{char} 的卡 {card.get('id','?')} 缺少 name"
                assert len(card["name"]) > 0, f"{char} 的卡 {card.get('id','?')} name 为空"

    def test_character_cards_all_characters(self):
        """character_cards.json 包含所有角色。"""
        fpath = os.path.join(PROJECT_DIR, "data", "cards", "character_cards.json")
        if not os.path.exists(fpath):
            pytest.skip("character_cards.json 不存在")
        with open(fpath) as f:
            data = json.load(f)
        expected = {"铁甲战士", "静默猎手", "缺陷体", "储君", "亡灵契约师"}
        actual = set(data.keys())
        # 至少包含这些角色（可能还有"无色"、"诅咒"等）
        for char in expected:
            assert char in actual, f"缺少角色：{char}"

    def test_card_dict_values_are_strings(self):
        """card_dict.json 的值应该是字符串描述。"""
        fpath = os.path.join(PROJECT_DIR, "data", "cards", "card_dict.json")
        if not os.path.exists(fpath):
            pytest.skip("card_dict.json 不存在")
        with open(fpath) as f:
            data = json.load(f)
        for name, desc in list(data.items())[:20]:
            assert isinstance(desc, str), f"card_dict['{name}'] 不是字符串"


# ═══════════════════════════════════════════
#  Session 文件路径
# ═══════════════════════════════════════════
class TestSessionFileConfig:

    def test_session_file_path_defined(self, commander_module):
        """SESSION_FILE 常量已定义。"""
        assert hasattr(commander_module, "SESSION_FILE")
        assert "session.json" in commander_module.SESSION_FILE

    def test_history_file_path_defined(self, commander_module):
        """HISTORY_FILE 常量已定义。"""
        assert hasattr(commander_module, "HISTORY_FILE")
        assert "run_history.json" in commander_module.HISTORY_FILE
