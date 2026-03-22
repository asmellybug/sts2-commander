"""STS2 模拟器 — 流派牌组构建"""
from .entities import Card
from .data_loader import (
    ARCHETYPES, CARD_STATS, CHAR_EN, build_card,
)


def build_archetype_deck(char_cn: str, arch_name: str) -> list[Card]:
    char_data = ARCHETYPES.get("characters", {}).get(char_cn, {})
    arch_data = char_data.get("archetypes", {}).get(arch_name, {})

    core = arch_data.get("core_cards", [])
    support = arch_data.get("support_cards", [])

    deck = []
    char_en = CHAR_EN.get(char_cn, "Ironclad")

    is_exhaust = "消耗" in arch_name
    is_doom = "灾厄" in arch_name or "Doom" in arch_name
    is_osty = "Osty" in arch_name or "召唤" in arch_name

    if is_exhaust:
        deck.append(build_card(f"Strike{char_en}"))
        deck.append(build_card(f"Strike{char_en}"))
        deck.append(build_card(f"Defend{char_en}"))
        deck.append(build_card(f"Defend{char_en}"))
    elif is_doom:
        deck.append(build_card(f"Strike{char_en}"))
        deck.append(build_card(f"Strike{char_en}"))
        deck.append(build_card("DefendNecrobinder"))
        deck.append(build_card("DefendNecrobinder"))
        deck.append(build_card("BoneSpear"))
    elif is_osty:
        deck.append(build_card(f"Strike{char_en}"))
        deck.append(build_card("DefendNecrobinder"))
        deck.append(build_card("SummonOsty"))
    else:
        deck.append(build_card(f"Strike{char_en}"))
        deck.append(build_card(f"Strike{char_en}"))
        deck.append(build_card(f"Defend{char_en}"))
        deck.append(build_card(f"Defend{char_en}"))

    # 核心牌（升级版）
    for c in core:
        cid = c.get("id", "")
        if cid and cid in CARD_STATS:
            deck.append(build_card(cid, upgraded=True))

    # 辅助牌
    support_count = 6 if len(core) <= 3 else 5
    for c in support[:support_count]:
        cid = c.get("id", "")
        if cid and cid in CARD_STATS:
            deck.append(build_card(cid))

    # 流派特殊牌组
    _EXTRA_CARDS = {
        "消耗流": {
            "upgraded": ["Metallicize", "ShrugItOff", "FlameBarrier", "Inflame", "DemonForm",
                         "Bash", "Mangle", "Uppercut", "Mangle"],
            "normal": ["DefendIronclad"] * 5 + ["StrikeIronclad"] * 8,
        },
        "弃牌流": {
            "upgraded": ["Eviscerate", "BladeDance", "BladeDance", "Footwork",
                         "Backflip", "AfterImage", "Accuracy"],
        },
        "自伤流": {
            "mixed": [("ShrugItOff", False), ("FlameBarrier", False),
                      ("Metallicize", True), ("Rupture", False),
                      ("Barricade", True), ("DefendIronclad", False),
                      ("DefendIronclad", False), ("BodySlam", False)],
        },
        "重击流": {
            "upgraded": ["Glow", "Glow", "Conqueror", "Guards", "Guards",
                         "DefendRegent", "DefendRegent", "DefendRegent",
                         "DefendRegent", "DefendRegent"],
        },
        "连击流": {
            "normal": ["ShrugItOff", "ShrugItOff", "FlameBarrier",
                       "DefendIronclad", "DefendIronclad", "DefendIronclad"],
        },
        "喂食回血流": {
            "normal": ["ShrugItOff", "ShrugItOff", "FlameBarrier",
                       "DefendIronclad", "DefendIronclad", "DefendIronclad"],
        },
        "打击流": {
            "normal": ["ShrugItOff", "FlameBarrier", "DefendIronclad", "DefendIronclad"]
                      + ["StrikeIronclad"] * 6,
        },
        "暗杀流": {
            "normal": ["BladeDance", "BladeDance", "Backflip", "Backflip",
                       "DodgeAndRoll", "DefendSilent", "DefendSilent"],
        },
        "幽灵防御流": {
            "normal": ["Backflip", "Backflip", "DodgeAndRoll",
                       "DefendSilent", "DefendSilent", "DefendSilent", "DefendSilent"],
        },
        "超载爆发流": {
            "normal": ["BootSequence", "BoostAway", "ShadowShield",
                       "DefendDefect", "DefendDefect", "DefendDefect"],
        },
        "能量循环流": {
            "normal": ["BootSequence", "BoostAway", "ShadowShield",
                       "DefendDefect", "DefendDefect"],
        },
        "冰霜护盾流": {
            "normal": ["Coolheaded", "Glacier", "ShadowShield",
                       "DefendDefect", "DefendDefect", "DefendDefect"],
        },
        "粒子防御流": {
            "upgraded": ["BeatIntoShape", "BeatIntoShape", "Conqueror",
                         "Guards", "CloakOfStars", "Glow", "Glow"],
        },
        "虚空形态流": {
            "normal": ["Glow", "Glow", "Guards", "DefendRegent",
                       "DefendRegent", "CloakOfStars", "BeatIntoShape"],
        },
        "高费斩杀流": {
            "normal": ["DefendNecrobinder"] * 4 + ["Scourge", "Haunt"],
            "extra_base": ["BoneSpear", "BoneSpear"],
        },
        "恐惧削弱流": {
            "normal": ["DefendNecrobinder"] * 3 + ["Scourge", "Haunt"],
            "extra_base": ["BoneSpear"],
        },
        "墓地回收流": {
            "normal": ["DefendNecrobinder"] * 3 + ["Scourge"],
            "extra_base": ["BoneSpear", "SummonOsty"],
        },
    }

    extra = _EXTRA_CARDS.get(arch_name, {})
    for eid in extra.get("extra_base", []):
        deck.append(build_card(eid))
    for eid in extra.get("upgraded", []):
        if eid in CARD_STATS:
            deck.append(build_card(eid, upgraded=True))
    for eid in extra.get("normal", []):
        if eid in CARD_STATS:
            deck.append(build_card(eid))
    for eid, up in extra.get("mixed", []):
        if eid in CARD_STATS:
            deck.append(build_card(eid, upgraded=up))

    # 0费速攻流 (角色分支)
    if arch_name == "0费速攻流" and char_cn == "静默猎手":
        for eid in ["BladeDance", "BladeDance", "Backflip",
                    "DodgeAndRoll", "DefendSilent", "DefendSilent"]:
            if eid in CARD_STATS:
                deck.append(build_card(eid))
    elif arch_name == "0费速攻流" and char_cn == "储君":
        for eid in ["Glow", "Glow", "DefendRegent", "DefendRegent",
                    "Guards", "CloakOfStars"]:
            if eid in CARD_STATS:
                deck.append(build_card(eid))

    # 确保至少12张
    while len(deck) < 12:
        if is_doom or is_osty:
            deck.append(build_card("DefendNecrobinder"))
        else:
            deck.append(build_card(f"Defend{char_en}"))

    return deck
