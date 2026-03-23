"""Tests for overlay/data.py — data loading with mocked file I/O."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from overlay.data import DataMixin


# ── _make_run_id ─────────────────────────────────

class TestMakeRunId:
    def _make_mixin(self, player=None, run=None, deck_acquired=None):
        m = DataMixin()
        m.last_player = player or {}
        m.last_run = run or {}
        m.deck_acquired = deck_acquired or []
        return m

    def test_basic_id(self):
        m = self._make_mixin(
            player={"character": "战士"},
            run={"act": 1},
            deck_acquired=["旋风斩", "重刃", "供奉"]
        )
        rid = m._make_run_id()
        assert "战士" in rid
        assert "旋风斩" in rid

    def test_empty_deck(self):
        m = self._make_mixin(player={"character": "盗贼"})
        rid = m._make_run_id()
        assert "init" in rid

    def test_no_player(self):
        m = self._make_mixin()
        rid = m._make_run_id()
        assert "?" in rid

    def test_deck_sorted(self):
        m = self._make_mixin(deck_acquired=["C", "A", "B"])
        rid = m._make_run_id()
        # Deck sig uses sorted first 5
        assert "A|B|C" in rid


# ── _get_relics_from_save ────────────────────────

class TestGetRelicsFromSave:
    def test_reads_relics(self, tmp_path):
        save_data = {
            "players": [{
                "relics": [
                    {"id": "RELIC.BurningBlood"},
                    {"id": "RELIC.Vajra"},
                ]
            }]
        }
        # _get_relics_from_save tries modded/ path first
        save_dir = tmp_path / "modded" / "profile1" / "saves"
        save_dir.mkdir(parents=True)
        (save_dir / "current_run.save").write_text(json.dumps(save_data))

        m = DataMixin()
        with patch("overlay.constants._SAVE_BASE", str(tmp_path)):
            relics = m._get_relics_from_save()

        assert len(relics) == 2
        assert relics[0]["name"] == "BurningBlood"
        assert relics[1]["name"] == "Vajra"

    def test_no_save_base(self):
        m = DataMixin()
        with patch("overlay.constants._SAVE_BASE", ""):
            assert m._get_relics_from_save() == []

    def test_missing_file_returns_empty(self):
        m = DataMixin()
        with patch("overlay.constants._SAVE_BASE", "/nonexistent/path"):
            assert m._get_relics_from_save() == []

    def test_empty_players(self, tmp_path):
        save_data = {"players": []}
        save_dir = tmp_path / "modded" / "profile1" / "saves"
        save_dir.mkdir(parents=True)
        (save_dir / "current_run.save").write_text(json.dumps(save_data))

        m = DataMixin()
        with patch("overlay.constants._SAVE_BASE", str(tmp_path)):
            relics = m._get_relics_from_save()
        assert relics == []


# ── _load_save_data ──────────────────────────────

class TestLoadSaveData:
    def test_loads_player(self, tmp_path):
        save_data = {
            "players": [{
                "character_id": "CHARACTER.IRONCLAD",
                "current_hp": 60,
                "max_hp": 80,
                "gold": 150,
                "max_energy": 3,
                "relics": [{"id": "RELIC.BurningBlood"}],
                "deck": [{"id": "CARD.Strike"}],
            }]
        }
        save_dir = tmp_path / "modded" / "profile1" / "saves"
        save_dir.mkdir(parents=True)
        (save_dir / "current_run.save").write_text(json.dumps(save_data))

        m = DataMixin()
        with patch("overlay.constants._SAVE_BASE", str(tmp_path)):
            player, deck = m._load_save_data()

        assert player["hp"] == 60
        assert player["max_hp"] == 80
        assert player["gold"] == 150
        assert len(player["relics"]) == 1
        assert player["relics"][0]["name"] == "BurningBlood"
        assert len(deck) == 1

    def test_no_save_base(self):
        m = DataMixin()
        with patch("overlay.constants._SAVE_BASE", ""):
            player, deck = m._load_save_data()
        assert player == {}
        assert deck == []
