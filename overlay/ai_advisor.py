"""AIAdvisorMixin — 所有LLM调用和策略分析。

修改AI prompt和策略逻辑只需编辑此文件。
"""
import threading
import time
import subprocess
import os
import shutil
import json
import re
from collections import Counter

import requests

import html as _html

from overlay.constants import (
    API_URL, LLM_CLI, CARD_DICT, STRATEGY_DB, COMBAT_BASICS,
    SYSTEM_PROMPT_FILE, INTENT_CN,
    _cn_power, _cn_relic, _cn_potion,
    PARCH, GOLD, GREEN,
)


class AIAdvisorMixin:
    _system_prompt_cache = None

    # ───── 智能上下文构建器（0 token 查表）─────

    def _build_context(self, context_type="combat"):
        """根据当前状态查本地数据库，返回精准上下文字符串（0 token开销）。

        context_type: combat / deck / card_reward / map / event / shop / boss
        返回: 字符串，直接注入prompt
        """
        state = self.last_state or {}
        player = self._get_player(state) or self.last_player or {}
        run = state.get("run") or self.last_run or {}
        char = player.get("character", "?")
        ascension = run.get("ascension", 0)
        relics = [r.get("name", "") for r in player.get("relics", [])]
        relic_ids = [r.get("id", r.get("name", "")) for r in player.get("relics", [])]

        parts = []

        # 1. 从 archetype_matrix 查当前角色的流派推荐
        if hasattr(self, '_matrix') and self._matrix and char in self._matrix.get("characters", {}):
            char_data = self._matrix["characters"][char]
            archetypes = char_data.get("archetypes", {})

            # 进阶区间
            if ascension <= 2: asc_key = "0-2"
            elif ascension <= 5: asc_key = "3-5"
            elif ascension <= 7: asc_key = "6-7"
            else: asc_key = "8-10"

            # 筛选：只输出当前进阶下A级以上的流派 + 有匹配遗物的流派
            relevant = []
            for aname, adata in archetypes.items():
                asc_info = adata.get("ascension_impact", {}).get(asc_key, {})
                tier = asc_info.get("tier", "B")
                # 检查遗物匹配
                relic_match = []
                for t in ["S_tier", "A_tier"]:
                    for r in adata.get("relic_synergies", {}).get(t, []):
                        rname = r.get("name", "")
                        if any(rname in pr for pr in relics):
                            relic_match.append(f"{rname}({r.get('reason', '')[:20]})")

                # 检查遗物触发转向
                pivots = []
                for p in adata.get("relic_synergies", {}).get("pivot_relics", []):
                    pname = p.get("name", "")
                    if any(pname in pr for pr in relics):
                        pivots.append(f"🔥{pname}→{p.get('pivot_to','')}: {p.get('reason','')[:30]}")

                score = 0
                if "S" in tier: score = 3
                elif "A" in tier: score = 2
                elif "B" in tier: score = 1
                if relic_match: score += 2
                if pivots: score += 3

                if score >= 2:  # 只保留有意义的
                    relevant.append({
                        "name": aname,
                        "tier": tier,
                        "note": asc_info.get("note", ""),
                        "relic_match": relic_match,
                        "pivots": pivots,
                        "win": adata.get("win_condition", "")[:50],
                        "weakness": adata.get("weakness", "")[:50],
                        "combos": adata.get("key_combos", [])[:2],
                        "score": score
                    })

            relevant.sort(key=lambda x: -x["score"])

            if relevant:
                lines = [f"[{char} A{ascension} 流派参考]"]
                for r in relevant[:3]:  # 最多3个
                    line = f"  {r['name']}({r['tier']}): {r['win']}"
                    if r['relic_match']:
                        line += f" | 遗物协同: {', '.join(r['relic_match'][:2])}"
                    if r['pivots']:
                        line += f" | {'  '.join(r['pivots'])}"
                    lines.append(line)
                    if r.get('combos') and context_type in ("combat", "deck"):
                        for combo in r['combos'][:1]:
                            if isinstance(combo, dict):
                                cmech = combo.get('mechanic', '') or combo.get('cards', '')
                                lines.append(f"    combo: {str(cmech)[:60]}")
                            else:
                                lines.append(f"    combo: {str(combo)[:60]}")
                parts.append("\n".join(lines))

        # 2. 战斗时：查Boss/精英应对
        if context_type == "combat" and hasattr(self, '_boss_guide') and self._boss_guide:
            enemies = []
            battle = state.get("battle", {})
            for e in battle.get("enemies", []):
                ename = e.get("name", "")
                # 查Boss指南
                for bid, bdata in self._boss_guide.get("bosses", {}).items():
                    if bdata.get("name_cn") == ename:
                        tips = bdata.get("general_tips", [])[:2]
                        danger = [d.get("name", "") + ": " + d.get("counter", "") for d in bdata.get("danger_moves", [])[:2]]
                        # 查当前流派 matchup
                        arch_match = ""
                        if self._deck_archetype:
                            mu = bdata.get("archetype_matchups", {}).get(self._deck_archetype, {})
                            if mu:
                                arch_match = f"{self._deck_archetype} vs {ename}: {mu.get('rating','')} — {mu.get('counter','')[:30]}"

                        info = f"[Boss指南: {ename}]"
                        if arch_match: info += f"\n  {arch_match}"
                        if tips: info += f"\n  要点: {'; '.join(tips)}"
                        if danger: info += f"\n  危险招: {'; '.join(danger)}"
                        enemies.append(info)
                        break
                # 也查精英
                for eid_key, edata in self._boss_guide.get("elites", {}).items():
                    if edata.get("name_cn") == ename:
                        tips = edata.get("general_tips", [])[:2]
                        info = f"[精英指南: {ename}]"
                        if tips: info += f"\n  要点: {'; '.join(tips)}"
                        enemies.append(info)
                        break
            if enemies:
                parts.append("\n".join(enemies))

        # 3. 选牌/卡组分析时：查卡牌协同
        if context_type in ("card_reward", "deck") and hasattr(self, '_synergy_index') and self._synergy_index:
            deck_cards = [c.get("id", c.get("name", "")) for c in player.get("deck", [])]
            # 如果是选牌，查每个选项与当前牌组的协同
            if context_type == "card_reward":
                options = state.get("card_reward", {}).get("cards", [])
                synergy_hints = []
                for opt in options:
                    oid = opt.get("id", opt.get("name", ""))
                    oname = opt.get("name", oid)
                    card_syn = self._synergy_index.get(oid, {})
                    if card_syn:
                        fits = card_syn.get("archetype_fit", [])
                        tags = card_syn.get("tags", [])
                        # 检查与牌组中牌的协同
                        synergies_found = []
                        for s in card_syn.get("synergies", [])[:5]:
                            if s.get("card") in deck_cards:
                                synergies_found.append(f"{s['name']}: {s['reason'][:25]}")
                        if synergies_found or fits:
                            hint = f"  {oname}: "
                            if fits: hint += f"流派[{','.join(fits[:2])}] "
                            if synergies_found: hint += f"与牌组协同[{'; '.join(synergies_found[:2])}]"
                            synergy_hints.append(hint)
                if synergy_hints:
                    parts.append("[选牌协同分析]\n" + "\n".join(synergy_hints))

        # 4. 遗物转向规则（单遗物）
        if hasattr(self, '_pivot_rules') and self._pivot_rules:
            for rule in self._pivot_rules.get("rules", []):
                cond = rule.get("condition", {})
                req_relic = cond.get("has_relic", "")
                req_char = cond.get("character", "")
                if req_char and req_char != char:
                    continue
                if req_relic and any(req_relic in r for r in relics):
                    req_cards = cond.get("has_card_any", [])
                    if req_cards:
                        deck_ids = set(c.get("id", "") for c in player.get("deck", []))
                        if not any(c in deck_ids for c in req_cards):
                            continue
                    parts.append(f"[遗物转向] {rule['action']}: {rule['reason'][:50]}")
                    break

            # 5. 多遗物联合效应
            combo_hits = []
            for rule in self._pivot_rules.get("combo_rules", []):
                cond = rule.get("condition", {})
                req_cns = cond.get("has_relics_cn", [])
                req_char = cond.get("character", "")
                req_chars = cond.get("character_any", [])
                if req_char and req_char != char:
                    continue
                if req_chars and char not in req_chars:
                    continue
                # 用中文名匹配
                if req_cns and all(any(rcn == r for r in relics) for rcn in req_cns):
                    combo_hits.append(f"🔥 {rule['action']}: {rule['reason'][:60]}")
            if combo_hits:
                parts.append("[遗物联合效应]\n" + "\n".join(combo_hits[:3]))

        # 6. 事件时：查事件指南
        if context_type == "event" and self._event_guide:
            event_data = state.get("event", {})
            event_id = event_data.get("event_id") or event_data.get("id") or event_data.get("name", "")
            guide = self._event_guide.get(event_id, {})
            if guide:
                lines = [f"[事件指南: {guide.get('name_cn', event_id)}]"]
                for opt in guide.get("options", []):
                    rating = opt.get("rating", "")
                    lines.append(f"  {rating} {opt.get('name','?')}: {opt.get('effect','?')[:60]}")
                strat = guide.get("strategy", "")
                if strat:
                    lines.append(f"  策略: {strat[:80]}")
                parts.append("\n".join(lines))

        # 7. 选牌时：查Tier评级
        if context_type == "card_reward" and self._card_tiers:
            char_tiers = self._card_tiers.get(char, {})
            if char_tiers:
                options = state.get("card_reward", {}).get("cards", [])
                tier_hints = []
                # 判断阶段
                floor = run.get("floor", 0)
                if floor <= 8: phase = "early"
                elif floor <= 20: phase = "mid"
                else: phase = "late"
                for opt in options:
                    oid = opt.get("id", opt.get("name", ""))
                    ct = char_tiers.get(oid, {})
                    if ct:
                        tier = ct.get("tier", {}).get(phase, "?")
                        note = ct.get("note", "")[:40]
                        tier_hints.append(f"  {ct.get('name_cn', oid)}[{phase}:{tier}] {note}")
                if tier_hints:
                    parts.append("[牌评级]\n" + "\n".join(tier_hints))

        # 8. 战斗中：查怪物AI行为模式
        if context_type == "combat" and self._monster_ai:
            battle = state.get("battle", state.get("monster", {}))
            for e in battle.get("enemies", []):
                eid = e.get("id", e.get("name", ""))
                # 尝试多种key匹配
                ai = self._monster_ai.get(eid, {})
                if not ai:
                    # 尝试用中文名匹配
                    ename = e.get("name", "")
                    for mk, mv in self._monster_ai.items():
                        if isinstance(mv, dict) and mv.get("name_cn") == ename:
                            ai = mv
                            break
                if ai and isinstance(ai, dict):
                    pattern = ai.get("ai_pattern", "")
                    if pattern:
                        parts.append(f"[{ai.get('name_cn', eid)}行为] {pattern[:80]}")

        return "\n\n".join(parts) if parts else ""

    def _ask_llm(self, prompt):
        # 检查 LLM 是否可用
        if not os.path.exists(LLM_CLI) and not shutil.which(LLM_CLI):
            raise RuntimeError(f"LLM 未找到：{LLM_CLI}\n请检查 config.json 中的 llm_cli 路径")
        cmd = [LLM_CLI, "--print", "--permission-mode", "bypassPermissions"]
        # 加载 system prompt（缓存读一次）
        if self._system_prompt_cache is None:
            try:
                if os.path.exists(SYSTEM_PROMPT_FILE):
                    with open(SYSTEM_PROMPT_FILE) as f:
                        self.__class__._system_prompt_cache = f.read().strip()
                else:
                    self.__class__._system_prompt_cache = ""
            except Exception:
                self.__class__._system_prompt_cache = ""
        if self._system_prompt_cache:
            cmd += ["--system-prompt", self._system_prompt_cache]
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=45)
        except FileNotFoundError:
            raise RuntimeError(f"LLM 无法执行：{LLM_CLI}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("分析超时（45秒），请重试")
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "调用失败")
        return r.stdout.strip()

    @staticmethod
    def _parse_intent_damage(intent):
        """从intent提取(damage, hits)。优先用数值字段，fallback到label解析。"""
        import re as _re
        damage = intent.get("damage") or intent.get("base_damage")
        hits = intent.get("hits") or intent.get("times") or intent.get("count")
        if damage:
            return int(damage), int(hits or 1)
        label = (intent.get("label") or "").strip()
        if not label:
            return 0, 0
        m = _re.match(r"(\d+)\s*[×xX]\s*(\d+)", label)
        if m:
            return int(m.group(1)), int(m.group(2))
        m2 = _re.match(r"(\d+)", label)
        if m2:
            return int(m2.group(1)), 1
        return 0, 0

    @staticmethod
    def _clean_desc(text):
        """清理描述文本中的图片标记等。"""
        import re as _re
        return _re.sub(r"\[[\w.]+\.png\]", "⚡", text)

    @staticmethod
    def _parse_card_values(card):
        """从卡牌description解析伤害和格挡数值。
        返回 (damage, block)。"""
        import re as _re
        desc = card.get("description", "")
        # 已有数值字段则直接用
        dmg = card.get("damage") or card.get("base_damage") or 0
        blk = card.get("block") or card.get("base_block") or 0
        if dmg or blk:
            return int(dmg), int(blk)
        # 从描述解析: "造成X点伤害" / "获得X点格挡"
        m_dmg = _re.search(r"造成(\d+)点伤害", desc)
        m_blk = _re.search(r"获得(\d+)点格挡", desc)
        return int(m_dmg.group(1)) if m_dmg else 0, int(m_blk.group(1)) if m_blk else 0

    def _fmt_intent(self, intents):
        """格式化敌人意图，精确展示攻击数值。"""
        parts = []
        for i in intents:
            label = (i.get("label") or "").strip()
            itype = i.get("type", "")
            damage, hits = self._parse_intent_damage(i)

            # 优先用数值构建精确描述
            if damage and hits > 1:
                parts.append(f"攻击 {damage}×{hits} = {damage*hits}总伤")
            elif damage:
                parts.append(f"攻击 {damage}伤")
            elif label:
                # label格式: "12" (单次) / "1×3" (多次) / "7，7" (逗号)
                import re as _re
                m_multi = _re.match(r"(\d+)\s*[×xX]\s*(\d+)", label)
                if m_multi:
                    dmg, hits = int(m_multi.group(1)), int(m_multi.group(2))
                    parts.append(f"攻击 {dmg}×{hits} = {dmg*hits}总伤")
                elif any(c.isdigit() for c in label):
                    nums = [s.strip() for s in label.replace("，", ",").split(",") if s.strip().isdigit()]
                    if len(nums) > 1:
                        total = sum(int(n) for n in nums)
                        parts.append(f"攻击 {'×'.join(nums)} = {total}总伤")
                    elif len(nums) == 1:
                        parts.append(f"攻击 {nums[0]}伤")
                    else:
                        parts.append(label)
                else:
                    parts.append(label)
            elif itype:
                cn = INTENT_CN.get(itype, itype)
                parts.append(cn)
        return "  ".join(parts) or "—"

    def _ai_combat(self, state):
        self._busy_combat = True
        self._js('app.setButtonState("btn-situation", "⏳ 分析中…", true)')
        self._js(f'app.updateAdvice({json.dumps("◌  正在分析战斗…")})')
        try:
            time.sleep(1.5)
            try:
                fresh = requests.get(API_URL, timeout=5).json()
                if fresh.get("state_type") in ("monster", "elite", "boss"):
                    state = fresh
            except Exception:
                pass

            battle = state.get("battle", {})
            player = battle.get("player", {})
            run    = state.get("run", {})
            enemies= battle.get("enemies", [])
            hand   = player.get("hand", [])
            rnd    = battle.get("round", "?")

            hand_lines = []
            for c in hand:
                name = c["name"]
                upg  = "+" if c.get("is_upgraded") else ""
                ok   = "✓" if c.get("can_play") else "✗"
                hint = CARD_DICT.get(name, c.get("description", "")[:28])
                hand_lines.append(f"  [{c['index']}]{ok} {name}{upg}  费:{c.get('cost','?')}  {hint}")
            hand_str = "\n".join(hand_lines) or "  （手牌为空）"

            # 敌人区分：同名敌人加编号
            self._number_enemies(enemies)
            enemy_lines = []
            for e in enemies:
                display_name = e.get("_display_name", e.get("name", "?"))

                hp  = e.get("hp", 0); mhp = e.get("max_hp", 1)
                pct = int(hp/mhp*100)
                intent = self._fmt_intent(e.get("intents", []))
                powers = "  ".join(f"{_cn_power(p)}×{p['amount']}" for p in e.get("powers", []))
                blk = e.get("block", 0)
                line = f"  {display_name}  HP:{hp}/{mhp}({pct}%)" + (f"  格挡:{blk}" if blk else "")
                line += f"\n  意图：{intent}"
                if powers:
                    line += f"\n  状态：{powers}"
                enemy_lines.append(line)
            enemy_str = "\n".join(enemy_lines)

            # 友方召唤物（如Osty）
            allies = [a for a in battle.get("allies", []) if a.get("name")]
            ally_lines = []
            for a in allies:
                ahp = a.get("hp", 0); amhp = a.get("max_hp", 1)
                aname = a.get("name", "?")
                apowers = "  ".join(f"{_cn_power(p)}×{p['amount']}" for p in a.get("powers", []))
                ablk = a.get("block", 0)
                aline = f"  {aname}  HP:{ahp}/{amhp}" + (f"  格挡:{ablk}" if ablk else "")
                if apowers:
                    aline += f"  [{apowers}]"
                ally_lines.append(aline)
            ally_str = "\n".join(ally_lines) if ally_lines else ""

            # buff/debuff效果计算
            p_str = player.get("powers", [])
            p_strength = sum(p["amount"] for p in p_str if p.get("id") == "Strength" or p.get("name") in ("力量", "Strength"))
            p_dexterity = sum(p["amount"] for p in p_str if p.get("id") == "Dexterity" or p.get("name") in ("敏捷", "Dexterity"))
            p_weak = any(p.get("id") == "Weak" or p.get("name") in ("虚弱", "Weak") for p in p_str)
            p_vulnerable = any(p.get("id") == "Vulnerable" or p.get("name") in ("易伤", "Vulnerable") for p in p_str)

            # 检查敌人是否有易伤/虚弱
            for e in enemies:
                e_powers = e.get("powers", [])
                e["_vulnerable"] = any(p.get("id") == "Vulnerable" or p.get("name") in ("易伤", "Vulnerable") for p in e_powers)
                e["_weak"] = any(p.get("id") == "Weak" or p.get("name") in ("虚弱", "Weak") for p in e_powers)

            # 构建伤害计算提示
            dmg_notes = []
            if p_strength: dmg_notes.append(f"力量{p_strength:+d}(每张攻击牌{p_strength:+d}伤害)")
            if p_dexterity: dmg_notes.append(f"敏捷{p_dexterity:+d}(每张技能牌{p_dexterity:+d}格挡)")
            if p_weak: dmg_notes.append("我方虚弱(攻击-25%)")
            if p_vulnerable: dmg_notes.append("我方易伤(受伤+50%)")
            vuln_enemies = [e["_display_name"] for e in enemies if e.get("_vulnerable")]
            weak_enemies = [e["_display_name"] for e in enemies if e.get("_weak")]
            if vuln_enemies: dmg_notes.append(f"{','.join(vuln_enemies)}易伤(受伤+50%)")
            if weak_enemies: dmg_notes.append(f"{','.join(weak_enemies)}虚弱(攻击-25%)")
            dmg_hint = "  ".join(dmg_notes) if dmg_notes else ""

            p_powers = "  ".join(f"{_cn_power(p)}×{p['amount']}" for p in player.get("powers", []))
            relic_list = player.get("relics", [])
            relics = ", ".join(_cn_relic(r["name"]) for r in relic_list) or "无"
            potions = ", ".join(_cn_potion(p["name"]) for p in player.get("potions", [])) or "无"

            # ── 遗物战斗效果分析（查数值表） ──
            relic_ids = {r.get("id", r.get("name", "")) for r in relic_list}
            relic_names_set = {r.get("name", "") for r in relic_list}
            relic_effects = []
            atk_playable = len([c for c in hand if c.get("can_play") and c.get("type") in ("Attack","attack","攻击")])
            skill_playable = len([c for c in hand if c.get("can_play") and c.get("type") in ("Skill","skill","技能")])
            power_playable = len([c for c in hand if c.get("can_play") and c.get("type") in ("Power","power","能力")])
            playable_count = len([c for c in hand if c.get("can_play")])
            has_potion = any(p.get("name") for p in player.get("potions", []))
            current_round = int(rnd) if str(rnd).isdigit() else 1

            for rid, rdata in self._relic_combat.items():
                if rid.startswith("_"): continue
                cn = rdata.get("name_cn", rid)
                if rid not in relic_ids and cn not in relic_names_set:
                    continue
                trigger = rdata.get("trigger", "")
                eff = rdata.get("effect", "")
                val = rdata.get("value", 0)
                thresh = rdata.get("threshold", 0)
                note = rdata.get("note", "")
                hint = None

                # ── 战斗开始触发 ──
                if trigger == "battle_start" and current_round == 1:
                    if eff == "vigor":
                        hint = f"{cn}：首回合+{val}活力，首张攻击+{val}伤害"
                    elif eff == "block":
                        hint = f"{cn}：首回合+{val}格挡"
                    elif eff == "vuln_all":
                        hint = f"{cn}：首回合敌人{val}层易伤，攻击+50%"
                    elif eff == "weak_all":
                        hint = f"{cn}：首回合敌人{val}层虚弱，攻击-25%"
                    elif eff == "draw":
                        hint = f"{cn}：首回合多抽{val}张"
                    elif eff == "strength":
                        hint = f"{cn}：+{val}力量，所有攻击+{val}伤害"
                    elif eff == "dexterity":
                        hint = f"{cn}：+{val}敏捷，所有格挡+{val}"
                    elif eff == "plating":
                        hint = f"{cn}：+{val}覆甲，每回合+{val}格挡"
                    elif eff == "thorns":
                        hint = f"{cn}：+{val}荆棘，被攻击反弹{val}伤"
                    elif eff == "aoe_dmg":
                        hint = f"{cn}：全体敌人受{val}伤害"
                    elif eff == "draw_confusion":
                        hint = f"{cn}：多抽{val}张但费用随机"
                elif trigger == "elite_start" and is_elite:
                    if eff == "draw":
                        hint = f"{cn}：精英战多抽{val}张"
                    elif eff == "strength":
                        hint = f"{cn}：精英战+{val}力量"
                elif trigger == "turn2_start" and current_round == 2:
                    hint = f"{cn}：第2回合+{val}{'格挡' if eff == 'block' else '能量'}"
                elif trigger == "turn3_start" and current_round == 3:
                    if isinstance(val, list):
                        hint = f"{cn}：第3回合+{val[0]}力量+{val[1]}敏捷"
                    else:
                        hint = f"{cn}：第3回合+{val}格挡"

                # ── 每回合触发 ──
                elif trigger == "turn_start":
                    if eff == "block":
                        hint = f"{cn}：每回合+{val}格挡"
                    elif eff == "aoe_dmg":
                        hint = f"{cn}：每回合全体{val}伤害"
                    elif eff == "str_both" and isinstance(val, list):
                        hint = f"{cn}：你+{val[0]}力量，敌人+{val[1]}力量→速战速决"
                    elif eff == "energy_enemy_str" and isinstance(val, list):
                        hint = f"{cn}：+{val[0]}能量但敌人+{val[1]}力量"
                    elif eff == "draw":
                        hint = f"{cn}：每回合多抽{val}张"
                    elif eff == "draw_no_mid":
                        hint = f"{cn}：多抽{val}张但回合中不能抽"
                    elif eff == "energy_no_pot":
                        hint = f"{cn}：+{val}能量（无法获得药水）"

                # ── 打牌触发 ──
                elif trigger == "play_3atk" and atk_playable >= thresh:
                    if eff == "strength":
                        hint = f"{cn}：打{thresh}攻击+{val}力量（手里{atk_playable}张攻击）"
                    elif eff == "dexterity":
                        hint = f"{cn}：打{thresh}攻击+{val}敏捷（手里{atk_playable}张攻击）"
                    elif eff == "block":
                        hint = f"{cn}：打{thresh}攻击+{val}格挡（手里{atk_playable}张攻击）"
                    elif eff == "random_dmg":
                        hint = f"{cn}：打{thresh}攻击→随机敌人{val}伤害"
                elif trigger == "play_3skill" and skill_playable >= thresh:
                    if eff == "aoe_dmg":
                        hint = f"{cn}：打{thresh}技能→全体{val}伤害（手里{skill_playable}张技能）"
                    elif eff == "block":
                        hint = f"{cn}：打{thresh}技能+{val}格挡"
                elif trigger == "play_power" and power_playable > 0:
                    hint = f"{cn}：打能力牌→{'抽'+str(val)+'张' if eff == 'draw' else '全体'+str(val)+'伤害'}"
                elif trigger == "play_atk" and atk_playable > 0:
                    if eff == "block":
                        hint = f"{cn}：每打攻击+{val}格挡（{atk_playable}张=+{val*atk_playable}格挡）"
                elif trigger == "play_cost2+":
                    cost2 = [c for c in hand if c.get("can_play") and (c.get("cost",0) or 0) >= 2]
                    if cost2:
                        hint = f"{cn}：打费≥2牌+{val}格挡（{len(cost2)}张可触发）"
                elif trigger == "play_5card" and playable_count >= thresh:
                    hint = f"{cn}：第{thresh}张牌免费（可出{playable_count}张）"
                elif trigger == "play_4card" and playable_count >= thresh:
                    hint = f"{cn}：每{thresh}张牌抽{val}张（可打{playable_count}张）"
                elif trigger == "play_shiv":
                    shivs = [c for c in hand if "小刀" in c.get("name","") or "Shiv" in c.get("name","")]
                    if shivs:
                        hint = f"{cn}：每打小刀+{val}敏捷（{len(shivs)}张小刀）"

                # ── 药水协同 ──
                elif trigger == "use_potion" and has_potion:
                    hint = f"{cn}：用药水时+{val}力量！攻击回合用药水"

                # ── 被动类 ──
                elif trigger == "passive":
                    if eff == "potion_double" and has_potion:
                        hint = f"{cn}：药水效果×{val}！所有药水价值翻倍"
                    elif eff == "no_pot_dex" and not has_potion:
                        hint = f"{cn}：没药水+{val}敏捷，格挡+{val}"
                    elif eff == "strike_dmg":
                        strikes = [c for c in hand if "打击" in c.get("name","") or "Strike" in c.get("name","")]
                        if strikes:
                            hint = f"{cn}：{len(strikes)}张打击各+{val}伤害"
                    elif eff == "upg_atk_dmg":
                        upg_atk = [c for c in hand if c.get("is_upgraded") and c.get("type") in ("Attack","attack","攻击")]
                        if upg_atk:
                            hint = f"{cn}：{len(upg_atk)}张升级攻击各+{val}伤害"
                    elif eff == "energy_retain":
                        hint = f"{cn}：能量保留到下回合，不必硬凑用完"
                    elif eff == "low_hp_str" and hp_pct <= thresh:
                        hint = f"{cn}：HP≤{thresh}%已激活，+{val}力量"
                    elif eff == "max_hp_loss":
                        hint = f"{cn}：单回合最多掉{val}HP"
                    elif eff == "few_card_halfdmg":
                        hint = f"{cn}：出≤{thresh}牌受伤减半{'（当前可触发）' if playable_count <= thresh else '（当前出牌多无法触发）'}"
                    elif eff == "block_retain":
                        hint = f"{cn}：保留最多{val}格挡到下回合"
                    elif eff == "min_dmg":
                        hint = f"{cn}：未挡伤害<{val}→提升为{val}"

                # ── 回合结束触发 ──
                elif trigger == "turn_end":
                    if eff == "no_atk_energy":
                        no_atk = not any(c.get("type") in ("Attack","attack","攻击") for c in hand if c.get("can_play"))
                        hint = f"{cn}：{'不出攻击→下回合+' + str(val) + '能量' if no_atk else '出攻击会失去下回合+' + str(val) + '能量'}"
                    elif eff == "few_card_draw" and playable_count <= thresh:
                        hint = f"{cn}：出≤{thresh}牌→下回合多抽{val}张"
                    elif eff == "no_block_block":
                        hint = f"{cn}：回合结束无格挡→+{val}格挡"
                    elif eff == "hand_block":
                        hint = f"{cn}：回合结束每张手牌+{val}格挡"
                    elif eff == "block_dmg" and isinstance(val, list):
                        hint = f"{cn}：回合结束格挡≥{thresh}→对敌{val[1]}伤害"
                    elif eff == "empty_hand_aoe":
                        hint = f"{cn}：回合结束无手牌→全体{val}伤害"

                # ── 条件触发 ──
                elif trigger == "on_hurt":
                    hint = f"{cn}：受伤→下回合+{val}格挡，可策略性受伤"
                elif trigger == "first_hurt" and current_round <= 2:
                    hint = f"{cn}：首次受伤→抽{val}张牌"
                elif trigger == "on_exhaust":
                    hint = f"{cn}：消耗牌→{'全体' if 'aoe' in eff else '随机敌人'}{val}伤害"
                elif trigger == "on_discard":
                    hint = f"{cn}：弃牌→{'随机敌人'+str(val)+'伤害' if 'dmg' in eff else '+'+str(val)+'格挡'}"
                elif trigger == "on_kill":
                    if isinstance(val, list):
                        hint = f"{cn}：击杀→+{val[0]}能量+抽{val[1]}张"
                elif trigger == "on_shuffle" and shuffle_info:
                    hint = f"{cn}：洗牌+{val}格挡（即将洗牌！）"
                elif trigger == "on_death":
                    hint = f"{cn}：HP归0复活回{val}%HP，可更激进"
                elif trigger == "break_block":
                    hint = f"{cn}：突破格挡→{val}层易伤"
                elif trigger == "ally_attack":
                    hint = f"{cn}：Osty攻击时+{val}格挡"
                elif trigger == "first_spend":
                    hint = f"{cn}：首次花费→+{val}力量"

                if hint:
                    relic_effects.append(hint)

            # 不在数值表但重要的遗物
            if "MarkOfTheBloom" in relic_ids:
                relic_effects.append("绽放印记：⚠ 无法回血！最小化受伤")

            relic_combat_info = "\n".join(relic_effects) if relic_effects else ""

            # ── 牌组追踪：推算摸牌堆可能内容 ──
            draw_count = player.get("draw_pile_count", 0)
            disc_count = player.get("discard_pile_count", 0)
            hand_names = [c["name"] + ("+" if c.get("is_upgraded") else "") for c in hand]
            # 用完整牌组减去手牌 = 摸牌堆+弃牌堆中的牌
            remaining = list(self.deck_acquired) if self.deck_acquired else []
            for h in hand_names:
                if h in remaining:
                    remaining.remove(h)
            # 如果摸牌堆比剩余牌少，说明部分在弃牌堆
            # 统计剩余牌出现频次，计算摸牌概率
            deck_tracking = ""
            if remaining and draw_count > 0:

                remain_cnt = Counter(remaining)
                total_unseen = len(remaining)  # 摸牌堆+弃牌堆
                if draw_count <= total_unseen and draw_count > 0:
                    # 摸牌堆中每张牌的概率 ≈ 该牌剩余数/max(摸牌堆数,1)
                    key_cards = []
                    for card, cnt in remain_cnt.most_common():
                        prob = min(cnt / max(draw_count, 1) * 100, 100)
                        if prob >= 15:  # 只显示≥15%概率的
                            key_cards.append(f"{card}({prob:.0f}%)")
                    if key_cards:
                        deck_tracking = f"摸牌堆推算（{draw_count}张）：" + " ".join(key_cards[:8])

            # ── 战术计算 ──
            my_hp = player.get("hp", 0)
            my_max_hp = player.get("max_hp", 1)
            hp_pct = int(my_hp / max(my_max_hp, 1) * 100)
            my_block = player.get("block", 0)
            my_energy = player.get("energy", 0)

            # 致命线：敌人本回合总输出 vs 我方HP+格挡
            total_incoming = 0
            for e in enemies:
                for intent in e.get("intents", []):
                    if intent.get("type") in ("attack", "Attack"):
                        base_dmg, hits = self._parse_intent_damage(intent)
                        # 敌人虚弱则 ×0.75
                        if e.get("_weak"):
                            base_dmg = int(base_dmg * 0.75)
                        # 我方易伤则 ×1.5
                        if p_vulnerable:
                            base_dmg = int(base_dmg * 1.5)
                        total_incoming += base_dmg * hits
            effective_hp = my_hp + my_block
            lethal_info = ""
            if total_incoming > 0:
                survival_need = max(total_incoming - my_block, 0)
                if total_incoming >= effective_hp:
                    lethal_info = f"⚠ 致命！敌人总伤{total_incoming}，你HP+格挡={effective_hp}，必须格挡≥{survival_need}才能活"
                elif total_incoming >= effective_hp * 0.5:
                    lethal_info = f"危险：敌人总伤{total_incoming}，需格挡{survival_need}点（否则掉到{my_hp - survival_need}HP）"

            # 击杀预估：手牌总输出 vs 敌人总HP
            total_hand_dmg = 0
            for c in hand:
                if c.get("can_play") and c.get("type") in ("Attack", "attack", "攻击"):
                    base, _ = self._parse_card_values(c)
                    actual = base + p_strength
                    if p_weak: actual = int(actual * 0.75)
                    hits = c.get("hits", 1)
                    total_hand_dmg += actual * hits
            total_enemy_hp = sum(e.get("hp", 0) for e in enemies)
            kill_info = ""
            if total_hand_dmg > 0 and total_enemy_hp > 0:
                if total_hand_dmg >= total_enemy_hp:
                    kill_info = f"★ 可击杀！手牌总输出≈{total_hand_dmg}，敌人总HP={total_enemy_hp}"
                else:
                    turns_est = max(1, round(total_enemy_hp / max(total_hand_dmg, 1)))
                    kill_info = f"预估{turns_est}回合击杀（本回合输出≈{total_hand_dmg}，敌人剩{total_enemy_hp}HP）"

            # 洗牌预判
            shuffle_info = ""
            if draw_count <= 3 and draw_count >= 0:
                shuffle_info = f"摸牌堆仅{draw_count}张，下回合将洗牌（弃牌堆{disc_count}张回来）"

            # ── 药水智能分析 ──
            potion_list = player.get("potions", [])
            potion_hints = []
            is_elite = state.get("state_type") in ("elite", "boss")
            is_boss = state.get("state_type") == "boss"
            facing_lethal = lethal_info.startswith("⚠ 致命")
            can_kill = kill_info.startswith("★ 可击杀")

            has_sacred_bark = "SacredBark" in relic_ids
            bark_note = "（圣树皮翻倍！）" if has_sacred_bark else ""
            for pot in potion_list:
                pname = pot.get("name", "")
                if not pname:
                    continue
                cn_name = _cn_potion(pname)
                guide = self._potion_guide.get(pname, {})
                effect = guide.get("effect", "")
                best_use = guide.get("best_use", "")
                pvars = guide.get("vars", {})
                # 圣树皮翻倍数值
                bark_mult = 2 if has_sacred_bark else 1

                # 分类药水并给出时机建议
                hint = None

                # 力量/敏捷类 — 持续增益，越早用越赚
                if pvars.get("StrengthPower") or pvars.get("DexterityPower"):
                    buff_val = (pvars.get("StrengthPower", 0) or pvars.get("DexterityPower", 0)) * bark_mult
                    buff_type = "力量" if pvars.get("StrengthPower") else "敏捷"
                    if is_boss and int(rnd) <= 2:
                        hint = f"★ {cn_name}：Boss战前2回合用！+{buff_val}{buff_type}每回合吃加成{bark_note}"
                    elif is_elite and int(rnd) <= 2:
                        hint = f"★ {cn_name}：精英战早期用，+{buff_val}{buff_type}越早越赚{bark_note}"
                    elif facing_lethal:
                        if buff_type == "敏捷":
                            hint = f"○ {cn_name}：面临致命，+{buff_val}敏捷能多挡{buff_val * len([c for c in hand if c.get('type') in ('Skill','skill','技能')])}点"
                    else:
                        hint = f"留着：{cn_name}留给精英/Boss战第1回合用"

                # 攻击药水 — 能补刀击杀时用
                elif pvars.get("Damage"):
                    pot_dmg = pvars["Damage"] * bark_mult
                    if not can_kill and total_hand_dmg + pot_dmg >= total_enemy_hp:
                        hint = f"★ {cn_name}：用了能击杀！手牌{total_hand_dmg}+药水{pot_dmg}≥敌人{total_enemy_hp}HP"
                    elif facing_lethal:
                        # 能杀掉某个敌人减少伤害
                        for e in enemies:
                            if e.get("hp", 0) <= pot_dmg:
                                hint = f"★ {cn_name}：直接秒{e.get('_display_name', e.get('name'))}减少承伤"
                                break
                    elif not is_elite:
                        hint = f"留着：{cn_name}({pot_dmg}伤)留给精英/Boss补刀"

                # 格挡药水
                elif pvars.get("Block"):
                    pot_blk = pvars["Block"] * bark_mult
                    if facing_lethal:
                        hint = f"★ {cn_name}：致命危机！+{pot_blk}格挡保命"
                    elif total_incoming > 0 and total_incoming > my_block + sum(
                        self._parse_card_values(c)[1] for c in hand if c.get("can_play") and c.get("type") in ("Skill","skill","技能")):
                        hint = f"○ {cn_name}：本回合格挡不够，+{pot_blk}能减少掉血"

                # 回血药水
                elif pvars.get("Heal") or pvars.get("HealPercent"):
                    heal = (pvars.get("Heal", 0) or int(my_max_hp * pvars.get("HealPercent", 0) / 100)) * bark_mult
                    if facing_lethal:
                        hint = f"★ {cn_name}：致命危机，+{heal}HP保命"
                    elif hp_pct < 30:
                        hint = f"○ {cn_name}：HP很低({hp_pct}%)，考虑现在用+{heal}HP"
                    else:
                        hint = f"留着：{cn_name}留到HP更低时保命"

                # 能量药水 — 关键回合多出牌
                elif pvars.get("Energy"):
                    extra_e = pvars["Energy"]
                    unplayable = [c for c in hand if not c.get("can_play") and c.get("cost", 99) <= my_energy + extra_e]
                    if facing_lethal and unplayable:
                        hint = f"★ {cn_name}：+{extra_e}能量，多出{len(unplayable)}张牌保命"
                    elif is_boss and int(rnd) <= 2:
                        hint = f"○ {cn_name}：Boss战+{extra_e}能量，多出关键牌"
                    else:
                        hint = f"留着：{cn_name}留给关键回合爆发"

                # 抽牌药水
                elif pvars.get("Draw"):
                    draw_n = pvars["Draw"]
                    if deck_tracking and is_elite:
                        hint = f"○ {cn_name}：抽{draw_n}张，可能抽到关键牌"
                    else:
                        hint = f"留着：{cn_name}留给需要找关键牌的回合"

                # 毒药水 — 叠毒
                elif pvars.get("PoisonPower"):
                    poison_val = pvars["PoisonPower"] * bark_mult
                    if is_boss:
                        hint = f"★ {cn_name}：Boss战+{poison_val}层毒，长期战斗毒伤可观{bark_note}"
                    elif not is_elite:
                        hint = f"留着：{cn_name}({poison_val}毒)留给精英/Boss"

                # 灾厄药水 — 强力DOT
                elif pvars.get("DoomPower"):
                    doom_val = pvars["DoomPower"] * bark_mult
                    if is_boss or is_elite:
                        hint = f"★ {cn_name}：+{doom_val}灾厄，每回合{doom_val}伤害{bark_note}"
                    else:
                        hint = f"留着：{cn_name}({doom_val}灾厄)留给精英/Boss"

                # 消亡粉末 — 受伤时额外伤害
                elif pvars.get("Demise"):
                    demise_val = pvars["Demise"] * bark_mult
                    if is_elite or is_boss:
                        hint = f"○ {cn_name}：+{demise_val}消亡，敌人每次受伤额外+{demise_val}伤害"

                # 集中药水 — 充能球加成
                elif pvars.get("FocusPower"):
                    focus_val = pvars["FocusPower"] * bark_mult
                    if is_boss and int(rnd) <= 2:
                        hint = f"★ {cn_name}：Boss战+{focus_val}集中，充能球被动效果翻倍{bark_note}"
                    elif is_elite:
                        hint = f"○ {cn_name}：精英战+{focus_val}集中"
                    else:
                        hint = f"留着：{cn_name}留给精英/Boss"

                # 覆甲药水 — 持续格挡
                elif pvars.get("PlatingPower"):
                    plate_val = pvars["PlatingPower"] * bark_mult
                    if is_boss:
                        hint = f"★ {cn_name}：Boss战+{plate_val}覆甲，每回合+{plate_val}格挡{bark_note}"
                    elif facing_lethal:
                        hint = f"★ {cn_name}：+{plate_val}覆甲保命"

                # 荆棘药水 — 被打反伤
                elif pvars.get("ThornsPower"):
                    thorns_val = pvars["ThornsPower"] * bark_mult
                    enemies_multi = len(enemies) > 1
                    if enemies_multi:
                        hint = f"○ {cn_name}：+{thorns_val}荆棘，{len(enemies)}个敌人打你都反弹{thorns_val}伤害"

                # 祭祀药水 — 每回合+力量
                elif pvars.get("RitualPower"):
                    ritual_val = pvars["RitualPower"] * bark_mult
                    if is_boss and int(rnd) <= 2:
                        hint = f"★ {cn_name}：Boss战+{ritual_val}祭祀，每回合末+{ritual_val}力量，越早越赚{bark_note}"
                    elif is_elite:
                        hint = f"○ {cn_name}：精英战+{ritual_val}祭祀（每回合+力量）"
                    else:
                        hint = f"留着：{cn_name}(每回合+力量)留给Boss"

                # 抽牌类（Cards变量）— 迅捷/狡诈/明晰等
                elif pvars.get("Cards") and not pvars.get("Energy"):
                    cards_val = pvars["Cards"]
                    if facing_lethal:
                        hint = f"○ {cn_name}：抽/生成{cards_val}张牌，可能找到保命牌"
                    elif is_elite or is_boss:
                        hint = f"○ {cn_name}：{effect[:25]}"

                # ── 特殊高价值药水 ──

                # 易伤药水 — 攻击伤害+50%，多攻击牌时收益巨大
                elif pvars.get("VulnerablePower"):
                    atk_count = len([c for c in hand if c.get("can_play") and c.get("type") in ("Attack","attack","攻击")])
                    if is_boss and int(rnd) <= 2:
                        hint = f"★ {cn_name}：Boss战用！{atk_count}张攻击牌全吃+50%伤害"
                    elif atk_count >= 3:
                        hint = f"★ {cn_name}：手里{atk_count}张攻击牌，+50%伤害收益极高"
                    elif not is_elite:
                        hint = f"留着：{cn_name}留给精英/Boss，攻击牌多的回合用"

                # 虚弱药水 — 降低敌人攻击25%
                elif pvars.get("WeakPower"):
                    if facing_lethal or total_incoming > 20:
                        reduced = int(total_incoming * 0.25)
                        hint = f"★ {cn_name}：敌人伤害{total_incoming}，虚弱后减少{reduced}点"
                    elif is_boss:
                        hint = f"○ {cn_name}：Boss战减伤25%，大攻击回合用"

                # 无实体药水 — S级，1回合所有伤害变1
                elif pvars.get("IntangiblePower"):
                    if facing_lethal:
                        hint = f"★ {cn_name}：S级！致命时用，本回合所有伤害→1"
                    elif is_boss and total_incoming >= 30:
                        hint = f"★ {cn_name}：Boss大招回合用！{total_incoming}伤害→1"
                    else:
                        hint = f"留着：{cn_name}(S级)留给Boss最危险的回合"

                # 复制药水 — S级，下一张牌打两次
                elif pvars.get("DuplicationPower"):
                    best_card = max(hand, key=lambda c: sum(self._parse_card_values(c)) or 0) if hand else None
                    if best_card and is_elite:
                        bc_name = best_card.get("name", "?")
                        hint = f"★ {cn_name}：S级！复制{bc_name}打两次，精英战用"
                    else:
                        hint = f"留着：{cn_name}(S级)留给Boss，复制最强牌"

                # 缓冲药水 — 挡1次致命伤害
                elif pvars.get("BufferPower"):
                    if facing_lethal:
                        hint = f"★ {cn_name}：完美保命！阻止下1次HP伤害"
                    else:
                        hint = f"留着：{cn_name}留给致命危机"

                # 超巨化 — 伤害翻倍，受伤也翻倍
                elif pvars.get("GigantificationPower"):
                    if can_kill or (is_boss and my_block > total_incoming):
                        hint = f"★ {cn_name}：攻击翻倍！格挡够就用，但受伤也翻倍"
                    elif facing_lethal:
                        hint = f"✗ {cn_name}：致命时别用！受伤翻倍会更惨"
                    else:
                        hint = f"留着：{cn_name}留给格挡充足+能爆发的回合"

                # 预知之滴 — 从摸牌堆搜索1张牌
                elif "选择1张牌放入手牌" in effect or "搜索" in effect:
                    if is_elite or is_boss:
                        hint = f"○ {cn_name}：搜索关键牌，精英/Boss战需要特定牌时用"
                    else:
                        hint = f"留着：{cn_name}留给需要特定牌的关键回合"

                # 癫狂之触 — 1张牌永久0费，极强
                elif "永久0费" in effect:
                    if is_boss:
                        hint = f"★ {cn_name}：Boss战选最贵的牌永久0费！"

                # 镣铐药水 — 敌人失去力量
                elif pvars.get("ShacklingPotionPower"):
                    str_enemies = [e for e in enemies if any(
                        p.get("id") == "Strength" or p.get("name") in ("力量","Strength")
                        for p in e.get("powers", []))]
                    if str_enemies:
                        hint = f"★ {cn_name}：敌人有力量buff，用了降7点力量大幅减伤"
                    elif is_boss:
                        hint = f"○ {cn_name}：Boss战减力量"

                # 固化药水 — 格挡翻倍
                elif "翻倍" in effect and "格挡" in effect:
                    if my_block >= 15:
                        hint = f"★ {cn_name}：当前格挡{my_block}→{my_block*2}！翻倍价值高"
                    elif my_block > 0:
                        hint = f"○ {cn_name}：格挡{my_block}→{my_block*2}，格挡再高一点用更赚"

                # 液态记忆 — 从弃牌堆选牌
                elif "弃牌堆" in effect and "手牌" in effect:
                    if is_elite or is_boss:
                        hint = f"○ {cn_name}：从弃牌堆捞关键牌回手"

                # 熔炉祝福 — 升级所有手牌
                elif "升级" in effect and "手牌" in effect and "所有" in effect:
                    if is_boss and int(rnd) <= 2:
                        hint = f"★ {cn_name}：Boss战全手牌升级！越早越好"
                    elif is_elite:
                        hint = f"○ {cn_name}：精英战手牌全升级"

                # 骨头酿 — 召唤Osty
                elif pvars.get("Summon") or "召唤" in effect:
                    if is_boss or is_elite:
                        hint = f"★ {cn_name}：召唤Osty，精英/Boss战多一个肉盾+输出"

                # 瓶中船 — 分两回合给格挡
                elif "下回合" in effect and "格挡" in effect:
                    if facing_lethal or total_incoming > 15:
                        hint = f"○ {cn_name}：本回合+下回合都给格挡"

                # 其他药水 — 用知识库的best_use
                else:
                    if facing_lethal:
                        hint = f"○ {cn_name}：面临致命，效果：{effect[:30]}"
                    elif is_elite or is_boss:
                        if best_use:
                            hint = f"参考：{cn_name} — {best_use[:40]}"

                if hint:
                    potion_hints.append(hint)

            potion_analysis = "\n".join(potion_hints) if potion_hints else ""

            tactical_info = "\n".join(x for x in [lethal_info, kill_info, shuffle_info] if x)
            if potion_analysis:
                tactical_info += ("\n" if tactical_info else "") + "药水分析：\n" + potion_analysis

            char = player.get('character', '?')

            # 智能上下文构建（0 token查表）
            smart_ctx = self._build_context("combat")

            # 获取怪物AI信息（保留，补充smart_ctx未覆盖的怪物）
            monster_hints = []
            for e in enemies:
                ename = e.get("name", "")
                for mid, mdata in self._monster_ai.items():
                    if mdata.get("name_cn") == ename or mid == ename:
                        pattern = mdata.get("ai_pattern", "")
                        if pattern:
                            monster_hints.append(f"{ename}: {pattern}")
                        break
            monster_info = "\n".join(monster_hints) if monster_hints else ""

            prompt = f"""你是杀戮尖塔2战斗教练。纯文字，不用markdown符号。所有牌名遗物名用中文。

{smart_ctx}
{"怪物行为规律：" + chr(10) + monster_info if monster_info else ""}

角色：{player.get('character')}  HP：{player.get('hp')}/{player.get('max_hp')}  格挡：{player.get('block')}
能量：{player.get('energy')}/{player.get('max_energy')}  幕{run.get('act')}层{run.get('floor')}  第{rnd}回合
{"增减益：" + dmg_hint if dmg_hint else ""}
遗物：{relics}
药水：{potions}

手牌：
{hand_str}

敌人：
{enemy_str}
{"友方召唤物：" + chr(10) + ally_str if ally_str else ""}
摸牌堆：{draw_count}张  弃牌堆：{disc_count}张
{deck_tracking}
{"战术分析：" + chr(10) + tactical_info if tactical_info else ""}
{"遗物效果（本回合相关）：" + chr(10) + relic_combat_info if relic_combat_info else ""}

重要：
1. 计算伤害时必须考虑力量加成、虚弱减伤、易伤增伤。攻击牌面板伤害+力量=基础伤害，我方虚弱则×0.75，敌方易伤则×1.5。格挡牌面板+敏捷=实际格挡。
2. 如果有摸牌堆推算信息，分析是否值得用抽牌效果（如后空翻、猛力抽牌）来抽到关键牌。
3. 如果摸牌堆快空了（≤3张），弃牌堆会洗回来——考虑弃牌堆里有什么好牌即将回来。

请严格按以下简洁格式输出，每行一条，不要多余解释：

▶ 出牌（按顺序）
1. [序号]牌名 ⚔目标 — 实际效果数值（攻击牌用⚔，技能牌用🛡，能力牌用✦）
2. ...
（能量剩余：X）

⚠ 本回合最大威胁
谁，什么意图，多少伤害，是否致命。如果有连击/buff叠加要算总伤。

💡 核心思路
为什么这样出牌，优先解决什么问题。如果摸牌堆有关键牌或即将洗牌，说明跨回合策略。

🧪 药水建议（如果有药水分析信息）
哪瓶该用/该留？第几回合用收益最大？用了能改变什么局面？"""

            advice = self._ask_llm(prompt)

            # ── 极简排版 ──
            lines = [f"◆ 第{rnd}回合"]
            # 敌人（每个一行：名字 HP 意图 buff）
            for e in enemies:
                hp  = e.get("hp", 0); mhp = e.get("max_hp", 1)
                intent = self._fmt_intent(e.get("intents", []))
                blk = e.get("block", 0)
                dn = e.get("_display_name", e.get("name", "?"))
                pw_list = [f"{p['name']}{p['amount']}" for p in e.get("powers", [])]
                line = f"{dn} {hp}/{mhp}"
                if blk: line += f" 🛡{blk}"
                line += f" →{intent}"
                if pw_list: line += f" [{' '.join(pw_list)}]"
                lines.append(line)
            # 友方（同样一行）
            for a in allies:
                aname = a.get("name", "?")
                ahp = a.get("hp", 0); amhp = a.get("max_hp", 1)
                ablk = a.get("block", 0)
                apw = [f"{p['name']}{p['amount']}" for p in a.get("powers", [])]
                aline = f"🤝{aname} {ahp}/{amhp}"
                if ablk: aline += f" 🛡{ablk}"
                if apw: aline += f" [{' '.join(apw)}]"
                lines.append(aline)

            # 我方状态（一行）
            status_parts = []
            if p_strength: status_parts.append(f"力量{p_strength:+d}")
            if p_dexterity: status_parts.append(f"敏捷{p_dexterity:+d}")
            other_buffs = [f"{p['name']}{p['amount']}" for p in player.get("powers", [])
                          if p.get("name") not in ("力量","Strength","敏捷","Dexterity")]
            status_parts.extend(other_buffs[:4])
            if status_parts:
                lines.append(f"我方: {' '.join(status_parts)}")

            # 手牌（一行紧凑）
            hand_compact = []
            for c in hand:
                name = c["name"]
                upg = "+" if c.get("is_upgraded") else ""
                cost = c.get("cost", "?")
                hand_compact.append(f"{name}{upg}({cost})")
            lines.append(f"⚡{player.get('energy')}/{player.get('max_energy')} 手牌：{' · '.join(hand_compact)}")
            lines.append(f"摸:{player.get('draw_pile_count')} 弃:{player.get('discard_pile_count')}")

            # 致命警告（仅危险时）
            if facing_lethal:
                lines.append(f"⚠ 致命！总伤{total_incoming} 格挡{my_block} 缺口{total_incoming - my_block}")
            elif total_incoming > 0 and my_block < total_incoming:
                gap = total_incoming - my_block
                hp_after = player.get("hp", 0) - gap
                if hp_after > 0:
                    lines.append(f"受伤：-{gap}HP→{hp_after}HP")

            # 在 ▶ ⚠ 💡 🧪 前加空行
            formatted = advice.replace("▶", "\n▶").replace("⚠", "\n⚠").replace("💡", "\n💡").replace("🧪", "\n🧪").strip()

            if not self._analysis_stale():
                # 上栏：战场信息
                scene_html = self._render_formatted_html("\n".join(lines))
                self._js(f'app.updateScene({{type:"html",html:{json.dumps(scene_html)}}})')
                # 下栏：AI建议
                self._push_advice(formatted)
                self._js('app.setTab("situation")')
        except Exception as e:
            if not self._analysis_stale():
                self._js(f'app.updateAdvice({json.dumps(_html.escape(f"⚠ 战斗分析失败：{e}"))})')
        finally:
            self._busy_combat = False

    def _ai_map(self, state):
        self._busy_strat = True
        self._js(f'app.updateScene({{type:"html",html:{json.dumps("◌  正在分析路线…")}}})')
        self._clear_advice()
        try:
            run    = state.get("run", {})
            player = self._get_player(state) or self.last_player or {}
            mdata  = state.get("map", {})
            hp_pct = int(player.get("hp",0)/max(player.get("max_hp",1),1)*100)
            # 地图场景player可能没有relics/potions，fallback到上次缓存
            p_relics = player.get('relics') or self.last_player.get('relics', [])
            p_potions = player.get('potions') or self.last_player.get('potions', [])
            relics = ', '.join(r['name'] for r in p_relics) or '无'

            node_cn = {"Monster":"普通怪","Elite":"精英怪","Boss":"Boss",
                       "Shop":"商店","Rest":"休息点","RestSite":"休息点","Event":"事件",
                       "Treasure":"宝箱","Unknown":"未知","Ancient":"古代事件"}
            opts = mdata.get("next_options", [])
            opts_str = "\n".join(
                f"路线{o['index']+1}：{node_cn.get(o['type'],o['type'])}"
                + (" → " + " / ".join(node_cn.get(n['type'],n['type']) for n in o.get('leads_to',[])[:3])
                   if o.get('leads_to') else "")
                for o in opts) or "（无路线信息）"

            boss_data = mdata.get("boss", {})
            boss = boss_data.get("name") or boss_data.get("type") or "未知"
            deck_info = f"已选牌：{', '.join(self.deck_acquired)}" if self.deck_acquired else ""
            removed   = f"已移除：{', '.join(self.deck_removed)}" if self.deck_removed else ""

            char = player.get('character', '?')
            smart_ctx = self._build_context("map")

            # 资源管理信息
            potions = p_potions
            potion_cnt = sum(1 for p in potions if p.get("name"))
            gold = player.get("gold", 0)
            act = run.get("act", 1)
            floor = run.get("floor", 0)
            archetype = self._deck_archetype or "未定型"

            # 计算路线中各节点类型数量
            route_summary = []
            for o in opts:
                types = [o.get("type", "")]
                types.extend(n.get("type", "") for n in o.get("leads_to", []))
                route_summary.append(types)

            # ── 遗物对路线的影响 ──
            relic_list_map = p_relics
            relic_ids_map = {r.get("id", r.get("name", "")) for r in relic_list_map}
            relic_route_notes = []

            # 战后回血类 — 影响能承受多少场战斗
            heal_per_fight = 0
            if "BurningBlood" in relic_ids_map or "燃烧之血" in {r.get("name","") for r in relic_list_map}:
                heal_per_fight += 6
                relic_route_notes.append(f"燃烧之血：每场战后+6HP，可多打怪")
            if "BlackBlood" in relic_ids_map or "黑暗之血" in {r.get("name","") for r in relic_list_map}:
                heal_per_fight += 12
                relic_route_notes.append(f"黑暗之血：每场战后+12HP，激进打精英")
            if "MeatOnTheBone" in relic_ids_map:
                if hp_pct <= 50:
                    relic_route_notes.append("肉骨头：战后HP≤50%多回12HP，低血打怪反而赚")
            if "BloodVial" in relic_ids_map or "小血瓶" in {r.get("name","") for r in relic_list_map}:
                relic_route_notes.append("小血瓶：每场战斗开始+2HP")

            # 金币类 — 影响商店价值
            gold_bonus = ""
            if "GoldenIdol" in relic_ids_map:
                relic_route_notes.append("黄金神像：每场战后+25金币，商店路线价值更高")
                gold_bonus = "（黄金神像加成）"
            if "MembershipCard" in relic_ids_map:
                relic_route_notes.append("会员卡：商店打折50%，商店路线极高价值")
            if "TheCourier" in relic_ids_map:
                relic_route_notes.append("送货员：商品不断货+打折，优先走商店")
            if "AmethystAubergine" in relic_ids_map:
                relic_route_notes.append("紫水晶茄子：敌人额外掉金币，多打怪攒钱")

            # 精英战加成类 — 影响是否值得打精英
            if "SlingOfCourage" in relic_ids_map:
                relic_route_notes.append("勇气投石索：精英战+2力量，精英更安全")
            if "BoomingConch" in relic_ids_map:
                relic_route_notes.append("轰鸣海螺：精英战多抽3张，精英更安全")
            if "Lizardtail" in relic_ids_map:
                relic_route_notes.append("蜥蜴尾巴：死亡复活，可冒险打精英")

            # 休息点类 — 影响休息点价值
            if "DreamCatcher" in relic_ids_map:
                relic_route_notes.append("捕梦网：休息时抽卡，休息点=休息+选牌")
            if "Regal Pillow" in relic_ids_map or "RegalPillow" in relic_ids_map:
                relic_route_notes.append("皇家枕头：休息多回15HP")
            if "PeacePipe" in relic_ids_map:
                relic_route_notes.append("和平烟斗：休息点可删牌，休息点价值更高")
            if "Shovel" in relic_ids_map:
                relic_route_notes.append("铲子：休息点可挖宝获遗物")

            # 事件类
            if "SsserpentHead" in relic_ids_map:
                relic_route_notes.append("蛇头：事件中金币选项+50金，事件路线更赚")
            if "JuzuBracelet" in relic_ids_map:
                relic_route_notes.append("念珠手链：?节点必定事件不遇怪，未知路线更安全")

            # 商店加血/加成类
            if "MealTicket" in relic_ids_map:
                relic_route_notes.append("餐券：进商店回血，商店路线=购物+回血")
            if "MawBank" in relic_ids_map:
                relic_route_notes.append("巨口储蓄罐：每层+金币，但商店消费会失效")

            # 药水类
            if "SacredBark" in relic_ids_map:
                relic_route_notes.append("圣树皮：药水翻倍，精英战更有底气")
            if "Sozu" in relic_ids_map:
                relic_route_notes.append("添水：无法获得药水，不用考虑药水路线")
            if "WhiteBeastStatue" in relic_ids_map:
                relic_route_notes.append("白兽雕像：战后必掉药水，多打怪攒药水")
            if "DelicateFrond" in relic_ids_map:
                relic_route_notes.append("娇嫩蕨草：战斗开始药水栏自动填满，空栏=免费药水")
            if "TinyMailbox" in relic_ids_map:
                relic_route_notes.append("小邮箱：休息时获得药水，休息路线更赚")

            # 精英额外掉落
            if "BlackStar" in relic_ids_map:
                relic_route_notes.append("黑星：精英多掉1遗物，打精英收益翻倍！")
            if "WhiteStar" in relic_ids_map:
                relic_route_notes.append("白星：精英多掉稀有卡，打精英拿好牌")
            if "SwordOfStone" in relic_ids_map:
                relic_route_notes.append("石之剑：打够精英后变强力遗物，优先精英路线")
            if "WarHammer" in relic_ids_map:
                relic_route_notes.append("战锤：打精英升级牌，精英路线加分")

            # 普通怪额外掉落
            if "PrayerWheel" in relic_ids_map:
                relic_route_notes.append("转经轮：普通怪多掉1组卡，多打怪拿更多牌")

            # 蛋类（拿牌自动升级）
            egg_notes = []
            if "MoltenEgg" in relic_ids_map:
                egg_notes.append("攻击")
            if "ToxicEgg" in relic_ids_map:
                egg_notes.append("技能")
            if "FrozenEgg" in relic_ids_map:
                egg_notes.append("能力")
            if egg_notes:
                relic_route_notes.append(f"{'、'.join(egg_notes)}蛋：获得{'、'.join(egg_notes)}牌自动升级，多拿牌价值高")

            # Boss战加成
            if "Pantograph" in relic_ids_map:
                relic_route_notes.append("缩放仪：Boss战开始回血，Boss前不必满血")
            if "StoneCracker" in relic_ids_map:
                relic_route_notes.append("碎石钻：Boss战自动升级牌")

            # 金币受限
            if "Ectoplasm" in relic_ids_map:
                relic_route_notes.append("灵体外质：⚠ 无法获金币，商店路线无意义")
            if "SealOfGold" in relic_ids_map:
                relic_route_notes.append("黄金印：每回合花金币换能量，需要攒钱")

            # 钨合金棍 — 减少HP损失
            if "TungstenRod" in relic_ids_map:
                relic_route_notes.append("钨合金棍：每次受伤-1HP，多场战斗累积省很多血")

            # 永恒羽毛 — 牌组大时休息回更多血
            if "EternalFeather" in relic_ids_map:
                deck_size = len(self.deck_acquired) if self.deck_acquired else 10
                heal_est = deck_size // 5 * 3
                relic_route_notes.append(f"永恒羽毛：牌组{deck_size}张，休息额外回{heal_est}HP")

            # 恶魔之舌 — 自伤回血
            if "DemonTongue" in relic_ids_map:
                relic_route_notes.append("恶魔之舌：首次自伤回等量HP，自伤流更安全")

            # 皮草大衣 — 标记战斗敌人1HP
            if "FurCoat" in relic_ids_map:
                relic_route_notes.append("皮草大衣：部分战斗敌人只有1HP，可放心打怪")

            # 休息点升级类
            if "Girya" in relic_ids_map:
                relic_route_notes.append("壶铃：休息点可+力量(最多3次)，休息路线更强")
            if "StoneHumidifier" in relic_ids_map:
                relic_route_notes.append("石炉加湿器：休息时+最大HP，休息路线长期收益高")
            if "MiniatureTent" in relic_ids_map:
                relic_route_notes.append("微型帐篷：休息点可选多个选项（回血+升级+删牌），休息极高价值")
            if "MeatCleaver" in relic_ids_map:
                relic_route_notes.append("切肉刀：休息点可烹饪，休息路线更多选择")

            # 古茶具
            if "VenerableTeaSet" in relic_ids_map or "FakeVenerableTeaSet" in relic_ids_map:
                relic_route_notes.append("古茶具：休息后下场战斗+能量，休息→战斗路线最优")

            # 活动星图
            if "Planisphere" in relic_ids_map:
                relic_route_notes.append("活动星图：进?房间回血，未知路线更安全")

            # 招财异鱼
            if "LuckyFysh" in relic_ids_map:
                relic_route_notes.append("招财异鱼：获得牌+金币，多拿牌更赚")

            # 圆顶礼帽
            if "BowlerHat" in relic_ids_map:
                relic_route_notes.append("圆顶礼帽：金币+20%，多打怪攒钱更快")

            # 火龙果
            if "DragonFruit" in relic_ids_map:
                relic_route_notes.append("火龙果：获得金币+最大HP，打怪=攒钱+变壮")

            # 战后回血补充
            if "ChosenCheese" in relic_ids_map:
                relic_route_notes.append("天选芝士：战后+最大HP，多打怪越来越壮")
            if "BookOfFiveRings" in relic_ids_map:
                relic_route_notes.append("五轮书：拿牌时回血，多拿牌=回血")
            if "BookRepairKnife" in relic_ids_map:
                relic_route_notes.append("修书小刀：敌人死于灾厄回血（灾厄流专属）")
            if "FakeBloodVial" in relic_ids_map:
                relic_route_notes.append("小血瓶？：每场开始+回血")

            # 药水栏/药水生成
            if "PetrifiedToad" in relic_ids_map:
                relic_route_notes.append("石化蟾蜍：每场战斗开始得药水石头（15伤害）")
            if "PotionBelt" in relic_ids_map:
                relic_route_notes.append("药水腰带：多药水栏，可存更多药水")

            # 战后奖励升级
            if "LavaLamp" in relic_ids_map:
                relic_route_notes.append("熔岩灯：不受伤打完→卡牌奖励全升级，值得完美通关")
            if "SilverCrucible" in relic_ids_map:
                relic_route_notes.append("白银熔炉：前几组卡牌奖励已升级")

            # Boss额外掉落
            if "LavaRock" in relic_ids_map:
                relic_route_notes.append("熔岩石：第1阶段Boss多掉遗物")

            # 蜥蜴尾巴（API里可能是LizardTail不是Lizardtail）
            if "LizardTail" in relic_ids_map:
                relic_route_notes.append("蜥蜴尾巴：死亡复活，可冒险打精英")

            # 佩尔之牙 — 战后返还升级牌
            if "PaelsTooth" in relic_ids_map:
                relic_route_notes.append("佩尔之牙：战后升级+返还删除的牌")

            relic_route_info = "\n".join(relic_route_notes) if relic_route_notes else ""
            if heal_per_fight > 0:
                relic_route_info = f"战后回血{heal_per_fight}HP/场\n" + relic_route_info

            prompt = f"""杀戮尖塔2路线规划。纯文字不用markdown。所有牌名遗物名用中文。极简。

{smart_ctx}

{char} HP{player.get('hp')}/{player.get('max_hp')}({hp_pct}%) 金{gold} 幕{act}层{floor}
遗物：{relics}  Boss：{boss}
药水：{potion_cnt}瓶
流派：{archetype}
{deck_info}  {removed}

可选路线：
{opts_str}

资源管理考量：
- HP{'充足(>70%)' if hp_pct > 70 else '偏低(<50%)需要回血机会' if hp_pct < 50 else '中等(50-70%)谨慎'}{"（战后回血"+str(heal_per_fight)+"HP/场）" if heal_per_fight > 0 else ""}
- 金币{gold}{'，够买牌/删牌' if gold >= 75 else '，不够买牌需攒钱'}{gold_bonus}
- 药水{potion_cnt}瓶{'，精英/Boss战可用' if potion_cnt > 0 else '，没有保命手段要小心'}
- Boss准备：{'牌组'+archetype+'成型中' if archetype != '未定型' else '牌组未定型，需要尽快确定方向'}
{"遗物路线加成：" + chr(10) + relic_route_info if relic_route_info else ""}

格式（不要多余解释）：
★ 推荐路线X — 理由（考虑HP预算、金币、药水、牌组完成度、遗物加成）
✗ 避开路线X — 理由
⚠ 资源预警 — HP/金币/药水是否够撑到Boss？遗物能否补足短板
📋 路线目标 — 接下来2-3层优先：拿牌/删牌/买装/回血/攒钱"""

            advice = self._ask_llm(prompt)
            if not self._analysis_stale():
                self._push_advice(advice, header="── 路线分析 ──────────────────────────")
                self._js('app.setTab("situation")')
        except Exception as e:
            if not self._analysis_stale():
                self._js(f'app.updateAdvice({json.dumps(_html.escape(f"⚠ {e}"))})')
        finally:
            self._busy_strat = False

    def _ai_card(self, state):
        self._busy_strat = True
        self._show_analyzing("⏳  分析选牌中…")
        try:
            player  = self._get_player(state)
            cr      = state.get("card_reward") or state.get("card_select") or {}
            rewards = cr.get("cards", [])
            run     = state.get("run", {})
            relics  = ', '.join(r['name'] for r in player.get('relics', [])) or '无'
            deck_info = f"已选牌：{', '.join(self.deck_acquired)}" if self.deck_acquired else "初始牌组"
            removed   = f"已移除：{', '.join(self.deck_removed)}" if self.deck_removed else ""
            arch_hint = f"期望流派：{self._deck_archetype}" if self._deck_archetype else ""

            cards_str = "\n".join(
                f"  [{i}] {c.get('name','')}{'+' if c.get('is_upgraded') else ''}  "
                f"{CARD_DICT.get(c.get('name',''), self._clean_desc(c.get('description',''))[:40])}"
                for i, c in enumerate(rewards)) or "  （无可选牌，可跳过）"

            char = player.get('character', '?')
            # 智能上下文（0 token查表）
            smart_ctx = self._build_context("card_reward")

            prompt = f"""杀戮尖塔2选牌建议。纯文字，不用markdown。所有牌名遗物名用中文。极简输出。

{smart_ctx}

{char} HP{player.get('hp')}/{player.get('max_hp')} 幕{run.get('act')}层{run.get('floor')}
遗物：{relics}  {deck_info}  {removed}  {arch_hint}

奖励牌：
{cards_str}

格式（每行一条，不要多余解释）：
★ [序号]牌名 — 一句话理由
○ [序号]牌名 — 一句话理由
✗ [序号]牌名 — 一句话理由
方向：一句话当前流派+缺什么"""

            advice = self._ask_llm(prompt)

            if not self._analysis_stale():
                full_text = (f"── 选牌分析 ──────────────\n\n"
                             f"奖励牌：\n{cards_str}\n\n"
                             + advice)
                self._push_advice(full_text)

                # 同步更新卡组构建区方向摘要
                self._display_deck_list()

            for line in advice.split("\n"):
                if line.startswith("期望方向："):
                    self._deck_archetype = line.replace("期望方向：", "").strip()
                    self._save_archetype()
                    break

        except Exception as e:
            self._js(f'app.updateScene({{type:"html",html:{json.dumps(_html.escape(f"⚠ 选牌分析失败：{e}"))}}})')
        finally:
            self._busy_strat = False
            self._card_analyzed = True

    def _ai_node(self, state):
        self._busy_strat = True
        stype = state.get("state_type", "")
        self._show_analyzing("◌  正在分析…")
        try:
            # 重新抓最新状态确保数据完整
            try:
                fresh = requests.get(API_URL, timeout=5).json()
                if fresh.get("state_type") == stype:
                    state = fresh
            except Exception:
                pass
            player = self._get_player(state)
            run    = state.get("run", {})
            relics = ', '.join(r['name'] for r in player.get('relics',[])) or '无'
            hp_pct = int(player.get('hp',0)/max(player.get('max_hp',1),1)*100)

            scene_cn = {"event":"随机事件","rest":"休息点","rest_site":"休息点","shop":"商店","treasure":"宝箱"}
            scene = scene_cn.get(stype, stype)

            extra = ""
            if stype == "event":
                ev   = state.get("event", {})
                name = ev.get("event_name","")
                opts = "\n".join(
                    f"[{o['index']}] {o['title']}：{o['description']}"
                    for o in ev.get("options",[]) if not o.get("is_locked"))
                extra = f"事件：{name}\n选项：\n{opts}"
                prompt = f"""杀戮尖塔2事件建议，纯文字不用markdown，所有牌名遗物名用中文，按格式输出每个选项。

幕{run.get('act')}·层{run.get('floor')}  {player.get('character','?')}  HP：{player.get('hp')}/{player.get('max_hp')}（{hp_pct}%）  金币：{player.get('gold')}
遗物：{relics}
{extra}

格式（每个选项独立分析）：
★ [选项名] — 推荐理由（获得什么，值不值）
○ [选项名] — 可选理由（利弊分析）
✗ [选项名] — 不推荐理由（风险是什么）

💡 最佳选择 — 综合当前HP/金币/牌组方向给出结论"""
            elif stype in ("rest", "rest_site"):
                prompt = f"""杀戮尖塔2休息点建议，纯文字不用markdown。所有牌名遗物名用中文。

{player.get('character','?')} HP：{player.get('hp')}/{player.get('max_hp')}（{hp_pct}%）  幕{run.get('act')}·层{run.get('floor')}
遗物：{relics}
{'已选牌组：'+', '.join(self.deck_acquired) if self.deck_acquired else '初始牌组'}
{'流派：'+self._deck_archetype if self._deck_archetype else ''}

格式：
★ 推荐：补血 或 锻造[牌名]
理由：一句话（考虑HP百分比、接下来的路线、升级哪张牌收益最大）
💡 如果锻造，说明升级后的效果变化"""
            elif stype == "shop":
                shop  = state.get("shop", {})
                shop_items = shop.get("items", [])
                items = []
                for si in shop_items:
                    if not si.get("is_stocked"):
                        continue
                    cat = si.get("category", "")
                    cost = si.get("cost", "?")
                    if cat == "card":
                        name = si.get("card_name", "?")
                        hint = CARD_DICT.get(name, si.get("card_description", "")[:30])
                        sale = " 🏷折扣" if si.get("on_sale") else ""
                        items.append(f"  牌·{name}（{cost}金{sale}）：{hint}")
                    elif cat == "relic":
                        items.append(f"  遗物·{si.get('relic_name','?')}（{cost}金）：{si.get('relic_description','')[:30]}")
                    elif cat == "potion":
                        items.append(f"  药水·{si.get('potion_name','?')}（{cost}金）")
                    elif cat == "purge":
                        items.append(f"  删牌服务（{cost}金）")
                items_str = chr(10).join(items) or '（无物品）'
                prompt = f"""杀戮尖塔2商店建议，纯文字不用markdown。所有牌名遗物名用中文。

金币：{player.get('gold')}  HP：{player.get('hp')}/{player.get('max_hp')}（{hp_pct}%）  幕{run.get('act')}
{'已选牌：'+', '.join(self.deck_acquired) if self.deck_acquired else '初始牌组'}

商店物品：
{items_str}

给出建议：优先买什么，哪些不值得。格式：
推荐购买：（列出物品及理由）
可以考虑：（性价比分析）
跳过：（不值得的原因）
删牌建议：（如果有删牌服务）"""
                advice = self._ask_llm(prompt)
                if not self._analysis_stale():
                    advice_html = self._render_formatted_html(advice)
                    self._js(f'app.updateAdvice({json.dumps(advice_html)})')
                    self._js('app.setTab("situation")')
                return
            else:  # treasure
                prompt = f"杀戮尖塔2宝箱，直接拿。HP：{player.get('hp')}/{player.get('max_hp')}，幕{run.get('act')}·层{run.get('floor')}。一句话说说拿到宝箱对当前局面的影响。"

            advice = self._ask_llm(prompt)
            if not self._analysis_stale():
                advice_html = self._render_formatted_html(advice)
                self._js(f'app.updateAdvice({json.dumps(advice_html)})')
                self._js('app.setTab("situation")')
        except Exception as e:
            if not self._analysis_stale():
                self._js(f'app.updateAdvice({json.dumps(_html.escape(f"⚠ {e}"))})')
        finally:
            self._busy_strat = False

    def _initial_analysis(self, state):
        """首次连接时自动分析角色和流派方向。"""
        self._busy_strat = True
        try:
            # 等 API 稳定再重新抓完整状态
            time.sleep(2)
            try:
                fresh = requests.get(API_URL, timeout=5).json()
                if fresh.get("state_type") not in ("unknown", "menu", None):
                    state = fresh
            except Exception:
                pass

            player = self._get_player(state)
            run    = state.get("run", {})
            # 如果仍然没有 player 数据，跳过分析
            if not player or not player.get("character"):
                self._js(f'app.updateDeckAnalysis({json.dumps("  等待游戏数据…")})')
                return
            relics  = ", ".join(r["name"] for r in player.get("relics", [])) or "无"
            potions = ", ".join(p["name"] for p in player.get("potions", [])) or "无"
            deck_info = f"已选牌：{', '.join(self.deck_acquired)}" if self.deck_acquired else "初始牌组"
            removed   = f"已移除：{', '.join(self.deck_removed)}" if self.deck_removed else ""
            arch      = f"上次流派：{self._deck_archetype}" if self._deck_archetype else ""

            # 遗物详细描述
            relic_details = "\n".join(
                f"  · {r['name']}：{r.get('description','')[:50]}"
                for r in player.get("relics", [])) or "  无"

            char = player.get('character', '?')
            # 角色知识库
            char_info = {
                "静默猎手": "核心机制：毒素叠加+弃牌流+灵活性。常见流派：毒素流（恶毒+催化剂+致死毒药）、弃牌流（暗器+专注+工具箱）、小刀/旋转流（无限刀+剑柄打击循环）、灵活过牌流。初始牌组含打击×5/防御×5/幸存者×1/中和×1。",
                "铁甲战士": "核心机制：力量叠加+重击+自伤流。常见流派：力量流（恶魔形态+重击）、格挡流（铁壁+金属化）、消耗流（感染+燃烧）。初始含打击×5/防御×4/猛击×1。",
                "缺陷体": "核心机制：充能球（闪电/冰霜/黑暗/等离子）+专注力。常见流派：闪电流、冰霜堆叠流、黑暗流、全球混合流。",
            }
            char_desc = char_info.get(char, f"未知角色（{char}），请根据遗物和已选牌推断流派。")

            # 获取历史教训 + 玩家趋势
            lessons = self._get_relevant_lessons(char)
            trend = self._get_player_trend()

            prompt = f"""你是杀戮尖塔2（Slay the Spire 2）专家教练。纯文字，不用markdown。所有牌名遗物名用中文。

这是一款roguelike卡牌游戏，玩家每局随机构建卡组，通过3幕关卡击败Boss通关。

角色知识：{char_desc}
{lessons}
{trend}

当前状态：
角色：{char}  HP：{player.get('hp')}/{player.get('max_hp')}  金币：{player.get('gold', 0)}
幕{run.get('act')}·层{run.get('floor')}  飞升：{run.get('ascension', 0)}

遗物（每个遗物都有被动效果）：
{relic_details}

药水：{potions}
{deck_info}  {removed}
{arch}

请给出开局方向分析（每项一行）：
角色优势：（这个角色最强的机制是什么）
遗物协同：（现有遗物配合什么流派最好）
期望成型：（最优流派目标）
核心需求：（接下来最需要找什么牌/遗物）
风险提示：（当前需要注意什么）"""

            result = self._ask_llm(prompt)
            result_html = self._render_formatted_html(result, header="── 开局分析 ──────────────────────────")
            self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')

            # 提取流派
            for line in result.split("\n"):
                if "期望成型" in line:
                    self._deck_archetype = line.split("：", 1)[-1].strip() if "：" in line else ""
                    if self._deck_archetype:
                        self._save_archetype()
                    break
        except Exception as e:
            self._js(f'app.updateDeckAnalysis({json.dumps(_html.escape(f"⚠ 开局分析失败：{e}"))})')
        finally:
            self._busy_strat = False

    def _refresh_deck_box(self):
        """Update deck building box with current archetype assessment."""
        if not self.deck_acquired and not self.deck_removed:
            return
        if self._busy_deck:
            return
        self._busy_deck = True
        def run():
            try:
                p   = self.last_player
                run = self.last_run
                deck = ', '.join(self.deck_acquired) or '初始牌组'
                rmv  = ', '.join(self.deck_removed)  or '无'
                prompt = f"""杀戮尖塔2卡组方向分析，纯文字不用markdown，所有牌名遗物名用中文，按格式输出。

{p.get('character','?')}  幕{run.get('act','?')}  遗物：{', '.join(r['name'] for r in p.get('relics',[]))}
已选牌（本局新增）：{deck}
已移除：{rmv}

格式：
流派判断：（当前最接近哪种流派）
最优方向：（继续发展这个方向需要什么）
次优方向：（备用路线）
当前缺口：（最需要哪类牌/遗物）"""
                result = self._ask_llm(prompt)
                full_text = (f"── 已选牌 ────────────────────────────\n"
                             f"{', '.join(self.deck_acquired)}\n\n"
                             f"── 方向分析 ──────────────────────────\n"
                             + result)
                result_html = self._render_formatted_html(full_text)
                self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')
            except Exception:
                pass
            finally:
                self._busy_deck = False
        threading.Thread(target=run, daemon=True).start()

    def _do_deck_strategy(self):
        """分析当前牌组的流派方向、强度、未来选牌策略。"""
        try:
            state = self.last_state or {}
            player = self._get_player(state) or self.last_player
            run = state.get("run") or self.last_run or {}
            char = player.get("character", "?")

            relics = ", ".join(r["name"] for r in player.get("relics", [])) or "无"
            deck_info = ", ".join(self.deck_acquired) if self.deck_acquired else "初始牌组"
            removed = ", ".join(self.deck_removed) if self.deck_removed else "无"
            current_arch = self._deck_archetype or "未确定"

            # 智能上下文构建（0 token查表）
            smart_ctx = self._build_context("deck")

            # 历史教训
            lessons = self._get_relevant_lessons(char)
            trend = self._get_player_trend()

            # 本局路线摘要
            route_summary = []
            for entry in self._run_replay[-10:]:  # 最近10个事件
                if entry.get("type") in ("card_reward", "card_select"):
                    opts = ", ".join(entry.get("options", []))
                    chosen = entry.get("chosen", "?")
                    route_summary.append(f"第{entry.get('floor','')}层选牌: [{opts}] → {chosen}")
                elif entry.get("type") == "combat":
                    enemies = ", ".join(entry.get("enemies", []))
                    hp_loss = entry.get("start_hp",0) - entry.get("end_hp",0)
                    route_summary.append(f"第{entry.get('floor','')}层战斗 vs {enemies} (损{hp_loss}HP)")
            route_text = "\n".join(route_summary) if route_summary else "刚开局"

            prompt = f"""你是杀戮尖塔2卡组构建顾问。纯文字，不用markdown符号。所有牌名遗物名用中文。简洁扼要。
【重要】所有牌名/遗物名必须用中文，禁止输出英文ID。

{smart_ctx}
{lessons}
{trend}

{char} HP{player.get('hp')}/{player.get('max_hp')} 金{player.get('gold',0)} 幕{run.get('act')}层{run.get('floor')} A{run.get('ascension',0)}
遗物：{relics}
已选牌：{deck_info}
已移除：{removed}
当前流派：{current_arch}
路线：{route_text}

简洁输出，每项1-2句。牌名后标✓已有 ✗缺少：

流派：走什么方向
核心牌：该流派的核心牌清单（每张标✓或✗）
辅助牌：协同辅助牌清单（每张标✓或✗），简述与核心牌的联动效果
过渡牌：当前牌组中不属于流派但暂时有用的牌，以及何时该替换
组合技：目前已有的或即将成型的关键combo，简述机制
强度：当前完成度（X/Y核心到位），缺什么关键拼图
找牌：下次优先拿什么（按优先级排序）
避雷：不拿什么，为什么
打法：当前牌组怎么打（简述回合套路）"""

            result = self._ask_llm(prompt)
            result_html = self._render_formatted_html(result)
            self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')

            # 保存分析文本到实例变量（供 session 持久化使用）
            self._deck_analysis_text = result

            # 更新流派判断（从AI回复中提取）
            if "流派" in result and not self._deck_archetype:
                # 从 archetype_matrix 获取当前角色的流派列表
                _char_archetypes = []
                if hasattr(self, '_matrix') and self._matrix:
                    _char_data = self._matrix.get("characters", {}).get(char, {})
                    _char_archetypes = [{"name": k} for k in _char_data.get("archetypes", {}).keys()]
                for a in _char_archetypes:
                    if a["name"] in result:
                        self._deck_archetype = a["name"]
                        self._save_archetype()
                        break

            # 保存 session（用户主动分析后持久化）
            self._save_session()

        except Exception as e:
            self._js(f'app.updateDeckAnalysis({json.dumps(_html.escape(f"⚠ 分析失败：{e}"))})')
        finally:
            self._js('app.setButtonState("btn-deck", "◆  求策·卡组  ◆", false)')

    def _do_freeform_ask(self, question):
        """自由提问：带上当前完整游戏状态，让 AI 回答玩家的任何问题。"""
        try:
            # 重新抓最新状态
            try:
                state = requests.get(API_URL, timeout=5).json()
            except Exception:
                state = self.last_state or {}

            player = self._get_player(state)
            run    = state.get("run", {})
            stype  = state.get("state_type", "")

            # 构建状态摘要
            ctx_parts = [
                f"角色：{player.get('character','?')}  HP：{player.get('hp','?')}/{player.get('max_hp','?')}  金币：{player.get('gold','?')}",
                f"幕{run.get('act','?')}·层{run.get('floor','?')}  当前状态：{stype}",
                f"遗物：{', '.join(r['name'] for r in player.get('relics', [])) or '无'}",
                f"药水：{', '.join(p['name'] for p in player.get('potions', [])) or '无'}",
            ]
            if self.deck_acquired:
                ctx_parts.append(f"已选牌：{', '.join(self.deck_acquired)}")
            if self._deck_archetype:
                ctx_parts.append(f"流派方向：{self._deck_archetype}")

            # 战斗中额外加手牌和敌人信息
            if stype in ("monster", "elite", "boss"):
                battle = state.get("battle", {})
                hand = battle.get("player", {}).get("hand", [])
                enemies = battle.get("enemies", [])
                if hand:
                    hand_str = ", ".join(f"{c['name']}(费{c.get('cost','?')})" for c in hand)
                    ctx_parts.append(f"手牌：{hand_str}")
                    ctx_parts.append(f"能量：{battle.get('player',{}).get('energy','?')}/{battle.get('player',{}).get('max_energy','?')}")
                if enemies:
                    for e in enemies:
                        intent = self._fmt_intent(e.get("intents", []))
                        ctx_parts.append(f"敌人：{e['name']} HP:{e.get('hp','?')}/{e.get('max_hp','?')} 意图:{intent}")

            ctx = "\n".join(ctx_parts)

            # 获取角色策略知识
            char = player.get('character', '?')
            char_db = STRATEGY_DB.get(char, {})
            all_strat = "\n".join(v for v in char_db.values())

            prompt = f"""你是杀戮尖塔2专家教练。纯文字回答，不用markdown符号。

角色策略知识：
{all_strat or COMBAT_BASICS}

当前游戏状态：
{ctx}

玩家的问题：{question}

请结合策略知识和当前游戏状态给出针对性的回答。简洁实用。"""

            answer = self._ask_llm(prompt)
            full_text = (f"── 提问 ──────────────────────────────\n"
                         f"❓ {question}\n\n{answer}")
            answer_html = self._render_formatted_html(full_text)
            self._js(f'app.updateScene({{type:"html",html:{json.dumps(answer_html)}}})')
            self._js('app.setTab("situation")')
        except Exception as e:
            self._js(f'app.updateScene({{type:"html",html:{json.dumps(_html.escape(f"⚠ 提问失败：{e}"))}}})')
        finally:
            self._js('app.setButtonState("btn-situation", "◆  求策·当前形势  ◆", false)')
