"""
STS2 Overlay 测试配置 — 不启动 GUI，不连接游戏 API。
通过 mock 掉 tkinter 和 requests 来测试纯逻辑。
"""
import sys
import os
import json
import types
import pytest

# ── 项目路径 ──
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "overlay"))

# ── Mock tkinter/customtkinter（无头测试）──
class _FakeWidget:
    def __init__(self, *a, **kw):
        self._text = ""
    def pack(self, *a, **kw): pass
    def grid(self, *a, **kw): pass
    def configure(self, *a, **kw): pass
    def bind(self, *a, **kw): pass
    def set(self, *a, **kw): pass
    def get(self, *a, **kw): return self._text
    def delete(self, *a, **kw):
        self._text = ""
    def insert(self, *a, **kw):
        if len(a) >= 2:
            self._text += str(a[1])
    def add(self, *a, **kw): return _FakeWidget()
    def winfo_x(self): return 0
    def winfo_y(self): return 0
    def geometry(self, *a): pass
    def attributes(self, *a, **kw): pass
    def resizable(self, *a): pass
    def title(self, *a): pass
    def mainloop(self): pass
    def after(self, ms, func=None, *args):
        if func:
            func(*args)
    @property
    def _textbox(self):
        return self
    def tag_configure(self, *a, **kw): pass
    def tag_add(self, *a, **kw): pass
    def search(self, *a, **kw): return ""
    def index(self, *a, **kw): return "1.0"

class _FakeCTk(_FakeWidget):
    pass

# Build mock customtkinter module
_mock_ctk = types.ModuleType("customtkinter")
_mock_ctk.CTk = _FakeCTk
_mock_ctk.CTkFrame = _FakeWidget
_mock_ctk.CTkLabel = _FakeWidget
_mock_ctk.CTkButton = _FakeWidget
_mock_ctk.CTkTextbox = _FakeWidget
_mock_ctk.CTkTabview = _FakeWidget
_mock_ctk.CTkEntry = _FakeWidget
_mock_ctk.CTkProgressBar = _FakeWidget
_mock_ctk.set_appearance_mode = lambda *a: None
_mock_ctk.set_default_color_theme = lambda *a: None
sys.modules["customtkinter"] = _mock_ctk

# Mock tkinter too (just in case)
if "tkinter" not in sys.modules:
    _mock_tk = types.ModuleType("tkinter")
    sys.modules["tkinter"] = _mock_tk


# ── 导入 commander（不启动 poll 线程）──
import unittest.mock as mock

@pytest.fixture
def commander_class():
    """返回 STS2Commander 类（不实例化）。"""
    import commander as mod
    return mod.STS2Commander

@pytest.fixture
def commander(commander_class):
    """返回一个 mock 过的 STS2Commander 实例（不启动线程/GUI）。"""
    with mock.patch.object(commander_class, '_build_ui'), \
         mock.patch.object(commander_class, '_load_card_db'), \
         mock.patch.object(commander_class, '_load_unlock_state'), \
         mock.patch.object(commander_class, '_load_knowledge'), \
         mock.patch.object(commander_class, '_load_archetype'), \
         mock.patch.object(commander_class, '_load_history'), \
         mock.patch.object(commander_class, '_load_session'), \
         mock.patch('threading.Thread'):
        obj = commander_class()
    # 手动设置必要属性
    obj.last_state = None
    obj.last_type = None
    obj.last_round = -1
    obj.last_player = {}
    obj.last_run = {}
    obj.run_log = []
    obj.deck_acquired = []
    obj.deck_removed = []
    obj._busy_combat = False
    obj._busy_strat = False
    obj._busy_deck = False
    obj._deck_archetype = ""
    obj._deck_analysis_text = ""
    obj._battle_log = []
    obj._run_replay = []
    obj._combat_start_hp = 0
    obj._combat_rounds = 0
    obj._first_connect = True
    obj._card_analyzed = False
    obj._prev_floor = 0
    obj._fail_count = 0
    obj._card_db = {}
    obj._card_id_map = {}
    obj._monster_ai = {}
    obj._archetypes = {}
    obj._matrix = {}
    obj._synergy_index = {}
    obj._pivot_rules = {}
    obj._boss_guide = {}
    obj._event_guide = {}
    obj._potion_guide = {}
    obj._card_tiers = {}
    obj._relic_combat = {}
    obj._lessons = []
    # Fake UI widgets
    obj.box_situation = _FakeWidget()
    obj.box_battlefield = obj.box_situation  # 战场栏=box_situation
    obj.box_advice = _FakeWidget()
    obj.box_log_stats = _FakeWidget()
    obj.box_deck = _FakeWidget()
    obj.box_deck_list = _FakeWidget()
    obj.box_log = _FakeWidget()
    obj.lbl_conn = _FakeWidget()
    obj.lbl_char = _FakeWidget()
    obj.lbl_floor = _FakeWidget()
    obj.lbl_hp = _FakeWidget()
    obj.lbl_blk = _FakeWidget()
    obj.lbl_nrg = _FakeWidget()
    obj.lbl_gld = _FakeWidget()
    obj.lbl_scene = _FakeWidget()
    obj.hp_bar = _FakeWidget()
    obj.tabs = _FakeWidget()
    obj.btn_situation = _FakeWidget()
    obj.btn_deck = _FakeWidget()
    obj.entry_ask = _FakeWidget()
    obj.root = _FakeWidget()
    return obj

@pytest.fixture
def commander_module():
    """返回 commander 模块本身（用于访问模块级常量）。"""
    import commander as mod
    return mod


# ── 测试数据 fixtures ──

@pytest.fixture
def sample_combat_state():
    return {
        "state_type": "monster",
        "battle": {
            "round": 2,
            "player": {
                "character": "静默猎手",
                "hp": 55, "max_hp": 72, "block": 5,
                "energy": 3, "max_energy": 3,
                "gold": 120,
                "hand": [
                    {"name": "打击", "index": 0, "cost": 1, "can_play": True,
                     "is_upgraded": False, "description": "造成6点伤害"},
                    {"name": "防御", "index": 1, "cost": 1, "can_play": True,
                     "is_upgraded": False, "description": "获得5点格挡"},
                    {"name": "中和", "index": 2, "cost": 0, "can_play": True,
                     "is_upgraded": False, "description": "造成3点伤害，施加1层虚弱"},
                ],
                "draw_pile_count": 8,
                "discard_pile_count": 3,
                "powers": [
                    {"name": "Dexterity", "id": "Dexterity", "amount": 2},
                    {"name": "Weak", "id": "Weak", "amount": 1},
                ],
                "relics": [
                    {"name": "Ring of the Snake"},
                    {"name": "Pen Nib"},
                ],
                "potions": [
                    {"name": "Fire Potion"},
                    {"name": "Block Potion"},
                ],
                "deck": [
                    {"name": "打击", "type": "攻击", "cost": 1},
                    {"name": "打击", "type": "攻击", "cost": 1},
                    {"name": "打击", "type": "攻击", "cost": 1},
                    {"name": "防御", "type": "技能", "cost": 1},
                    {"name": "防御", "type": "技能", "cost": 1},
                    {"name": "中和", "type": "技能", "cost": 0},
                    {"name": "恶毒", "type": "能力", "cost": 1},
                ],
            },
            "enemies": [
                {
                    "name": "绿虱",
                    "hp": 12, "max_hp": 18, "block": 0,
                    "intents": [{"type": "Attack", "damage": 7}],
                    "powers": [
                        {"name": "Curl Up", "id": "Curl Up", "amount": 5},
                    ],
                },
                {
                    "name": "蘑菇人",
                    "hp": 25, "max_hp": 30, "block": 3,
                    "intents": [{"type": "AttackBuff", "label": "10"}],
                    "powers": [
                        {"name": "Spore Cloud", "id": "Spore Cloud", "amount": 2},
                        {"name": "Vulnerable", "id": "Vulnerable", "amount": 1},
                    ],
                },
            ],
            "allies": [
                {
                    "name": "Osty",
                    "hp": 15, "max_hp": 20, "block": 0,
                    "powers": [{"name": "Strength", "id": "Strength", "amount": 3}],
                },
            ],
        },
        "run": {"act": 1, "floor": 5, "ascension": 3},
    }

@pytest.fixture
def sample_shop_state():
    return {
        "state_type": "shop",
        "shop": {
            "items": [
                {"category": "card", "card_name": "后空翻", "cost": 75, "is_stocked": True,
                 "can_afford": True, "card_description": "获得8点格挡，抽2张牌"},
                {"category": "relic", "relic_name": "Shuriken", "cost": 150, "is_stocked": True,
                 "relic_description": "每当你打出3张攻击牌，获得1力量"},
                {"category": "potion", "potion_name": "Strength Potion", "cost": 50, "is_stocked": True},
                {"category": "purge", "cost": 75, "is_stocked": True},
            ],
        },
        "run": {"act": 1, "floor": 7, "ascension": 3},
        "player": {"character": "静默猎手", "hp": 50, "max_hp": 72, "gold": 200,
                    "relics": [], "potions": []},
    }

@pytest.fixture
def sample_card_reward_state():
    return {
        "state_type": "card_reward",
        "card_reward": {
            "cards": [
                {"name": "恶毒", "index": 0, "cost": 1, "is_upgraded": False,
                 "type": "能力", "description": "每回合开始给所有敌人3毒"},
                {"name": "后空翻", "index": 1, "cost": 1, "is_upgraded": False,
                 "type": "技能", "description": "获得8点格挡，抽2张牌"},
                {"name": "毒刺", "index": 2, "cost": 1, "is_upgraded": True,
                 "type": "攻击", "description": "造成5点伤害，施加3层毒"},
            ],
        },
        "player": {"character": "静默猎手", "hp": 60, "max_hp": 72, "gold": 100,
                    "relics": [{"name": "Ring of the Snake"}], "potions": []},
        "run": {"act": 1, "floor": 4, "ascension": 3},
    }

@pytest.fixture
def sample_map_state():
    return {
        "state_type": "map",
        "map": {
            "next_options": [
                {"index": 0, "type": "Monster", "leads_to": [
                    {"type": "Elite"}, {"type": "Rest"}]},
                {"index": 1, "type": "Event", "leads_to": [
                    {"type": "Shop"}, {"type": "Monster"}]},
            ],
            "boss": {"name": "六角幽灵"},
            "player": {"character": "静默猎手", "hp": 60, "max_hp": 72, "gold": 100,
                        "relics": [{"name": "Ring of the Snake"}], "potions": []},
        },
        "run": {"act": 1, "floor": 3, "ascension": 3},
    }
