"""STS2 模拟器 — 数据实体定义"""
from dataclasses import dataclass, field


@dataclass
class Buff:
    strength: int = 0
    dexterity: int = 0
    focus: int = 0
    vulnerable: int = 0
    weak: int = 0
    frail: int = 0
    poison: int = 0
    doom: int = 0               # 灾厄层数（敌人身上）
    block_retain: bool = False  # Barricade
    strength_per_turn: int = 0  # DemonForm
    draw_per_turn: int = 0
    thorns: int = 0
    corruption: bool = False    # 技能0费+消耗
    feel_no_pain: int = 0       # 消耗牌时获得X格挡
    dark_embrace: int = 0       # 消耗牌时抽X张
    noxious_fume: int = 0       # 每回合对所有敌人上X毒
    metallicize: int = 0        # 每回合获得X格挡
    plated_armor: int = 0       # 每回合获得X格挡(被打减少)
    ritual: int = 0             # 每回合+X力量(敌人用)
    shroud_stacks: int = 0      # ShroudPower: 给予doom时获等量格挡
    countdown_doom: int = 0     # Countdown: 每回合对随机敌人施加X灾厄
    reaper_form: bool = False   # ReaperForm: 攻击伤害附带等量灾厄
    # 🔴 新增字段
    regenerate: int = 0         # 再生 — 每回合回HP
    artifact: int = 0           # 神器 — 抵消debuff
    curl_up: int = 0            # 蜷缩 — 首次受击获挡
    strength_down: int = 0      # 临时力量衰减
    buffer: int = 0             # 缓冲 — 抵消致命伤害
    intangible: int = 0         # 无实体 — 受到伤害降至1


@dataclass
class Card:
    id: str
    name_cn: str = ""
    cost: int = 1
    card_type: str = ""  # 攻击/技能/能力
    damage: int = 0
    block: int = 0
    hits: int = 1
    upgraded: bool = False
    effect: str = ""
    effect_value: int = 0


@dataclass
class Entity:
    name: str
    hp: int
    max_hp: int
    block: int = 0
    buffs: Buff = field(default_factory=Buff)


@dataclass
class Enemy(Entity):
    ai_id: str = ""
    move_index: int = 0
    moves: list = field(default_factory=list)
    ai_state: str = "initial"
    ai_turn: int = 0


@dataclass
class Orb:
    orb_type: str  # "lightning", "frost", "dark", "plasma"
    dark_damage: int = 6


@dataclass
class Player(Entity):
    energy: int = 3
    max_energy: int = 3
    deck: list = field(default_factory=list)
    draw_pile: list = field(default_factory=list)
    hand: list = field(default_factory=list)
    discard: list = field(default_factory=list)
    exhaust_pile: list = field(default_factory=list)
    orbs: list = field(default_factory=list)
    orb_slots: int = 3
    gold: int = 99
    potions: list = field(default_factory=list)
    relics: list = field(default_factory=list)
    osty_hp: int = 0
    turn_discards: int = 0
