"""DisplayMixin — 所有自动显示方法（不调用LLM）。

修改UI格式只需编辑此文件。
pywebview v6.0 — builds HTML strings and pushes via JS.
"""
import html
import json
import re as _re
import requests
from overlay.constants import (
    API_URL, CARD_DICT, INTENT_CN,
    _cn_power, _cn_relic, _cn_potion,
)


class DisplayMixin:

    def _colorize_desc(self, text):
        """Scan description text and wrap game-relevant terms in colored spans."""
        escaped = html.escape(text)
        # Gold/currency: 150金币, 50 金, 100金
        escaped = _re.sub(r'(\d+)\s*(?:点)?(金币|金(?!色))', r'<span style="color:var(--gold);font-weight:600">\1 \2</span>', escaped)
        # HP/damage: 7最大HP, 12 HP, 13点伤害, 8伤害
        escaped = _re.sub(r'(\d+)\s*(?:点)?(最大HP|HP|最大生命值|生命值|生命)', r'<span style="color:var(--hp);font-weight:600">\1 \2</span>', escaped)
        escaped = _re.sub(r'(\d+)\s*(?:点)?(伤害)', r'<span style="color:var(--hp);font-weight:600">\1 \2</span>', escaped)
        # Block: 8格挡, 5 格挡
        escaped = _re.sub(r'(\d+)\s*(?:点)?(格挡)', r'<span style="color:var(--block);font-weight:600">\1 \2</span>', escaped)
        # Buffs: 2力量, 3敏捷
        escaped = _re.sub(r'(\d+)\s*(力量|敏捷|集中|虚弱|易伤|能量)', r'<span style="color:var(--buff);font-weight:600">\1 \2</span>', escaped)
        # Items in「」
        escaped = _re.sub(r'「([^」]+)」', r'<span style="color:var(--accent2);font-weight:600">「\1」</span>', escaped)
        # Relic/card type labels (only specific terms, avoid over-matching)
        escaped = _re.sub(r'(稀有遗物|稀有卡牌|随机遗物)', r'<span style="color:var(--accent2)">\1</span>', escaped)
        # Numbers for 张牌
        escaped = _re.sub(r'(\d+)\s*(张牌|张)', r'<span style="font-weight:600">\1</span>\2', escaped)
        return escaped

    def _render_formatted_html(self, text, header=""):
        """Parse AI output and produce colored HTML string."""
        parts = []
        self._last_recommended_option = None  # Track recommended option for highlighting
        if header:
            parts.append(f'<span class="gold" style="font-weight:600">{html.escape(header)}</span><br><br>')

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()

            if not stripped:
                parts.append("<br>")
                i += 1
                continue

            escaped = html.escape(stripped)

            # Separator
            if stripped.startswith("──") or stripped.startswith("─"):
                parts.append(f'<span class="gold" style="font-weight:600">{escaped}</span><br>')

            # Play order title
            elif stripped.startswith("▶"):
                parts.append(f'<span class="gold" style="font-weight:600">{escaped}</span><br>')

            # Numbered steps
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".、":
                parts.append(f'<span style="font-weight:600">{escaped}</span><br>')

            # Energy remaining
            elif stripped.startswith("（能量剩余") or stripped.startswith("(能量剩余"):
                parts.append(f'<span class="dim">{escaped}</span><br>')

            # Threat block
            elif stripped.startswith("⚠"):
                parts.append(f'<br><span class="debuff">{escaped}</span><br>')
                i += 1
                while i < len(lines):
                    next_s = lines[i].strip()
                    if not next_s or next_s[0] in "▶★○✗💡📋─" or (len(next_s) > 2 and next_s[0].isdigit() and next_s[1] in ".、"):
                        break
                    parts.append(f'  <span class="debuff">{html.escape(next_s)}</span><br>')
                    i += 1
                continue

            # Strategy block 💡
            elif stripped.startswith("💡"):
                content = stripped.lstrip("💡 ")
                parts.append(f'<br><span style="color:var(--gold);font-weight:600">💡 {self._colorize_desc(content)}</span><br>')
                i += 1
                while i < len(lines):
                    next_s = lines[i].strip()
                    if not next_s or next_s[0] in "▶★○✗⚠📋─" or (len(next_s) > 2 and next_s[0].isdigit() and next_s[1] in ".、"):
                        break
                    parts.append(f'  {self._colorize_desc(next_s)}<br>')
                    i += 1
                continue

            # Recommend ★ — split marker + name from reasoning
            elif stripped.startswith("★") or stripped.startswith("推荐购买") or stripped.startswith("推荐选项"):
                content = stripped.lstrip("★ ")
                dash_pos = content.find("—")
                if dash_pos < 0: dash_pos = content.find("——")
                if dash_pos > 0:
                    name_part = content[:dash_pos].strip()
                    reason_part = content[dash_pos+1:].strip().lstrip("—").strip()
                    parts.append(f'<span class="gold" style="font-weight:600">★ {html.escape(name_part)}</span>'
                                 f' — {self._colorize_desc(reason_part)}<br>')
                    # Save for option highlighting
                    self._last_recommended_option = name_part
                else:
                    parts.append(f'<span class="gold" style="font-weight:600">★ {self._colorize_desc(content)}</span><br>')
                    # Try to extract name before any punctuation
                    for sep in ['，', '。', '：', ',', '.']:
                        if sep in content:
                            self._last_recommended_option = content[:content.index(sep)].strip()
                            break

            # Not recommended ✗
            elif stripped.startswith("✗") or stripped.startswith("跳过") or stripped.startswith("避雷"):
                content = stripped.lstrip("✗ ")
                dash_pos = content.find("—")
                if dash_pos > 0:
                    name_part = content[:dash_pos].strip()
                    reason_part = content[dash_pos+1:].strip().lstrip("—").strip()
                    parts.append(f'<span style="color:var(--hp);font-weight:600">✗ {html.escape(name_part)}</span>'
                                 f' — <span class="dim">{self._colorize_desc(reason_part)}</span><br>')
                else:
                    parts.append(f'<span style="color:var(--hp)">✗ {self._colorize_desc(content)}</span><br>')

            # Remove card advice
            elif stripped.startswith("删牌建议"):
                parts.append(f'<span class="debuff">{escaped}</span><br>')

            # Play style
            elif stripped.startswith("打法"):
                parts.append(f'<span class="blue">{escaped}</span><br>')

            # Archetype / summary
            elif stripped.startswith("📋") or stripped.startswith("流派"):
                parts.append(f'<span class="gold" style="font-weight:600">{escaped}</span><br>')

            # Direction
            elif stripped.startswith("方向"):
                parts.append(f'<span class="buff">{escaped}</span><br>')

            # Core / support / transition / combo cards
            elif stripped.startswith("核心牌"):
                parts.append(f'<span class="highlight">{escaped}</span><br>')
            elif stripped.startswith("辅助牌"):
                parts.append(f'<span class="buff">{escaped}</span><br>')
            elif stripped.startswith("过渡牌"):
                parts.append(f'<span class="dim">{escaped}</span><br>')
            elif stripped.startswith("组合技"):
                parts.append(f'<span style="font-weight:600">{escaped}</span><br>')

            # Strength / consider
            elif stripped.startswith("强度") or stripped.startswith("可以考虑"):
                parts.append(f'<span class="buff">{escaped}</span><br>')

            # Find cards
            elif stripped.startswith("找牌"):
                parts.append(f'<span class="highlight">{escaped}</span><br>')

            # Optional ○ — consider option
            elif stripped.startswith("○"):
                content = stripped.lstrip("○ ")
                dash_pos = content.find("—")
                if dash_pos > 0:
                    name_part = content[:dash_pos].strip()
                    reason_part = content[dash_pos+1:].strip().lstrip("—").strip()
                    parts.append(f'<span style="color:var(--block);font-weight:600">○ {html.escape(name_part)}</span>'
                                 f' — <span class="dim">{self._colorize_desc(reason_part)}</span><br>')
                else:
                    parts.append(f'<span style="color:var(--block)">○ {self._colorize_desc(content)}</span><br>')

            # Default — apply colorize for inline coloring
            else:
                parts.append(f'{self._colorize_desc(stripped)}<br>')

            i += 1

        return "".join(parts)

    def _push_advice(self, text, header=""):
        """Render AI advice HTML and push to UI, then highlight recommended option."""
        advice_html = self._render_formatted_html(text, header)
        self._js(f'app.updateAdvice({json.dumps(advice_html)})')
        # Highlight recommended option if found
        if getattr(self, '_last_recommended_option', None):
            opt_name = json.dumps(self._last_recommended_option)
            self._js(f'app.highlightOption({opt_name})')

    def _delayed_display_combat(self):
        """Delay then re-fetch latest state and display."""
        import threading
        def _do():
            try:
                state = requests.get(API_URL, timeout=5).json()
                if state.get("state_type") in ("monster", "elite", "boss"):
                    self._display_combat(state)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()

    @staticmethod
    def _number_enemies(enemies):
        """Give same-name enemies numbers: 绿虱#1, 绿虱#2."""
        name_count = {}
        for e in enemies:
            n = e.get("name", "?")
            name_count[n] = name_count.get(n, 0) + 1
        name_idx = {}
        for e in enemies:
            n = e.get("name", "?")
            if name_count[n] > 1:
                name_idx[n] = name_idx.get(n, 0) + 1
                e["_display_name"] = f"{n}#{name_idx[n]}"
            else:
                e["_display_name"] = n
        return enemies

    def _display_combat(self, state):
        """Auto-display battlefield state (no LLM)."""
        battle  = state.get("battle", {})
        enemies = battle.get("enemies", [])
        player  = battle.get("player", {})
        hand    = player.get("hand", [])
        draw    = player.get("draw_pile_count", 0)
        disc    = player.get("discard_pile_count", 0)
        exhaust = player.get("exhaust_pile_count", 0)
        rnd     = battle.get("round", "?")

        self._number_enemies(enemies)

        parts = [f'<span class="gold" style="font-weight:600">第{rnd}回合</span><br><br>']

        for ei, e in enumerate(enemies):
            display_name = e.get("_display_name", e.get("name", "?"))
            ehp  = e.get("hp", 0)
            emhp = e.get("max_hp", 1)
            intent = self._fmt_intent(e.get("intents", []))
            blk = e.get("block", 0)
            powers = e.get("powers", [])

            parts.append(f'<span class="warn" style="font-weight:600">{html.escape(display_name)}</span>  ')
            parts.append(f'<span class="warn">HP {ehp}/{emhp}</span>')
            if blk:
                parts.append(f'  <span class="blue">格挡 {blk}</span>')
            parts.append('<br>')
            parts.append(f'  <span class="dim">意图: </span><span class="warn">{html.escape(intent)}</span><br>')

            if powers:
                parts.append('  ')
                for p in powers:
                    amt = p.get("amount", 0)
                    pname = _cn_power(p)
                    cls = "debuff" if amt < 0 else "buff"
                    parts.append(f'<span class="{cls}">{html.escape(pname)}x{amt}</span>  ')
                parts.append('<br>')

            if ei < len(enemies) - 1:
                parts.append('<br>')

        # Allies
        allies = [a for a in battle.get("allies", []) if a.get("name")]
        if allies:
            parts.append('<br>')
        for a in allies:
            ahp = a.get("hp", 0)
            amhp = a.get("max_hp", 1)
            parts.append(f'<span class="highlight">{html.escape(a.get("name", "?"))}</span>  ')
            parts.append(f'<span class="buff">HP {ahp}/{amhp}</span>')
            ablk = a.get("block", 0)
            if ablk:
                parts.append(f'  <span class="blue">格挡 {ablk}</span>')
            apowers = a.get("powers", [])
            if apowers:
                parts.append('  ')
                for p in apowers:
                    parts.append(f'<span class="buff">{html.escape(_cn_power(p))}x{p["amount"]}</span>  ')
            parts.append('<br>')

        # Player section
        parts.append(f'<br><span class="gold" style="font-weight:600">我方</span><br><br>')

        # Powers
        p_powers = player.get("powers", [])
        if p_powers:
            parts.append('  能力: ')
            for p in p_powers:
                amt = p.get("amount", 0)
                pname = _cn_power(p)
                cls = "buff" if amt >= 0 else "debuff"
                parts.append(f'<span class="{cls}">{html.escape(pname)}x{amt}</span>  ')
            parts.append('<br>')

        # Hand
        parts.append('  手牌: ')
        if hand:
            card_counts = {}
            card_order = []
            for c in hand:
                name = c["name"]
                upg = "+" if c.get("is_upgraded") else ""
                key = f"{name}{upg}"
                if key not in card_counts:
                    card_counts[key] = 0
                    card_order.append((key, name))
                card_counts[key] += 1
            for idx, (key, raw_name) in enumerate(card_order):
                cnt = card_counts[key]
                if idx > 0:
                    parts.append(' · ')
                cost = "?"
                if hasattr(self, '_card_db'):
                    cost = self._card_db.get(raw_name, {}).get("cost", "?")
                parts.append(f'<span class="highlight">{html.escape(key)}</span>')
                parts.append(f'<span class="dim">({cost})</span>')
                if cnt > 1:
                    parts.append(f'x{cnt}')
        else:
            parts.append('<span class="dim">（空）</span>')
        parts.append('<br>')

        # Energy + piles
        energy = player.get("energy", "?")
        max_energy = player.get("max_energy", "?")
        parts.append(f'  <span style="font-weight:600">能量 {energy}/{max_energy}</span>')
        parts.append(f'  <span class="dim">|</span>  ')
        parts.append(f'<span class="dim">摸:{draw}  弃:{disc}</span>')
        if exhaust:
            parts.append(f'<span class="dim">  消:{exhaust}</span>')
        parts.append('<br>')

        content = "".join(parts)
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')
        self._js('app.setTab("situation")')

    def _display_map(self, state):
        """Auto-display map routes (no LLM)."""
        mdata = state.get("map", {})

        node_cn = {
            "Monster": "怪", "Elite": "精英", "Boss": "Boss",
            "Shop": "商店", "Rest": "休息", "Event": "事件",
            "Treasure": "宝箱", "Unknown": "?", "Ancient": "古代"
        }
        node_class = {
            "Monster": "node-enemy", "Elite": "node-elite", "Boss": "node-elite",
            "Shop": "node-shop", "Rest": "node-rest", "RestSite": "node-rest",
            "Event": "node-event", "Treasure": "highlight", "Unknown": "dim",
            "Ancient": "highlight"
        }

        parts = ['<div class="section-title">岔路选择</div>']

        opts = mdata.get("next_options", [])
        for o in opts:
            ntype = o.get("type", "")
            cn    = node_cn.get(ntype, ntype)
            cls   = node_class.get(ntype, "")
            leads = o.get("leads_to", [])
            route_num = o.get('index', 0) + 1

            parts.append(f'<div class="route-block">')
            parts.append(f'<div class="route-label">路线 {route_num}  <span class="{cls}">{html.escape(cn)}</span></div>')

            if leads:
                parts.append('<div class="route-nodes">')
                for j, n in enumerate(leads[:4]):
                    nt  = n.get("type", "")
                    ncn = node_cn.get(nt, nt)
                    ncls = node_class.get(nt, "")
                    parts.append(f'  &gt; <span class="{ncls}">{html.escape(ncn)}</span>')
                parts.append('</div>')
            parts.append('</div>')

        if not opts:
            parts.append('<div class="textbox"><span class="dim">（无路线信息）</span></div>')

        content = "".join(parts)
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')
        self._js('app.setTab("situation")')

    def _display_card_reward(self, state):
        """Auto-display card reward (no LLM)."""
        cr      = state.get("card_reward") or state.get("card_select") or {}
        rewards = cr.get("cards", [])

        TYPE_CN = {"attack": "攻击", "skill": "技能", "power": "能力"}
        _type_cls = {"attack": "warn", "skill": "blue", "power": "buff"}

        parts = ['<div class="section-title">选牌奖励</div>']

        if rewards:
            parts.append('<div class="card-grid">')
            for c in rewards:
                name = c.get("name", "?")
                upg  = "+" if c.get("is_upgraded") else ""
                hint_text = CARD_DICT.get(name, c.get("description", "")[:40])

                ctype = (c.get("type") or c.get("card_type") or "").lower()
                cost = "?"
                if hasattr(self, '_card_db'):
                    db = self._card_db.get(name, {})
                    if not ctype:
                        ctype = db.get("type", "").lower()
                    cost = db.get("cost", "?")
                type_cn = TYPE_CN.get(ctype, "")

                parts.append('<div class="card-item">')
                parts.append(f'<div class="card-name">{html.escape(name)}{html.escape(upg)}</div>')
                cost_type = f"{cost}费"
                if type_cn:
                    cost_type += f" · {type_cn}"
                parts.append(f'<div class="card-cost">{html.escape(cost_type)}</div>')
                if hint_text:
                    parts.append(f'<div class="card-desc">{html.escape(hint_text)}</div>')
                parts.append('</div>')
            parts.append('</div>')
        else:
            parts.append('<div class="textbox"><span class="dim">（无可选牌，可跳过）</span></div>')

        content = "".join(parts)
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')
        self._js('app.setTab("situation")')

    def _display_event(self, state):
        """Auto-display event options + knowledge base advice."""
        ev  = state.get("event", {})

        parts = []
        # Event box
        parts.append('<div class="event-box">')
        parts.append(f'<div class="event-title">{html.escape(ev.get("event_name", "未知事件"))}</div>')
        body = ev.get("body", "")
        if body:
            parts.append(f'<div class="event-desc">{html.escape(body)}</div>')
        parts.append('</div>')

        # Options
        parts.append('<div class="section-title">选项</div>')
        options = ev.get("options", [])
        for o in options:
            if o.get("is_locked"):
                continue
            idx = o.get("index", 0)
            parts.append('<div class="option-block">')
            parts.append(f'<div class="option-label">选项 {idx + 1}: {html.escape(o["title"])}</div>')
            desc = o.get("description", "")
            if desc:
                parts.append(f'<div class="option-desc">{self._colorize_desc(desc)}</div>')
            parts.append('</div>')

        # Knowledge base guide
        event_id = ev.get("event_id") or ev.get("id") or ev.get("event_name", "")
        guide = self._event_guide.get(event_id, {})
        if guide:
            parts.append('<div class="section-title">知识库建议</div>')
            for go in guide.get("options", []):
                rating = go.get("rating", "")
                parts.append(f'<div class="option-block">')
                parts.append(f'<span style="font-weight:600">{html.escape(rating)}</span> ')
                parts.append(f'<span class="highlight">{html.escape(go.get("name", "?"))}</span>')
                effect = go.get("effect", "")[:60]
                if effect:
                    parts.append(f'  <span class="dim">{html.escape(effect)}</span>')
                parts.append('</div>')
            strat = guide.get("strategy", "")
            if strat:
                parts.append(f'<div class="option-block"><span class="dim">策略: {html.escape(strat[:100])}</span></div>')

        content = "".join(parts)
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')
        self._js('app.setTab("situation")')

    def _display_shop(self, state):
        """Auto-display shop items (no LLM)."""
        shop   = state.get("shop", {})
        player = self._get_player(state)
        gold   = player.get("gold", "?")

        TYPE_CN = {"attack": "攻击", "skill": "技能", "power": "能力"}

        # STS2MCP items array
        items = shop.get("items", [])
        if not items:
            items = []
            for c in shop.get("cards", []):
                items.append({"category": "card", "card_name": c.get("name"), "cost": c.get("price"),
                              "is_stocked": True, "can_afford": True, "card_description": c.get("description", "")})
            for r in shop.get("relics", []):
                items.append({"category": "relic", "relic_name": r.get("name"), "cost": r.get("price"),
                              "is_stocked": True, "relic_description": r.get("description", "")})
            for p in shop.get("potions", []):
                items.append({"category": "potion", "potion_name": p.get("name"), "cost": p.get("price"),
                              "is_stocked": True})

        cards = [i for i in items if i.get("category") == "card" and i.get("is_stocked")]
        relics = [i for i in items if i.get("category") == "relic" and i.get("is_stocked")]
        potions = [i for i in items if i.get("category") == "potion" and i.get("is_stocked")]
        purge = [i for i in items if i.get("category") in ("purge", "card_removal") and i.get("is_stocked")]

        _type_cls = {"attack": "warn", "skill": "blue", "power": "buff"}

        parts = []
        parts.append(f'<span class="gold" style="font-weight:600">商店</span>')
        parts.append(f'  <span class="dim">金币: </span>')
        parts.append(f'<span style="font-weight:600">{html.escape(str(gold))}</span><br><br>')

        if cards:
            parts.append('<div class="section-title">卡牌</div>')
            parts.append('<div class="card-grid">')
            for c in cards:
                name = c.get("card_name", "?")
                cost = c.get("cost", "?")
                desc = self._clean_desc(c.get("card_description", ""))
                hint_text = CARD_DICT.get(name, desc[:30])
                ctype = (c.get("card_type") or "").lower()
                card_cost = "?"
                if hasattr(self, '_card_db'):
                    db = self._card_db.get(name, {})
                    if not ctype:
                        ctype = db.get("type", "").lower()
                    card_cost = db.get("cost", "?")
                type_cn = TYPE_CN.get(ctype, "")

                parts.append('<div class="card-item">')
                parts.append(f'<div class="card-name">{html.escape(name)}</div>')
                cost_type = f"{card_cost}费"
                if type_cn:
                    cost_type += f" · {type_cn}"
                parts.append(f'<div class="card-cost">{html.escape(cost_type)}</div>')
                if hint_text:
                    parts.append(f'<div class="card-desc">{html.escape(hint_text)}</div>')
                price_str = f"{cost}金"
                if c.get("on_sale"):
                    price_str += " 折扣"
                if not c.get("can_afford", True):
                    price_str += " 买不起"
                parts.append(f'<div class="card-price">{html.escape(price_str)}</div>')
                parts.append('</div>')
            parts.append('</div>')

        if relics:
            parts.append('<div class="section-title">遗物</div>')
            parts.append('<div class="textbox">')
            for r in relics:
                rname = _cn_relic(r.get('relic_name', '?'))
                rcost = r.get('cost', '?')
                rdesc = r.get('relic_description', '')
                parts.append(f'<span class="highlight">{html.escape(rname)}</span> ')
                parts.append(f'<span class="gold">{rcost}金</span>')
                if not r.get("can_afford", True):
                    parts.append(f'  <span class="debuff">买不起</span>')
                if rdesc:
                    parts.append(f'<br><span class="dim">  {html.escape(self._clean_desc(rdesc)[:40])}</span>')
                parts.append('<br>')
            parts.append('</div>')

        if potions:
            parts.append('<div class="section-title">药水</div>')
            parts.append('<div class="textbox">')
            for p in potions:
                pname = _cn_potion(p.get('potion_name', '?'))
                pcost = p.get('cost', '?')
                parts.append(f'<span class="blue">{html.escape(pname)}</span> ')
                parts.append(f'<span class="gold">{pcost}金</span><br>')
            parts.append('</div>')

        if purge:
            parts.append(f'<div class="section-title">删牌服务</div>')
            parts.append(f'<div class="textbox"><span class="debuff">{purge[0].get("cost", "?")}金</span></div>')

        content = "".join(parts)
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')
        self._js('app.setTab("situation")')

    def _display_rest(self, state):
        """Auto-display rest site options (no LLM)."""
        rest   = state.get("rest_site", state.get("rest", {}))
        player = self._get_player(state)

        rest_labels = {
            "rest": ("补血", "回复35%最大HP"),
            "smith": ("锻造", "升级一张牌"),
            "recall": ("孵化", "激活炉子遗物"),
            "toke": ("抽牌", "记忆水晶"),
            "lift": ("力量+", "举重训练"),
            "dig": ("挖掘", "铲子"),
        }

        hp  = player.get("hp", 0)
        mhp = player.get("max_hp", 1)
        hp_pct = int(hp / mhp * 100)
        heal_amt = int(mhp * 0.35)

        parts = []
        parts.append(f'<div class="section-title">休息点</div>')
        parts.append(f'<div class="textbox">')
        parts.append(f'<span class="dim">HP: </span><span class="warn">{hp}/{mhp}</span>')
        parts.append(f' <span class="dim">({hp_pct}%)</span><br><br>')

        opts = rest.get("options", [])
        if opts:
            for oi, o in enumerate(opts):
                key = o.get("type", o.get("label", "?"))
                label_pair = rest_labels.get(key)

                if label_pair:
                    title, desc = label_pair
                    if key == "rest":
                        desc = f"回复35%最大HP（约+{heal_amt} HP）"
                else:
                    title = o.get("label", key)
                    desc = ""

                parts.append(f'<span style="font-weight:600">选项 {oi + 1}: </span>')
                parts.append(f'<span class="highlight">{html.escape(title)}</span><br>')
                if desc:
                    parts.append(f'  <span class="dim">{html.escape(desc)}</span><br>')
                parts.append('<br>')
        else:
            parts.append(f'<span style="font-weight:600">选项 1: </span>')
            parts.append(f'<span class="highlight">补血</span><br>')
            parts.append(f'  <span class="dim">回复35%最大HP（约+{heal_amt} HP）</span><br><br>')
            parts.append(f'<span style="font-weight:600">选项 2: </span>')
            parts.append(f'<span class="highlight">锻造</span><br>')
            parts.append(f'  <span class="dim">升级一张牌</span><br>')

        parts.append('</div>')

        content = "".join(parts)
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')
        self._js('app.setTab("situation")')
