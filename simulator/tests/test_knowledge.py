#!/usr/bin/env python3
"""知识库完整性测试 — 适配新模块化结构"""
import json, os, sys

BASE = os.path.expanduser("~/Projects/sts2")
KB = os.path.join(BASE, "knowledge")
DATA = os.path.join(BASE, "data")

# Also check skills repo for files not yet copied
SKILL_BASE = os.path.expanduser("~/Projects/skills/sts2-advisor")

passed = 0
failed = 0
warnings = 0

def ok(msg):
    global passed; passed += 1; print(f"  ✅ {msg}")

def fail(msg):
    global failed; failed += 1; print(f"  ❌ {msg}")

def warn(msg):
    global warnings; warnings += 1; print(f"  ⚠️  {msg}")

def load(path):
    with open(path) as f:
        return json.load(f)

def try_load(rel_path):
    """Try BASE first, then SKILL_BASE"""
    p1 = os.path.join(BASE, rel_path)
    p2 = os.path.join(SKILL_BASE, rel_path)
    if os.path.exists(p1):
        return load(p1), p1
    elif os.path.exists(p2):
        return load(p2), p2
    return None, None

# ═══ 1. 核心文件完整性 ═══
print("\n═══ 1. 核心数据文件 ═══")
core_files = [
    "knowledge/archetype_matrix.json",
    "knowledge/card_tier_list.json",
    "knowledge/monster_ai.json",
    "data/cards/card_stats.json",
    "data/cards/character_cards.json",
]
for f in core_files:
    path = os.path.join(BASE, f)
    if os.path.exists(path):
        try:
            load(path)
            ok(f"{f} ({os.path.getsize(path)/1024:.0f}KB)")
        except json.JSONDecodeError as e:
            fail(f"{f} — JSON解析失败: {e}")
    else:
        fail(f"{f} — 文件不存在")

# Optional files (may be in skills repo only)
optional_files = [
    "knowledge/boss_counter_guide.json",
    "knowledge/card_synergy_index.json",
    "knowledge/combat_rules.json",
    "knowledge/event_guide.json",
    "knowledge/potion_guide.json",
    "knowledge/relic_pivot_rules.json",
    "data/cards/card_database_merged.json",
    "data/relics/relics.json",
    "data/relics/potions.json",
    "data/monsters/monsters.json",
    "data/meta/epochs.json",
]
for f in optional_files:
    data, path = try_load(f)
    if data is not None:
        ok(f"{f} ({os.path.getsize(path)/1024:.0f}KB)")
    else:
        warn(f"{f} — 文件不存在(可选)")

# ═══ 2. 牌ID交叉验证 ═══
print("\n═══ 2. 牌ID交叉验证 ═══")
char_cards = load(os.path.join(DATA, "cards/character_cards.json"))
card_stats = load(os.path.join(DATA, "cards/card_stats.json"))
matrix = load(os.path.join(KB, "archetype_matrix.json"))

all_card_ids = set()
for char, cards in char_cards.items():
    for c in cards:
        all_card_ids.add(c["id"])
print(f"  合法牌ID总数: {len(all_card_ids)}")

matrix_bad = []
for char, cdata in matrix.get("characters", {}).items():
    for aname, adata in cdata.get("archetypes", {}).items():
        for card in adata.get("core_cards", []) + adata.get("support_cards", []):
            cid = card.get("id", "")
            if cid and cid not in all_card_ids and cid not in card_stats:
                matrix_bad.append(f"{char}/{aname}: {cid}")
if matrix_bad:
    warn(f"archetype_matrix引用了{len(matrix_bad)}个不存在的牌ID(命名差异)")
    for b in matrix_bad[:5]:
        print(f"    {b}")
else:
    ok("archetype_matrix所有牌ID有效")

# ═══ 3. 怪物类型验证 ═══
print("\n═══ 3. 怪物类型验证 ═══")
monster_ai = load(os.path.join(KB, "monster_ai.json"))
ai_keys = set(k for k in monster_ai.keys() if k != "_meta")
boss_count = sum(1 for k, v in monster_ai.items() if isinstance(v, dict) and v.get("type") == "Boss")
elite_count = sum(1 for k, v in monster_ai.items() if isinstance(v, dict) and "精英" in str(v.get("type", "")))
normal_count = sum(1 for k, v in monster_ai.items() if isinstance(v, dict) and v.get("type") == "普通怪")
ok(f"monster_ai: {len(ai_keys)}条 (Boss:{boss_count} 精英:{elite_count} 普通怪:{normal_count})")

# Verify corrected types
type_checks = {
    "OwlMagistrate": "普通怪",
    "FrogKnight": "普通怪",
    "HunterKiller": "普通怪",
    "Fabricator": "普通怪",
    "Fogmog": "普通怪",
    "LouseProgenitor": "普通怪",
    "GremlinMerc": "普通怪",
    "SlimedBerserker": "普通怪",
    "FlailKnight": "精英",
    "SpectralKnight": "精英",
    "MagiKnight": "精英",
}
type_ok = True
for mk, expected_type in type_checks.items():
    if mk in monster_ai:
        actual = monster_ai[mk].get("type", "?")
        if expected_type not in actual:
            fail(f"{mk}: 期望'{expected_type}', 实际'{actual}'")
            type_ok = False
if type_ok:
    ok("怪物类型修正验证通过")

# ═══ 4. 模块导入测试 ═══
print("\n═══ 4. 模块导入测试 ═══")
try:
    from simulator.entities import Card, Player, Enemy, Buff, Orb
    ok("entities 导入成功")
except Exception as e:
    fail(f"entities 导入失败: {e}")

try:
    from simulator.data_loader import build_card, build_enemy, MONSTER_AI
    ok("data_loader 导入成功")
except Exception as e:
    fail(f"data_loader 导入失败: {e}")

try:
    from simulator.combat import CombatSim
    ok("combat 导入成功")
except Exception as e:
    fail(f"combat 导入失败: {e}")

try:
    from simulator.archetypes import build_archetype_deck
    ok("archetypes 导入成功")
except Exception as e:
    fail(f"archetypes 导入失败: {e}")

try:
    from simulator.full_run import simulate_full_run, batch_simulate_full
    ok("full_run 导入成功")
except Exception as e:
    fail(f"full_run 导入失败: {e}")

try:
    from simulator import CombatSim, simulate_full_run
    ok("__init__ 导入成功")
except Exception as e:
    fail(f"__init__ 导入失败: {e}")

# ═══ 5. 快速功能测试 ═══
print("\n═══ 5. 快速功能测试 ═══")
try:
    from simulator.data_loader import build_card, build_enemy
    c = build_card("StrikeIronclad")
    assert c.damage == 6, f"Strike damage should be 6, got {c.damage}"
    assert c.id == "StrikeIronclad"
    ok(f"build_card: {c.id} dmg={c.damage}")

    c2 = build_card("Bash")
    assert c2.effect == "vulnerable"
    ok(f"build_card: {c2.id} effect={c2.effect}")

    e = build_enemy("SpinyToad")
    assert e.hp > 0
    ok(f"build_enemy: {e.name} HP={e.hp}")
except Exception as ex:
    fail(f"功能测试失败: {ex}")

# ═══ Summary ═══
print(f"\n═══ 总计: ✅{passed} ⚠️{warnings} ❌{failed} ═══\n")
if failed:
    sys.exit(1)
