"""Tests for overlay/card_db.py — CardDB lookup, normalization, and translation."""
import pytest
from overlay.card_db import CardDB


# ── _normalize_type (static) ──────────────────────

class TestNormalizeType:
    def test_attack(self):
        assert CardDB._normalize_type("attack") == "attack"

    def test_attack_uppercase_returns_other(self):
        """_normalize_type is case-sensitive — 'Attack' doesn't contain 'attack'."""
        assert CardDB._normalize_type("Attack") == "other"

    def test_attack_chinese(self):
        assert CardDB._normalize_type("攻击") == "attack"

    def test_skill(self):
        assert CardDB._normalize_type("skill") == "skill"

    def test_skill_chinese(self):
        assert CardDB._normalize_type("技能") == "skill"

    def test_power(self):
        assert CardDB._normalize_type("power") == "power"

    def test_power_chinese(self):
        assert CardDB._normalize_type("能力") == "power"

    def test_curse(self):
        assert CardDB._normalize_type("curse") == "curse"

    def test_status(self):
        assert CardDB._normalize_type("status") == "status"

    def test_unknown_returns_other(self):
        assert CardDB._normalize_type("xyz") == "other"

    def test_empty_returns_other(self):
        assert CardDB._normalize_type("") == "other"

    def test_mixed_case_returns_other(self):
        """_normalize_type is case-sensitive — callers lowercase before calling."""
        assert CardDB._normalize_type("ATTACK_CARD") == "other"


# ── _normalize_rarity (static) ────────────────────

class TestNormalizeRarity:
    def test_basic(self):
        assert CardDB._normalize_rarity("basic") == "basic"

    def test_basic_chinese(self):
        assert CardDB._normalize_rarity("基础") == "basic"

    def test_common(self):
        assert CardDB._normalize_rarity("common") == "common"

    def test_common_chinese(self):
        assert CardDB._normalize_rarity("普通") == "common"

    def test_uncommon(self):
        assert CardDB._normalize_rarity("uncommon") == "uncommon"

    def test_uncommon_chinese(self):
        assert CardDB._normalize_rarity("罕见") == "uncommon"

    def test_uncommon_before_common(self):
        """'uncommon' contains 'common' — must match uncommon first."""
        assert CardDB._normalize_rarity("Uncommon") == "uncommon"

    def test_rare(self):
        assert CardDB._normalize_rarity("rare") == "rare"

    def test_rare_chinese(self):
        assert CardDB._normalize_rarity("稀有") == "rare"

    def test_ancient(self):
        assert CardDB._normalize_rarity("ancient") == "ancient"

    def test_curse_maps_to_basic(self):
        assert CardDB._normalize_rarity("curse") == "basic"

    def test_status_maps_to_basic(self):
        assert CardDB._normalize_rarity("status") == "basic"

    def test_empty_returns_empty(self):
        assert CardDB._normalize_rarity("") == ""

    def test_unknown_returns_empty(self):
        assert CardDB._normalize_rarity("legendary") == ""


# ── _build_tooltip_html (static) ──────────────────

class TestBuildTooltipHtml:
    def test_full_tooltip(self):
        tip = {"cost": 1, "type": "攻击", "rarity": "common", "keywords": "消耗", "desc_cn": "造成6点伤害"}
        result = CardDB._build_tooltip_html(tip)
        assert "1费" in result
        assert "攻击" in result
        assert "common" in result
        assert "消耗" in result
        assert "造成6点伤害" in result

    def test_empty_tooltip(self):
        assert CardDB._build_tooltip_html({}) == ""

    def test_cost_zero(self):
        tip = {"cost": 0}
        result = CardDB._build_tooltip_html(tip)
        assert "0费" in result

    def test_desc_truncated_at_100(self):
        tip = {"desc_cn": "A" * 200}
        result = CardDB._build_tooltip_html(tip)
        # desc is truncated to 100 chars
        assert "A" * 100 in result
        assert "A" * 101 not in result

    def test_html_escaping(self):
        tip = {"type": "<script>"}
        result = CardDB._build_tooltip_html(tip)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


# ── CardDB instance methods (use fixture) ─────────

class TestCardDBLookup:
    def test_detail_known_card(self, card_db):
        d = card_db.detail("打击")
        # 打击 is in _SKIP_TOOLTIP, so might be empty — check a real card
        # Try a card that should exist
        all_names = list(card_db._tooltip.keys())
        if all_names:
            name = all_names[0]
            d = card_db.detail(name)
            assert isinstance(d, dict)
            assert "desc_cn" in d or "type" in d

    def test_detail_unknown_returns_empty(self, card_db):
        assert card_db.detail("不存在的牌") == {}

    def test_id_to_cn_unknown(self, card_db):
        assert card_db.id_to_cn("ZZZZZ_NONEXISTENT") == ""

    def test_get_type_from_dict(self, card_db):
        assert card_db.get_type({"type": "attack"}) == "attack"

    def test_get_type_from_card_type(self, card_db):
        assert card_db.get_type({"card_type": "Skill"}) == "skill"

    def test_get_type_empty(self, card_db):
        assert card_db.get_type({}) == "other"

    def test_get_rarity_from_dict(self, card_db):
        assert card_db.get_rarity({"rarity": "rare"}) == "rare"

    def test_get_rarity_basic_card(self, card_db):
        assert card_db.get_rarity({"name": "打击"}) == "basic"

    def test_get_rarity_strike_id(self, card_db):
        assert card_db.get_rarity({"id": "CARD.STRIKE_R", "name": ""}) == "basic"

    def test_fmt_name_with_name(self, card_db):
        assert card_db.fmt_name({"name": "旋风斩"}) == "旋风斩"

    def test_fmt_name_fallback_to_id(self, card_db):
        result = card_db.fmt_name({"id": "CARD.some_card"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_passthrough(self, card_db):
        """Text without card IDs should pass through unchanged."""
        text = "这是普通文本"
        assert card_db.translate(text) == text


# ── _fuzzy_find ───────────────────────────────────

class TestFuzzyFind:
    def test_exact_match(self, card_db):
        """If an exact English ID exists, fuzzy should find it."""
        if card_db._id_to_cn:
            eid = next(k for k in card_db._id_to_cn if len(k) >= 4)
            result = card_db._fuzzy_find(eid)
            assert result is not None

    def test_no_match(self, card_db):
        assert card_db._fuzzy_find("ZZZZZZZZZ") is None

    def test_short_word(self, card_db):
        """Very short inputs unlikely to match (min eid length is 4)."""
        result = card_db._fuzzy_find("AB")
        # Could match or not depending on data, but shouldn't crash
        assert result is None or isinstance(result, str)
