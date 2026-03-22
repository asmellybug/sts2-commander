"""STS2 模拟器 — 战斗引擎（MonsterAI + CombatSim + 遗物/药水系统）"""
import random, copy
from typing import Optional
from .entities import Buff, Card, Entity, Enemy, Orb, Player
from .data_loader import (
    MONSTER_AI, CARD_STATS, build_card, build_enemy,
    HAND_SIZE, CHAR_EN, STARTING_HP,
)


# ═══ MonsterAI 状态机 ═══
class MonsterAI:
    """怪物AI状态机"""

    BOSS_SEQUENCES = {
        "Queen": {
            "phases": [
                {"name": "setup", "moves": [0, 1]},
                {"name": "attack", "moves": [2, 3, 4, 3, 4]}
            ],
            "phase_trigger": lambda e, cs: e.ai_turn >= 2,
        },
        "Doormaker": {"sequence": [-1, 1, -1, 1, -1, 1, -1]},
        "KnowledgeDemon": {"sequence": [0, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3]},
        "TheInsatiable": {"sequence": [0, -1, 2, 0, -1, 2, 2, 2]},
        "SlimedBerserker": {"sequence": [0, 1, 2, 3, 0, 1, 2, 3]},
        "WaterfallGiant": {"sequence": [0, 1, 2, 0, 1, 2]},
        "LagavulinMatriarch": {"sleep_turns": 3, "sequence": [0, 1, 2, 1, 2]},
        "Vantom": {"sequence": [0, 1, 2, 1, 2]},
        "CeremonialBeast": {"sequence": [-1, -1, 1, -1, -1, 1]},
        "TestSubject": {"sequence": [0, -1, 1, 0, -1, 1, 2]},
        "SoulFysh": {"sequence": [0, 1, 2, 0, 1, 2]},
    }

    def __init__(self, enemy: Enemy, ai_data: dict):
        self.enemy = enemy
        self.state = "initial"
        self.ai_data = ai_data
        self.ai_pattern = ai_data.get("ai_pattern", "")
        self.moves_raw = ai_data.get("moves", [])
        self.moves = self._parse_moves()
        self.seq_idx = 0
        self.curse_count = 0
        self.amalgam_alive = True

    def _parse_moves(self) -> list[dict]:
        result = []
        for m in self.moves_raw:
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
            result.append({
                "id": m.get("id", ""), "damage": dmg, "hits": hits, "block": blk,
                "intent": m.get("intent", ""), "effects": m.get("effects", []),
            })
        if not result:
            result = [{"id": "BASIC", "damage": 10, "hits": 1, "block": 0,
                       "intent": "SingleAttack", "effects": []}]
        return result

    def get_next_move(self, combat_state: dict) -> dict:
        self.enemy.ai_turn += 1
        eid = self.enemy.ai_id

        if eid == "Queen":
            return self._queen_ai()
        elif eid == "Doormaker":
            return self._sequence_ai("Doormaker")
        elif eid == "KnowledgeDemon":
            return self._knowledge_demon_ai()
        elif eid == "TheInsatiable":
            return self._sequence_ai("TheInsatiable")
        elif eid == "SlimedBerserker":
            return self._sequence_ai("SlimedBerserker")
        elif eid == "WaterfallGiant":
            return self._sequence_ai("WaterfallGiant")
        elif eid == "LagavulinMatriarch":
            return self._lagavulin_ai()
        elif eid == "Vantom":
            return self._sequence_ai("Vantom")
        elif eid == "CeremonialBeast":
            return self._sequence_ai("CeremonialBeast")
        elif eid in ("TestSubject", "TestSubjectBoss"):
            return self._sequence_ai("TestSubject")
        elif eid == "SoulFysh":
            return self._soulfysh_ai()
        elif eid in ("KaiserCrabBoss", "KaiserCrab"):
            return self._kaiser_crab_ai()
        elif eid in ("TheKin", "TheKinBoss"):
            return self._sequence_ai("TestSubject")
        elif eid == "MechaKnight":
            idx = (self.enemy.ai_turn - 1) % 4
            move = self.moves[min(idx, len(self.moves) - 1)]
            if idx == 2:
                self.enemy.buffs.strength += 5
                move = dict(move)
                move["damage"] = 0
                move["block"] = 15
            return move
        elif eid == "CalcifiedCultist":
            self.enemy.buffs.strength += self.enemy.buffs.ritual if self.enemy.buffs.ritual > 0 else 1
            return self._cycle_ai()
        else:
            return self._cycle_ai()

    def _cycle_ai(self) -> dict:
        if not self.moves:
            return {"damage": 8, "hits": 1, "block": 0}
        move = self.moves[self.enemy.move_index % len(self.moves)]
        self.enemy.move_index += 1
        return move

    def _sequence_ai(self, boss_id: str) -> dict:
        seq_data = self.BOSS_SEQUENCES.get(boss_id, {})
        seq = seq_data.get("sequence", list(range(len(self.moves))))
        if not seq or not self.moves:
            return self._cycle_ai()
        idx = seq[self.seq_idx % len(seq)]
        self.seq_idx += 1
        if idx == -1:
            return {"damage": 0, "hits": 1, "block": 0, "id": "CHARGE", "intent": "Buff"}
        return self.moves[min(idx, len(self.moves) - 1)]

    def _queen_ai(self) -> dict:
        t = self.enemy.ai_turn
        if t == 1:
            return {"damage": 0, "hits": 1, "block": 0, "id": "PUPPET_STRINGS", "intent": "Debuff"}
        elif t == 2:
            return {"damage": 0, "hits": 1, "block": 0, "id": "YOU_ARE_MINE", "intent": "Debuff"}
        else:
            cycle_pos = (t - 3) % 3
            if cycle_pos == 2:
                self.enemy.buffs.strength += 3
                return {"damage": 0, "hits": 1, "block": 10, "id": "ENRAGE", "intent": "Buff"}
            attack_moves = self.moves[2:]
            if not attack_moves:
                return self.moves[-1]
            return attack_moves[min(cycle_pos, len(attack_moves) - 1)]

    def _knowledge_demon_ai(self) -> dict:
        t = self.enemy.ai_turn
        if self.curse_count < 3:
            if t % 4 == 1:
                self.curse_count += 1
                return {"damage": 0, "hits": 1, "block": 0, "id": "CURSE", "intent": "Debuff"}
            elif t % 4 == 2:
                return self.moves[min(1, len(self.moves) - 1)]
            elif t % 4 == 3:
                self.enemy.buffs.strength += 2
                return {"damage": 0, "hits": 1, "block": 0, "id": "CONTEMPLATE", "intent": "Buff"}
            else:
                return self.moves[min(2, len(self.moves) - 1)]
        else:
            cycle_pos = (t - 1) % 3
            if cycle_pos == 2:
                self.enemy.buffs.strength += 2
                return {"damage": 0, "hits": 1, "block": 0, "id": "CONTEMPLATE", "intent": "Buff"}
            return self.moves[min(cycle_pos + 1, len(self.moves) - 1)]

    def _lagavulin_ai(self) -> dict:
        t = self.enemy.ai_turn
        sleep_turns = self.BOSS_SEQUENCES.get("LagavulinMatriarch", {}).get("sleep_turns", 3)
        if t <= sleep_turns:
            return {"damage": 0, "hits": 1, "block": 0, "id": "SLEEP", "intent": "Stun"}
        else:
            awake_turn = t - sleep_turns
            if awake_turn % 2 == 0:
                return {"damage": 0, "hits": 1, "block": 0, "id": "DEBUFF", "intent": "Debuff"}
            attack_moves = [m for m in self.moves if m.get("damage", 0) > 0]
            if not attack_moves:
                return self._cycle_ai()
            idx = (awake_turn // 2) % len(attack_moves)
            return attack_moves[idx]

    def _soulfysh_ai(self) -> dict:
        hp_pct = self.enemy.hp / self.enemy.max_hp
        if hp_pct > 0.66:
            phase_moves = self.moves[:2] if len(self.moves) >= 2 else self.moves
        elif hp_pct > 0.33:
            phase_moves = self.moves[1:3] if len(self.moves) >= 3 else self.moves
        else:
            phase_moves = self.moves[2:] if len(self.moves) >= 3 else self.moves
        if not phase_moves:
            return self._cycle_ai()
        move = phase_moves[self.seq_idx % len(phase_moves)]
        self.seq_idx += 1
        return move

    def _kaiser_crab_ai(self) -> dict:
        t = self.enemy.ai_turn
        if t % 3 == 0:
            return {"damage": 0, "hits": 1, "block": 15, "id": "SHIELD", "intent": "Block"}
        if not self.moves:
            return {"damage": 10, "hits": 1, "block": 0}
        idx = (t - 1) % len(self.moves)
        return self.moves[idx]


# ═══ 遗物系统 ═══
ARCHETYPE_RELICS = {
    "力量流": ["Vajra", "RedSkull", "BurningBlood"],
    "消耗流": ["BurningBlood", "PenNib"],
    "格挡撞击流": ["BurningBlood", "Vajra"],
    "自伤流": ["BurningBlood", "RedSkull"],
    "连击流": ["Vajra", "Shuriken", "BurningBlood"],
    "喂食回血流": ["BurningBlood", "Vajra"],
    "打击流": ["Vajra", "PenNib", "BurningBlood"],
    "毒素流": ["SneckoSkull", "TheSpecimen"],
    "飞刀流": ["Shuriken", "Kunai"],
    "弃牌流": ["Shuriken", "Kunai"],
    "敏捷格挡流": ["Kunai", "BurningBlood"],
    "暗杀流": ["Shuriken", "Kunai", "BurningBlood"],
    "幽灵防御流": ["BurningBlood", "Kunai"],
    "0费速攻流": ["Shuriken", "Kunai", "PenNib"],
    "集中全能流": ["FrozenCore", "Inserter"],
    "闪电流": ["CrackedOrb", "FrozenCore"],
    "暗球爆发流": ["CrackedOrb", "FrozenCore", "Inserter"],
    "0费爪击流": ["PenNib", "Shuriken"],
    "超载爆发流": ["CrackedOrb", "FrozenCore"],
    "能量循环流": ["CrackedOrb", "FrozenCore"],
    "冰霜护盾流": ["FrozenCore", "Inserter"],
    "星辰控制流": ["Vajra", "PenNib"],
    "铸造战士流": ["Vajra", "RedSkull", "BurningBlood", "PenNib"],
    "无色生成流": ["PenNib", "BurningBlood"],
    "重击流": ["Vajra", "RedSkull"],
    "粒子防御流": ["BurningBlood", "Vajra"],
    "虚空形态流": ["Vajra", "BurningBlood"],
    "Osty召唤流": ["BurningBlood", "Vajra"],
    "灾厄(Doom)流": ["BurningBlood", "Vajra"],
    "灵魂虚无流": ["BurningBlood", "Vajra"],
    "Osty+灾厄混合流": ["BurningBlood", "Vajra"],
    "高费斩杀流": ["BurningBlood", "Vajra"],
    "恐惧削弱流": ["BurningBlood", "Vajra"],
    "墓地回收流": ["BurningBlood", "Vajra"],
}

ARCHETYPE_POTIONS = {
    "力量流": ["strength", "strength", "block"],
    "消耗流": ["strength", "block", "block"],
    "格挡撞击流": ["block", "dexterity"],
    "自伤流": ["strength", "strength", "block"],
    "毒素流": ["poison", "poison"],
    "飞刀流": ["dexterity", "strength"],
    "弃牌流": ["dexterity", "strength", "block"],
    "敏捷格挡流": ["dexterity", "block"],
    "集中全能流": ["focus", "focus"],
    "闪电流": ["focus", "focus"],
    "暗球爆发流": ["focus", "focus"],
    "0费爪击流": ["strength", "strength"],
    "星辰控制流": ["strength", "strength"],
    "铸造战士流": ["strength", "strength", "block"],
    "无色生成流": ["strength", "block"],
    "重击流": ["strength", "strength", "block"],
    "Osty召唤流": ["strength", "strength"],
    "灾厄(Doom)流": ["strength", "block"],
    "灵魂虚无流": ["strength", "block"],
    "Osty+灾厄混合流": ["strength", "strength"],
    "连击流": ["strength", "strength", "block"],
    "喂食回血流": ["strength", "strength"],
    "打击流": ["strength", "strength"],
    "暗杀流": ["strength", "dexterity"],
    "幽灵防御流": ["dexterity", "poison"],
    "0费速攻流": ["strength", "dexterity"],
    "超载爆发流": ["focus", "strength"],
    "能量循环流": ["focus", "focus"],
    "冰霜护盾流": ["focus", "focus"],
    "粒子防御流": ["dexterity", "block"],
    "虚空形态流": ["strength", "strength"],
    "高费斩杀流": ["strength", "strength"],
    "恐惧削弱流": ["strength", "block"],
    "墓地回收流": ["strength", "strength"],
}


def apply_relics_start(player: Player, arch_name: str):
    relics = ARCHETYPE_RELICS.get(arch_name, [])
    if relics:
        player.relics = relics
    for r in (relics or []):
        if r == "Vajra":
            player.buffs.strength += 1
        elif r == "PenNib":
            player.buffs.strength += 2
    # Archetype-specific starting buffs
    _ARCH_BUFFS = {
        "消耗流": dict(feel_no_pain=30, metallicize=25, draw_per_turn=3,
                      dark_embrace=2, strength=20, block_retain=True),
        "自伤流": dict(draw_per_turn=2, metallicize=20, _rupture=6,
                      strength=14, block_retain=True),
        "力量流": dict(strength=8, metallicize=10, draw_per_turn=1,
                      strength_per_turn=3),
        "毒素流": dict(noxious_fume=10, dexterity=6, metallicize=8),
        "飞刀流": dict(_accuracy=6, _infinite_blades=4, dexterity=5,
                      metallicize=6, strength=3),
        "弃牌流": dict(dexterity=5, _after_image=3, draw_per_turn=2,
                      metallicize=4, strength=3),
        "敏捷格挡流": dict(dexterity=6, block_retain=True, metallicize=3,
                        thorns=5, noxious_fume=2),
        "暗球爆发流": dict(focus=14, metallicize=14, draw_per_turn=2, strength=3),
        "闪电流": dict(focus=9, _storm_power=1, metallicize=8, draw_per_turn=1),
        "铸造战士流": dict(strength=10, metallicize=10, draw_per_turn=2, dexterity=4),
        "重击流": dict(strength=18, metallicize=15, draw_per_turn=2,
                      dexterity=5, strength_per_turn=1),
        "无色生成流": dict(strength=10, draw_per_turn=2, metallicize=8),
        "灵魂虚无流": dict(countdown_doom=3, shroud_stacks=2),
        "Osty召唤流": dict(strength=7, metallicize=7),
        "灾厄(Doom)流": dict(strength=6, countdown_doom=5, metallicize=6),
        "Osty+灾厄混合流": dict(strength=5, countdown_doom=3, metallicize=3),
        "集中全能流": dict(focus=10, metallicize=10, draw_per_turn=2),
        "0费爪击流": dict(strength=5, draw_per_turn=2, metallicize=5),
        "星辰控制流": dict(strength=6, metallicize=5, draw_per_turn=1),
        "连击流": dict(strength=6, metallicize=5, draw_per_turn=1),
        "喂食回血流": dict(strength=12, metallicize=12, draw_per_turn=2),
        "打击流": dict(strength=8, metallicize=5, draw_per_turn=1),
        "暗杀流": dict(strength=6, dexterity=3, _accuracy=4,
                      draw_per_turn=2, metallicize=4),
        "幽灵防御流": dict(noxious_fume=5, dexterity=5, metallicize=5,
                        _after_image=3, intangible=3),
        "0费速攻流": dict(strength=5, dexterity=3, _after_image=3,
                        _accuracy=4, draw_per_turn=2, metallicize=4),
        "超载爆发流": dict(focus=5, strength=3, metallicize=6, draw_per_turn=1),
        "能量循环流": dict(focus=4, metallicize=5, draw_per_turn=1),
        "格挡撞击流": dict(dexterity=5, block_retain=True, metallicize=4, strength=3),
        "粒子防御流": dict(strength=14, strength_per_turn=2, dexterity=6,
                        metallicize=16, plated_armor=10, thorns=8, draw_per_turn=2),
        "虚空形态流": dict(strength_per_turn=3, strength=6, metallicize=8,
                        draw_per_turn=2, dexterity=4),
        "高费斩杀流": dict(strength=6, metallicize=8, draw_per_turn=1),
        "恐惧削弱流": dict(strength=5, metallicize=6, countdown_doom=3, draw_per_turn=1),
        "墓地回收流": dict(strength=8, metallicize=9, countdown_doom=4, draw_per_turn=1),
    }
    buffs_cfg = _ARCH_BUFFS.get(arch_name, {})
    for key, val in buffs_cfg.items():
        if key.startswith('_'):
            setattr(player.buffs, key, getattr(player.buffs, key, 0) + val)
        elif key == "block_retain":
            player.buffs.block_retain = val
        elif hasattr(player.buffs, key):
            setattr(player.buffs, key, getattr(player.buffs, key) + val)

    # Special setup
    if arch_name == "暗球爆发流":
        player.orb_slots = 8
    elif arch_name == "超载爆发流":
        player.orb_slots = 5
    elif arch_name == "能量循环流":
        player.orb_slots = 4
        player.max_energy = 4
        player.energy = 4
    elif arch_name == "冰霜护盾流":
        player.buffs.focus += 20
        player.buffs.metallicize += 20
        player.buffs.strength += 16
        player.orb_slots = 8
        player.buffs.draw_per_turn += 2
        player.buffs.thorns += 8
        player.buffs.block_retain = True
        player.orbs = [Orb(orb_type="frost") for _ in range(6)]
    elif arch_name == "Osty召唤流":
        player.osty_hp = 20
    elif arch_name == "Osty+灾厄混合流":
        player.osty_hp = 18
    elif arch_name == "高费斩杀流":
        player.max_energy = 5
        player.energy = 5
    elif arch_name == "墓地回收流":
        player.osty_hp = 18


def apply_relics_turn(sim: 'CombatSim'):
    p = sim.player
    for r in p.relics:
        if r == "RedSkull" and p.hp <= p.max_hp // 2:
            if not getattr(p.buffs, '_red_skull_active', False):
                p.buffs.strength += 3
                p.buffs._red_skull_active = True
        elif r == "Inserter":
            if sim.turn % 2 == 0:
                p.orb_slots += 1
        elif r == "FrozenCore":
            if not p.orbs and p.orb_slots > 0:
                sim._channel_orb("frost")


def apply_relics_combat_end(player: Player):
    for r in player.relics:
        if r == "BurningBlood":
            player.hp = min(player.max_hp, player.hp + 6)


def use_potion(player: Player, potion: str, enemies: list):
    if potion == "strength":
        player.buffs.strength += 2
    elif potion == "dexterity":
        player.buffs.dexterity += 2
    elif potion == "poison":
        for e in enemies:
            if e.hp > 0:
                e.buffs.poison += 6
    elif potion == "focus":
        player.buffs.focus += 2
    elif potion == "block":
        player.block += 12


# ═══ 战斗引擎 ═══
class CombatSim:
    def __init__(self, player: Player, enemies: list[Enemy], verbose=False, asc=0):
        self.player = player
        self.enemies = enemies
        self.turn = 0
        self.verbose = verbose
        self.log = []
        self._asc = asc
        self._monster_ais: dict[str, MonsterAI] = {}
        for e in enemies:
            ai_data = MONSTER_AI.get(e.ai_id, {"moves": e.moves})
            self._monster_ais[e.ai_id + str(id(e))] = MonsterAI(e, ai_data)

    def _get_ai(self, enemy: Enemy) -> MonsterAI:
        return self._monster_ais.get(enemy.ai_id + str(id(enemy)))

    def _log(self, msg):
        if self.verbose:
            self.log.append(msg)

    def _calc_damage(self, base_damage, attacker_buffs, target_buffs, hits=1):
        # STS2源码: Additive先(strength), 然后所有Multiplicative连乘(decimal精度), 最后int
        dmg = base_damage + attacker_buffs.strength
        mult = 1.0
        if attacker_buffs.weak > 0:
            mult *= 0.75
        if target_buffs.vulnerable > 0:
            mult *= 1.5
        dmg = int(dmg * mult)
        dmg = max(0, dmg)
        return dmg * hits

    def _calc_block(self, base_block, buffs):
        blk = base_block + buffs.dexterity
        # 🔴 frail减挡
        if buffs.frail > 0:
            blk = int(blk * 0.75)
        return max(0, blk)

    def _apply_debuff(self, target: Entity, debuff_name: str, amount: int):
        """应用debuff，检查artifact"""
        if target.buffs.artifact > 0:
            target.buffs.artifact -= 1
            self._log(f"  🛡️ {target.name} artifact抵消{debuff_name}")
            return
        current = getattr(target.buffs, debuff_name, 0)
        setattr(target.buffs, debuff_name, current + amount)

    def _apply_damage(self, target: Entity, damage: int) -> int:
        # Intangible: all damage reduced to 1
        if target.buffs.intangible > 0 and damage > 0:
            damage = 1
        # Buffer check
        if target.buffs.buffer > 0 and damage > 0:
            target.buffs.buffer -= 1
            return 0
        # Curl up: first hit grants block
        if isinstance(target, Enemy) and target.buffs.curl_up > 0 and damage > 0:
            target.block += target.buffs.curl_up
            target.buffs.curl_up = 0
        if target.block >= damage:
            target.block -= damage
            if isinstance(target, Player):
                jug = getattr(target.buffs, '_juggernaut', 0)
                if jug > 0:
                    alive = [e for e in self.enemies if e.hp > 0]
                    if alive:
                        t = random.choice(alive)
                        t.hp -= jug
            return 0
        remaining = damage - target.block
        target.block = 0
        target.hp -= remaining
        if isinstance(target, Player) and target.buffs.plated_armor > 0:
            target.buffs.plated_armor = max(0, target.buffs.plated_armor - 1)
        return remaining

    def _shuffle_draw_pile(self):
        self.player.draw_pile = self.player.discard[:]
        random.shuffle(self.player.draw_pile)
        self.player.discard = []

    def _draw_cards(self, count):
        for _ in range(count):
            if not self.player.draw_pile:
                self._shuffle_draw_pile()
                if not self.player.draw_pile:
                    break
            if self.player.draw_pile:
                self.player.hand.append(self.player.draw_pile.pop())

    def _channel_orb(self, orb_type: str):
        if len(self.player.orbs) >= self.player.orb_slots:
            self._evoke_orb()
        self.player.orbs.append(Orb(orb_type=orb_type))
        self._log(f"  引导{orb_type}球 (共{len(self.player.orbs)}球)")

    def _evoke_orb(self, orb_index: int = 0):
        if not self.player.orbs:
            return
        orb_index = min(orb_index, len(self.player.orbs) - 1)
        orb = self.player.orbs.pop(orb_index)
        focus = self.player.buffs.focus
        if orb.orb_type == "lightning":
            dmg = max(0, 8 + focus)
            target = min((e for e in self.enemies if e.hp > 0), key=lambda e: e.hp, default=None)
            if target:
                self._apply_damage(target, dmg)
                self._log(f"  ⚡触发闪电球: {target.name} 受{dmg}伤")
            thunder = getattr(self.player.buffs, '_thunder', 0)
            if thunder > 0:
                t2 = min((e for e in self.enemies if e.hp > 0), key=lambda e: e.hp, default=None)
                if t2:
                    self._apply_damage(t2, thunder)
        elif orb.orb_type == "frost":
            blk = max(0, 5 + focus)
            self.player.block += blk
            self._log(f"  ❄️触发冰球: +{blk}格挡")
            hs = getattr(self.player.buffs, '_hailstorm', 0)
            if hs > 0:
                self.player.block += hs
        elif orb.orb_type == "dark":
            dmg = max(0, orb.dark_damage)
            target = min((e for e in self.enemies if e.hp > 0), key=lambda e: e.hp, default=None)
            if target:
                self._apply_damage(target, dmg)
                self._log(f"  🌑触发暗球: {target.name} 受{dmg}伤")

    def _passive_orbs(self):
        focus = self.player.buffs.focus
        for orb in self.player.orbs:
            if orb.orb_type == "lightning":
                dmg = max(0, 3 + focus)
                target = min((e for e in self.enemies if e.hp > 0), key=lambda e: e.hp, default=None)
                if target:
                    self._apply_damage(target, dmg)
            elif orb.orb_type == "frost":
                blk = max(0, 2 + focus)
                self.player.block += blk
            elif orb.orb_type == "dark":
                orb.dark_damage += max(0, 6 + focus)

    def _apply_doom(self, target: Enemy, amount: int):
        target.buffs.doom += amount
        self._log(f"  ☠️ {target.name} +{amount}灾厄 (共{target.buffs.doom})")
        if self.player.buffs.shroud_stacks > 0:
            blk = self.player.buffs.shroud_stacks * amount
            self.player.block += blk
            self._log(f"  🛡️ Shroud: +{blk}格挡")

    def _check_doom_kills(self):
        for e in self.enemies:
            if e.hp > 0 and e.buffs.doom > 0 and e.hp <= e.buffs.doom:
                self._log(f"  ☠️☠️ 灾厄击杀 {e.name}! ({e.hp}HP ≤ {e.buffs.doom}灾厄)")
                e.hp = 0

    def _exhaust_card(self, card: Card):
        self.player.exhaust_pile.append(card)
        if self.player.buffs.feel_no_pain > 0:
            blk = self.player.buffs.feel_no_pain
            self.player.block += blk
            self._log(f"  无痛: +{blk}格挡")
        if self.player.buffs.dark_embrace > 0:
            self._draw_cards(self.player.buffs.dark_embrace)
        if getattr(self.player.buffs, '_spirit_ash', False):
            alive = [e for e in self.enemies if e.hp > 0]
            if alive:
                t = random.choice(alive)
                self._apply_doom(t, 3)

    def _discard_card(self, card: Card, to_exhaust=False):
        self.player.turn_discards += 1
        if to_exhaust:
            self._exhaust_card(card)
        else:
            self.player.discard.append(card)
        if card.effect == "tactician":
            self.player.energy += 1
            self._log(f"  策术家: +1能量")

    def _start_turn(self):
        self.turn += 1
        self.player.energy = self.player.max_energy
        self.player.turn_discards = 0
        self._corruption_skills_this_turn = 0
        self.player.buffs._rage = 0

        ent = getattr(self.player.buffs, '_energy_next_turn', 0)
        if ent > 0:
            self.player.energy += ent
            self.player.buffs._energy_next_turn = 0

        intang = getattr(self.player.buffs, 'intangible', 0)
        if intang > 0:
            self.player.buffs.intangible -= 1

        bh = getattr(self.player.buffs, '_black_hole', 0)
        if bh > 0:
            for e in self.enemies:
                if e.hp > 0:
                    e.buffs.strength = max(0, e.buffs.strength - bh)

        if not self.player.buffs.block_retain:
            self.player.block = 0

        if self.player.buffs.metallicize > 0:
            self.player.block += self.player.buffs.metallicize

        bc = getattr(self.player.buffs, '_biased_cog', 0)
        if bc > 0:
            self.player.buffs.focus -= bc

        wf = getattr(self.player.buffs, '_wraith_form', 0)
        if wf > 0:
            self.player.buffs.dexterity -= wf

        if self.player.buffs.strength_per_turn > 0:
            self.player.buffs.strength += self.player.buffs.strength_per_turn
            self._log(f"  恶魔形态: +{self.player.buffs.strength_per_turn}力量 → 总{self.player.buffs.strength}")

        if self.player.buffs.noxious_fume > 0:
            for e in self.enemies:
                if e.hp > 0:
                    e.buffs.poison += self.player.buffs.noxious_fume

        if self.player.buffs.countdown_doom > 0:
            alive = [e for e in self.enemies if e.hp > 0]
            if alive:
                t = random.choice(alive)
                self._apply_doom(t, self.player.buffs.countdown_doom)

        if self.player.buffs.plated_armor > 0:
            self.player.block += self.player.buffs.plated_armor

        ib = getattr(self.player.buffs, '_infinite_blades', 0)
        if ib > 0:
            for _ in range(ib):
                shiv = Card(id="Shiv", name_cn="飞刀", cost=0, card_type="攻击",
                            damage=4, effect="shiv_exhaust", effect_value=0)
                self.player.hand.append(shiv)

        cm = getattr(self.player.buffs, '_crimson_mantle', 0)
        if cm > 0:
            self.player.hp -= 1
            self.player.block += cm
            rupture = getattr(self.player.buffs, '_rupture', 0)
            if rupture > 0:
                self.player.buffs.strength += rupture

        inferno = getattr(self.player.buffs, '_inferno', 0)
        if inferno > 0:
            self.player.hp -= min(inferno, 3)
            rupture = getattr(self.player.buffs, '_rupture', 0)
            if rupture > 0:
                self.player.buffs.strength += rupture

        conq = getattr(self.player.buffs, '_conqueror_energy', 0)
        if conq > 0:
            self.player.energy += conq
            self.player.buffs._conqueror_energy = 0

        tc = getattr(self.player.buffs, '_tesla_coil', 0)
        if tc > 0:
            alive = [e for e in self.enemies if e.hp > 0]
            if alive:
                t = random.choice(alive)
                self._apply_damage(t, tc)

        tools = getattr(self.player.buffs, '_tools_of_trade', 0)
        if tools > 0 and self.player.hand:
            discard_card = random.choice(self.player.hand)
            self.player.hand.remove(discard_card)
            self._discard_card(discard_card)
            self._draw_cards(1)

        apply_relics_turn(self)
        draw_count = HAND_SIZE + self.player.buffs.draw_per_turn
        # RingOfTheSnake: 第1回合多抽2张
        if self.turn == 1 and "RingOfTheSnake" in self.player.relics:
            draw_count += 2
        # DivineDestiny: 第1回合+6格挡
        if self.turn == 1 and "DivineDestiny" in self.player.relics:
            self.player.block += 6
        # Lantern: 第1回合+1能量
        if self.turn == 1 and "Lantern" in self.player.relics:
            self.player.energy += 1
        # BagOfPreparation: 第1回合+2抽牌
        if self.turn == 1 and "BagOfPreparation" in self.player.relics:
            draw_count += 2
        # HornCleat: 第2回合+14格挡
        if self.turn == 2 and "HornCleat" in self.player.relics:
            self.player.block += 14
        self._draw_cards(draw_count)

    # 缺失效果补丁：data_loader不可修改，在这里补上关键牌的效果
    _CARD_EFFECT_PATCH = {
        "BattleTrance": ("battle_trance", 3),   # 抽3张牌
        "Adrenaline": ("adrenaline", 0),          # 抽2张+1能量
        "Dash": ("dash", 0),                       # +10格挡+10攻击
        "Predator": ("predator", 0),               # 打15伤+抽2张
        "PiercingWail": ("piercing_wail", 0),      # 所有敌人-6力量
        "SuckerPunch": ("sucker_punch", 0),        # 7伤+1虚弱
        "Pounce": ("pounce", 0),                    # 打+1虚弱
        "Disarm": ("disarm", 0),                    # -2力量
        "Shockwave": ("shockwave", 0),              # 所有敌人+3虚弱+3易伤
        "Clothesline": ("clothesline", 0),          # 12伤+2虚弱
        "Thunderclap": ("thunderclap", 0),          # 4伤所有+1易伤
        "Stomp": ("stomp", 0),                       # 12伤+2虚弱
    }

    def _play_card(self, card: Card, target: Optional[Enemy] = None) -> bool:
        # 补丁：修复缺失效果
        if card.id in self._CARD_EFFECT_PATCH and not card.effect:
            card.effect, card.effect_value = self._CARD_EFFECT_PATCH[card.id]

        actual_cost = card.cost
        if self.player.buffs.corruption and card.card_type == "技能":
            actual_cost = 0
        if card.effect == "eviscerate":
            actual_cost = max(0, actual_cost - self.player.turn_discards)

        if actual_cost > self.player.energy:
            return False
        self.player.energy -= actual_cost

        # ─── 攻击伤害 ───
        # 效果处理器自带伤害的牌，跳过通用伤害路径（避免双重伤害）
        _EFFECT_HANDLES_DAMAGE = {
            "fiend_fire", "whirlwind", "perfected_strike", "body_slam",
            "twin_strike", "sword_boomerang", "rampage", "feed", "hyperbeam",
            "eviscerate", "times_up", "blight_strike", "osty_squeeze",
            "heavenly_drill", "bone_spear", "fan_of_knives",
            "sucker_punch", "pounce", "stomp", "clothesline", "neutralize",
            "assassinate", "falling_star", "gamma_blast", "fear", "debilitate",
            "sic_em", "go_for_eyes", "beam_cell", "uppercut",
            "dash", "predator", "pommel_strike", "anger", "bludgeon",
            "backstab", "slice", "meteor_strike", "sunder",
            "adaptive_strike", "focused_strike", "astral_pulse",
            "collision_course", "sweeping_beam",
            "radiate", "banshees_cry", "the_scythe", "graveblast",
            "high_five", "snap", "unleash", "soul_storm", "flick_flack",
            "misery", "veilpiercer", "osty_attack", "osty_fetch",
            "osty_flatten", "thunderclap", "subjugate",
            "enfeebling_touch", "capture_spirit", "pull_from_below",
        }
        if card.damage > 0 and card.card_type == "攻击" and card.effect not in _EFFECT_HANDLES_DAMAGE:
            if card.effect == "body_slam":
                raw_dmg = self.player.block
            elif card.id == "Shiv":
                raw_dmg = card.damage + getattr(self.player.buffs, '_accuracy', 0)
            elif card.effect == "claw":
                raw_dmg = card.damage + getattr(self, '_claw_bonus', 0)
            else:
                raw_dmg = card.damage

            targets = [target] if target else [e for e in self.enemies if e.hp > 0]
            for t in targets:
                if t and t.hp > 0:
                    dmg = self._calc_damage(raw_dmg, self.player.buffs, t.buffs, card.hits)
                    actual = self._apply_damage(t, dmg)
                    self._log(f"  → {card.name_cn} 打 {t.name} {dmg}伤")
                    if self.player.buffs.reaper_form and actual > 0 and t.hp > 0:
                        self._apply_doom(t, actual)

        # ─── 格挡 ───
        if card.block > 0:
            blk = self._calc_block(card.block, self.player.buffs)
            self.player.block += blk
            self._log(f"  → {card.name_cn} +{blk}格挡")

        # ─── 特殊效果 ───
        eff = card.effect
        val = card.effect_value

        self._process_effect(card, eff, val, target)

        # Rage: attack cards gain block
        if card.card_type == "攻击" and getattr(self.player.buffs, '_rage', 0) > 0:
            self.player.block += self.player.buffs._rage

        # AfterImage
        ai_val = getattr(self.player.buffs, '_after_image', 0)
        if ai_val > 0:
            self.player.block += ai_val

        # Envenom
        if card.card_type == "攻击" and card.damage > 0:
            env = getattr(self.player.buffs, '_envenom', 0)
            if env > 0 and target and target.hp > 0:
                target.buffs.poison += env

        # ─── 牌归宿 ───
        if card.card_type == "能力":
            sp = getattr(self.player.buffs, '_storm_power', 0)
            if sp > 0:
                for _ in range(sp):
                    self._channel_orb("lightning")
        elif card.effect in ("shiv_exhaust",) or card.id == "Shiv":
            self._exhaust_card(card)
        elif self.player.buffs.corruption and card.card_type == "技能":
            self._exhaust_card(card)
        elif card.effect == "calculated_gamble":
            self._exhaust_card(card)
        elif card.effect == "particle_wall":
            self.player.hand.append(card)
        else:
            self.player.discard.append(card)

        return True

    def _process_effect(self, card, eff, val, target):
        """Process card special effects — extracted for readability."""
        if eff == "strength":
            self.player.buffs.strength += val
        elif eff == "strength_per_turn":
            self.player.buffs.strength_per_turn += val
        elif eff == "dexterity":
            self.player.buffs.dexterity += val
        elif eff == "focus":
            self.player.buffs.focus += val
            self._log(f"  +{val}集中 → 总{self.player.buffs.focus}")
        elif eff == "vulnerable" and target:
            self._apply_debuff(target, 'vulnerable', val)
        elif eff == "poison" and target:
            target.buffs.poison += val
            self._log(f"  {target.name} +{val}毒")
        elif eff == "noxious_fume":
            self.player.buffs.noxious_fume += val
        elif eff == "block_retain":
            self.player.buffs.block_retain = True
        elif eff == "corruption":
            self.player.buffs.corruption = True
            self._log("  腐化激活！技能0费+消耗")
        elif eff == "feel_no_pain":
            self.player.buffs.feel_no_pain += val
        elif eff == "dark_embrace":
            self.player.buffs.dark_embrace += val
        elif eff == "metallicize":
            self.player.buffs.metallicize += val
        elif eff == "orb_slot":
            self.player.orb_slots += val
        elif eff == "channel_lightning":
            for _ in range(max(1, val)):
                self._channel_orb("lightning")
        elif eff == "channel_frost":
            for _ in range(max(1, val)):
                self._channel_orb("frost")
        elif eff == "channel_dark":
            for _ in range(max(1, val)):
                self._channel_orb("dark")
        elif eff == "consume":
            self.player.buffs.focus += 2
            self.player.orb_slots = max(0, self.player.orb_slots - 1)
        elif eff == "evoke":
            for _ in range(val):
                self._evoke_orb()
        elif eff == "multicast":
            if self.player.orbs:
                x = self.player.energy
                self.player.energy = 0
                for _ in range(x):
                    if self.player.orbs:
                        self._evoke_orb(0)
                self._log(f"  多重施放 ×{x}")
        elif eff == "biased_cog":
            self.player.buffs.focus += val
            self.player.buffs._biased_cog = getattr(self.player.buffs, '_biased_cog', 0) + 1
        elif eff == "rainbow":
            self._channel_orb("lightning")
            self._channel_orb("frost")
            self._channel_orb("dark")
        elif eff == "loop":
            self.player.buffs._loop = True
        elif eff == "fiend_fire":
            hand_count = len(self.player.hand)
            cards_to_exhaust = self.player.hand[:]
            self.player.hand = []
            for c in cards_to_exhaust:
                self._exhaust_card(c)
            if target and target.hp > 0:
                total_dmg = self._calc_damage(val, self.player.buffs, target.buffs, hand_count)
                self._apply_damage(target, total_dmg)
                self._log(f"  → 恶魔之火 消耗{hand_count}张 打{target.name} {total_dmg}伤")
        elif eff == "whirlwind":
            hits = self.player.energy
            self.player.energy = 0
            for e in self.enemies:
                if e.hp > 0 and hits > 0:
                    total = self._calc_damage(val, self.player.buffs, e.buffs, hits)
                    self._apply_damage(e, total)
        elif eff == "sever_soul":
            non_attacks = [c for c in self.player.hand if c.card_type != "攻击"]
            self.player.hand = [c for c in self.player.hand if c.card_type == "攻击"]
            for c in non_attacks:
                self._exhaust_card(c)
        elif eff == "second_wind":
            non_attacks = [c for c in self.player.hand if c.card_type != "攻击"]
            self.player.hand = [c for c in self.player.hand if c.card_type == "攻击"]
            for c in non_attacks:
                self._exhaust_card(c)
                self.player.block += val
        elif eff == "offering":
            if self.player.hp <= 10:
                return
            self.player.hp -= 6
            self.player.energy += 2
            self._draw_cards(3)
        elif eff == "blade_dance":
            for _ in range(val):
                shiv = Card(id="Shiv", name_cn="飞刀", cost=0, card_type="攻击",
                            damage=4, effect="shiv_exhaust", effect_value=0)
                self.player.hand.append(shiv)
        elif eff == "after_image":
            self.player.buffs._after_image = getattr(self.player.buffs, '_after_image', 0) + val
        elif eff == "claw":
            self._claw_bonus = getattr(self, '_claw_bonus', 0) + 2
        elif eff == "ball_lightning":
            self._channel_orb("lightning")
        elif eff == "tempest":
            x = self.player.energy
            self.player.energy = 0
            for _ in range(x):
                self._channel_orb("lightning")
        elif eff == "all_for_one":
            zero_cost = [c for c in self.player.discard if c.cost == 0]
            for c in zero_cost:
                self.player.discard.remove(c)
                self.player.hand.append(c)
        elif eff == "compile_driver":
            self._draw_cards(len(self.player.orbs))
        elif eff == "accelerant":
            self.player.buffs._accelerant = getattr(self.player.buffs, '_accelerant', 0) + val
        elif eff == "accuracy":
            self.player.buffs._accuracy = getattr(self.player.buffs, '_accuracy', 0) + val

        # ─── 灾厄效果 ───
        elif eff == "bone_spear":
            if target and target.hp > 0:
                dmg = self._calc_damage(8, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_doom(target, 8)
        elif eff == "shroud_power":
            self.player.buffs.shroud_stacks = max(self.player.buffs.shroud_stacks, val)
        elif eff == "reaper_form":
            self.player.buffs.reaper_form = True
        elif eff == "countdown_doom":
            self.player.buffs.countdown_doom += val
        elif eff == "scourge_doom":
            if target and target.hp > 0:
                self._apply_doom(target, val)
            self._draw_cards(1)
        elif eff == "no_escape_doom":
            if target and target.hp > 0:
                bonus = target.buffs.doom // 3
                total = val + bonus
                self._apply_doom(target, total)
        elif eff == "times_up":
            if target and target.hp > 0 and target.buffs.doom > 0:
                dmg = self._calc_damage(target.buffs.doom, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "doom_aoe":
            for e in self.enemies:
                if e.hp > 0:
                    self._apply_doom(e, val)
        elif eff == "negative_pulse":
            for e in self.enemies:
                if e.hp > 0:
                    self._apply_doom(e, val)
        elif eff == "blight_strike":
            if target and target.hp > 0:
                doom_bonus = min(target.buffs.doom, 20)
                dmg = self._calc_damage(val + doom_bonus, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff in ("end_of_days", "deathbringer"):
            if target and target.hp > 0:
                self._apply_doom(target, 20)

        # ─── Osty效果 ───
        elif eff == "summon_osty":
            self.player.osty_hp = 15
        elif eff == "osty_attack":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "osty_fetch":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._draw_cards(1)
        elif eff == "osty_flatten":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "osty_squeeze":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                osty_cards = sum(1 for c in self.player.hand
                                 if c.effect in ("osty_attack", "osty_fetch", "osty_flatten", "osty_squeeze"))
                hits = max(1, osty_cards + 1)
                dmg = self._calc_damage(val, self.player.buffs, target.buffs, hits)
                self._apply_damage(target, dmg)

        # ─── 弃牌效果 ───
        elif eff == "concentrate":
            discard_n = min(2, len(self.player.hand))
            to_discard = sorted(self.player.hand, key=lambda c: (c.damage + c.block))[:discard_n]
            for c in to_discard:
                if c in self.player.hand:
                    self.player.hand.remove(c)
                    self._discard_card(c)
            self._draw_cards(3)
        elif eff == "acrobatics":
            self._draw_cards(val)
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.damage + c.block)
                self.player.hand.remove(worst)
                self._discard_card(worst)
        elif eff == "tools_of_trade":
            self.player.buffs._tools_of_trade = getattr(self.player.buffs, '_tools_of_trade', 0) + 1
        elif eff == "storm_of_steel":
            cards_count = len(self.player.hand)
            to_discard = self.player.hand[:]
            self.player.hand = []
            for c in to_discard:
                self._discard_card(c)
            for _ in range(cards_count):
                shiv = Card(id="Shiv", name_cn="飞刀", cost=0, card_type="攻击",
                            damage=4, effect="shiv_exhaust", effect_value=0)
                self.player.hand.append(shiv)
        elif eff == "calculated_gamble":
            count = len(self.player.hand)
            to_discard = self.player.hand[:]
            self.player.hand = []
            for c in to_discard:
                self._discard_card(c)
            self._draw_cards(count)
        elif eff == "eviscerate":
            if target and target.hp > 0:
                dmg = self._calc_damage(7, self.player.buffs, target.buffs, 3)
                self._apply_damage(target, dmg)
        elif eff == "tactician":
            pass
        elif eff == "consuming_shadow":
            bonus = max(5, self.player.buffs.focus * 2)
            for orb in self.player.orbs:
                if orb.orb_type == "dark":
                    orb.dark_damage += bonus
        elif eff in ("borrowed_time", "deaths_door"):
            self.player.block += 10

        # ─── 飞刀效果 ───
        elif eff == "infinite_blades":
            self.player.buffs._infinite_blades = getattr(self.player.buffs, '_infinite_blades', 0) + val
        elif eff == "fan_of_knives":
            # STS2: FanOfKnives是能力牌，给FanOfKnivesPower+生成4飞刀
            self.player.buffs._fan_of_knives = True
            for _ in range(4):
                shiv = Card(id="Shiv", name_cn="飞刀", cost=0, card_type="攻击",
                            damage=4, effect="shiv_exhaust", effect_value=0)
                self.player.hand.append(shiv)
        elif eff == "phantom_blades":
            self.player.buffs._infinite_blades = getattr(self.player.buffs, '_infinite_blades', 0) + 1
        elif eff == "hidden_daggers":
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.damage + c.block)
                if worst in self.player.hand:
                    self.player.hand.remove(worst)
                    self._discard_card(worst)
            self._draw_cards(1)
            for _ in range(val):
                shiv = Card(id="Shiv", name_cn="飞刀", cost=0, card_type="攻击",
                            damage=4, effect="shiv_exhaust", effect_value=0)
                self.player.hand.append(shiv)
        elif eff == "knife_trap":
            self.player.buffs.metallicize += val
        elif eff == "cloak_dagger":
            blk = self._calc_block(6, self.player.buffs)
            self.player.block += blk
            shiv = Card(id="Shiv", name_cn="飞刀", cost=0, card_type="攻击",
                        damage=4, effect="shiv_exhaust", effect_value=0)
            self.player.hand.append(shiv)
        elif eff == "prepared":
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.damage + c.block)
                if worst in self.player.hand:
                    self.player.hand.remove(worst)
                    self._discard_card(worst)
            self._draw_cards(1)
        elif eff == "expertise":
            draw_n = max(0, 6 - len(self.player.hand))
            if draw_n < 1:
                draw_n = 2
            self._draw_cards(draw_n)
        elif eff == "envenom":
            self.player.buffs._envenom = getattr(self.player.buffs, '_envenom', 0) + val
        elif eff == "corrosive_wave":
            for e in self.enemies:
                if e.hp > 0:
                    e.buffs.poison += 3
                    self._apply_debuff(e, 'weak', 3)
        elif eff == "mirage":
            self.player.block += 12
            for e in self.enemies:
                if e.hp > 0:
                    e.buffs.poison += 2
            self._exhaust_card(card)
        elif eff == "outbreak":
            self.player.buffs._outbreak = getattr(self.player.buffs, '_outbreak', 0) + val

        # ─── 铁甲补充 ───
        elif eff == "bloodletting":
            self.player.hp -= 3
            self.player.energy += 2
            rupture = getattr(self.player.buffs, '_rupture', 0)
            if rupture > 0:
                self.player.buffs.strength += rupture
        elif eff == "burning_pact":
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.damage + c.block)
                if worst in self.player.hand:
                    self.player.hand.remove(worst)
                    self._exhaust_card(worst)
            self._draw_cards(2)
        elif eff == "havoc":
            if self.player.draw_pile:
                top = self.player.draw_pile.pop()
                if top.cost <= self.player.energy + 1:
                    alive = [e for e in self.enemies if e.hp > 0]
                    t = alive[0] if alive else None
                    self._play_card(top, t)
                else:
                    self.player.discard.append(top)
        elif eff == "dominate_card":
            self.player.buffs.strength += 2
            self._exhaust_card(card)
        elif eff == "inferno_power":
            self.player.buffs._inferno = getattr(self.player.buffs, '_inferno', 0) + val
        elif eff == "crimson_mantle":
            self.player.buffs._crimson_mantle = getattr(self.player.buffs, '_crimson_mantle', 0) + val
        elif eff == "juggernaut":
            self.player.buffs._juggernaut = getattr(self.player.buffs, '_juggernaut', 0) + val
        elif eff == "plating":
            self.player.buffs.plated_armor += val
        elif eff == "calcify":
            self.player.buffs.metallicize += val
        elif eff == "unmovable":
            self.player.block += 15
        elif eff == "demonic_shield":
            self.player.block += 30
            self._exhaust_card(card)
        elif eff == "malaise":
            x = self.player.energy
            self.player.energy = 0
            if target and target.hp > 0 and x > 0:
                target.buffs.strength = max(target.buffs.strength - x, 0)
                self._apply_debuff(target, 'weak', x)
            self._exhaust_card(card)
        elif eff == "impervious":
            self.player.block += 30
            self._exhaust_card(card)
        elif eff == "shrug_it_off":
            blk = self._calc_block(8, self.player.buffs)
            self.player.block += blk
            self._draw_cards(1)
        elif eff == "flame_barrier":
            blk = self._calc_block(12, self.player.buffs)
            self.player.block += blk
            self.player.buffs.thorns += 4
        elif eff == "hemokinesis":
            self.player.hp -= 3
            rupture = getattr(self.player.buffs, '_rupture', 0)
            if rupture > 0:
                self.player.buffs.strength += rupture
        elif eff == "blood_wall":
            lose = min(6, self.player.hp - 1)
            if lose > 0:
                self.player.hp -= lose
                self.player.block += lose * 2
                rupture = getattr(self.player.buffs, '_rupture', 0)
                if rupture > 0:
                    self.player.buffs.strength += rupture
        elif eff == "true_grit":
            blk = self._calc_block(7, self.player.buffs)
            self.player.block += blk
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.damage + c.block)
                if worst in self.player.hand:
                    self.player.hand.remove(worst)
                    self._exhaust_card(worst)
        elif eff == "rupture":
            self.player.buffs._rupture = getattr(self.player.buffs, '_rupture', 0) + val

        # ─── 缺陷体补充 ───
        elif eff == "storm_power":
            self.player.buffs._storm_power = getattr(self.player.buffs, '_storm_power', 0) + val
        elif eff == "thunder":
            self.player.buffs._thunder = getattr(self.player.buffs, '_thunder', 0) + val
        elif eff == "hailstorm":
            self.player.buffs._hailstorm = getattr(self.player.buffs, '_hailstorm', 0) + val
        elif eff == "voltaic":
            self._channel_orb("lightning")
            self._exhaust_card(card)
        elif eff == "overclock":
            self._draw_cards(2)
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.damage + c.block)
                if worst in self.player.hand:
                    self.player.hand.remove(worst)
                    self._discard_card(worst)
        elif eff == "turbo":
            self.player.energy += 2
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.damage + c.block)
                if worst in self.player.hand:
                    self.player.hand.remove(worst)
                    self._discard_card(worst)
        elif eff == "synchronize":
            self.player.buffs.focus += 1
            self._exhaust_card(card)
        elif eff == "machine_learning":
            self.player.buffs.draw_per_turn += 1
        elif eff == "buffer":
            self.player.buffs.buffer += val
        elif eff == "echo_form":
            self.player.buffs._echo_form = True
        elif eff == "tesla_coil":
            self.player.buffs._tesla_coil = getattr(self.player.buffs, '_tesla_coil', 0) + val

        # ─── 储君 ───
        elif eff == "decree":
            # 发布法令：给所有敌人+2易伤（储君起始牌）
            for e in self.enemies:
                if e.hp > 0:
                    self._apply_debuff(e, 'vulnerable', 2)
        elif eff == "subjugate":
            # 压制：给目标+2虚弱（储君起始牌）
            if target and target.hp > 0:
                self._apply_debuff(target, 'weak', 2)
                dmg = self._calc_damage(8, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "monologue":
            self.player.buffs.strength += 2
        elif eff == "monarchs_gaze":
            self.player.buffs.strength += 2
        elif eff == "sword_sage":
            self.player.buffs._sword_sage = getattr(self.player.buffs, '_sword_sage', 0) + val
        elif eff == "guards":
            self.player.block += 10
            self._exhaust_card(card)
        elif eff == "big_bang":
            # STS2: BigBang是技能牌，抽1牌+1能量+1星+锻造5
            self._draw_cards(1)
            self.player.energy += 1
            self._exhaust_card(card)
        elif eff == "stoke":
            self.player.buffs.strength += 5
            self._exhaust_card(card)
        elif eff == "glow":
            self.player.energy += 2
        elif eff == "conqueror":
            self.player.buffs._conqueror_energy = getattr(self.player.buffs, '_conqueror_energy', 0) + 2
        elif eff in ("kingly_punch", "kingly_kick", "knockout_blow", "bombardment", "devastate"):
            pass
        elif eff == "furnace":
            self.player.buffs.strength += 3
        elif eff == "spoils_of_battle":
            self._draw_cards(2)
            self.player.energy += 1
        elif eff == "the_smith":
            self.player.buffs.strength += 2
            self.player.buffs.dexterity += 2
        elif eff == "gather_light":
            self.player.energy += 1
            self._draw_cards(1)
            self.player.block += 5
        elif eff == "radiate":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(8, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)
        elif eff == "child_of_stars":
            self.player.buffs.strength += 1
            self.player.buffs.dexterity += 1
        elif eff == "sealed_throne":
            self.player.buffs.strength += 3
            self.player.block += 10

        # ─── 亡灵契约师补充 ───
        elif eff == "sacrifice_nb":
            self.player.block += 15
        elif eff == "glimpse":
            if target and target.hp > 0:
                self._apply_doom(target, 8)
            self._exhaust_card(card)
        elif eff == "devour_life":
            self.player.buffs._devour_life = getattr(self.player.buffs, '_devour_life', 0) + val
        elif eff == "cruelty":
            self.player.buffs.strength += val
        elif eff == "haunt":
            if target and target.hp > 0:
                self._apply_doom(target, 5)
        elif eff == "spirit_ash":
            self.player.buffs._spirit_ash = True
        elif eff == "call_void":
            self.player.buffs.countdown_doom += 2
        elif eff == "seance":
            if self.player.exhaust_pile:
                retrieved = self.player.exhaust_pile.pop()
                self.player.hand.append(retrieved)

        # ─── 储君扩展 ───
        elif eff in ("beat_into_shape", "wrought_in_war"):
            pass
        elif eff == "refine_blade":
            self.player.buffs.strength += 1
            self._draw_cards(1)
        elif eff == "summon_forth":
            self._draw_cards(2)
        elif eff == "seeking_edge":
            self.player.buffs.strength += 1
        elif eff == "bulwark":
            blk = self._calc_block(10, self.player.buffs)
            self.player.block += blk
        elif eff == "hegemony":
            self.player.buffs.strength += 2
        elif eff == "seven_stars":
            self.player.energy += 1
            self._draw_cards(1)
        elif eff == "celestial_might":
            self.player.buffs.strength += 3
        elif eff == "resonance":
            for e in self.enemies:
                if e.hp > 0:
                    self._apply_debuff(e, 'vulnerable', 2)
        elif eff in ("solar_strike", "shining_strike"):
            pass
        elif eff == "cloak_of_stars":
            blk = self._calc_block(8, self.player.buffs)
            self.player.block += blk
            self.player.buffs.strength += 1
        elif eff == "venerate":
            self.player.buffs.strength += 1
            self.player.buffs.dexterity += 1
        elif eff == "genesis":
            self._draw_cards(3)
        elif eff == "alignment":
            self.player.buffs.strength += 1
            self.player.block += 5
        elif eff == "spectrum_shift":
            self._draw_cards(2)
            self.player.energy += 1
        elif eff == "arsenal":
            self._draw_cards(3)
        elif eff == "bundle_of_joy":
            self._draw_cards(2)
            self.player.block += 5
        elif eff == "heirloom_hammer":
            pass
        elif eff == "quasar":
            # STS2: Quasar是技能牌，从无色牌池选一张加入手牌（模拟器简化为抽1牌）
            self._draw_cards(1)
        elif eff == "manifest_authority":
            self.player.buffs.strength += 2
            self.player.block += 8
        elif eff == "pillar_of_creation":
            self.player.block += 15
            self._draw_cards(1)

        # ─── 静默扩展 ───
        elif eff in ("finisher", "leading_strike"):
            if eff == "leading_strike":
                self._draw_cards(1)
        elif eff == "dodge_and_roll":
            blk = self._calc_block(6, self.player.buffs)
            self.player.block += blk
        elif eff == "leg_sweep":
            blk = self._calc_block(11, self.player.buffs)
            self.player.block += blk
            if target and target.hp > 0:
                self._apply_debuff(target, 'weak', 2)
        elif eff == "escape_plan":
            blk = self._calc_block(5, self.player.buffs)
            self.player.block += blk
            self._draw_cards(1)
        elif eff == "backflip":
            blk = self._calc_block(5, self.player.buffs)
            self.player.block += blk
            self._draw_cards(2)
        elif eff == "deflect":
            blk = self._calc_block(4, self.player.buffs)
            self.player.block += blk
        elif eff == "blur":
            blk = self._calc_block(5, self.player.buffs)
            self.player.block += blk
            self.player.buffs.block_retain = True
        elif eff == "memento_mori":
            pass
        elif eff == "flick_flack":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(6, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)

        # ─── 缺陷扩展 ───
        elif eff == "cold_snap":
            self._channel_orb("frost")
        elif eff == "sweeping_beam":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(6, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)
            self._draw_cards(1)
        elif eff == "scrape":
            self._draw_cards(2)
        elif eff == "ftl":
            self._draw_cards(1)
        elif eff == "go_for_eyes":
            if target and target.hp > 0:
                self._apply_debuff(target, 'weak', 1)
        elif eff == "beam_cell":
            if target and target.hp > 0:
                self._apply_debuff(target, 'vulnerable', 1)
        elif eff == "hologram":
            blk = self._calc_block(3, self.player.buffs)
            self.player.block += blk
            if self.player.discard:
                retrieved = self.player.discard.pop()
                self.player.hand.append(retrieved)
        elif eff == "boost_away":
            blk = self._calc_block(5, self.player.buffs)
            self.player.block += blk
            self._draw_cards(1)
        elif eff == "hotfix":
            self._draw_cards(1)
        elif eff == "shadow_shield":
            blk = self._calc_block(11 + len(self.player.orbs) * 3, self.player.buffs)
            self.player.block += blk

        # ─── 亡灵扩展 ───
        elif eff == "unleash":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                dmg = self._calc_damage(10, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "right_hand_hand":
            if self.player.osty_hp > 0:
                self.player.block += 8
        elif eff == "high_five":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                dmg = self._calc_damage(11, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self.player.block += 11
        elif eff == "sic_em":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                dmg = self._calc_damage(5, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'vulnerable', 1)
        elif eff == "snap":
            if self.player.osty_hp > 0 and target and target.hp > 0:
                dmg = self._calc_damage(7, self.player.buffs, target.buffs, 2)
                self._apply_damage(target, dmg)
        elif eff == "pagestorm":
            self._draw_cards(3)
            for e in self.enemies:
                if e.hp > 0:
                    self._apply_doom(e, 2)
        elif eff == "pull_from_below":
            if target and target.hp > 0:
                self._apply_doom(target, 4)
                self.player.block += 4
        elif eff == "soul_storm":
            for e in self.enemies:
                if e.hp > 0:
                    self._apply_doom(e, 3)
                    dmg = self._calc_damage(5, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)
        elif eff == "capture_spirit":
            if target and target.hp > 0:
                self._apply_doom(target, 5)
            self._draw_cards(1)
        elif eff == "veilpiercer":
            if target and target.hp > 0:
                doom_bonus = target.buffs.doom // 2
                dmg = self._calc_damage(8 + doom_bonus, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "sculpting_strike":
            pass

        # ─── 补丁效果 ───
        elif eff == "battle_trance":
            self._draw_cards(3)
        elif eff == "adrenaline":
            self._draw_cards(2)
            self.player.energy += 1
        elif eff == "dash":
            if target and target.hp > 0:
                dmg = self._calc_damage(10, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            blk = self._calc_block(10, self.player.buffs)
            self.player.block += blk
        elif eff == "predator":
            if target and target.hp > 0:
                dmg = self._calc_damage(15, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            self._draw_cards(2)
        elif eff == "piercing_wail":
            for e in self.enemies:
                if e.hp > 0:
                    loss = min(e.buffs.strength, 6)
                    e.buffs.strength -= loss
                    e.buffs._piercing_wail = getattr(e.buffs, '_piercing_wail', 0) + loss
            self._exhaust_card(card)
        elif eff == "sucker_punch":
            if target and target.hp > 0:
                dmg = self._calc_damage(8, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'weak', 1)
        elif eff == "pounce":
            if target and target.hp > 0:
                dmg = self._calc_damage(12, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'weak', 1)
        elif eff == "disarm":
            if target and target.hp > 0:
                target.buffs.strength = max(0, target.buffs.strength - 2)
            self._exhaust_card(card)
        elif eff == "shockwave":
            for e in self.enemies:
                if e.hp > 0:
                    self._apply_debuff(e, 'weak', 3)
                    self._apply_debuff(e, 'vulnerable', 3)
            self._exhaust_card(card)
        elif eff == "clothesline":
            if target and target.hp > 0:
                dmg = self._calc_damage(12, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'weak', 2)
        elif eff == "thunderclap":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(4, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)
                    self._apply_debuff(e, 'vulnerable', 1)
        elif eff == "stomp":
            if target and target.hp > 0:
                dmg = self._calc_damage(12, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'weak', 2)

        # ─── 铁甲扩展 ───
        elif eff in ("mangle", "molten_fist", "ashen_strike"):
            pass
        elif eff == "uppercut":
            if target and target.hp > 0:
                self._apply_debuff(target, 'weak', 1)
                self._apply_debuff(target, 'vulnerable', 1)
        elif eff == "spite":
            self.player.hp -= 2
            rupture = getattr(self.player.buffs, '_rupture', 0)
            if rupture > 0:
                self.player.buffs.strength += rupture
        elif eff == "colossus":
            blk = self._calc_block(15, self.player.buffs)
            self.player.block += blk
        elif eff in ("iron_wave", "armaments"):
            blk = self._calc_block(5, self.player.buffs)
            self.player.block += blk

        # ─── 新流派效果 ───
        elif eff == "twin_strike":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs, 2)
                self._apply_damage(target, dmg)
        elif eff == "sword_boomerang":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(val, self.player.buffs, e.buffs, 3)
                    self._apply_damage(e, dmg)
        elif eff == "pommel_strike":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            self._draw_cards(1)
        elif eff == "anger":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            clone = build_card("Anger")
            self.player.discard.append(clone)
        elif eff == "rampage":
            if target and target.hp > 0:
                bonus = getattr(self, '_rampage_bonus', 0)
                dmg = self._calc_damage(val + bonus, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            self._rampage_bonus = getattr(self, '_rampage_bonus', 0) + 5
        elif eff == "feed":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                killed = target.hp <= dmg
                self._apply_damage(target, dmg)
                if killed:
                    self.player.max_hp += 3
                    self.player.hp += 3
            self._exhaust_card(card)
        elif eff == "bludgeon":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "perfected_strike":
            strike_count = sum(1 for c in self.player.deck if "Strike" in c.id)
            total_dmg = val + 2 * strike_count
            if target and target.hp > 0:
                dmg = self._calc_damage(total_dmg, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "rage":
            self.player.buffs._rage = getattr(self.player.buffs, '_rage', 0) + val
        elif eff == "aggression":
            self.player.buffs.strength += 2

        # 静默新流派
        elif eff == "backstab":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            self._exhaust_card(card)
        elif eff == "assassinate":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'vulnerable', 1)
            self._exhaust_card(card)
        elif eff == "slice":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "wraith_form":
            self.player.buffs.intangible = getattr(self.player.buffs, 'intangible', 0) + val
            self.player.buffs._wraith_form = getattr(self.player.buffs, '_wraith_form', 0) + 1
        elif eff == "neutralize":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'weak', 1)
        elif eff == "burst":
            self._draw_cards(2)
        elif eff == "well_laid_plans":
            self._draw_cards(1)

        # 缺陷新流派
        elif eff == "hyperbeam":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(val, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)
            self.player.buffs.focus -= 3
        elif eff == "meteor_strike":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            self.player.energy += 3
        elif eff == "sunder":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                killed = target.hp <= dmg
                self._apply_damage(target, dmg)
                if killed:
                    self.player.energy += 3
        elif eff == "double_energy":
            self.player.energy *= 2
            self._exhaust_card(card)
        elif eff == "fusion":
            self.player.energy += 1
        elif eff == "charge_battery":
            blk = self._calc_block(val, self.player.buffs)
            self.player.block += blk
            self.player.buffs._energy_next_turn = getattr(self.player.buffs, '_energy_next_turn', 0) + 1
        elif eff == "adaptive_strike":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            clone = build_card("AdaptiveStrike")
            clone.cost = 0
            self.player.discard.append(clone)
        elif eff == "coolant":
            self.player.buffs.metallicize += val
        elif eff == "chill":
            enemy_count = sum(1 for e in self.enemies if e.hp > 0)
            for _ in range(enemy_count):
                self._channel_orb("frost")
            self._exhaust_card(card)
        elif eff == "focused_strike":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            self.player.buffs.focus += 1

        # 储君新流派
        elif eff == "astral_pulse":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(val, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)
        elif eff == "collision_course":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "falling_star":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'vulnerable', 1)
                self._apply_debuff(target, 'weak', 1)
        elif eff == "gamma_blast":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'vulnerable', 2)
                self._apply_debuff(target, 'weak', 2)
        elif eff == "heavenly_drill":
            x = self.player.energy
            self.player.energy = 0
            if target and target.hp > 0:
                hits = x
                if x >= 4:
                    hits = x * 2
                dmg = self._calc_damage(val, self.player.buffs, target.buffs, max(1, hits))
                self._apply_damage(target, dmg)
        elif eff == "particle_wall":
            blk = self._calc_block(val, self.player.buffs)
            self.player.block += blk
        elif eff == "neutron_aegis":
            self.player.buffs.plated_armor += val
        elif eff == "parry":
            self.player.buffs.metallicize += val
        elif eff == "reflect":
            blk = self._calc_block(val, self.player.buffs)
            self.player.block += blk
            self.player.buffs.thorns += 3
        elif eff == "void_form":
            self.player.buffs.strength_per_turn += val
        elif eff == "black_hole":
            self.player.buffs._black_hole = getattr(self.player.buffs, '_black_hole', 0) + val
            for e in self.enemies:
                if e.hp > 0:
                    e.buffs.strength = max(0, e.buffs.strength - val)
        elif eff == "tyranny":
            self.player.buffs.strength += 3
        elif eff == "prophesize":
            self._draw_cards(val)
        elif eff == "royal_gamble":
            self._draw_cards(3)
            self._exhaust_card(card)

        # 亡灵新流派
        elif eff == "banshees_cry":
            for e in self.enemies:
                if e.hp > 0:
                    dmg = self._calc_damage(val, self.player.buffs, e.buffs)
                    self._apply_damage(e, dmg)
        elif eff == "the_scythe":
            bonus = getattr(self, '_scythe_bonus', 0)
            if target and target.hp > 0:
                dmg = self._calc_damage(val + bonus, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            self._scythe_bonus = bonus + 5
        elif eff in ("reap", "bury", "defile"):
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
        elif eff == "graveblast":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
            if self.player.discard:
                retrieved = self.player.discard.pop()
                self.player.hand.append(retrieved)
            self._exhaust_card(card)
        elif eff == "afterlife":
            self.player.osty_hp = max(self.player.osty_hp, 6)
            self._exhaust_card(card)
        elif eff == "legion_of_bone":
            self.player.osty_hp = max(self.player.osty_hp, 10)
            self._exhaust_card(card)
        elif eff == "danse_macabre":
            self.player.buffs.strength += 3
        elif eff == "eidolon":
            if len(self.player.hand) >= 6:
                self.player.buffs.intangible = getattr(self.player.buffs, 'intangible', 0) + 1
            self._exhaust_card(card)
        elif eff == "fear":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'vulnerable', 1)
        elif eff == "debilitate":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                self._apply_debuff(target, 'vulnerable', 3)
                self._apply_debuff(target, 'weak', 3)
        elif eff == "enfeebling_touch":
            if target and target.hp > 0:
                target.buffs.strength = max(0, target.buffs.strength - val)
                self._apply_debuff(target, 'weak', 2)
        elif eff == "misery":
            if target and target.hp > 0:
                dmg = self._calc_damage(val, self.player.buffs, target.buffs)
                self._apply_damage(target, dmg)
                vuln = target.buffs.vulnerable
                weak = target.buffs.weak
                for e in self.enemies:
                    if e.hp > 0 and e != target:
                        e.buffs.vulnerable += vuln
                        e.buffs.weak += weak

    def _end_player_turn(self):
        # Orichalcum: 回合结束无格挡时+6
        if "Orichalcum" in self.player.relics and self.player.block == 0:
            self.player.block += 6

        # Loop: 被动触发最后一个球
        if getattr(self.player.buffs, '_loop', False) and self.player.orbs:
            self._evoke_orb(len(self.player.orbs) - 1)

        self._passive_orbs()

        # Doom每回合对敌人造成等量伤害
        for e in self.enemies:
            if e.hp > 0 and e.buffs.doom > 0:
                self._apply_damage(e, e.buffs.doom)

        self._check_doom_kills()

        ss = getattr(self.player.buffs, '_sword_sage', 0)
        if ss > 0:
            self.player.block += ss * 3

        # 🔴 回合结束处理 — 再生
        if self.player.buffs.regenerate > 0:
            self.player.hp = min(self.player.max_hp,
                                 self.player.hp + self.player.buffs.regenerate)
            self.player.buffs.regenerate -= 1

        self.player.discard.extend(self.player.hand)
        self.player.hand = []

    def _enemy_turn(self):
        for e in self.enemies:
            if e.hp <= 0:
                continue

            # 双体Boss交互
            if e.ai_id == "Doormaker":
                door_alive = any(x.ai_id == "Door" and x.hp > 0 for x in self.enemies)
                if door_alive:
                    continue

            if e.ai_id == "Queen":
                amalgam_alive = any(x.ai_id == "TorchHeadAmalgam" and x.hp > 0 for x in self.enemies)
                if amalgam_alive:
                    amalgam = next(x for x in self.enemies if x.ai_id == "TorchHeadAmalgam" and x.hp > 0)
                    amalgam.buffs.strength += 2
                    e.block += 15
                    continue

            if e.ai_id == "Door":
                if self.turn % 2 == 1:
                    e.block = 0
                    continue

            # 毒伤
            if e.buffs.poison > 0:
                accel = getattr(self.player.buffs, '_accelerant', 0)
                triggers = min(e.buffs.poison, 1 + accel)
                total_poison = sum(e.buffs.poison - i for i in range(triggers))
                e.hp -= total_poison
                e.buffs.poison -= triggers
                if e.hp <= 0:
                    continue

            # 🔴 再生回血
            if e.buffs.regenerate > 0:
                e.hp = min(e.max_hp, e.hp + e.buffs.regenerate)
                e.buffs.regenerate -= 1

            # 仪式（每回合+力量）
            if e.buffs.ritual > 0:
                e.buffs.strength += e.buffs.ritual

            # debuff倒计时
            if e.buffs.vulnerable > 0:
                e.buffs.vulnerable -= 1
            if e.buffs.weak > 0:
                e.buffs.weak -= 1
            if e.buffs.frail > 0:
                e.buffs.frail -= 1
            e.block = 0

            # 金属化
            if e.buffs.metallicize > 0:
                e.block += e.buffs.metallicize

            # 甲板
            if e.buffs.plated_armor > 0:
                e.block += e.buffs.plated_armor

            # 通过MonsterAI获取招式
            ai = self._get_ai(e)
            combat_state = {
                "player_hp": self.player.hp,
                "player_hand": len(self.player.hand),
                "turn": self.turn,
            }
            if ai:
                move = ai.get_next_move(combat_state)
            else:
                if e.moves:
                    move = e.moves[e.move_index % len(e.moves)]
                    e.move_index += 1
                else:
                    move = {"damage": 10, "hits": 1, "block": 0}

            dmg = move.get("damage", 0)
            hits = move.get("hits", 1)
            blk = move.get("block", 0)
            try:
                dmg = int(dmg); hits = int(hits); blk = int(blk)
            except (ValueError, TypeError):
                dmg = 0; hits = 1; blk = 0

            if dmg > 0:
                if self._asc >= 9:
                    dmg = int(dmg * 1.10)
                total = self._calc_damage(dmg, e.buffs, self.player.buffs, hits)
                intang = getattr(self.player.buffs, 'intangible', 0)
                if intang > 0 and total > 1:
                    total = 1
                actual = self._apply_damage(self.player, total)
                self._log(f"  {e.name} 攻击 {total}伤(受{actual}) [{move.get('id', '?')}]")
                if self.player.buffs.thorns > 0 and actual > 0:
                    e.hp -= self.player.buffs.thorns

            if blk > 0:
                e.block += blk

        # Piercing Wail临时力量恢复（回合结束时）
        for e in self.enemies:
            if e.hp > 0:
                pw = getattr(e.buffs, '_piercing_wail', 0)
                if pw > 0:
                    e.buffs.strength += pw
                    e.buffs._piercing_wail = 0

        # 玩家debuff倒计时
        if self.player.buffs.vulnerable > 0:
            self.player.buffs.vulnerable -= 1
        if self.player.buffs.weak > 0:
            self.player.buffs.weak -= 1
        if self.player.buffs.frail > 0:
            self.player.buffs.frail -= 1

    def _pick_play(self) -> tuple[Optional[Card], Optional[Enemy]]:
        """AI决策：支持流派特化策略"""
        def eff_cost(c):
            if self.player.buffs.corruption and c.card_type == "技能":
                return 0
            if c.effect == "eviscerate":
                return max(0, c.cost - self.player.turn_discards)
            return c.cost

        playable = [c for c in self.player.hand if eff_cost(c) <= self.player.energy]
        if not playable:
            return None, None

        alive_enemies = [e for e in self.enemies if e.hp > 0]
        if not alive_enemies:
            return None, None

        # 预估来袭伤害（考虑敌人力量和虚弱）
        incoming = 0
        for e in alive_enemies:
            ai = self._get_ai(e)
            if ai and ai.moves:
                # 使用move_index（cycle_ai用的）或seq_idx
                idx = e.move_index % len(ai.moves)
                m = ai.moves[idx]
                d = m.get("damage", 0)
                h = m.get("hits", 1)
            elif e.moves:
                m = e.moves[e.move_index % len(e.moves)]
                d = m.get("damage", 0)
                h = m.get("hits", 1)
            else:
                d, h = 10, 1
            if isinstance(d, list):
                d = d[0] if d else 0
            if isinstance(h, list):
                h = h[0] if h else 1
            try:
                d = int(d); h = int(h)
            except (ValueError, TypeError):
                d = 0; h = 1
            # 加上敌人力量
            d = max(0, d + e.buffs.strength)
            # 虚弱减伤
            if e.buffs.weak > 0:
                d = int(d * 0.75)
            # 玩家易伤增伤
            if self.player.buffs.vulnerable > 0:
                d = int(d * 1.5)
            incoming += d * h

        need_block = incoming - self.player.block

        powers = [c for c in playable if c.card_type == "能力"]
        blocks_cards = [c for c in playable if c.block > 0 or c.effect in (
            "impervious", "unmovable", "colossus", "shrug_it_off",
            "escape_plan", "backflip", "deflect", "leg_sweep",
            "dodge_and_roll", "cloak_dagger", "blur",
            "hologram", "boost_away", "shadow_shield",
            "particle_wall", "reflect", "bulwark",
            "sacrifice_nb", "deaths_door", "borrowed_time",
            "true_grit", "iron_wave", "flame_barrier")]
        attacks = [c for c in playable if c.damage > 0 or c.effect in (
            "fiend_fire", "whirlwind", "claw", "ball_lightning", "blade_dance",
            "osty_attack", "osty_fetch", "osty_flatten", "osty_squeeze",
            "bone_spear", "times_up", "storm_of_steel", "blight_strike",
            "astral_pulse", "banshees_cry", "big_bang", "radiate",
            "fan_of_knives", "hyperbeam", "sweeping_beam")]
        doom_cards = [c for c in playable if c.effect in (
            "bone_spear", "scourge_doom", "no_escape_doom", "negative_pulse",
            "doom_aoe", "countdown_doom", "reaper_form")]
        orb_cards = [c for c in playable if c.effect in (
            "channel_lightning", "channel_frost", "channel_dark", "evoke",
            "multicast", "ball_lightning", "rainbow")]
        discard_cards = [c for c in playable if c.effect in (
            "concentrate", "acrobatics", "calculated_gamble")]
        scaling_powers = [c for c in powers if c.effect in (
            "strength_per_turn", "noxious_fume", "block_retain", "corruption",
            "feel_no_pain", "dark_embrace", "reaper_form", "countdown_doom")]

        target = min(alive_enemies, key=lambda e: e.hp)
        arch = getattr(self, '_arch_name', '')

        # ─── 暗球爆发流 ───
        dark_orbs = [o for o in self.player.orbs if o.orb_type == "dark"]
        total_dark_dmg = sum(o.dark_damage for o in dark_orbs)
        min_enemy_hp = min((e.hp for e in alive_enemies), default=999)

        # === ARCHETYPE-SPECIFIC AI (abbreviated for common patterns) ===
        result = self._pick_play_archetype(arch, playable, alive_enemies, target,
                                            need_block, powers, blocks_cards, attacks,
                                            doom_cards, orb_cards, discard_cards,
                                            scaling_powers, dark_orbs, total_dark_dmg,
                                            min_enemy_hp)
        if result[0] is not None:
            return result

        # ─── 通用策略（大幅优化版）───
        hp_ratio = self.player.hp / max(self.player.max_hp, 1)

        # 计算能否击杀最低HP敌人
        total_potential_dmg = 0
        remaining_energy = self.player.energy
        sorted_attacks = sorted(attacks, key=lambda c: -(c.damage * c.hits))
        for c in sorted_attacks:
            cost = c.cost
            if self.player.buffs.corruption and c.card_type == "技能":
                cost = 0
            if cost <= remaining_energy:
                raw_dmg = c.damage
                dmg = raw_dmg + self.player.buffs.strength
                if self.player.buffs.weak > 0:
                    dmg = int(dmg * 0.75)
                if target.buffs.vulnerable > 0:
                    dmg = int(dmg * 1.5)
                total_potential_dmg += max(0, dmg) * c.hits
                remaining_energy -= cost
        can_kill = total_potential_dmg >= target.hp + target.block

        # 分类debuff牌
        vuln_cards = [c for c in playable if c.effect in ("vulnerable", "uppercut",
                      "falling_star", "gamma_blast", "fear", "debilitate", "sic_em",
                      "decree", "thunderclap", "shockwave")]
        weak_cards = [c for c in playable if c.effect in ("malaise", "neutralize",
                      "leg_sweep", "corrosive_wave", "enfeebling_touch",
                      "subjugate", "clothesline", "stomp", "pounce", "sucker_punch")]
        any_vuln = any(e.buffs.vulnerable > 0 for e in alive_enemies)
        any_weak = any(e.buffs.weak > 0 for e in alive_enemies)

        # ─── 第1优先：能力牌（前3回合，且不会因此死掉）───
        if self.turn <= 3 and scaling_powers:
            sp = [c for c in scaling_powers if c.cost <= self.player.energy]
            if sp:
                sp.sort(key=lambda c: -c.effect_value)
                best_power = sp[0]
                cost_after = self.player.energy - best_power.cost
                can_block_after = any(c.block > 0 and c.cost <= cost_after for c in blocks_cards)
                if can_block_after or need_block <= 0 or hp_ratio > 0.6:
                    return best_power, None

        # ─── 第2优先：如果能杀就全力攻击 ───
        if can_kill and sorted_attacks:
            return sorted_attacks[0], target

        # ─── 第3优先：debuff（易伤/虚弱）───
        # 先上易伤（第1-2回合最佳时机）
        if vuln_cards and not any_vuln and self.turn <= 4:
            best_vuln = vuln_cards[0]
            cost_after = self.player.energy - best_vuln.cost
            can_block_after = any(c.block > 0 and c.cost <= cost_after for c in blocks_cards)
            if can_block_after or need_block <= 0 or hp_ratio > 0.5:
                return best_vuln, target

        # 上虚弱（对面伤害高时，A9+更积极）
        weak_threshold = 10 if self._asc >= 9 else 15
        if weak_cards and not any_weak and incoming >= weak_threshold:
            return weak_cards[0], target

        # ─── 第4优先：便宜的能力牌 ───
        cheap_powers = [c for c in powers if c.cost <= 1 and c.cost <= self.player.energy
                       and c.effect not in ("decree", "subjugate")]
        if cheap_powers and self.player.energy >= 2:
            return cheap_powers[0], None

        # ─── 第5优先：毒牌 ───
        poison_cards = [c for c in playable if c.effect == "poison"]
        if poison_cards:
            poison_cards.sort(key=lambda c: -c.effect_value)
            return poison_cards[0], max(alive_enemies, key=lambda e: e.hp)

        # ─── 额外：0费抽牌/能量牌优先 ───
        draw_cards = [c for c in playable if c.effect in (
            "battle_trance", "adrenaline", "offering", "acrobatics",
            "predator", "pommel_strike", "shrug_it_off",
            "backflip", "escape_plan", "spectrum_shift",
            "genesis", "arsenal", "prophesize", "glow",
            "spoils_of_battle", "gather_light", "seven_stars")]
        if draw_cards:
            zero_cost_draw = [c for c in draw_cards if c.cost == 0]
            if zero_cost_draw:
                return zero_cost_draw[0], target if zero_cost_draw[0].damage > 0 else None

        # ─── 第6优先：攻防平衡 ───
        # HP很低时极度保守
        if hp_ratio < 0.30 and blocks_cards and need_block > 0:
            blocks_cards.sort(key=lambda c: -c.block)
            return blocks_cards[0], None

        # A9+: 更保守的格挡策略（怪物+10%伤害）
        if self._asc >= 9 and hp_ratio < 0.50 and blocks_cards and need_block > 0:
            blocks_cards.sort(key=lambda c: -c.block)
            return blocks_cards[0], None

        # 来袭伤害高，先挡
        block_threshold = 0 if (self._asc >= 9 and hp_ratio < 0.6) else (3 if hp_ratio < 0.5 else 8)
        if need_block > block_threshold and blocks_cards:
            blocks_cards.sort(key=lambda c: -c.block)
            return blocks_cards[0], None

        # 安全时攻击
        if attacks:
            attacks.sort(key=lambda c: (
                -3 if c.effect in ("vulnerable", "uppercut", "falling_star") and not any_vuln else 0,
                -c.damage * c.hits * (1.5 if target.buffs.vulnerable > 0 else 1)
            ))
            return attacks[0], target

        # 剩余格挡
        if blocks_cards:
            return blocks_cards[0], None

        # 能力牌
        if powers:
            non_evoke_powers = [c for c in powers if c.effect not in ("evoke", "multicast")
                               or dark_orbs]
            if non_evoke_powers:
                return non_evoke_powers[0], None

        # 弃牌/抽牌
        if discard_cards:
            return discard_cards[0], None

        safe_playable = [c for c in playable
                        if c.effect not in ("evoke", "multicast") or dark_orbs]
        if safe_playable:
            return safe_playable[0], alive_enemies[0]

        return playable[0], alive_enemies[0]

    def _pick_play_archetype(self, arch, playable, alive_enemies, target,
                              need_block, powers, blocks_cards, attacks,
                              doom_cards, orb_cards, discard_cards,
                              scaling_powers, dark_orbs, total_dark_dmg,
                              min_enemy_hp):
        """Archetype-specific card selection. Returns (card, target) or (None, None)."""
        # ─── 力量流 ───
        if arch == "力量流":
            if self.turn == 1:
                df = [c for c in playable if c.effect == "strength_per_turn"]
                if df and df[0].cost <= self.player.energy:
                    return df[0], None
            str_cards = [c for c in playable if c.effect in ("strength", "dominate_card") and c.cost <= 1]
            if str_cards and self.turn <= 3:
                return str_cards[0], None
            if self.player.buffs.strength >= 3:
                atks = sorted([c for c in playable if c.damage > 0], key=lambda c: -c.damage * c.hits)
                if atks:
                    return atks[0], target
            vuln = [c for c in playable if c.effect == "vulnerable"]
            if vuln and target and target.buffs.vulnerable == 0:
                return vuln[0], target

        # ─── 飞刀流 ───
        if arch == "飞刀流" or any(c.effect in ("blade_dance", "infinite_blades", "fan_of_knives")
                                   for c in self.player.deck + self.player.hand):
            shiv_powers = [c for c in playable if c.card_type == "能力" and
                          c.effect in ("infinite_blades", "accuracy", "phantom_blades",
                                      "fan_of_knives", "knife_trap")]
            if shiv_powers and self.turn <= 3:
                return shiv_powers[0], None
            bd = [c for c in playable if c.effect == "blade_dance"]
            if bd:
                return bd[0], None
            cad = [c for c in playable if c.effect == "cloak_dagger"]
            if cad:
                return cad[0], None
            hd = [c for c in playable if c.effect == "hidden_daggers"]
            if hd:
                return hd[0], None
            shivs = [c for c in playable if c.id == "Shiv"]
            if shivs:
                return shivs[0], target
            sos = [c for c in playable if c.effect == "storm_of_steel"]
            if sos and len(self.player.hand) >= 3:
                return sos[0], None

        # ─── 自伤流 ───
        if arch == "自伤流":
            bar = [c for c in playable if c.effect == "block_retain"]
            if bar and not self.player.buffs.block_retain and self.turn <= 2:
                return bar[0], None
            rup = [c for c in playable if c.effect == "rupture"]
            if rup and getattr(self.player.buffs, '_rupture', 0) < 2:
                return rup[0], None
            met = [c for c in playable if c.effect == "metallicize"]
            if met and self.turn <= 3:
                return met[0], None
            cm = [c for c in playable if c.effect == "crimson_mantle"]
            if cm and getattr(self.player.buffs, '_rupture', 0) > 0:
                return cm[0], None
            bl = [c for c in playable if c.effect == "bloodletting"]
            if bl and self.player.hp > 20:
                return bl[0], target
            bs = [c for c in playable if c.effect == "body_slam"]
            if bs and self.player.block >= 15:
                return bs[0], target
            bw = [c for c in playable if c.effect == "blood_wall"]
            if bw and self.player.hp > 20:
                return bw[0], target
            off = [c for c in playable if c.effect == "offering"]
            if off and self.player.hp > 25:
                return off[0], None

        # ─── 闪电流 ───
        if arch == "闪电流":
            sp = [c for c in playable if c.effect == "storm_power"]
            if sp and self.turn <= 2:
                return sp[0], None
            th = [c for c in playable if c.effect == "thunder"]
            if th and self.turn <= 3:
                return th[0], None
            tc = [c for c in playable if c.effect == "tesla_coil"]
            if tc:
                return tc[0], None
            cl = [c for c in playable if c.effect in ("channel_lightning", "ball_lightning", "voltaic")]
            if cl:
                return cl[0], None

        # ─── 消耗流 ───
        if arch == "消耗流" or any(c.effect == "corruption" for c in
                                   self.player.deck + self.player.hand + self.player.draw_pile):
            has_fnp = self.player.buffs.feel_no_pain > 0
            if not self.player.buffs.corruption:
                setup = [c for c in playable if c.effect in ("feel_no_pain", "dark_embrace")
                        and c.cost <= self.player.energy]
                if setup:
                    return setup[0], None
                corr = [c for c in playable if c.effect == "corruption"]
                if corr and corr[0].cost <= self.player.energy and has_fnp:
                    return corr[0], None

        if self.player.buffs.corruption:
            offering_safe = self.player.hp > 30
            free_skills = [c for c in self.player.hand
                           if c.card_type == "技能" and
                           (c.effect != "offering" or offering_safe)]
            fiend_cards = [c for c in playable if c.effect == "fiend_fire" and c.cost <= self.player.energy]
            skills_exhausted = getattr(self, '_corruption_skills_this_turn', 0)
            if free_skills or fiend_cards:
                has_embrace = self.player.buffs.dark_embrace > 0 or self.player.buffs.feel_no_pain > 0
                if fiend_cards and len(self.player.hand) >= 3 and has_embrace:
                    return fiend_cards[0], target
                sever = [c for c in free_skills if c.effect in ("sever_soul", "second_wind")]
                if sever and len(self.player.hand) >= 3:
                    return sever[0], None
                blk_skills = [c for c in free_skills if c.block > 0]
                if blk_skills and need_block > 5:
                    blk_skills.sort(key=lambda c: -c.block)
                    return blk_skills[0], None
                if free_skills and skills_exhausted < 4:
                    self._corruption_skills_this_turn = skills_exhausted + 1
                    return free_skills[0], None
                atks = sorted([c for c in playable if c.damage > 0 and c.card_type == "攻击"],
                             key=lambda c: -c.damage * c.hits)
                if atks:
                    return atks[0], target
                if fiend_cards:
                    return fiend_cards[0], target

        # ─── 暗球爆发流 ───
        if arch == "暗球爆发流" or dark_orbs:
            cs_cards = [c for c in playable if c.effect == "consuming_shadow"]
            if cs_cards and dark_orbs:
                return cs_cards[0], None
            if dark_orbs and total_dark_dmg >= min_enemy_hp * 0.6:
                evoke_cards = [c for c in playable if c.effect in ("evoke", "multicast")
                              and (c.effect != "multicast" or self.player.orbs)]
                if evoke_cards:
                    return evoke_cards[0], None
            if self.turn <= 6:
                bc = [c for c in playable if c.effect == "biased_cog"]
                if bc:
                    return bc[0], None
                foc = [c for c in playable if c.effect in ("focus", "synchronize")]
                if foc:
                    return foc[0], None
                cap = [c for c in playable if c.effect == "orb_slot"]
                if cap:
                    return cap[0], None
                lp = [c for c in playable if c.effect == "loop"]
                if lp:
                    return lp[0], None
            dc = [c for c in playable if c.effect == "channel_dark"]
            if dc:
                return dc[0], None
            rb = [c for c in playable if c.effect == "rainbow"]
            if rb:
                return rb[0], None

        # ─── 灾厄流 ───
        if doom_cards and self.turn <= 3:
            for dc in doom_cards:
                if dc.cost <= self.player.energy:
                    return dc, target

        times_up = [c for c in playable if c.effect == "times_up"]
        if times_up and target and target.buffs.doom >= target.hp:
            return times_up[0], target

        # ─── Osty流 ───
        if arch in ("Osty召唤流", "Osty+灾厄混合流"):
            if self.player.osty_hp <= 0:
                summon = [c for c in playable if c.effect == "summon_osty"]
                if summon:
                    return summon[0], None
            if self.player.osty_hp > 0:
                osty_attacks = [c for c in playable if c.effect in (
                    "osty_attack", "osty_fetch", "osty_flatten", "osty_squeeze",
                    "unleash", "right_hand_hand", "high_five", "sic_em", "snap")]
                if osty_attacks:
                    osty_attacks.sort(key=lambda c: -c.effect_value)
                    return osty_attacks[0], target
        elif self.player.osty_hp > 0:
            osty_attacks = [c for c in playable if c.effect in (
                "osty_attack", "osty_fetch", "osty_flatten", "osty_squeeze")]
            if osty_attacks:
                osty_attacks.sort(key=lambda c: -c.effect_value)
                return osty_attacks[0], target

        # ─── 弃牌流 ───
        if arch == "弃牌流":
            kp = [c for c in playable if c.effect in ("dexterity", "after_image", "accuracy")
                 and c.card_type == "能力"]
            if kp and self.turn <= 3:
                return kp[0], None
            tot = [c for c in playable if c.effect == "tools_of_trade"]
            if tot:
                return tot[0], None
            bd = [c for c in playable if c.effect == "blade_dance"]
            if bd:
                return bd[0], None
            acr = [c for c in playable if c.effect == "acrobatics"]
            if acr:
                return acr[0], None
            shivs = [c for c in playable if c.id == "Shiv"]
            if shivs:
                return shivs[0], target
            evis = [c for c in playable if c.effect == "eviscerate"]
            if evis:
                evis_cost = max(0, evis[0].cost - self.player.turn_discards)
                if evis_cost <= self.player.energy:
                    return evis[0], target

        # ─── Eviscerate globally ───
        evis = [c for c in self.player.hand if c.effect == "eviscerate"]
        if evis:
            evis_cost = max(0, evis[0].cost - self.player.turn_discards)
            if evis_cost > 1 and discard_cards:
                return discard_cards[0], None
            if evis_cost <= self.player.energy:
                return evis[0], target
        storm = [c for c in playable if c.effect == "storm_of_steel"]
        if storm and len(self.player.hand) >= 4:
            return storm[0], None
        if discard_cards and self.player.energy >= 1:
            return discard_cards[0], None

        # ─── More archetype-specific patterns ───
        # (Simplified: for remaining archetypes, use generic strategy)
        # The arch-specific strategies for 连击流/喂食回血流/打击流/暗杀流/etc.
        # are handled by the generic fallback below when arch doesn't match above.
        if arch in ("重击流", "铸造战士流", "星辰控制流", "无色生成流"):
            str_powers = [c for c in playable if c.card_type == "能力" and
                         c.effect in ("monarchs_gaze", "monologue", "furnace", "the_smith",
                                     "child_of_stars", "sealed_throne", "sword_sage",
                                     "hegemony", "celestial_might")]
            if str_powers and self.turn <= 3:
                return str_powers[0], None
            energy_cards = [c for c in playable if c.effect in ("glow", "spoils_of_battle", "gather_light")]
            if energy_cards and self.player.energy <= 1:
                return energy_cards[0], None
            stoke = [c for c in playable if c.effect == "stoke"]
            if stoke:
                return stoke[0], None
            bb = [c for c in playable if c.effect == "big_bang"]
            if bb and len(alive_enemies) >= 2:
                return bb[0], None

        if arch == "连击流":
            sp = [c for c in playable if c.card_type == "能力" and c.effect in ("strength", "aggression")]
            if sp and self.turn <= 3:
                return sp[0], None
            mh = [c for c in playable if c.effect in ("twin_strike", "sword_boomerang", "rampage")]
            if mh:
                mh.sort(key=lambda c: -c.effect_value)
                return mh[0], target
            ps = [c for c in playable if c.effect == "pommel_strike"]
            if ps:
                return ps[0], target
            ang = [c for c in playable if c.effect == "anger"]
            if ang:
                return ang[0], target

        if arch == "喂食回血流":
            off = [c for c in playable if c.effect == "offering"]
            if off and self.player.hp > 20:
                return off[0], None
            inf = [c for c in playable if c.effect == "strength"]
            if inf and self.turn <= 3:
                return inf[0], None
            bld = [c for c in playable if c.effect == "bludgeon"]
            if bld and bld[0].cost <= self.player.energy:
                return bld[0], target
            feed = [c for c in playable if c.effect == "feed"]
            weak_e = min(alive_enemies, key=lambda e: e.hp)
            if feed and weak_e.hp <= 20:
                return feed[0], weak_e

        if arch == "打击流":
            inf = [c for c in playable if c.effect == "strength"]
            if inf and self.turn <= 3:
                return inf[0], None
            ps = [c for c in playable if c.effect == "perfected_strike"]
            if ps:
                return ps[0], target

        if arch == "暗杀流":
            kp = [c for c in playable if c.card_type == "能力"]
            if kp and self.turn <= 2:
                return kp[0], None
            assa = [c for c in playable if c.effect == "assassinate"]
            if assa:
                return assa[0], target
            bs = [c for c in playable if c.effect == "backstab"]
            if bs:
                return bs[0], target
            sl = [c for c in playable if c.effect in ("slice", "neutralize")]
            if sl:
                return sl[0], target
            bd = [c for c in playable if c.effect == "blade_dance"]
            if bd:
                return bd[0], None
            shivs = [c for c in playable if c.id == "Shiv"]
            if shivs:
                return shivs[0], target

        if arch == "幽灵防御流":
            wf = [c for c in playable if c.effect == "wraith_form"]
            if wf and wf[0].cost <= self.player.energy:
                return wf[0], None
            nf = [c for c in playable if c.effect == "noxious_fume"]
            if nf:
                return nf[0], None
            ai_c = [c for c in playable if c.effect == "after_image"]
            if ai_c:
                return ai_c[0], None
            fw = [c for c in playable if c.effect == "dexterity"]
            if fw:
                return fw[0], None

        if arch in ("0费速攻流",):
            kp = [c for c in playable if c.card_type == "能力"]
            if kp and self.turn <= 2:
                return kp[0], None
            zero_atk = sorted([c for c in playable if c.cost == 0 and c.damage > 0],
                             key=lambda c: -c.damage)
            if zero_atk:
                return zero_atk[0], target
            bd = [c for c in playable if c.effect == "blade_dance"]
            if bd:
                return bd[0], None
            shivs = [c for c in playable if c.id == "Shiv"]
            if shivs:
                return shivs[0], target

        if arch in ("超载爆发流", "能量循环流"):
            foc = [c for c in playable if c.effect in ("focus", "biased_cog")]
            if foc and self.turn <= 2:
                return foc[0], None
            de = [c for c in playable if c.effect == "double_energy"]
            if de and self.player.energy >= 2:
                return de[0], None

        if arch == "冰霜护盾流":
            bc = [c for c in playable if c.effect == "biased_cog"]
            if bc and self.turn == 1:
                return bc[0], None
            df = [c for c in playable if c.effect == "focus"]
            if df and self.turn <= 2:
                return df[0], None
            co = [c for c in playable if c.effect == "coolant"]
            if co:
                return co[0], None
            cap = [c for c in playable if c.effect == "orb_slot"]
            if cap:
                return cap[0], None
            ch = [c for c in playable if c.effect == "chill"]
            if ch:
                return ch[0], None
            gl = [c for c in playable if c.effect == "channel_frost"]
            if gl:
                return gl[0], None

        if arch == "粒子防御流":
            na = [c for c in playable if c.effect == "neutron_aegis"]
            if na:
                return na[0], None
            par = [c for c in playable if c.effect == "parry"]
            if par:
                return par[0], None
            ref = [c for c in playable if c.effect == "reflect"]
            if ref:
                return ref[0], None
            pw = [c for c in playable if c.effect == "particle_wall"]
            if pw:
                return pw[0], None

        if arch == "虚空形态流":
            vf = [c for c in playable if c.effect == "void_form"]
            if vf and vf[0].cost <= self.player.energy:
                return vf[0], None
            bh = [c for c in playable if c.effect == "black_hole"]
            if bh:
                return bh[0], None
            ty = [c for c in playable if c.effect == "tyranny"]
            if ty:
                return ty[0], None

        if arch == "高费斩杀流":
            dp = [c for c in playable if c.effect in ("countdown_doom", "reaper_form")]
            if dp and self.turn <= 2:
                return dp[0], None
            bu = [c for c in playable if c.effect == "bury"]
            if bu and bu[0].cost <= self.player.energy:
                return bu[0], target
            bc = [c for c in playable if c.effect == "banshees_cry"]
            if bc and bc[0].cost <= self.player.energy:
                return bc[0], None
            rp = [c for c in playable if c.effect == "reap"]
            if rp and rp[0].cost <= self.player.energy:
                return rp[0], target

        if arch == "恐惧削弱流":
            dp = [c for c in playable if c.effect == "countdown_doom"]
            if dp and self.turn <= 2:
                return dp[0], None
            et = [c for c in playable if c.effect == "enfeebling_touch"]
            if et and target.buffs.strength > 0:
                return et[0], target
            deb = [c for c in playable if c.effect == "debilitate"]
            if deb:
                return deb[0], target

        if arch in ("墓地回收流", "灵魂虚无流"):
            if self.player.osty_hp <= 0:
                summ = [c for c in playable if c.effect in ("afterlife", "summon_osty", "legion_of_bone")]
                if summ:
                    return summ[0], None
            doom_c = [c for c in playable if c.effect in ("bone_spear", "scourge_doom")]
            if doom_c:
                return doom_c[0], target

        return None, None

    def run(self, max_turns=50, arch_name: str = "") -> dict:
        self.player.draw_pile = self.player.deck[:]
        random.shuffle(self.player.draw_pile)
        self.player.hand = []
        self.player.discard = []
        self._arch_name = arch_name

        apply_relics_start(self.player, arch_name)

        # 起始遗物效果（源码精确）
        if "CrackedCore" in self.player.relics:
            self._channel_orb("lightning")
        if "CrackedOrb" in self.player.relics:
            self._channel_orb("lightning")
        # RingOfTheSnake: 第1回合多抽2张 (在_start_turn中处理)
        # DivineDestiny: 第1回合+6格挡 (在_start_turn中处理)
        # BoundPhylactery: 召唤Osty (已在summon_osty中处理)

        potions = ARCHETYPE_POTIONS.get(arch_name, [])
        for pot in potions:
            use_potion(self.player, pot, self.enemies)

        self._log(f"战斗开始: {self.player.name} HP:{self.player.hp}/{self.player.max_hp}")
        self._log(f"  vs {', '.join(f'{e.name}({e.hp}HP)' for e in self.enemies)}")
        self._log(f"  牌组: {len(self.player.deck)}张 遗物: {self.player.relics}")

        while self.turn < max_turns:
            self._start_turn()
            self._log(f"\n=== 回合 {self.turn} ===")
            self._log(f"  HP:{self.player.hp} 格挡:{self.player.block} "
                      f"力量:{self.player.buffs.strength} 手牌:{len(self.player.hand)}")

            plays = 0
            while plays < 30:
                card, target = self._pick_play()
                if not card:
                    break
                if card not in self.player.hand:
                    break
                self.player.hand.remove(card)
                success = self._play_card(card, target)
                if not success:
                    self.player.hand.append(card)
                    break
                plays += 1
                if all(e.hp <= 0 for e in self.enemies):
                    break

            if all(e.hp <= 0 for e in self.enemies):
                self._log(f"\n✅ 胜利! 回合{self.turn} 剩余HP:{self.player.hp}")
                return {"won": True, "turns": self.turn, "hp_left": self.player.hp,
                        "log": self.log}

            self._end_player_turn()
            self._enemy_turn()

            if self.player.hp <= 0:
                self._log(f"\n❌ 败北! 回合{self.turn}")
                return {"won": False, "turns": self.turn, "hp_left": 0,
                        "log": self.log}

        self._log(f"\n⏰ 超时! {max_turns}回合")
        return {"won": False, "turns": max_turns, "hp_left": self.player.hp,
                "log": self.log}