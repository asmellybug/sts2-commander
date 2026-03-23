"""Tests for overlay/constants.py — translation & mapping functions."""
import pytest
from overlay.constants import _cn_power, _cn_relic, _cn_potion, POWER_CN, RELIC_CN, POTION_CN


# ── _cn_power ──────────────────────────────────────

class TestCnPower:
    def test_known_power_by_name(self):
        assert _cn_power({"name": "Strength"}) == "力量"

    def test_known_power_by_id(self):
        assert _cn_power({"id": "Vulnerable", "name": ""}) == "易伤"

    def test_known_power_name_takes_priority(self):
        assert _cn_power({"name": "Strength", "id": "Dexterity"}) == "力量"

    def test_unknown_power_returns_name(self):
        assert _cn_power({"name": "UnknownBuff"}) == "UnknownBuff"

    def test_empty_dict_returns_empty(self):
        assert _cn_power({}) == ""

    def test_id_only(self):
        assert _cn_power({"id": "Focus"}) == "专注"

    def test_all_known_powers_translate(self):
        """Every entry in POWER_CN should be resolvable."""
        for en, cn in POWER_CN.items():
            assert _cn_power({"name": en}) == cn


# ── _cn_relic ──────────────────────────────────────

class TestCnRelic:
    def test_known_relic(self):
        assert _cn_relic("Burning Blood") == "燃烧之血"

    def test_another_known_relic(self):
        assert _cn_relic("Vajra") == "金刚杵"

    def test_unknown_relic_returns_original(self):
        assert _cn_relic("NonExistentRelic") == "NonExistentRelic"

    def test_empty_string(self):
        assert _cn_relic("") == ""


# ── _cn_potion ──────────────────────────────────────

class TestCnPotion:
    def test_known_potion(self):
        assert _cn_potion("Fire Potion") == "火焰药水"

    def test_another_known_potion(self):
        assert _cn_potion("Strength Potion") == "力量药水"

    def test_unknown_potion_returns_original(self):
        assert _cn_potion("MysteryBrew") == "MysteryBrew"

    def test_empty_string(self):
        assert _cn_potion("") == ""
