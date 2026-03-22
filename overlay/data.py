"""DataMixin — 数据加载、卡牌DB、知识库、存档读取、session管理。

修改数据加载逻辑只需编辑此文件。
"""
import json
import os
import threading
from datetime import datetime

from overlay.constants import (
    CARD_DICT, CARD_DB_FILE, CARD_DB_FULL, CARD_DICT_FILE,
    EPOCHS_FILE, ARCHETYPES_FILE, MONSTER_AI_FILE, EVENT_GUIDE_FILE,
    POTION_GUIDE_FILE, RELIC_COMBAT_FILE, CARD_TIER_FILE, MATRIX_FILE,
    SYNERGY_FILE, PIVOT_FILE, BOSS_FILE, HISTORY_FILE, SESSION_FILE,
    PROGRESS_FILE, _proj,
)


class DataMixin:

    # ══════════════════════════════════════════
    #  SESSION PERSISTENCE（同局恢复）
    # ══════════════════════════════════════════
    def _make_run_id(self):
        """生成当前局的唯一标识符。"""
        p    = self.last_player or {}
        run  = self.last_run or {}
        char = p.get("character", "?")
        act  = run.get("act", "?")
        # 用角色名 + 已选牌前3张 组合作为稳定 ID（不依赖楼层，避免进度误判）
        deck_sig = "|".join(sorted(self.deck_acquired[:5])) if self.deck_acquired else "init"
        return f"{char}::{deck_sig}"

    def _save_session(self):
        """保存当前局状态到 session.json。"""
        try:
            os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
            p    = self.last_player or {}
            run  = self.last_run or {}
            data = {
                "run_id":            self._make_run_id(),
                "character":         p.get("character", ""),
                "act":               run.get("act", ""),
                "floor":             run.get("floor", ""),
                "archetype":         self._deck_archetype,
                "deck_acquired":     list(self.deck_acquired),
                "deck_removed":      list(self.deck_removed),
                "deck_analysis_text": self._deck_analysis_text,
                "run_log":           list(self.run_log),
                "run_replay":        list(self._run_replay),
                "battle_log":        list(self._battle_log),
                "saved_at":          datetime.now().isoformat(),
            }
            with open(SESSION_FILE, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Session] Save failed: {e}")

    def _load_session(self):
        """启动时尝试恢复同局 session。"""
        try:
            if not os.path.exists(SESSION_FILE):
                return
            with open(SESSION_FILE) as f:
                data = json.load(f)
            if not data:
                return

            saved_char     = data.get("character", "")
            saved_acquired = data.get("deck_acquired", [])
            saved_run_id   = data.get("run_id", "")

            # 用 archetype.json 里的角色+牌组来判断是否同一局
            arch_char = ""
            arch_deck = []
            if os.path.exists(self.ARCHETYPE_FILE):
                try:
                    with open(self.ARCHETYPE_FILE) as f:
                        arch_data = json.load(f)
                    arch_char = arch_data.get("character", "")
                    arch_deck = arch_data.get("deck", [])
                except Exception:
                    pass

            # 判断是否同一局：角色名匹配 + 已选牌集合高度重叠
            def is_same_run():
                if not saved_char:
                    return False
                # 如果 archetype.json 有角色，用它对比
                if arch_char and arch_char != saved_char:
                    return False
                if arch_deck and saved_acquired:
                    # 已选牌至少有 50% 匹配
                    overlap = len(set(arch_deck) & set(saved_acquired))
                    if overlap == 0 and len(saved_acquired) > 2:
                        return False
                return True

            if not is_same_run():
                print(f"[Session] Different run detected, skipping restore "
                      f"(saved={saved_char}, arch={arch_char})")
                return

            # 恢复所有状态
            self.deck_acquired       = saved_acquired
            self.deck_removed        = data.get("deck_removed", [])
            self._deck_archetype     = data.get("archetype", "")
            self._deck_analysis_text = data.get("deck_analysis_text", "")
            self.run_log             = data.get("run_log", [])
            self._run_replay         = data.get("run_replay", [])
            self._battle_log         = data.get("battle_log", [])

            print(f"[Session] Restored: {saved_char}, "
                  f"{len(self.deck_acquired)} cards, "
                  f"{len(self.run_log)} log entries")

            # 恢复 UI（延迟执行，等窗口 ready）
            def _restore_ui():
                if self.deck_acquired or self.deck_removed:
                    self._display_deck_list()
                if self._deck_analysis_text:
                    result_html = self._render_formatted_html(self._deck_analysis_text)
                    self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')
                else:
                    self._js(f'app.updateDeckAnalysis({json.dumps("  点击「求策·卡组」获取AI分析")})')
                if self.run_log:
                    self._refresh_log()

            threading.Timer(0.5, _restore_ui).start()

        except Exception as e:
            print(f"[Session] Load failed: {e}")

    def _load_history(self):
        """加载历史，在日志标签页底部展示最近几局（timeline-item 格式）。"""
        try:
            if not os.path.exists(HISTORY_FILE):
                return
            with open(HISTORY_FILE) as f:
                history = json.load(f)
            if not history:
                return
            import html as _html
            tl_parts = []
            tl_parts.append(
                '<div class="timeline-item">'
                '<span class="tl-turn"></span>'
                '<span class="tl-dot" style="background:var(--gold);"></span>'
                '<span class="tl-text" style="color:var(--gold);font-weight:600;">历史对局</span>'
                '</div>'
            )
            for rec in reversed(history[-5:]):
                hp = rec.get("hp", "?")
                gold = rec.get("gold", "?")
                char = _html.escape(str(rec.get("character", "?")))
                act = rec.get("act", "?")
                floor = rec.get("floor", "?")
                date = _html.escape(str(rec.get("date", "")))
                deck_str = ""
                if rec.get("deck"):
                    cards = ", ".join(_html.escape(c) for c in rec["deck"][:8])
                    deck_str = f' <span class="dim">&middot; 新增: {cards}</span>'
                tl_parts.append(
                    f'<div class="timeline-item">'
                    f'<span class="tl-turn">楼层 {floor}</span>'
                    f'<span class="tl-dot" style="background:var(--accent);"></span>'
                    f'<span class="tl-text">{char} 幕{act} '
                    f'<span class="dim">HP:{hp} 金:{gold}</span> '
                    f'<span class="dim">{date}</span>{deck_str}</span>'
                    f'</div>'
                )
            # Don't push past sessions to timeline — it should show current run only
            # log_html = "".join(tl_parts)
            # threading.Timer(0.1, lambda: self._js(f'app.updateLogTimeline({json.dumps(log_html)})')).start()
            pass
        except Exception:
            pass

    # ══════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════
    def _display_deck_list(self):
        """deck-grid 卡牌网格显示（匹配 royal_purple 参考 HTML）。"""
        import html as _html

        # 优先从 API 获取完整牌组
        api_deck = []
        state = self.last_state or {}
        player = self._get_player(state) or self.last_player or {}
        api_deck = player.get("deck", [])

        # 如果 API 无 deck，从存档读取
        if not api_deck:
            _, save_deck = self._load_save_data()
            api_deck = save_deck or []

        def fmt_card_name(c):
            """获取卡牌中文名/显示名。"""
            if c.get("name"):
                return c["name"]
            cid = c.get("id", "?").replace("CARD.", "")
            if hasattr(self, '_card_id_map') and cid in self._card_id_map:
                return self._card_id_map[cid]
            if hasattr(self, '_card_db') and cid in self._card_db:
                return self._card_db[cid].get("name", cid)
            return cid.replace("_", " ").title()

        def get_card_type(c):
            """获取卡牌类型（attack/skill/power/curse/status）。"""
            t = (c.get("type") or c.get("card_type") or "").lower()
            if not t and hasattr(self, '_card_db'):
                cid = c.get("id", "").replace("CARD.", "")
                t = self._card_db.get(cid, {}).get("type", "").lower()
            if "attack" in t:   return "attack"
            if "skill" in t:    return "skill"
            if "power" in t:    return "power"
            if "curse" in t:    return "curse"
            if "status" in t:   return "status"
            return "other"

        def get_card_rarity(c):
            """获取卡牌稀有度。"""
            r = (c.get("rarity") or "").lower()
            if not r and hasattr(self, '_card_db'):
                cid = c.get("id", "").replace("CARD.", "")
                r = self._card_db.get(cid, {}).get("rarity", "").lower()
            # Try merged card DB for rarity
            if not r and hasattr(self, '_card_rarity_map'):
                name = c.get("name", "")
                r = self._card_rarity_map.get(name, "").lower()
            # Basic cards fallback
            if not r:
                name = c.get("name", "")
                cid = c.get("id", "")
                if name in _BASIC_CARDS or "STRIKE" in cid.upper() or "DEFEND" in cid.upper():
                    r = "basic"
            return r

        TYPE_CN = {"attack": "攻击", "skill": "技能", "power": "能力",
                   "curse": "诅咒", "status": "状态", "other": "其他"}
        RARITY_CN = {"basic": "基础", "common": "普通", "uncommon": "罕见",
                     "rare": "稀有"}
        _BASIC_CARDS = {"打击", "防御", "Strike", "Defend"}

        if api_deck:
            total = len(api_deck)
            # Only show archetype if player has picked cards (not initial deck)
            arch_label = ""
            if self._deck_archetype and self.deck_acquired:
                arch_label = _html.escape(self._deck_archetype)
            if arch_label:
                title = f'卡组一览 — {arch_label} ({total}张)'
            else:
                title = f'卡组一览 ({total}张)'

            # Group cards by type
            TYPE_ORDER = ["attack", "skill", "power", "curse", "status", "other"]
            TYPE_LABEL_COLOR = {
                "attack": ("攻击", "var(--hp)"),
                "skill": ("技能", "var(--block)"),
                "power": ("能力", "var(--buff)"),
                "curse": ("诅咒", "var(--debuff)"),
                "status": ("状态", "var(--dim)"),
                "other": ("其他", "var(--dim)"),
            }
            grouped = {}
            for c in api_deck:
                ct = get_card_type(c)
                grouped.setdefault(ct, []).append(c)

            html_parts = [f'<div class="section-title">{title}</div>']

            for ct in TYPE_ORDER:
                cards_in_type = grouped.get(ct, [])
                if not cards_in_type:
                    continue
                label, color = TYPE_LABEL_COLOR.get(ct, ("其他", "var(--dim)"))
                html_parts.append(f'<div style="font-size:11px;color:{color};font-weight:600;margin:8px 0 4px;">{label} ({len(cards_in_type)})</div>')
                html_parts.append('<div class="deck-grid">')

                for c in cards_in_type:
                    name = fmt_card_name(c)
                    is_upgraded = bool(c.get("is_upgraded") or c.get("upgraded") or c.get("upgrades", 0) > 0)
                    rarity = get_card_rarity(c)

                    display_name = _html.escape(name + ("+" if is_upgraded else ""))

                    # Card name color by rarity — matches in-game border colors
                    RARITY_COLOR = {
                        "basic": "var(--dim)",       # gray, unimportant
                        "common": "var(--text)",     # white/default
                        "uncommon": "var(--block)",  # blue
                        "rare": "var(--gold)",       # gold
                    }
                    UPGRADED_COLOR = "var(--buff)"   # green
                    if is_upgraded:
                        name_style = f' style="color:{UPGRADED_COLOR};"'
                    elif rarity in RARITY_COLOR:
                        name_style = f' style="color:{RARITY_COLOR[rarity]};"'
                    else:
                        name_style = ''

                    cost = c.get("cost")
                    if cost is None and hasattr(self, '_card_db'):
                        cid = c.get("id", "").replace("CARD.", "")
                        db_entry = self._card_db.get(cid, {})
                        cost = db_entry.get("cost", "?")
                    elif cost is None:
                        cost = "?"

                    if is_upgraded:
                        rarity_text = "已升级"
                    else:
                        rarity_text = RARITY_CN.get(rarity, rarity if rarity else "普通")

                    # Get description for hover
                    desc = c.get("description", "")
                    if not desc:
                        cid_d = c.get("id", "").replace("CARD.", "")
                        desc = self._card_db.get(cid_d, {}).get("description", "")
                    if not desc:
                        from overlay.constants import CARD_DICT
                        desc = CARD_DICT.get(name, "")

                    # Single line: name + cost. Hover shows desc via CSS tooltip
                    desc_attr = f' data-desc="{_html.escape(desc)}"' if desc else ""
                    html_parts.append(
                        f'<div class="deck-card"{desc_attr}>'
                        f'<span class="dc-name"{name_style}>{display_name}</span>'
                        f' <span style="color:var(--gold);font-size:10px">{cost}费</span>'
                        f'</div>'
                    )

                html_parts.append('</div>')

            deck_html = "".join(html_parts)
            self._js(f'app.updateDeckList({json.dumps(deck_html)})')
            return

        # 无牌组数据时，显示 deck_acquired/removed 摘要
        if self.deck_acquired or self.deck_removed:
            total = len(self.deck_acquired)
            arch_label = _html.escape(self._deck_archetype) if self._deck_archetype else ""
            if arch_label:
                title = f'卡组一览 — {arch_label} ({total}张新增)'
            else:
                title = f'卡组一览 ({total}张新增)'
            html_parts = [f'<div class="section-title">{title}</div>']
            html_parts.append('<div class="deck-grid">')
            for card_name in self.deck_acquired:
                is_upgraded = card_name.endswith("+")
                raw_name = card_name.rstrip("+")
                display_name = _html.escape(card_name)
                if is_upgraded:
                    name_style = ' style="color:var(--gold);"'
                else:
                    name_style = ''
                html_parts.append(
                    f'<div class="deck-card">'
                    f'<div class="dc-name"{name_style}>{display_name}</div>'
                    f'<div class="dc-type">新增</div>'
                    f'</div>'
                )
            for card_name in self.deck_removed:
                html_parts.append(
                    f'<div class="deck-card">'
                    f'<div class="dc-name" style="color:var(--hp);text-decoration:line-through;">{_html.escape(card_name)}</div>'
                    f'<div class="dc-type">已移除</div>'
                    f'</div>'
                )
            html_parts.append('</div>')
            deck_html = "".join(html_parts)
            self._js(f'app.updateDeckList({json.dumps(deck_html)})')
        else:
            self._js(f'app.updateDeckList({json.dumps("  等待游戏数据…")})')

    # ══════════════════════════════════════════
    #  CARD DATABASE (auto-collector, 0 token)
    # ══════════════════════════════════════════
    def _load_card_db(self):
        try:
            if os.path.exists(CARD_DB_FILE):
                with open(CARD_DB_FILE) as f:
                    self._card_db = json.load(f)
            else:
                self._card_db = {}
        except Exception:
            self._card_db = {}
        # Load merged card DB for rarity info
        self._card_rarity_map = {}
        try:
            merged = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "data", "cards", "card_database_merged.json")
            if os.path.exists(merged):
                with open(merged) as f:
                    mdb = json.load(f)
                for k, v in mdb.items():
                    cn_name = v.get("name_cn", "")
                    if cn_name:
                        self._card_rarity_map[cn_name] = v.get("rarity", "")
        except Exception:
            pass
        # 加载精确数值的 card_dict（反编译数据）
        try:
            if os.path.exists(CARD_DICT_FILE):
                with open(CARD_DICT_FILE) as f:
                    precise = json.load(f)
                for name, desc in precise.items():
                    if name not in CARD_DICT or len(desc) > len(CARD_DICT.get(name, "")):
                        CARD_DICT[name] = desc
                print(f"[CardDB] Loaded {len(precise)} cards from decompiled data")
        except Exception as e:
            print(f"[CardDB] Failed to load card_dict: {e}")
        # 补充未命中的从翻译文件加载
        try:
            if os.path.exists(CARD_DB_FULL):
                with open(CARD_DB_FULL) as f:
                    full = json.load(f)
                added = 0
                for cid, info in full.items():
                    name = info.get("name", "")
                    if name and name not in CARD_DICT:
                        desc = info.get("description", "")[:35]
                        CARD_DICT[name] = desc
                        added += 1
                if added:
                    print(f"[CardDB] Added {added} extra cards from translations")
        except Exception:
            pass
        # 构建 card_id → 中文名 映射（从character_cards.json）
        self._card_id_map = {}
        try:
            cc_file = _proj("data", "cards", "character_cards.json")
            if os.path.exists(cc_file):
                with open(cc_file) as f:
                    cc = json.load(f)
                import re
                for char_name, cards in cc.items():
                    if isinstance(cards, list):
                        for card in cards:
                            cid = card.get("id", "")
                            name = card.get("name", "")
                            if cid and name:
                                self._card_id_map[cid] = name
                                self._card_id_map[cid.upper()] = name
                                # PascalCase→UPPER_SNAKE: NoEscape → NO_ESCAPE
                                snake = re.sub(r'(?<=[a-z])(?=[A-Z])', '_', cid).upper()
                                self._card_id_map[snake] = name
                                # 也加到 _card_db（带cost/type）供卡组显示用
                                for key in (cid, cid.upper(), snake):
                                    if key not in self._card_db:
                                        self._card_db[key] = {
                                            "name": name,
                                            "cost": card.get("cost", "?"),
                                            "type": card.get("type", ""),
                                        }
                print(f"[CardDB] Built id→name map: {len(self._card_id_map)} entries")
        except Exception:
            pass

    def _save_card_db(self):
        try:
            with open(CARD_DB_FILE, "w") as f:
                json.dump(self._card_db, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_unlock_state(self):
        """从存档读取解锁状态。"""
        self._unlocked_cards = set()
        self._unlocked_relics = set()
        self._unlocked_epochs = set()
        self._locked_epoch_cards = set()
        self._char_ascension = {}
        try:
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE) as f:
                    prog = json.load(f)
                self._unlocked_cards = set(prog.get("discovered_cards", []))
                self._unlocked_relics = set(prog.get("discovered_relics", []))
                self._unlocked_epochs = {e["id"] for e in prog.get("epochs", []) if e["state"] == "revealed"}
                for cs in prog.get("character_stats", []):
                    self._char_ascension[cs["id"]] = cs.get("max_ascension", 0)
                # 解析锁定纪元的牌
                if os.path.exists(EPOCHS_FILE):
                    with open(EPOCHS_FILE) as f:
                        epochs = json.load(f)
                    for eid, data in epochs.items():
                        if eid not in self._unlocked_epochs:
                            for c in data.get("cards", []):
                                self._locked_epoch_cards.add(c["id"])
                print(f"[Unlock] {len(self._unlocked_cards)} cards, {len(self._unlocked_relics)} relics, asc={self._char_ascension}")
        except Exception as e:
            print(f"[Unlock] Failed: {e}")

    def _load_knowledge(self):
        """加载知识库。"""
        self._monster_ai = {}
        self._archetypes = {}
        self._lessons = []
        self._event_guide = {}
        self._potion_guide = {}
        self._relic_combat = {}
        self._card_tiers = {}

        # 加载所有知识文件
        self._matrix = {}
        self._synergy_index = {}
        self._pivot_rules = {}
        self._boss_guide = {}
        for fpath, attr, label in [
            (MONSTER_AI_FILE, "_monster_ai", "Monster AI"),
            (ARCHETYPES_FILE, "_archetypes", "Archetype matrix"),
            (SYNERGY_FILE, "_synergy_index", "Card synergy index"),
            (PIVOT_FILE, "_pivot_rules", "Relic pivot rules"),
            (BOSS_FILE, "_boss_guide", "Boss counter guide"),
            (EVENT_GUIDE_FILE, "_event_guide", "Event guide"),
            (POTION_GUIDE_FILE, "_potion_guide", "Potion guide"),
            (RELIC_COMBAT_FILE, "_relic_combat", "Relic combat values"),
            (CARD_TIER_FILE, "_card_tiers", "Card tier list"),
        ]:
            try:
                if os.path.exists(fpath):
                    with open(fpath) as f:
                        setattr(self, attr, json.load(f))
                    sz = os.path.getsize(fpath)
                    print(f"[Knowledge] {label} loaded ({sz/1024:.0f}KB)")
            except Exception as e:
                print(f"[Knowledge] {label} failed: {e}")
        # _matrix和_archetypes现在是同一个文件(archetype_matrix.json)
        if self._archetypes and not self._matrix:
            self._matrix = self._archetypes
        # 加载历史教训
        lessons_file = os.path.expanduser("~/Projects/sts2/knowledge/lessons.json")
        try:
            if os.path.exists(lessons_file):
                with open(lessons_file) as f:
                    self._lessons = json.load(f)
                print(f"[Knowledge] {len(self._lessons)} post-run lessons loaded")
        except Exception:
            pass

    def _get_relevant_lessons(self, char, max_lessons=3):
        """获取与当前角色相关的最近教训。"""
        relevant = [l for l in self._lessons if l.get("character") == char]
        # 最近的优先
        recent = relevant[-max_lessons:] if relevant else []
        if not recent:
            return ""
        parts = ["历史教训（过往局复盘）："]
        for l in recent:
            if l.get('result') and l.get('review'):
                parts.append(f"  {l['result']} ({l.get('archetype','')}) → {l['review'][:80]}")
            elif l.get('lesson'):
                parts.append(f"  {l['lesson'][:100]}")
        return "\n".join(parts)

    def _get_player_trend(self):
        """获取最新的跨局趋势分析。"""
        profile_file = os.path.expanduser("~/Projects/sts2/knowledge/player_profile.json")
        try:
            if os.path.exists(profile_file):
                with open(profile_file) as f:
                    profile = json.load(f)
                trend = profile.get("latest_trend", "")
                if trend:
                    return f"玩家近期趋势：{trend[:120]}"
        except Exception:
            pass
        return ""

    def _collect_cards(self, state):
        """从 API 状态中静默收集卡牌信息。"""
        changed = False
        sources = []

        # 手牌
        battle = state.get("battle", {})
        if battle:
            sources.extend(battle.get("player", {}).get("hand", []))

        # 选牌奖励
        cr = state.get("card_reward") or state.get("card_select") or {}
        sources.extend(cr.get("cards", []))

        # 商店
        shop = state.get("shop", {})
        sources.extend(shop.get("cards", []))

        for c in sources:
            cid = c.get("id") or c.get("name", "")
            if not cid or cid in self._card_db:
                continue
            entry = {
                "name": c.get("name", ""),
                "type": c.get("type", ""),
                "cost": c.get("cost", "?"),
                "description": c.get("description", ""),
                "keywords": [k.get("name", "") for k in c.get("keywords", [])],
            }
            self._card_db[cid] = entry
            changed = True
            # 同时更新 CARD_DICT
            name = c.get("name", "")
            if name and name not in CARD_DICT:
                desc = c.get("description", "")[:30].replace("\n", " ")
                CARD_DICT[name] = desc

        if changed:
            self._save_card_db()

    def _load_save_data(self):
        """从存档文件读取玩家数据（character, HP, gold, deck）。
        返回 (player_dict, deck_list) 其中 deck_list 是 [{id, floor}, ...] 格式。
        """
        from overlay.constants import _SAVE_BASE
        save_paths = []
        if _SAVE_BASE:
            save_paths.append(os.path.join(_SAVE_BASE, "modded/profile1/saves/current_run.save"))
            save_paths.append(os.path.join(_SAVE_BASE, "profile1/saves/current_run.save"))
        for path in save_paths:
            if not os.path.exists(path):
                continue
            try:
                with open(path) as f:
                    data = json.load(f)
                players = data.get("players", [])
                if not players:
                    continue
                p = players[0]
                char_id = p.get("character_id", "")
                _CHAR_CN = {
                    "CHARACTER.IRONCLAD": "铁甲战士", "CHARACTER.SILENT": "静默猎手",
                    "CHARACTER.DEFECT": "缺陷体", "CHARACTER.REGENT": "储君",
                    "CHARACTER.NECROBINDER": "亡灵契约师",
                }
                char_name = _CHAR_CN.get(char_id, char_id.replace("CHARACTER.", "")) if char_id else "—"
                player_dict = {
                    "character": char_name,
                    "hp":        p.get("current_hp", 0),
                    "max_hp":    p.get("max_hp", 80),
                    "gold":      p.get("gold", 0),
                    "energy":    p.get("max_energy", 3),
                    "max_energy": p.get("max_energy", 3),
                    "block":     0,
                    "relics":    [{"name": r.get("id", "?").replace("RELIC.", "")} for r in p.get("relics", [])],
                }
                deck_list = p.get("deck", [])
                return player_dict, deck_list
            except Exception as e:
                print(f"[SaveLoad] {e}")
        return {}, []

    def _get_player(self, state):
        return (state.get("battle", {}).get("player") or
                state.get("event", {}).get("player") or
                state.get("map", {}).get("player") or
                state.get("rest_site", state.get("rest", {})).get("player") or
                state.get("shop", {}).get("player") or
                state.get("rewards", {}).get("player") or
                state.get("card_reward", {}).get("player") or
                state.get("card_select", {}).get("player") or
                state.get("treasure", {}).get("player") or
                state.get("player") or {})
