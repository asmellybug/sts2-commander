#!/usr/bin/env python3
"""
STS2 战略指挥官 v6.0 — pywebview Rewrite

主文件：UI构建 + 轮询 + 状态分发 + 按钮回调
其余逻辑分布在：
  - constants.py  — 翻译字典、颜色、配置
  - display.py    — UI显示方法（改UI改这里）
  - ai_advisor.py — LLM调用和策略（改prompt改这里）
  - history.py    — 日志、回放、复盘
  - data.py       — 数据加载、存档、session
"""

import json
import html
import os
import threading
import time
import requests
import webview
from collections import Counter

from overlay.constants import (
    API_URL, POLL_SECS,
    BG, PANEL, CARD, BORDER, GOLD, GOLD_DIM, PARCH, PARCH_DIM,
    RED, GREEN, BLUE, SHADOW,
    _cn_power,
)

from overlay.display import DisplayMixin
from overlay.ai_advisor import AIAdvisorMixin
from overlay.history import HistoryMixin
from overlay.data import DataMixin

# ── Theme constants (matching HTML reference :root) ──
ACCENT    = "#9b6fd4"
ACCENT2   = "#c9a0f0"
TITLEBAR  = "#1a1030"
TITLEBAR2 = "#251845"
DIM       = "#a89ab8"
HP_COLOR  = "#e74c3c"
BUFF_CLR  = "#45c480"
BLOCK_CLR = "#5dade2"
DEBUFF_CLR = "#d47a30"


class BridgeAPI:
    """JS -> Python bridge for pywebview."""

    def __init__(self, commander):
        self._cmd = commander

    def onAnalyze(self, analysis_type):
        if analysis_type == "situation":
            self._cmd._on_situation_analyze()
        elif analysis_type == "deck":
            self._cmd._on_deck_analyze()

    def onAsk(self, text):
        text = (text or "").strip()
        if text and self._cmd.last_state:
            self._cmd._js(f'app.setButtonState("btn-situation", "分析中…", true)')
            threading.Thread(target=self._cmd._do_freeform_ask, args=(text,), daemon=True).start()


class STS2Commander(DisplayMixin, AIAdvisorMixin, HistoryMixin, DataMixin):

    def __init__(self):
        # State
        self.last_state    = None
        self.last_type     = None
        self.last_round    = -1
        self.last_player   = {}
        self.last_run      = {}
        self.run_log       = []
        self.deck_acquired = []
        self.deck_removed  = []
        self._busy_combat  = False
        self._busy_strat   = False
        self._busy_deck    = False
        self._fail_count   = 0
        self._prev_floor   = 0
        self._combat_start_hp    = 0
        self._battle_log   = []
        self._run_replay   = []
        self._combat_start_floor = 0
        self._combat_rounds      = 0
        self._deck_archetype     = ""
        self._first_connect      = True
        self._card_analyzed      = False
        self._deck_analysis_text = ""
        self._window = None
        self._window_ready = threading.Event()

        self._build_ui()
        self._load_card_db()
        self._load_unlock_state()
        self._load_knowledge()
        self._load_archetype()
        self._load_history()
        self._load_session()

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
    def _build_ui(self):
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.html")
        api = BridgeAPI(self)
        self._window = webview.create_window(
            "STS2 战略指挥官",
            html_path,
            width=480,
            height=780,
            on_top=True,
            js_api=api,
            background_color=BG,
        )

    # ══════════════════════════════════════════
    #  JS EVAL HELPER
    # ══════════════════════════════════════════
    def _js(self, call):
        """Thread-safe JS evaluation."""
        if not self._window_ready.is_set():
            return  # Skip silently if window not ready yet
        try:
            if self._window:
                self._window.evaluate_js(call)
        except Exception:
            pass

    # ══════════════════════════════════════════
    #  POLLING
    # ══════════════════════════════════════════
    def _poll_loop(self):
        print("[Poll] Thread started", flush=True)
        while True:
            try:
                r = requests.get(API_URL, timeout=5)
                state = r.json()
                self._fail_count = 0
                self._connected = True
                if not hasattr(self, '_poll_logged'):
                    print(f"[Poll] API OK: {state.get('state_type')}", flush=True)
                    self._poll_logged = True
                    threading.Timer(3.0, self._save_session).start()
                self._js('app.setConnection("●  已连接")')
                try:
                    self._collect_cards(state)
                    self._on_update(state)
                except Exception as ue:
                    print(f"[Update Error] {ue}")
            except requests.exceptions.ConnectionError:
                self._fail_count += 1
                if self._fail_count == 1:
                    self._js('app.setConnection("等待游戏连接…")')
                    msg = json.dumps(
                        "等待游戏启动…\n\n"
                        "请确保：\n"
                        "  1. 杀戮尖塔2已启动\n"
                        "  2. MCP API 已开启\n"
                        f"  3. API地址：{API_URL}")
                    self._js(f'app.updateScene({{type:"html",html:{msg}}})')
                elif self._fail_count >= 5:
                    self._js('app.setConnection("等待游戏…")')
            except requests.exceptions.RequestException:
                self._fail_count += 1
                if self._fail_count >= 3:
                    self._js('app.setConnection("重连中…")')
            except Exception as e:
                print(f"[Update Error] {e}")
            time.sleep(POLL_SECS)

    # ══════════════════════════════════════════
    #  STATE DISPATCH
    # ══════════════════════════════════════════
    def _on_update(self, state):
        self._js('app.setConnection("●  已连接")')

        stype = state.get("state_type", "unknown")
        player = self._get_player(state)
        run = state.get("run", {})

        if player:
            self.last_player = player
        elif not self.last_player:
            save_player, _ = self._load_save_data()
            if save_player:
                self.last_player = save_player
        if run:
            self.last_run = run

        self._refresh_header(self.last_player, self.last_run)

        type_changed  = stype != self.last_type
        cur_round     = state.get("battle", {}).get("round", -1)
        round_changed = cur_round != self.last_round

        # Reset busy locks on state change
        if type_changed:
            self._busy_strat  = False
            self._busy_combat = False
            self._busy_deck   = False
            self._js('app.setButtonState("btn-situation", "◆  求策·当前形势  ◆", false)')
            self._js('app.setButtonState("btn-deck", "◆  求策·卡组  ◆", false)')

        # First connection
        valid_types = ("monster", "elite", "boss", "map", "event", "shop", "rest",
                       "card_reward", "card_select", "combat_rewards", "rest_site", "treasure")
        if self._first_connect and stype in valid_types:
            self._first_connect = False
            self._display_deck_list()
            type_changed = True

        # Combat
        if stype in ("monster", "elite", "boss"):
            if type_changed:
                self._combat_start_hp    = self.last_player.get("hp", 0)
                self._combat_start_floor = run.get("floor", 0)
                self._combat_rounds      = 1
                self._battle_log = []
            else:
                self._combat_rounds = max(self._combat_rounds, cur_round)

            self._record_combat_snapshot(state, cur_round, type_changed or round_changed)

            if type_changed or round_changed:
                threading.Timer(1.5, self._delayed_display_combat).start()

        elif stype == "map":
            if type_changed:
                self._display_map(state)

        elif stype in ("card_reward", "card_select"):
            if type_changed:
                self._card_analyzed = False
                # Track if this came from an event
                if stype == "card_select" and self.last_type == "event":
                    self._card_select_from_event = getattr(self, '_last_event_context', None)
                else:
                    self._card_select_from_event = None
                self._display_card_reward(state)
                self._js('app.setTab("situation")')

        elif stype == "event":
            if type_changed:
                # Store event context for subsequent card_select
                ev = state.get("event", {})
                self._last_event_context = {
                    "event_name": ev.get("event_name", ""),
                    "options": [o.get("title", "") for o in ev.get("options", []) if not o.get("is_locked")],
                }
                self._display_event(state)

        elif stype == "shop":
            if type_changed:
                self._display_shop(state)

        elif stype in ("rest", "rest_site"):
            if type_changed:
                self._display_rest(state)

        elif stype == "treasure":
            if type_changed:
                msg = json.dumps("宝箱\n\n  直接领取即可。")
                self._js(f'app.updateScene({{type:"html",html:{msg}}})')

        # Log transition
        if type_changed and self.last_type:
            self._log_transition(self.last_state or state, self.last_type, state)
            if self.last_type in ("monster", "elite", "boss") and self._battle_log:
                battle_entry = {
                    "type": "combat",
                    "floor": self._combat_start_floor,
                    "enemies": [e.get("name","?") for e in (self.last_state or state).get("battle",{}).get("enemies",[])],
                    "start_hp": self._combat_start_hp,
                    "end_hp": player.get("hp", 0) if player else 0,
                    "rounds": self._combat_rounds,
                    "turns": self._battle_log,
                    "result": "win" if stype != "menu" else "loss"
                }
                self._run_replay.append(battle_entry)
                self._battle_log = []
            elif self.last_type in ("card_reward", "card_select", "shop", "event", "rest", "rest_site"):
                self._record_decision(self.last_state or state, self.last_type)

        # New run detection
        cur_floor = run.get("floor", 0)
        if (self._prev_floor >= 2 and cur_floor <= 1 and
                stype not in ("unknown", "map") and
                (self.run_log or self.deck_acquired)):
            self._on_new_run()
        self._prev_floor = cur_floor

        self.last_state = state
        self.last_type  = stype
        self.last_round = cur_round

    def _show_analyzing(self, msg="正在分析…"):
        self._js(f'app.updateAdvice({json.dumps(html.escape(msg))})')

    def _clear_advice(self):
        self._js('app.updateAdvice("")')

    # ══════════════════════════════════════════
    #  HEADER REFRESH
    # ══════════════════════════════════════════
    def _refresh_header(self, p, run):
        hp    = p.get("hp", 0)
        mhp   = p.get("max_hp", 80)
        gold  = p.get("gold", "—")
        char  = p.get("character", "—")
        act   = run.get("act", "?")
        floor = run.get("floor", "?")
        asc   = run.get("ascension", 0)

        asc_str = f" A{asc}" if asc else ""
        relics = len(p.get("relics", []))

        header_data = json.dumps({
            "char": f"{char}{asc_str}",
            "hp": hp,
            "maxHp": mhp,
            "gold": gold,
            "relics": relics,
        })
        self._js(f'app.updateHeader({header_data})')
        self._js(f'app.setConnection("幕{act} · 层{floor}")')

    def _refresh_combat_header(self, state):
        """Display combat state in the scene area using HTML."""
        try:
            self._refresh_combat_header_inner(state)
        except Exception as e:
            print(f"[Combat Header Error] {e}")
            import traceback; traceback.print_exc()

    def _refresh_combat_header_inner(self, state):
        battle  = state.get("battle", {})
        enemies = battle.get("enemies", [])
        player  = battle.get("player", {})
        hand    = player.get("hand", [])
        draw    = player.get("draw_pile_count", 0)
        disc    = player.get("discard_pile_count", 0)
        exh     = player.get("exhaust_pile_count", 0)
        rnd     = battle.get("round", 1)

        parts = [f'<span class="gold" style="font-weight:600">第{rnd}回合</span><br><br>']

        for e in enemies:
            if not e.get("name"):
                continue
            ehp  = e.get("hp", 0)
            emhp = e.get("max_hp", 1)
            intents = self._fmt_intent(e.get("intents", []))
            powers  = "  ".join(f"{_cn_power(p)}x{p['amount']}" for p in e.get("powers", []))
            blk = e.get("block", 0)

            parts.append(f'<span class="warn" style="font-weight:600">{html.escape(e["name"])}</span>')
            parts.append(f'  <span class="warn">HP {ehp}/{emhp}</span>')
            if blk:
                parts.append(f'  <span class="blue">格挡{blk}</span>')
            parts.append(f'  意图：<span class="warn">{html.escape(intents)}</span>')
            parts.append('<br>')
            if powers:
                parts.append(f'  <span class="debuff">{html.escape(powers)}</span><br>')

        allies = [a for a in battle.get("allies", [])
                  if a.get("name") and a.get("name") != "None"]
        for a in allies:
            ahp  = a.get("hp", 0)
            amhp = a.get("max_hp", 1)
            ablk = a.get("block", 0)
            apow = "  ".join(f"{_cn_power(p)}x{p['amount']}" for p in a.get("powers", []))
            parts.append(f'<br><span class="buff">{html.escape(a["name"])}</span>')
            parts.append(f'  <span class="buff">HP {ahp}/{amhp}</span>')
            if ablk:
                parts.append(f'  <span class="blue">格挡{ablk}</span>')
            if apow:
                parts.append(f'  <span class="buff">{html.escape(apow)}</span>')
            parts.append('<br>')

        parts.append('<br><span class="gold" style="font-weight:600">我方</span><br>')
        ppow = player.get("powers", [])
        if ppow:
            ppow_str = "  ".join(f"{_cn_power(p)}x{p['amount']}" for p in ppow)
            parts.append(f'  能力：<span class="buff">{html.escape(ppow_str)}</span><br>')

        card_names = []
        for c in hand:
            upg = "+" if c.get("is_upgraded") else ""
            card_names.append(f"{c['name']}{upg}")
        counted = Counter(card_names)
        card_parts = []
        for name, cnt in counted.items():
            card_parts.append(f"{name}x{cnt}" if cnt > 1 else name)
        parts.append('  手牌：')
        parts.append(f'<span class="highlight">{html.escape(" · ".join(card_parts) if card_parts else "（空）")}</span>')
        parts.append('<br>')
        parts.append(f'  <span class="dim">抽牌堆 {draw} | 弃牌堆 {disc} | 消耗堆 {exh}</span><br>')

        content = "".join(parts)
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')

    # ══════════════════════════════════════════
    #  BUTTON CALLBACKS
    # ══════════════════════════════════════════
    def _on_freeform_enter(self):
        # This is handled by BridgeAPI.onAsk now
        pass

    def _on_situation_analyze(self):
        if not self.last_state:
            return
        stype = self.last_state.get("state_type", "")
        self._js('app.setButtonState("btn-situation", "分析中…", true)')
        threading.Timer(35.0, lambda: self._js(
            'app.setButtonState("btn-situation", "◆  求策·当前形势  ◆", false)')).start()

        if stype in ("monster", "elite", "boss"):
            threading.Thread(target=self._do_analyze_situation, args=("combat",), daemon=True).start()
        elif stype == "map":
            threading.Thread(target=self._do_analyze_situation, args=("map",), daemon=True).start()
        elif stype in ("card_reward", "card_select"):
            threading.Thread(target=self._do_analyze_situation, args=("card",), daemon=True).start()
        elif stype in ("event", "shop", "rest", "rest_site", "treasure"):
            threading.Thread(target=self._do_analyze_situation, args=("node",), daemon=True).start()
        else:
            self._js('app.setButtonState("btn-situation", "◆  求策·当前形势  ◆", false)')

    def _do_analyze_situation(self, kind):
        self._analyze_state_type = self.last_type
        try:
            if kind == "combat":
                self._ai_combat(self.last_state)
            elif kind == "map":
                self._ai_map(self.last_state)
            elif kind == "card":
                self._ai_card(self.last_state)
            elif kind == "node":
                self._ai_node(self.last_state)
        finally:
            self._js('app.setButtonState("btn-situation", "◆  求策·当前形势  ◆", false)')

    def _analysis_stale(self):
        return getattr(self, '_analyze_state_type', None) != self.last_type

    def _on_deck_analyze(self):
        if not self.last_state:
            return
        self._js('app.setButtonState("btn-deck", "分析中…", true)')
        threading.Thread(target=self._do_deck_strategy, daemon=True).start()

    # ══════════════════════════════════════════
    #  HELPERS (compatibility stubs)
    # ══════════════════════════════════════════
    def _set_text(self, target_name, text):
        """Compatibility helper. target_name is a string key like 'box_advice'."""
        # This method is now only called from data.py for box_deck_list etc.
        # Those callers pass the actual box object (from CTk era).
        # In the new architecture, display methods use _js() directly.
        pass

    def _append_text(self, target_name, text):
        pass

    def _render_formatted(self, target_name, text, header=""):
        """Compatibility stub — real rendering is _render_formatted_html."""
        pass

    # ══════════════════════════════════════════
    #  RUN
    # ══════════════════════════════════════════
    def _on_window_ready(self):
        import time
        time.sleep(0.5)  # Small delay for DOM to be fully ready
        self._window_ready.set()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def run(self):
        # Start polling thread immediately, don't wait for callback
        def _startup():
            import time
            time.sleep(1.5)  # Give window 1.5s to load
            if not self._window_ready.is_set():
                self._window_ready.set()
                threading.Thread(target=self._poll_loop, daemon=True).start()
        threading.Thread(target=_startup, daemon=True).start()
        webview.start(self._on_window_ready, debug=False)


if __name__ == "__main__":
    app = STS2Commander()
    app.run()
