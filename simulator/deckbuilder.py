"""STS2 模拟器 — 构筑AI（选牌/商店/事件/休息）"""
import random
from typing import Optional
from .entities import Card
from .data_loader import (
    ARCHETYPES, CARD_STATS, CHAR_CARDS, TIER_LIST, CHAR_EN, build_card,
)


# ═══ 角色核心卡（必须尽早拿到）═══
CHAR_CORE_CARDS = {
    "铁甲战士": {
        # S级（看到必拿）
        "must_pick": ["DemonForm", "Barricade", "Impervious", "Offering",
                      "Corruption", "Inflame", "PommelStrike", "BattleTrance",
                      "ShrugItOff", "FeelNoPain", "Bludgeon", "FiendFire"],
        # A级（优先拿）
        "prefer": ["Metallicize", "Disarm", "Uppercut", "FlameBarrier",
                   "BodySlam", "DarkEmbrace", "SecondWind",
                   "OneTwoPunch", "Unmovable", "TrueGrit",
                   "Hemokinesis", "Whirlwind", "Feed", "Colossus",
                   "IronWave", "Rampage", "Rage", "Aggression",
                   "DemonicShield", "BurningPact", "Bloodletting"],
    },
    "静默猎手": {
        "must_pick": ["NoxiousFumes", "WraithForm", "Malaise", "Adrenaline",
                      "BladeDance", "Backstab", "Predator",
                      "Acrobatics", "EscapePlan", "Footwork",
                      "Afterimage", "LegSweep", "DeadlyPoison"],
        "prefer": ["Dash", "CloakAndDagger", "WellLaidPlans",
                   "Finisher", "Backflip", "Blur", "Envenom",
                   "Accuracy", "InfiniteBlades", "Burst",
                   "DodgeAndRoll", "Deflect", "CalculatedGamble",
                   "BouncingFlask", "CorrosiveWave", "Slice",
                   "PiercingWail", "Neutralize", "SuckerPunch"],
    },
    "缺陷体": {
        "must_pick": ["Defragment", "EchoForm", "Glacier", "Capacitor",
                      "ColdSnap", "BiasedCognition",
                      "Buffer", "Loop", "AllForOne", "Chill"],
        "prefer": ["ChargeBattery", "Coolheaded", "BallLightning",
                   "SelfRepair", "Hologram", "CompileDriver",
                   "BoostAway", "Fusion", "SweepingBeam",
                   "MachineLearning", "Overclock", "Turbo",
                   "DoubleEnergy", "Coolant", "ShadowShield",
                   "Hyperbeam", "MeteorStrike", "Storm",
                   "Rainbow", "Hailstorm", "Thunder"],
    },
    "储君": {
        "must_pick": ["FallingStar", "HeavenlyDrill",
                      "ParticleWall", "AstralPulse", "GammaBlast",
                      "BigBang", "Stoke", "Glow", "Furnace",
                      "ManifestAuthority", "BlackHole", "VoidForm"],
        "prefer": ["Reflect", "CollisionCourse", "Parry",
                   "Prophesize", "NeutronAegis", "CloakOfStars",
                   "Bulwark", "Hegemony", "CelestialMight",
                   "MonarchsGaze", "Monologue", "SevenStars",
                   "SpoilsOfBattle", "Bombardment", "Conqueror",
                   "Radiate", "Guards", "PillarOfCreation"],
    },
    "亡灵契约师": {
        "must_pick": ["SummonOsty", "Defile", "Misery", "Graveblast",
                      "Haunt", "ConsumingShadow", "EndOfDays",
                      "ReaperForm", "Countdown", "BansheesCry",
                      "DanseMacabre", "Fear", "Calcify"],
        "prefer": ["SpiritOfAsh", "Tyranny", "Shroud",
                   "BlightStrike", "CaptureSpirit", "PullFromBelow",
                   "SoulStorm", "Bodyguard", "DeathsDoor",
                   "Bury", "Reap", "Sacrifice", "Deathbringer",
                   "Debilitate", "EnfeeblingTouch", "Veilpiercer",
                   "Pagestorm", "Unleash", "RightHandHand",
                   "HighFive", "SicEm", "Snap"],
    },
}


# ═══ Synergy检测 ═══
_SYNERGY_TAGS = {
    "poison": ["Poison", "毒", "Noxious", "Envenom", "BouncingFlask",
               "CripplingPoison", "DeadlyPoison", "Catalyst", "Bane",
               "NoxiousFume", "CorpseExplosion", "PoisonousStab"],
    "strength": ["Strength", "力量", "Inflame", "Spot", "DemonForm",
                 "HeavyBlade", "SwordBoomerang", "PommelStrike",
                 "Uppercut", "Pummel", "Reaper", "LimitBreak"],
    "focus": ["Focus", "集中", "Defragment", "Consume", "Inserter",
              "Capacitor", "BiasedCognition", "CoreSurge"],
    "orb": ["Orb", "充能球", "Zap", "Dualcast", "BallLightning",
            "ColdSnap", "Glacier", "Blizzard", "Tempest", "Doom"],
    "block": ["Block", "格挡", "Barricade", "Entrench", "BodySlam",
              "Metallicize", "ShrugItOff", "Impervious", "FlameBarrier"],
    "exhaust": ["Exhaust", "消耗", "Corruption", "FeelNoPain",
                "DarkEmbrace", "Sentinel", "SecondWind"],
    "doom_tag": ["灾厄", "Doom", "Shroud", "Countdown", "Reaper"],
}

_TIER_SCORE = {"S": 12, "A": 9, "B": 6, "C": 3, "D": 0, "F": -5}


def _detect_synergies(deck_ids: list) -> dict:
    counts = {}
    for tag, keywords in _SYNERGY_TAGS.items():
        c = sum(1 for cid in deck_ids if any(kw.lower() in cid.lower() for kw in keywords))
        if c >= 2:
            counts[tag] = c
    return counts


def _score_card_for_pick(card_entry: dict, char_cn: str, deck_ids: list,
                         act: int) -> float:
    cid = card_entry.get("id", "")

    # ─── 角色核心卡优先 ───
    char_core = CHAR_CORE_CARDS.get(char_cn, {})
    if cid in char_core.get("must_pick", []):
        # 已经有2张了就不拿了
        copies = deck_ids.count(cid)
        if copies >= 2:
            return 8
        return 20  # 无条件拿
    if cid in char_core.get("prefer", []):
        copies = deck_ids.count(cid)
        if copies >= 2:
            return 5
        return 14  # 优先拿

    # ─── Tier评分 ───
    char_tiers = TIER_LIST.get(char_cn, {})
    tier_data = char_tiers.get(cid, {})
    tier_map = tier_data.get("tier", {}) if isinstance(tier_data, dict) else {}

    phase = "early" if act == 1 else ("mid" if act == 2 else "late")
    tier_letter = tier_map.get(phase, "C") if isinstance(tier_map, dict) else "C"
    score = _TIER_SCORE.get(tier_letter, 3)

    # ─── Synergy加分 ───
    synergies = _detect_synergies(deck_ids)
    for tag, count in synergies.items():
        keywords = _SYNERGY_TAGS[tag]
        if any(kw.lower() in cid.lower() for kw in keywords):
            score += min(count, 4) * 2

    # ─── 基础打击/防御惩罚 ───
    if "Strike" in cid and any(c in cid for c in ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]):
        score -= 10
    if "Defend" in cid and any(c in cid for c in ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]):
        score -= 8

    # ─── 稀有度加分 ───
    rarity = card_entry.get("rarity", "普通")
    if rarity == "稀有":
        score += 3
    elif rarity == "罕见":
        score += 1

    # ─── 牌组质量控制 ───
    deck_size = len(deck_ids)
    if deck_size >= 28:
        score -= 3  # 牌组太大，扣分
    elif deck_size >= 23:
        score -= 1

    # ─── 避免重复 ───
    copies = deck_ids.count(cid)
    if copies >= 2:
        score -= 5  # 已有2张以上，扣分
    elif copies >= 1:
        score -= 1  # 已有1张，轻微扣分

    return score


def _pick_card_reward(char_cn: str, deck_ids: list, act: int, asc: int) -> Optional[str]:
    pool = CHAR_CARDS.get(char_cn, [])
    if not pool:
        return None

    rare_rate = 0.015 if asc >= 7 else 0.03
    weights = []
    for c in pool:
        r = c.get("rarity", "普通")
        if r == "稀有":
            weights.append(rare_rate)
        elif r == "罕见":
            weights.append(0.37)
        elif r in ("基础", "CardRarity.Ancient"):
            weights.append(0.001)
        else:
            weights.append(0.60)

    if len(pool) < 3:
        choices = pool[:]
    else:
        choices = random.choices(pool, weights=weights, k=3)
        seen = set()
        unique = []
        for c in choices:
            if c["id"] not in seen:
                seen.add(c["id"])
                unique.append(c)
        choices = unique

    if not choices:
        return None

    best_card = None
    best_score = -999
    for c in choices:
        s = _score_card_for_pick(c, char_cn, deck_ids, act)
        if s > best_score:
            best_score = s
            best_card = c

    # 动态skip阈值：Act1积极拿牌，后期挑剔
    # 高进阶更挑剔（只拿好牌，减少废牌）
    deck_size = len(deck_ids)
    if act == 1:
        skip_threshold = 2 if asc >= 8 else 1
    elif act == 2:
        if asc >= 8:
            skip_threshold = 5 if deck_size < 18 else 7
        else:
            skip_threshold = 3 if deck_size < 18 else 5
    else:
        if asc >= 8:
            skip_threshold = 6 if deck_size < 20 else 8
        else:
            skip_threshold = 4 if deck_size < 20 else 6

    if best_score < skip_threshold:
        return None

    return best_card["id"] if best_card else None


def _visit_shop(deck: list, deck_ids: list, gold: int, char_cn: str, act: int, asc: int):
    char_en = CHAR_EN.get(char_cn, "Ironclad")
    strike_id = f"Strike{char_en}"
    remove_cost = 75

    # 优先移除打击牌（高进阶更积极删牌）
    remove_attempts = 2 if asc >= 5 else 1
    for _ in range(remove_attempts):
        if gold >= remove_cost and strike_id in deck_ids:
            for i, c in enumerate(deck):
                if c.id == strike_id:
                    deck.pop(i)
                    deck_ids.remove(strike_id)
                    gold -= remove_cost
                    break

    # A8+: 也移除基础防御牌（如果牌组有更好的格挡牌）
    if asc >= 8 and gold >= remove_cost:
        defend_id = f"Defend{char_en}"
        has_good_blocks = sum(1 for cid in deck_ids if cid in (
            "ShrugItOff", "Impervious", "FlameBarrier", "Backflip",
            "EscapePlan", "Glacier", "Hologram", "ParticleWall",
            "DeathsDoor", "Calcify", "Bodyguard")) >= 2
        if has_good_blocks and defend_id in deck_ids:
            for i, c in enumerate(deck):
                if c.id == defend_id:
                    deck.pop(i)
                    deck_ids.remove(defend_id)
                    gold -= remove_cost
                    break

    # 如果还有钱，移除诅咒
    if gold >= remove_cost:
        curse_ids = [c.id for c in deck if c.card_type == "诅咒"]
        if curse_ids:
            for i, c in enumerate(deck):
                if c.card_type == "诅咒":
                    deck.pop(i)
                    if c.id in deck_ids:
                        deck_ids.remove(c.id)
                    gold -= remove_cost
                    break

    buy_cost = random.randint(75, 150)
    if gold >= buy_cost:
        picked = _pick_card_reward(char_cn, deck_ids, act, asc)
        if picked and picked in CARD_STATS:
            deck.append(build_card(picked))
            deck_ids.append(picked)
            gold -= buy_cost

    return deck, deck_ids, gold


def _resolve_event(player_hp: int, max_hp: int, gold: int,
                   deck: list, deck_ids: list) -> tuple:
    roll = random.random()
    if roll < 0.30:
        gold += random.randint(20, 40)
    elif roll < 0.55:
        gold += random.randint(50, 100)
    elif roll < 0.75:
        hp_loss = random.randint(5, 15)
        player_hp = max(1, player_hp - hp_loss)
        gold += random.randint(50, 80)
    elif roll < 0.90:
        non_upgraded = [i for i, c in enumerate(deck) if not c.upgraded and c.card_type != "诅咒"]
        if non_upgraded:
            idx = random.choice(non_upgraded)
            deck[idx].upgraded = True
            if deck[idx].damage > 0:
                deck[idx].damage += 3
            if deck[idx].block > 0:
                deck[idx].block += 3
    else:
        if random.random() < 0.5:
            player_hp = max(1, player_hp - random.randint(8, 18))
        else:
            curse = Card(id="Regret", name_cn="遗憾", cost=99,
                         card_type="诅咒", damage=0, effect="unplayable", effect_value=0)
            deck.append(curse)
            deck_ids.append("Regret")

    return player_hp, gold, deck, deck_ids


def _rest_site(player_hp: int, max_hp: int, deck: list, asc: int) -> tuple:
    heal_pct = 0.20 if asc >= 2 else 0.30

    hp_ratio = player_hp / max_hp
    if hp_ratio < 0.60:
        do_heal = True
    elif hp_ratio > 0.80:
        do_heal = False
    else:
        do_heal = random.random() < 0.5

    if do_heal:
        heal = int(max_hp * heal_pct)
        player_hp = min(max_hp, player_hp + heal)
    else:
        candidates = [(i, c) for i, c in enumerate(deck)
                      if not c.upgraded and c.card_type != "诅咒"
                      and "Strike" not in c.id and "Defend" not in c.id]
        if not candidates:
            candidates = [(i, c) for i, c in enumerate(deck)
                          if not c.upgraded and c.card_type != "诅咒"]
        if candidates:
            idx, card = random.choice(candidates)
            deck[idx].upgraded = True
            if deck[idx].damage > 0:
                deck[idx].damage += 3
            if deck[idx].block > 0:
                deck[idx].block += 3

    return player_hp, deck
