"""STS2 模拟器 — 数据加载 & 卡牌/敌人构建"""
import json, random
from pathlib import Path
from .entities import Buff, Card, Enemy

# 路径: ~/Projects/sts2/simulator/data_loader.py → ~/Projects/sts2/
PROJECT_ROOT = Path(__file__).parent.parent


def _load(rel_path: str):
    with open(PROJECT_ROOT / rel_path) as f:
        return json.load(f)


# ═══ 数据加载 ═══
CARD_STATS = _load("data/cards/card_stats.json")
CARD_DB = _load("data/cards/card_database_merged.json")
CHAR_CARDS = _load("data/cards/character_cards.json")
MONSTER_AI = _load("knowledge/monster_ai.json")
ARCHETYPES = _load("knowledge/archetype_matrix.json")
TIER_LIST = _load("knowledge/card_tier_list.json")

# ═══ 常量 ═══
STARTING_HP = {
    "铁甲战士": 88, "静默猎手": 78, "缺陷体": 82,
    "储君": 82, "亡灵契约师": 76,
}
STARTING_DECK = {
    "铁甲战士": [("StrikeIronclad", 5), ("DefendIronclad", 4), ("Bash", 1)],
    "静默猎手": [("StrikeSilent", 5), ("DefendSilent", 5), ("Survivor", 1), ("Neutralize", 1)],
    "缺陷体": [("StrikeDefect", 4), ("DefendDefect", 4), ("Zap", 1), ("Dualcast", 1)],
    "储君": [("StrikeRegent", 4), ("DefendRegent", 4), ("Decree", 1), ("Subjugate", 1)],
    "亡灵契约师": [("StrikeNecrobinder", 4), ("DefendNecrobinder", 4), ("BoneSpear", 1), ("SummonOsty", 1)],
}
CHAR_EN = {
    "铁甲战士": "Ironclad", "静默猎手": "Silent", "缺陷体": "Defect",
    "储君": "Regent", "亡灵契约师": "Necrobinder",
}
ENERGY_PER_TURN = 3
HAND_SIZE = 5


# ═══ 牌效果编码 ═══
_SPECIAL_EFFECTS = {
    # 铁甲战士
    "DemonForm":      ("strength_per_turn", 2),
    "Inflame":        ("strength", 2),
    "FightMe":        ("strength", 2),
    "SetupStrike":    ("strength", 1),
    "Barricade":      ("block_retain", 1),
    "Corruption":     ("corruption", 1),
    "FeelNoPain":     ("feel_no_pain", 3),
    "DarkEmbrace":    ("dark_embrace", 1),
    "Metallicize":    ("metallicize", 3),
    "BodySlam":       ("body_slam", 0),
    "Rupture":        ("rupture", 1),
    "FiendFire":      ("fiend_fire", 7),
    "Whirlwind":      ("whirlwind", 5),
    "SeverSoul":      ("sever_soul", 0),
    "Offering":       ("offering", 0),
    "SecondWind":     ("second_wind", 5),
    # 静默猎手
    "NoxiousFume":    ("noxious_fume", 2),
    "Footwork":       ("dexterity", 2),
    "Accuracy":       ("accuracy", 4),
    "AfterImage":     ("after_image", 1),
    "Accelerant":     ("accelerant", 1),
    "DeadlyPoison":   ("poison", 5),
    "BladeDance":     ("blade_dance", 3),
    "CloakAndDagger": ("cloak_dagger", 0),
    "PhantasmalKiller": ("phantasmal", 0),
    "Concentrate":    ("concentrate", 0),
    "Eviscerate":     ("eviscerate", 21),
    "Tactician":      ("tactician", 0),
    "Acrobatics":     ("acrobatics", 3),
    "ToolsOfTheTrade": ("tools_of_trade", 0),
    "StormOfSteel":   ("storm_of_steel", 0),
    "CalculatedGamble": ("calculated_gamble", 0),
    "InfiniteBlades": ("infinite_blades", 1),
    "FanOfKnives":    ("fan_of_knives", 0),
    "PhantomBlades":  ("phantom_blades", 1),
    "HiddenDaggers":  ("hidden_daggers", 2),
    "KnifeTrap":      ("knife_trap", 3),
    "Prepared":       ("prepared", 0),
    "Expertise":      ("expertise", 0),
    "Envenom":        ("envenom", 1),
    "CorrosiveWave":  ("corrosive_wave", 0),
    "Mirage":         ("mirage", 0),
    "Outbreak":       ("outbreak", 11),
    # 铁甲战士 补充
    "Bloodletting":   ("bloodletting", 0),
    "BurningPact":    ("burning_pact", 0),
    "Havoc":          ("havoc", 0),
    "Dominate":       ("dominate_card", 0),
    "Inferno":        ("inferno_power", 6),
    "CrimsonMantle":  ("crimson_mantle", 8),
    "Juggernaut":     ("juggernaut", 5),
    "StoneArmor":     ("plating", 4),
    "Calcify":        ("calcify", 4),
    "Unmovable":      ("unmovable", 0),
    "DemonicShield":  ("demonic_shield", 0),
    "Malaise":        ("malaise", 0),
    "Impervious":     ("impervious", 0),
    "ShrugItOff":     ("shrug_it_off", 0),
    "FlameBarrier":   ("flame_barrier", 0),
    "Hemokinesis":    ("hemokinesis", 0),
    "BloodWall":      ("blood_wall", 0),
    "TrueGrit":       ("true_grit", 0),
    # 缺陷体
    "Defragment":     ("focus", 1),
    "Capacitor":      ("orb_slot", 2),
    "BiasedCognition": ("biased_cog", 4),
    "Zap":            ("channel_lightning", 1),
    "Dualcast":       ("evoke", 2),
    "Coolheaded":     ("channel_frost", 1),
    "Glacier":        ("channel_frost", 2),
    "BallLightning":  ("ball_lightning", 1),
    "Tempest":        ("tempest", 0),
    "Consume":        ("consume", 0),
    "AllForOne":      ("all_for_one", 10),
    "Claw":           ("claw", 3),
    "CompileDriver":  ("compile_driver", 7),
    "Darkness":       ("channel_dark", 1),
    "MultiCast":      ("multicast", 0),
    "ConsumingShadow": ("consuming_shadow", 0),
    "Loop":           ("loop", 0),
    "Rainbow":        ("rainbow", 0),
    "Quadcast":       ("evoke", 4),
    "Storm":          ("storm_power", 1),
    "Thunder":        ("thunder", 6),
    "Hailstorm":      ("hailstorm", 6),
    "Voltaic":        ("voltaic", 0),
    "Overclock":      ("overclock", 0),
    "Turbo":          ("turbo", 0),
    "Synchronize":    ("synchronize", 0),
    "MachineLearning": ("machine_learning", 0),
    "Buffer":         ("buffer", 1),
    "EchoForm":       ("echo_form", 0),
    "TeslaCoil":      ("tesla_coil", 3),
    # 储君
    "Decree":         ("decree", 0),
    "Subjugate":      ("subjugate", 0),
    "Monologue":      ("monologue", 0),
    "MonarchsGaze":   ("monarchs_gaze", 0),
    "SwordSage":      ("sword_sage", 1),
    "Guards":         ("guards", 0),
    "BigBang":        ("big_bang", 0),
    "Stoke":          ("stoke", 0),
    "Glow":           ("glow", 0),
    "Conqueror":      ("conqueror", 0),
    "KinglyPunch":    ("kingly_punch", 0),
    "KinglyKick":     ("kingly_kick", 0),
    "KnockoutBlow":   ("knockout_blow", 0),
    "Bombardment":    ("bombardment", 0),
    "Devastate":      ("devastate", 0),
    "Furnace":        ("furnace", 0),
    "SpoilsOfBattle": ("spoils_of_battle", 0),
    "TheSmith":       ("the_smith", 0),
    "GatherLight":    ("gather_light", 0),
    "Radiate":        ("radiate", 0),
    "ChildOfTheStars": ("child_of_stars", 0),
    "TheSealedThrone": ("sealed_throne", 0),
    "BeatIntoShape":  ("beat_into_shape", 0),
    "WroughtInWar":   ("wrought_in_war", 0),
    "RefineBlade":    ("refine_blade", 0),
    "SummonForth":    ("summon_forth", 0),
    "SeekingEdge":    ("seeking_edge", 0),
    "Bulwark":        ("bulwark", 0),
    "Hegemony":       ("hegemony", 0),
    "SevenStars":     ("seven_stars", 0),
    "CelestialMight": ("celestial_might", 0),
    "Resonance":      ("resonance", 0),
    "SolarStrike":    ("solar_strike", 0),
    "ShiningStrike":  ("shining_strike", 0),
    "CloakOfStars":   ("cloak_of_stars", 0),
    "Venerate":       ("venerate", 0),
    "Genesis":        ("genesis", 0),
    "Alignment":      ("alignment", 0),
    "SpectrumShift":  ("spectrum_shift", 0),
    "Arsenal":        ("arsenal", 0),
    "BundleOfJoy":    ("bundle_of_joy", 0),
    "HeirloomHammer": ("heirloom_hammer", 0),
    "Quasar":         ("quasar", 0),
    "ManifestAuthority": ("manifest_authority", 0),
    "PillarOfCreation": ("pillar_of_creation", 0),
    # 静默猎手更多
    "Finisher":       ("finisher", 0),
    "LeadingStrike":  ("leading_strike", 0),
    "DodgeAndRoll":   ("dodge_and_roll", 0),
    "LegSweep":       ("leg_sweep", 0),
    "EscapePlan":     ("escape_plan", 0),
    "Backflip":       ("backflip", 0),
    "Deflect":        ("deflect", 0),
    "Blur":           ("blur", 0),
    "MementoMori":    ("memento_mori", 0),
    "FlickFlack":     ("flick_flack", 0),
    # 缺陷体更多
    "ColdSnap":       ("cold_snap", 0),
    "SweepingBeam":   ("sweeping_beam", 0),
    "Scrape":         ("scrape", 0),
    "Ftl":            ("ftl", 0),
    "GoForTheEyes":   ("go_for_eyes", 0),
    "BeamCell":       ("beam_cell", 0),
    "Hologram":       ("hologram", 0),
    "BoostAway":      ("boost_away", 0),
    "Hotfix":         ("hotfix", 0),
    "ShadowShield":   ("shadow_shield", 0),
    # 亡灵契约师
    "SummonOsty":     ("summon_osty", 0),
    "Reanimate":      ("summon_osty", 0),
    "Sacrifice":      ("sacrifice_nb", 0),
    "GlimpseBeyond":  ("glimpse", 0),
    "DevourLife":     ("devour_life", 1),
    "Cruelty":        ("cruelty", 5),
    "Haunt":          ("haunt", 0),
    "SpiritOfAsh":    ("spirit_ash", 0),
    "CallOfTheVoid":  ("call_void", 0),
    "Seance":         ("seance", 0),
    "Shroud":         ("shroud_power", 2),
    "BoneSpear":      ("bone_spear", 8),
    "ReaperForm":     ("reaper_form", 0),
    "Countdown":      ("countdown_doom", 3),
    "Scourge":        ("scourge_doom", 5),
    "NoEscape":       ("no_escape_doom", 8),
    "TimesUp":        ("times_up", 0),
    "Poke":           ("osty_attack", 6),
    "Fetch":          ("osty_fetch", 3),
    "Flatten":        ("osty_flatten", 12),
    "Squeeze":        ("osty_squeeze", 5),
    "BlightStrike":   ("blight_strike", 8),
    "NegativePulse":  ("negative_pulse", 6),
    "Oblivion":       ("doom_aoe", 5),
    "EndOfDays":      ("end_of_days", 0),
    "Deathbringer":   ("deathbringer", 0),
    "BorrowedTime":   ("borrowed_time", 0),
    "DeathsDoor":     ("deaths_door", 0),
    "Unleash":        ("unleash", 0),
    "RightHandHand":  ("right_hand_hand", 0),
    "HighFive":       ("high_five", 0),
    "SicEm":          ("sic_em", 0),
    "Snap":           ("snap", 0),
    "Pagestorm":      ("pagestorm", 0),
    "PullFromBelow":  ("pull_from_below", 0),
    "SoulStorm":      ("soul_storm", 0),
    "CaptureSpirit":  ("capture_spirit", 0),
    "Veilpiercer":    ("veilpiercer", 0),
    "SculptingStrike": ("sculpting_strike", 0),
    # 铁甲战士更多
    "Mangle":         ("mangle", 0),
    "Uppercut":       ("uppercut", 0),
    "MoltenFist":     ("molten_fist", 0),
    "AshenStrike":    ("ashen_strike", 0),
    "Spite":          ("spite", 0),
    "Colossus":       ("colossus", 0),
    "IronWave":       ("iron_wave", 0),
    "Armaments":      ("armaments", 0),
    # 新增流派牌效果
    "TwinStrike":     ("twin_strike", 5),
    "SwordBoomerang": ("sword_boomerang", 3),
    "PommelStrike":   ("pommel_strike", 9),
    "Anger":          ("anger", 6),
    "Rampage":        ("rampage", 9),
    "Feed":           ("feed", 10),
    "Bludgeon":       ("bludgeon", 32),
    "PerfectedStrike": ("perfected_strike", 6),
    "Rage":           ("rage", 3),
    "Aggression":     ("aggression", 0),
    "Backstab":       ("backstab", 11),
    "Assassinate":    ("assassinate", 10),
    "Slice":          ("slice", 6),
    "WraithForm":     ("wraith_form", 2),
    "Neutralize":     ("neutralize", 3),
    "Burst":          ("burst", 0),
    "WellLaidPlans":  ("well_laid_plans", 0),
    "Hyperbeam":      ("hyperbeam", 26),
    "MeteorStrike":   ("meteor_strike", 24),
    "Sunder":         ("sunder", 24),
    "DoubleEnergy":   ("double_energy", 0),
    "Fusion":         ("fusion", 0),
    "ChargeBattery":  ("charge_battery", 7),
    "AdaptiveStrike": ("adaptive_strike", 18),
    "Coolant":        ("coolant", 2),
    "Chill":          ("chill", 0),
    "FocusedStrike":  ("focused_strike", 9),
    "AstralPulse":    ("astral_pulse", 14),
    "CollisionCourse": ("collision_course", 9),
    "FallingStar":    ("falling_star", 7),
    "GammaBlast":     ("gamma_blast", 13),
    "HeavenlyDrill":  ("heavenly_drill", 8),
    "ParticleWall":   ("particle_wall", 9),
    "NeutronAegis":   ("neutron_aegis", 8),
    "Parry":          ("parry", 6),
    "Reflect":        ("reflect", 17),
    "VoidForm":       ("void_form", 2),
    "BlackHole":      ("black_hole", 3),
    "Tyranny":        ("tyranny", 0),
    "Prophesize":     ("prophesize", 6),
    "RoyalGamble":    ("royal_gamble", 0),
    "BansheesCry":    ("banshees_cry", 33),
    "TheScythe":      ("the_scythe", 13),
    "Reap":           ("reap", 27),
    "Bury":           ("bury", 52),
    "Defile":         ("defile", 13),
    "Graveblast":     ("graveblast", 4),
    "Afterlife":      ("afterlife", 6),
    "LegionOfBone":   ("legion_of_bone", 6),
    "DanseMacabre":   ("danse_macabre", 3),
    "Eidolon":        ("eidolon", 0),
    "Fear":           ("fear", 7),
    "Debilitate":     ("debilitate", 7),
    "EnfeeblingTouch": ("enfeebling_touch", 8),
    "Misery":         ("misery", 7),
}


def _build_card(card_id: str, upgraded=False) -> Card:
    stats = CARD_STATS.get(card_id, {})
    db = CARD_DB.get(card_id, {})

    cost = stats.get("cost", db.get("cost", 1))
    try:
        cost = int(cost)
    except (ValueError, TypeError):
        cost = 1

    card_type = stats.get("type", db.get("type", "攻击"))

    damage = 0
    dmg_raw = stats.get("damage", db.get("damage"))
    if isinstance(dmg_raw, list) and dmg_raw:
        damage = int(dmg_raw[0])
    elif isinstance(dmg_raw, (int, float)):
        damage = int(dmg_raw)

    block = 0
    blk_raw = stats.get("block", db.get("block"))
    if isinstance(blk_raw, list) and blk_raw:
        block = int(blk_raw[0])
    elif isinstance(blk_raw, (int, float)):
        block = int(blk_raw)

    hits = 1
    hits_raw = stats.get("hits")
    if isinstance(hits_raw, (int, float)):
        hits = int(hits_raw)

    name_cn = db.get("name_cn", card_id)

    # 从powers字段自动识别
    effect = ""
    effect_value = 0
    powers = stats.get("powers", [])
    for p in powers:
        ptype = p.get("type", "")
        amt = p.get("amount", 0)
        try:
            amt = int(amt)
        except (ValueError, TypeError):
            amt = 0
        if "Strength" in ptype:
            effect = "strength"; effect_value = amt
        elif "Dexterity" in ptype:
            effect = "dexterity"; effect_value = amt
        elif "Focus" in ptype:
            effect = "focus"; effect_value = amt
        elif "Poison" in ptype or "NoxiousFume" in card_id:
            effect = "poison"; effect_value = amt

    # 特殊牌手动编码
    if card_id in _SPECIAL_EFFECTS:
        effect, effect_value = _SPECIAL_EFFECTS[card_id]

    # 升级加成
    upgrades = stats.get("upgrade", [])
    if upgraded and upgrades:
        if damage > 0 and len(upgrades) > 0:
            damage += int(upgrades[0])
        if block > 0 and len(upgrades) > 0:
            block += int(upgrades[0])
        if effect_value > 0 and effect not in ("block_retain", "corruption"):
            if len(upgrades) > 0:
                effect_value += int(upgrades[-1])

    return Card(
        id=card_id, name_cn=name_cn, cost=cost, card_type=card_type,
        damage=damage, block=block, hits=hits, upgraded=upgraded,
        effect=effect, effect_value=effect_value,
    )


# 基础牌覆盖
_BASIC_OVERRIDE = {
    "StrikeIronclad": (6, 0), "StrikeSilent": (6, 0), "StrikeDefect": (6, 0),
    "StrikeRegent": (6, 0), "StrikeNecrobinder": (6, 0),
    "DefendIronclad": (0, 5), "DefendSilent": (0, 5), "DefendDefect": (0, 5),
    "DefendRegent": (0, 5), "DefendNecrobinder": (0, 5),
    "Bash": (8, 0),
}


def build_card(card_id: str, upgraded=False) -> Card:
    c = _build_card(card_id, upgraded)
    if card_id in _BASIC_OVERRIDE:
        d, b = _BASIC_OVERRIDE[card_id]
        if d:
            c.damage = d
        if b:
            c.block = b
    if card_id == "Bash":
        c.effect = "vulnerable"
        c.effect_value = 2
    return c


def build_enemy(monster_key: str, asc=0) -> Enemy:
    data = MONSTER_AI.get(monster_key, {})
    hp_data = data.get("hp", {})

    # hp_data might be a string, int, list, or dict
    if not isinstance(hp_data, dict):
        if isinstance(hp_data, (int, float)):
            hp_range = [int(hp_data)]
        elif isinstance(hp_data, list):
            hp_range = hp_data
        else:
            hp_range = [100]
    elif asc >= 8 and "ascension" in hp_data:
        hp_range = hp_data["ascension"]
    else:
        hp_range = hp_data.get("normal", [100, 100])

    if isinstance(hp_range, list) and hp_range:
        hp = random.randint(int(hp_range[0]), int(hp_range[-1])) if len(hp_range) > 1 else int(hp_range[0])
    elif isinstance(hp_range, int):
        hp = hp_range
    else:
        hp = 100

    moves_raw = data.get("moves", [])
    moves = []
    for m in moves_raw:
        if not isinstance(m, dict):
            continue
        dmg = m.get("damage", 0)
        if isinstance(dmg, list):
            dmg = dmg[0] if dmg else 0
        hits = m.get("hits", 1)
        if isinstance(hits, list):
            hits = hits[0] if hits else 1
        blk = m.get("block", 0)
        if isinstance(blk, list):
            blk = blk[0] if blk else 0
        try:
            dmg = int(dmg); hits = int(hits); blk = int(blk)
        except (ValueError, TypeError):
            dmg = 0; hits = 1; blk = 0
        moves.append({
            "damage": dmg, "hits": hits, "block": blk,
            "id": m.get("id", ""), "intent": m.get("intent", ""),
            "effects": m.get("effects", []),
        })

    if not moves:
        moves = [{"damage": 10, "hits": 1, "block": 0, "id": "BASIC",
                  "intent": "SingleAttack", "effects": []}]

    enemy_buffs = Buff()
    if monster_key == "CalcifiedCultist":
        enemy_buffs.ritual = 1
    if monster_key == "MechaKnight":
        enemy_buffs.strength = 0

    return Enemy(
        name=data.get("name_cn", monster_key),
        hp=hp, max_hp=hp,
        ai_id=monster_key,
        moves=moves,
        buffs=enemy_buffs,
    )
