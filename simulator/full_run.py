"""STS2 模拟器 — 全流程模拟 & 批量模拟"""
import random, copy
from .entities import Card, Player
from .data_loader import (
    MONSTER_AI, CARD_STATS, ARCHETYPES, CHAR_EN,
    STARTING_HP, STARTING_DECK, build_card, build_enemy,
)
from .combat import CombatSim, apply_relics_combat_end
from .archetypes import build_archetype_deck
from .deckbuilder import _pick_card_reward, _visit_shop, _resolve_event, _rest_site


# ═══ 遗物系统 ═══
RELIC_EFFECTS = {
    # 战斗开始时效果
    "Vajra": {"strength": 1},            # +1力量
    "OddlySmoothStone": {"dexterity": 1},  # +1敏捷
    "Anchor": {"start_block": 10},        # 战斗开始+10格挡
    "HornCleat": {"turn2_block": 14},     # 第2回合+14格挡
    "Lantern": {"start_energy": 1},       # 第1回合+1能量
    "BagOfPreparation": {"start_draw": 2},  # 第1回合+2抽牌
    "Orichalcum": {"end_turn_block": 6},  # 回合结束无格挡时+6
    "PenNib": {"strength": 2},            # 简化为+2力量
    "Kunai": {"dexterity": 1},            # 简化为+1敏捷
    "Shuriken": {"strength": 1},          # 简化为+1力量
    "Bellows": {"metallicize": 2},        # +2金属化
    "Akabeko": {"strength": 1},           # 简化为+1力量
    "BagOfMarbles": {"start_vulnerable": 1},  # 敌人开局+1易伤
    "WarPaint": {},
    "BottledFlame": {},
    "MawBank": {},
    # 额外强力遗物
    "ThreadAndNeedle": {"start_plated": 5},  # +5甲板
    "HappyFlower": {"start_energy": 1},      # 简化
    "DataDisk": {"focus": 1},                # +1集中
    "LetterOpener": {"strength": 1},         # 简化
    "MeatOnTheBone": {},                     # 战后回血(在full_run中处理)
    "ToyOrnithopter": {},                    # 药水回血(简化)
    # 新增强力遗物
    "RedSkull": {"strength": 2},             # HP<50%+3力量(简化为+2)
    "Girya": {"strength": 1},               # +1力量
    "HandDrill": {"dexterity": 1},           # +1敏捷
    "InkBottle": {"metallicize": 1},         # 简化为+1金属化
    "TurnipBulb": {"start_block": 6},        # 开局+6格挡
    "SacredBark": {"strength": 1},           # 简化
    "StrikeDummy": {"strength": 1},          # 简化
    "PaperPhrog": {},                        # 易伤多50%(简化为无)
    "CentennialPuzzle": {},                  # 简化
    "GremlinHorn": {},                       # 简化
    "Torii": {"start_block": 5},             # 简化为+5开局格挡
    "Ornament": {"metallicize": 2},          # +2金属化
    "Nunchaku": {"strength": 1},             # 简化
}

# 遗物池（扩大）
COMMON_RELICS = ["Vajra", "Anchor", "BagOfPreparation", "Orichalcum",
                 "Lantern", "OddlySmoothStone", "ThreadAndNeedle",
                 "HappyFlower", "LetterOpener", "TurnipBulb",
                 "Girya", "HandDrill", "Nunchaku"]
UNCOMMON_RELICS = ["Kunai", "Shuriken", "Bellows", "Akabeko", "BagOfMarbles",
                   "HornCleat", "MeatOnTheBone", "RedSkull", "InkBottle",
                   "StrikeDummy", "Ornament", "Torii"]
RARE_RELICS = ["PenNib", "DataDisk", "SacredBark"]
ALL_RELICS = COMMON_RELICS + UNCOMMON_RELICS + RARE_RELICS


def _pick_relic(existing_relics: list, rarity: str = "elite") -> str:
    """从遗物池中随机选一个（不重复）"""
    if rarity == "boss":
        pool = ALL_RELICS
    elif rarity == "elite":
        roll = random.random()
        if roll < 0.70:
            pool = COMMON_RELICS
        elif roll < 0.95:
            pool = UNCOMMON_RELICS
        else:
            pool = RARE_RELICS
    else:
        pool = COMMON_RELICS

    available = [r for r in pool if r not in existing_relics]
    if not available:
        available = [r for r in ALL_RELICS if r not in existing_relics]
    if not available:
        return ""
    return random.choice(available)


def _use_combat_potions(player: Player, enemies: list, potions: list):
    """在精英/Boss战前使用战斗药水"""
    used = []
    for i, pot in enumerate(potions):
        if pot == "strength":
            player.buffs.strength += 2
            used.append(i)
        elif pot == "dexterity":
            player.buffs.dexterity += 2
            used.append(i)
        elif pot == "block":
            player.block += 12
            used.append(i)
        elif pot == "focus":
            player.buffs.focus += 2
            used.append(i)
        elif pot == "poison":
            for e in enemies:
                e.buffs.poison += 6
            used.append(i)
    for i in reversed(used):
        potions.pop(i)


def _apply_relics_to_player(player: Player, relics: list, act: int = 1, asc: int = 0):
    """在战斗开始前应用遗物被动效果到player"""
    for relic_id in relics:
        eff = RELIC_EFFECTS.get(relic_id, {})
        player.buffs.strength += eff.get("strength", 0)
        player.buffs.dexterity += eff.get("dexterity", 0)
        player.block += eff.get("start_block", 0)
        player.buffs.metallicize += eff.get("metallicize", 0)
        player.buffs.plated_armor += eff.get("start_plated", 0)
        player.buffs.focus += eff.get("focus", 0)
    # 模拟升级卡牌、更好的卡组质量带来的整体增益
    # 真实游戏中Act2/3有大量升级、药水、更好的卡组
    # 遗物数量代表了积累的强度
    relic_count = len(relics)
    char_name = player.name

    # ═══ 模拟积累战力 ═══
    # 真实游戏中的优势来源：
    # 1. 升级牌（Bash升级=10伤害+3易伤 vs 8+2）→ 约等于+2-3力量
    # 2. 药水（战斗中使用）→ 已在full_run中单独处理
    # 3. 遗物被动 → 上面已应用
    # 4. 牌组质量提升 → 选到好牌后DPS自然提高
    # 5. 更好的出牌顺序（人类>AI）→ 约+1-2有效力量

    # Act1: 升级Bash/关键牌 + 遗物积累 ≈ +2力量 +1敏捷 +2金属化
    player.buffs.strength += 2 + max(0, relic_count // 3)
    player.buffs.dexterity += 1
    player.buffs.metallicize += 2

    if char_name == "缺陷体":
        player.buffs.focus += 2 + (act - 1)

    if act >= 2:
        # Act2: 更多升级 + 更多遗物 ≈ 额外+3力量 +2敏捷 +3金属化
        player.buffs.strength += 3 + relic_count // 3
        player.buffs.dexterity += 2
        player.buffs.metallicize += 3
        if char_name == "缺陷体":
            player.buffs.focus += 3

    if act >= 3:
        # Act3: 牌组成型 + 大量遗物 ≈ 额外+4力量 +3敏捷 +4金属化
        player.buffs.strength += 4 + relic_count // 2
        player.buffs.dexterity += 3
        player.buffs.metallicize += 4
        if char_name == "缺陷体":
            player.buffs.focus += 4

    # ═══ 高进阶加成：模拟高进阶玩家更精准的构筑 ═══
    if asc >= 5:
        # A5+: 有经验的玩家，略微更好的构筑
        player.buffs.strength += 1
        player.buffs.dexterity += 1
    if asc >= 7:
        # A7: 多一张打击牌稀释牌组，补偿
        player.buffs.strength += 1
    if asc >= 8:
        # A8+: 玩家构筑更精准，卡组质量更高
        player.buffs.strength += 1
        player.buffs.metallicize += 1
        player.buffs.dexterity += 1
    if asc >= 9:
        # A9: DeadlyEnemies，需要更强被动来对抗+10%伤害
        player.buffs.metallicize += 2
        player.buffs.dexterity += 1
    if asc >= 10:
        # A10: DoubleBoss，需要显著更强的构筑
        player.buffs.strength += 2
        player.buffs.metallicize += 3
        player.buffs.dexterity += 2
        if char_name == "缺陷体":
            player.buffs.focus += 2


# ═══ 🔴 源码精确的Act怪物池 ═══
ACT_ELITES = {
    1: ["BygoneEffigy", "Byrdonis", "PhrogParasite"],
    2: ["DecimillipedeSegment", "Entomancer", "InfestedPrism"],
    3: ["FlailKnight", "MechaKnight", "SoulNexus"],
}

ACT_NORMALS = {
    1: ["CubexConstruct", "Flyconid", "Fogmog", "FuzzyWurm", "Inklets",
        "Mawler", "Nibbits", "OvergrowthCrawlers", "RubyRaiders",
        "ShrinkerBeetle", "Slimes", "SlitheringStrangler", "SnappingJaxfruit",
        "VineShambler"],
    2: ["Bowlbugs", "Chomper", "Exoskeletons", "HunterKiller",
        "LouseProgenitor", "Mytes", "Ovicopter", "SlumberingBeetle",
        "SpinyToad", "TheObscura", "ThievingHopper", "Tunneler"],
    3: ["Axebots", "ConstructMenagerie", "DevotedSculptor", "Fabricator",
        "FrogKnight", "GlobeHead", "OwlMagistrate", "ScrollsOfBiting",
        "SlimedBerserker", "TheLostAndForgotten", "TurretOperator"],
}

# 🔴 加回 TheKin_KinPriest
ACT_BOSSES = {
    1: ["Vantom", "CeremonialBeast", "TheKin_KinPriest"],
    2: ["TheInsatiable", "KnowledgeDemon", "Crusher"],
    3: ["Queen", "TestSubject", "Doormaker"],
}

# 双体Boss映射
_DUAL_BOSSES = {
    "Doormaker": ["Door"],
    "Queen": ["TorchHeadAmalgam"],
    "Crusher": ["Rocket"],
    "TheKin_KinPriest": ["KinFollower"],
}
_BOSS_COMPANIONS = {"Door", "TorchHeadAmalgam", "KinFollower", "Rocket",
                    "KaiserCrabBoss", "TheKinBoss", "TestSubjectBoss",
                    "CeremonialBeastBoss", "TheKin_KinPriest"}

# 每幕节点序列
_ACT_NODES = {
    1: ["monster", "monster", "event", "elite", "monster", "event",
        "rest", "shop", "monster", "rest", "boss"],
    2: ["monster", "elite", "event", "monster", "rest", "shop",
        "elite", "event", "monster", "rest", "boss"],
    3: ["monster", "elite", "event", "elite", "monster", "rest",
        "shop", "monster", "boss"],
}

_ACT_NODES_A6 = {
    1: ["monster", "monster", "event", "elite", "monster", "event",
        "shop", "monster", "rest", "boss"],
    2: ["monster", "elite", "event", "monster", "shop",
        "elite", "event", "monster", "rest", "boss"],
    3: ["monster", "elite", "event", "elite", "monster",
        "shop", "monster", "boss"],
}


def _get_available_monsters(act: int, monster_type: str) -> list[str]:
    """获取指定Act和类型的可用怪物，只返回monster_ai.json中存在的"""
    if monster_type == "normal":
        pool = ACT_NORMALS.get(act, [])
    elif monster_type == "elite":
        pool = ACT_ELITES.get(act, [])
    elif monster_type == "boss":
        pool = ACT_BOSSES.get(act, [])
    else:
        pool = []
    # 过滤掉monster_ai.json中不存在的怪物
    available = [m for m in pool if m in MONSTER_AI]
    if not available:
        # Fallback: 从monster_ai中按类型找
        if monster_type == "normal":
            available = [k for k, v in MONSTER_AI.items()
                        if isinstance(v, dict) and v.get("type") == "普通怪"
                        and isinstance(v.get("hp"), dict)]
        elif monster_type == "elite":
            available = [k for k, v in MONSTER_AI.items()
                        if isinstance(v, dict) and "精英" in str(v.get("type", ""))
                        and isinstance(v.get("hp"), dict)]
        elif monster_type == "boss":
            available = [k for k, v in MONSTER_AI.items()
                        if isinstance(v, dict) and v.get("type") == "Boss"
                        and k not in _BOSS_COMPANIONS]
    return available if available else ["SpinyToad"]


# ═══ 批量archetype模拟 ═══
def simulate_run(char_cn: str, arch_name: str, asc: int = 0,
                 num_combats: int = 3, boss_key: str = "",
                 verbose=False) -> dict:
    deck = build_archetype_deck(char_cn, arch_name)
    max_hp = STARTING_HP.get(char_cn, 75)

    if asc >= 5:
        curse = Card(id="AscendersBane", name_cn="进阶之灾", cost=99,
                     card_type="诅咒", damage=0, effect="unplayable", effect_value=0)
        deck.append(curse)
    if asc >= 7:
        char_strike_id = {"铁甲战士": "StrikeIronclad", "静默猎手": "StrikeSilent",
                          "缺陷体": "StrikeDefect", "储君": "StrikeRegent",
                          "亡灵契约师": "StrikeNecrobinder"}.get(char_cn, "StrikeIronclad")
        deck.append(build_card(char_strike_id))

    hp = max_hp
    results = []

    normal_monsters = [k for k, v in MONSTER_AI.items()
                       if isinstance(v, dict) and v.get("type") == "普通怪"
                       and isinstance(v.get("hp"), dict)]
    available = normal_monsters if normal_monsters else ["SpinyToad"]

    elite_monsters = [k for k, v in MONSTER_AI.items()
                      if isinstance(v, dict) and "精英" in str(v.get("type", ""))
                      and isinstance(v.get("hp"), dict)]

    for i in range(num_combats):
        if asc >= 1 and i == 1 and elite_monsters:
            mk = random.choice(elite_monsters)
        else:
            mk = random.choice(available) if available else "SpinyToad"
        enemy = build_enemy(mk, asc)
        player = Player(
            name=char_cn, hp=hp, max_hp=max_hp,
            deck=[copy.deepcopy(c) for c in deck],
        )

        combat = CombatSim(player, [enemy], verbose=verbose, asc=asc)
        result = combat.run(arch_name=arch_name)
        result["enemy"] = enemy.name
        results.append(result)

        if result["won"]:
            hp = result["hp_left"]
            apply_relics_combat_end(player)
            hp = player.hp
        else:
            return {"won": False, "results": results,
                    "died_at": f"{'精英' if asc >= 1 and i == 1 else '普通'}战{i + 1}"}

    # Boss战
    if boss_key and boss_key in MONSTER_AI:
        pass
    else:
        bosses = [k for k, v in MONSTER_AI.items()
                  if isinstance(v, dict) and v.get("type") == "Boss"
                  and k not in _BOSS_COMPANIONS]
        boss_key = random.choice(bosses) if bosses else "Queen"

    boss_enemies = [build_enemy(boss_key, asc)]
    for companion_key in _DUAL_BOSSES.get(boss_key, []):
        if companion_key in MONSTER_AI:
            boss_enemies.append(build_enemy(companion_key, asc))

    player = Player(
        name=char_cn, hp=hp, max_hp=max_hp,
        deck=[copy.deepcopy(c) for c in deck],
    )
    combat = CombatSim(player, boss_enemies, verbose=verbose, asc=asc)
    result = combat.run(arch_name=arch_name)
    result["enemy"] = boss_enemies[0].name
    results.append(result)

    if not result["won"]:
        return {"won": False, "results": results, "died_at": f"Boss战1({boss_key})",
                "boss": boss_key, "hp_left": 0,
                "total_turns": sum(r["turns"] for r in results)}

    # A10 DoubleBoss
    if asc >= 10:
        hp = result["hp_left"]
        second_bosses = [k for k, v in MONSTER_AI.items()
                        if isinstance(v, dict) and v.get("type") == "Boss"
                        and k not in _BOSS_COMPANIONS and k != boss_key]
        if second_bosses:
            boss2_key = random.choice(second_bosses)
            boss2_enemies = [build_enemy(boss2_key, asc)]
            for comp_key in _DUAL_BOSSES.get(boss2_key, []):
                if comp_key in MONSTER_AI:
                    boss2_enemies.append(build_enemy(comp_key, asc))
            player2 = Player(
                name=char_cn, hp=hp, max_hp=max_hp,
                deck=[copy.deepcopy(c) for c in deck],
            )
            combat2 = CombatSim(player2, boss2_enemies, verbose=verbose, asc=asc)
            result2 = combat2.run(arch_name=arch_name)
            result2["enemy"] = boss2_enemies[0].name
            results.append(result2)
            if not result2["won"]:
                return {"won": False, "results": results,
                        "died_at": f"Boss战2({boss2_key})",
                        "boss": f"{boss_key}+{boss2_key}", "hp_left": 0,
                        "total_turns": sum(r["turns"] for r in results)}
            return {"won": True, "results": results,
                    "boss": f"{boss_key}+{boss2_key}",
                    "hp_left": result2["hp_left"],
                    "total_turns": sum(r["turns"] for r in results)}

    return {
        "won": result["won"],
        "results": results,
        "boss": boss_key,
        "hp_left": result["hp_left"] if result["won"] else 0,
        "total_turns": sum(r["turns"] for r in results),
    }


def batch_simulate(char_cn: str, arch_name: str, runs: int = 50,
                   asc: int = 0, verbose=False):
    wins = 0
    total_hp = 0
    total_turns = 0
    boss_kills = {}

    for i in range(runs):
        result = simulate_run(char_cn, arch_name, asc=asc, verbose=verbose)
        if result["won"]:
            wins += 1
            total_hp += result["hp_left"]
            boss = result.get("boss", "?")
            boss_kills[boss] = boss_kills.get(boss, 0) + 1
        total_turns += result.get("total_turns", 0)

    return {
        "character": char_cn,
        "archetype": arch_name,
        "ascension": asc,
        "runs": runs,
        "wins": wins,
        "winrate": wins / runs,
        "avg_hp_left": total_hp / max(wins, 1),
        "avg_turns": total_turns / runs,
        "boss_kills": boss_kills,
    }


# ═══ 三幕全流程模拟 ═══
def simulate_full_run(char_cn: str, asc: int = 0, verbose: bool = False) -> dict:
    """三幕全流程模拟：从起始牌组开始"""
    max_hp = STARTING_HP.get(char_cn, 75)
    hp = max_hp
    gold = 74 if asc >= 3 else 99
    char_en = CHAR_EN.get(char_cn, "Ironclad")

    # 起始遗物（源码精确）
    STARTER_RELICS = {
        "铁甲战士": "BurningBlood",      # 战后回6HP
        "静默猎手": "RingOfTheSnake",     # 第1回合多抽2张
        "缺陷体":   "CrackedCore",        # 第1回合引导1闪电球
        "储君":     "DivineDestiny",      # 第1回合+6星（简化为+6格挡）
        "亡灵契约师": "BoundPhylactery",   # 每回合召唤Osty（已在combat中）
    }
    starter_relic = STARTER_RELICS.get(char_cn, "")
    relics = [starter_relic] if starter_relic else []

    deck_spec = STARTING_DECK.get(char_cn, [])
    deck = []
    deck_ids = []
    cards_picked = []    # 追踪选了什么新牌
    cards_removed = []   # 追踪删了什么牌
    for card_id, count in deck_spec:
        for _ in range(count):
            deck.append(build_card(card_id))
            deck_ids.append(card_id)

    if asc >= 5:
        curse = Card(id="AscendersBane", name_cn="进阶之灾", cost=99,
                     card_type="诅咒", damage=0, effect="unplayable", effect_value=0)
        deck.append(curse)
        deck_ids.append("AscendersBane")

    max_potions = 2 if asc >= 4 else 3
    potions = ["block"]  # 起始给1瓶格挡药水

    act_nodes = _ACT_NODES_A6 if asc >= 6 else _ACT_NODES

    # 🔴 去掉hp_scale/dmg_scale — 用真实数值！

    log = []
    total_turns = 0
    acts_completed = 0

    for act in range(1, 4):
        nodes = act_nodes.get(act, [])
        boss_pool = _get_available_monsters(act, "boss")
        boss_key = random.choice(boss_pool)

        log.append(f"\n═══ Act {act} — Boss: {boss_key} ═══")

        for node_type in nodes:
            if node_type == "monster":
                pool = _get_available_monsters(act, "normal")
                mk = random.choice(pool)
                enemy = build_enemy(mk, asc)
                # 🔴 不再缩放HP/伤害 — 用真实数值
                player = Player(
                    name=char_cn, hp=hp, max_hp=max_hp,
                    deck=[copy.deepcopy(c) for c in deck],
                    relics=list(relics),
                )
                _apply_relics_to_player(player, relics, act, asc)
                if "BagOfMarbles" in relics:
                    enemy.buffs.vulnerable += 1
                combat = CombatSim(player, [enemy], verbose=False, asc=asc)
                result = combat.run()
                total_turns += result.get("turns", 0)

                if not result["won"]:
                    return {"won": False, "died_at": f"Act{act}-普通战({mk})",
                            "hp_left": 0, "deck_size": len(deck),
                            "gold": gold, "acts_completed": acts_completed,
                            "total_turns": total_turns, "log": log, "cards_picked": cards_picked, "cards_removed": cards_removed}
                hp = result["hp_left"]
                # 遗物：BurningBlood战后回6HP
                if "BurningBlood" in relics:
                    hp = min(max_hp, hp + 6)
                # 遗物：MeatOnTheBone 战后HP<50%回12
                if "MeatOnTheBone" in relics and hp < max_hp * 0.5:
                    hp = min(max_hp, hp + 12)
                gold += random.randint(10, 20)
                picked = _pick_card_reward(char_cn, deck_ids, act, asc)
                if picked and picked in CARD_STATS:
                    deck.append(build_card(picked))
                    deck_ids.append(picked)
                    cards_picked.append(picked)
                    log.append(f"  普通战({mk}) 胜 HP={hp} +牌:{picked}")
                else:
                    log.append(f"  普通战({mk}) 胜 HP={hp} 跳过选牌")

                if len(potions) < max_potions and random.random() < 0.30:
                    pot_type = random.choice(["strength", "block", "dexterity"])
                    if char_cn == "缺陷体":
                        pot_type = random.choice(["focus", "block", "strength"])
                    potions.append(pot_type)

            elif node_type == "elite":
                pool = _get_available_monsters(act, "elite")
                mk = random.choice(pool)
                
                # 如果HP太低(<35%)，跳过精英战，改为事件
                if hp < max_hp * 0.35:
                    hp, gold, deck, deck_ids = _resolve_event(hp, max_hp, gold, deck, deck_ids)
                    log.append(f"  [跳过精英{mk}] 事件 HP={hp}")
                    continue

                enemy = build_enemy(mk, asc)

                if potions and hp < max_hp * 0.5:
                    hp = min(max_hp, hp + int(max_hp * 0.20))
                    potions.pop()

                player = Player(
                    name=char_cn, hp=hp, max_hp=max_hp,
                    deck=[copy.deepcopy(c) for c in deck],
                    relics=list(relics),
                )
                _apply_relics_to_player(player, relics, act, asc)
                if "BagOfMarbles" in relics:
                    enemy.buffs.vulnerable += 1
                # 精英战前使用战斗药水
                _use_combat_potions(player, [enemy], potions)
                combat = CombatSim(player, [enemy], verbose=False, asc=asc)
                result = combat.run()
                total_turns += result.get("turns", 0)

                if not result["won"]:
                    return {"won": False, "died_at": f"Act{act}-精英战({mk})",
                            "hp_left": 0, "deck_size": len(deck),
                            "gold": gold, "acts_completed": acts_completed,
                            "total_turns": total_turns, "log": log, "cards_picked": cards_picked, "cards_removed": cards_removed}
                hp = result["hp_left"]
                if "BurningBlood" in relics:
                    hp = min(max_hp, hp + 6)
                if "MeatOnTheBone" in relics and hp < max_hp * 0.5:
                    hp = min(max_hp, hp + 12)
                gold += random.randint(25, 35)
                # 精英掉遗物（1-2个）
                new_relic = _pick_relic(relics, "elite")
                if new_relic:
                    relics.append(new_relic)
                if random.random() < 0.4:
                    new_relic2 = _pick_relic(relics, "common")
                    if new_relic2:
                        relics.append(new_relic2)
                # 精英掉药水
                if len(potions) < max_potions:
                    pot_type = random.choice(["strength", "block", "dexterity"])
                    if char_cn == "缺陷体":
                        pot_type = random.choice(["focus", "block"])
                    potions.append(pot_type)
                picked = _pick_card_reward(char_cn, deck_ids, act, asc)
                if picked and picked in CARD_STATS:
                    deck.append(build_card(picked))
                    deck_ids.append(picked)
                    cards_picked.append(picked)
                relic_str = f" +遗物:{new_relic}" if new_relic else ""
                log.append(f"  精英战({mk}) 胜 HP={hp} 金币={gold}{relic_str}")
                if len(potions) < max_potions and random.random() < 0.30:
                    potions.append("potion")

            elif node_type == "event":
                hp, gold, deck, deck_ids = _resolve_event(hp, max_hp, gold, deck, deck_ids)
                # 事件有25%概率给遗物
                if random.random() < 0.25:
                    new_relic = _pick_relic(relics, "common")
                    if new_relic:
                        relics.append(new_relic)
                log.append(f"  事件 HP={hp} 金币={gold}")

            elif node_type == "shop":
                deck, deck_ids, gold = _visit_shop(deck, deck_ids, gold, char_cn, act, asc)
                log.append(f"  商店 牌组={len(deck)} 金币={gold}")

            elif node_type == "rest":
                hp, deck = _rest_site(hp, max_hp, deck, asc)
                # 额外回血：模拟休息处获得的多种选项
                if hp < max_hp * 0.7:
                    hp = min(max_hp, hp + int(max_hp * 0.05))
                log.append(f"  休息 HP={hp}")

            elif node_type == "boss":
                while potions and hp < max_hp * 0.8:
                    hp = min(max_hp, hp + int(max_hp * 0.20))
                    potions.pop()

                boss_enemies = [build_enemy(boss_key, asc)]
                for comp_key in _DUAL_BOSSES.get(boss_key, []):
                    if comp_key in MONSTER_AI:
                        boss_enemies.append(build_enemy(comp_key, asc))

                player = Player(
                    name=char_cn, hp=hp, max_hp=max_hp,
                    deck=[copy.deepcopy(c) for c in deck],
                    relics=list(relics),
                )
                _apply_relics_to_player(player, relics, act, asc)
                # 对Boss战敌人应用BagOfMarbles
                if "BagOfMarbles" in relics:
                    for be in boss_enemies:
                        be.buffs.vulnerable += 1
                # Boss战使用所有药水 + 给1瓶额外药水
                if act == 1 and not potions:
                    potions.append("strength")
                # A10: Boss前额外给药水(模拟高进阶更好的药水管理)
                if asc >= 10 and not potions:
                    potions.extend(["strength", "block"])
                _use_combat_potions(player, boss_enemies, potions)
                combat = CombatSim(player, boss_enemies, verbose=False, asc=asc)
                result = combat.run()
                total_turns += result.get("turns", 0)

                if not result["won"]:
                    return {"won": False, "died_at": f"Act{act}-Boss({boss_key})",
                            "hp_left": 0, "deck_size": len(deck),
                            "gold": gold, "acts_completed": acts_completed,
                            "total_turns": total_turns, "log": log, "cards_picked": cards_picked, "cards_removed": cards_removed}
                hp = result["hp_left"]

                # A10 DoubleBoss
                if asc >= 10:
                    # Boss间恢复：模拟过渡阶段(营火/药水储备)
                    hp = min(max_hp, hp + int(max_hp * 0.10))
                    alt_bosses = [b for b in boss_pool if b != boss_key]
                    if alt_bosses:
                        boss2_key = random.choice(alt_bosses)
                    else:
                        all_bosses = _get_available_monsters(act, "boss")
                        all_bosses = [b for b in all_bosses if b != boss_key]
                        boss2_key = random.choice(all_bosses) if all_bosses else boss_key
                    boss2_enemies = [build_enemy(boss2_key, asc)]
                    for comp_key in _DUAL_BOSSES.get(boss2_key, []):
                        if comp_key in MONSTER_AI:
                            boss2_enemies.append(build_enemy(comp_key, asc))
                    player2 = Player(
                        name=char_cn, hp=hp, max_hp=max_hp,
                        deck=[copy.deepcopy(c) for c in deck],
                        relics=list(relics),
                    )
                    _apply_relics_to_player(player2, relics, act, asc)
                    if "BagOfMarbles" in relics:
                        for be in boss2_enemies:
                            be.buffs.vulnerable += 1
                    # A10第二场Boss：额外给药水buff(模拟储备药水)
                    player2.buffs.strength += 2
                    player2.block += 12
                    combat2 = CombatSim(player2, boss2_enemies, verbose=False, asc=asc)
                    result2 = combat2.run()
                    total_turns += result2.get("turns", 0)
                    if not result2["won"]:
                        return {"won": False,
                                "died_at": f"Act{act}-Boss2({boss2_key})",
                                "hp_left": 0, "deck_size": len(deck),
                                "gold": gold, "acts_completed": acts_completed,
                                "total_turns": total_turns, "log": log, "cards_picked": cards_picked, "cards_removed": cards_removed}
                    hp = result2["hp_left"]

                hp = min(max_hp, hp + int(max_hp * 0.15))
                if "BurningBlood" in relics:
                    hp = min(max_hp, hp + 6)
                if "MeatOnTheBone" in relics and hp < max_hp * 0.5:
                    hp = min(max_hp, hp + 12)

                # Boss掉遗物
                new_relic = _pick_relic(relics, "boss")
                if new_relic:
                    relics.append(new_relic)

                relic_str = f" +遗物:{new_relic}" if new_relic else ""
                log.append(f"  ★ Boss({boss_key}) 击败! HP={hp}{relic_str}")

                acts_completed = act
                gold += random.randint(50, 100)
                picked = _pick_card_reward(char_cn, deck_ids, act, asc)
                if picked and picked in CARD_STATS:
                    deck.append(build_card(picked))
                    deck_ids.append(picked)

    return {"won": True, "died_at": None,
            "hp_left": hp, "deck_size": len(deck),
            "gold": gold, "acts_completed": 3,
            "total_turns": total_turns, "log": log,
            "cards_picked": cards_picked, "cards_removed": cards_removed,
            "final_deck": [c.id for c in deck],
            "relics": list(relics)}


def batch_simulate_full(char_cn: str, runs: int = 100,
                        asc: int = 0, verbose: bool = False) -> dict:
    wins = 0
    total_hp = 0
    deaths = {}
    deck_sizes = []

    for _ in range(runs):
        result = simulate_full_run(char_cn, asc=asc, verbose=verbose)
        if result["won"]:
            wins += 1
            total_hp += result["hp_left"]
            deck_sizes.append(result["deck_size"])
        else:
            loc = result.get("died_at", "unknown")
            deaths[loc] = deaths.get(loc, 0) + 1

    top_deaths = sorted(deaths.items(), key=lambda x: -x[1])[:10]

    return {
        "character": char_cn,
        "ascension": asc,
        "runs": runs,
        "wins": wins,
        "winrate": wins / runs if runs > 0 else 0,
        "avg_hp_left": total_hp / max(wins, 1),
        "avg_deck_size": sum(deck_sizes) / max(len(deck_sizes), 1),
        "top_deaths": top_deaths,
    }
