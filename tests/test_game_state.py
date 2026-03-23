"""Tests for overlay/game_state.py — state management classes."""
import pytest
from overlay.game_state import CombatState, DeckState, GameState


# ── CombatState ───────────────────────────────────

class TestCombatState:
    def test_initial_values(self):
        cs = CombatState()
        assert cs.start_hp == 0
        assert cs.start_floor == 0
        assert cs.rounds == 0
        assert cs.log == []

    def test_reset(self):
        cs = CombatState()
        cs.start_hp = 50
        cs.rounds = 3
        cs.log.append({"round": 1})
        cs.reset()
        assert cs.start_hp == 0
        assert cs.rounds == 0
        assert cs.log == []


# ── DeckState ─────────────────────────────────────

class TestDeckState:
    def test_initial_values(self):
        ds = DeckState()
        assert ds.acquired == []
        assert ds.removed == []
        assert ds.archetype == ""
        assert ds.analysis_text == ""

    def test_reset(self):
        ds = DeckState()
        ds.acquired.append("旋风斩")
        ds.removed.append("打击")
        ds.archetype = "力量流"
        ds.reset()
        assert ds.acquired == []
        assert ds.removed == []
        assert ds.archetype == ""


# ── GameState ─────────────────────────────────────

class TestGameState:
    def test_initial_state(self):
        gs = GameState()
        assert gs.raw is None
        assert gs.state_type is None
        assert gs.player == {}
        assert gs.run == {}
        assert gs.round == -1

    def test_update_battle_state(self):
        gs = GameState()
        gs.update({
            "state_type": "battle",
            "battle": {"player": {"hp": 50, "max_hp": 70, "gold": 100}},
            "run": {"floor": 5, "act": 1, "ascension": 0},
        })
        assert gs.state_type == "battle"
        assert gs.player["hp"] == 50
        assert gs.run["floor"] == 5

    def test_update_event_state(self):
        gs = GameState()
        gs.update({
            "state_type": "event",
            "player": {"hp": 30, "max_hp": 70, "character": "战士"},
            "run": {"floor": 3, "act": 1},
        })
        assert gs.state_type == "event"
        assert gs.player["character"] == "战士"

    def test_update_preserves_player_on_empty(self):
        gs = GameState()
        gs.update({"battle": {"player": {"hp": 50}}, "run": {"floor": 1}})
        gs.update({"state_type": "map"})  # no player in map state
        assert gs.player["hp"] == 50  # preserved from previous

    def test_properties(self):
        gs = GameState()
        gs.update({
            "battle": {"player": {"hp": 40, "max_hp": 80, "gold": 200, "character": "盗贼"}},
            "run": {"floor": 7, "act": 2, "ascension": 5},
        })
        assert gs.hp == 40
        assert gs.max_hp == 80
        assert gs.gold == 200
        assert gs.character == "盗贼"
        assert gs.floor == 7
        assert gs.act == 2
        assert gs.ascension == 5

    def test_properties_default_values(self):
        gs = GameState()
        assert gs.hp == 0
        assert gs.max_hp == 0
        assert gs.gold == 0
        assert gs.character == ""
        assert gs.floor == 0
        assert gs.act == 0

    def test_get_player_from_state(self):
        gs = GameState()
        state = {"battle": {"player": {"hp": 60}}}
        p = gs.get_player(state)
        assert p["hp"] == 60

    def test_get_player_fallback_to_cached(self):
        gs = GameState()
        gs.update({"battle": {"player": {"hp": 45}}})
        p = gs.get_player({})
        assert p["hp"] == 45

    def test_get_player_empty(self):
        gs = GameState()
        p = gs.get_player()
        assert p == {}

    def test_new_run_resets(self):
        gs = GameState()
        gs.update({"battle": {"player": {"hp": 50}}, "run": {"floor": 5}})
        gs.deck.acquired.append("重刃")
        gs.combat.rounds = 3
        gs.round = 5
        gs.new_run()
        assert gs.deck.acquired == []
        assert gs.combat.rounds == 0
        assert gs.round == -1
        assert gs.card_analyzed is False
