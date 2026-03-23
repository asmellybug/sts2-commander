"""Tests for overlay/display.py — pure rendering utilities."""
import sys
from unittest.mock import MagicMock

# Mock requests before importing display (avoids broken certifi)
if "requests" not in sys.modules:
    sys.modules["requests"] = MagicMock()

import pytest
from overlay.display import DisplayMixin


@pytest.fixture
def display():
    """Minimal DisplayMixin instance for testing instance methods."""
    return DisplayMixin()


# ── _get_power_amount (static) ────────────────────

class TestGetPowerAmount:
    def test_single_power(self):
        powers = [{"id": "Strength", "name": "力量", "amount": 3}]
        assert DisplayMixin._get_power_amount(powers, "Strength", "力量") == 3

    def test_stacked_powers(self):
        powers = [
            {"id": "Strength", "amount": 2},
            {"id": "Strength", "amount": 1},
        ]
        assert DisplayMixin._get_power_amount(powers, "Strength") == 3

    def test_missing_power(self):
        powers = [{"id": "Dexterity", "amount": 2}]
        assert DisplayMixin._get_power_amount(powers, "Strength") == 0

    def test_empty_powers(self):
        assert DisplayMixin._get_power_amount([], "Strength") == 0

    def test_match_by_cn_name(self):
        powers = [{"id": "x", "name": "力量", "amount": 5}]
        assert DisplayMixin._get_power_amount(powers, "Strength", "力量") == 5

    def test_no_amount_defaults_zero(self):
        powers = [{"id": "Strength"}]
        assert DisplayMixin._get_power_amount(powers, "Strength") == 0


# ── _has_power (static) ──────────────────────────

class TestHasPower:
    def test_has_by_id(self):
        powers = [{"id": "Weak", "name": "虚弱", "amount": 1}]
        assert DisplayMixin._has_power(powers, "Weak") is True

    def test_has_by_cn_name(self):
        powers = [{"id": "x", "name": "易伤", "amount": 2}]
        assert DisplayMixin._has_power(powers, "Vulnerable", "易伤") is True

    def test_not_found(self):
        powers = [{"id": "Strength", "amount": 3}]
        assert DisplayMixin._has_power(powers, "Weak") is False

    def test_empty_list(self):
        assert DisplayMixin._has_power([], "Strength") is False


# ── _pile_summary (static) ───────────────────────

class TestPileSummary:
    def test_empty_pile(self):
        assert DisplayMixin._pile_summary([]) == ""

    def test_single_card(self):
        pile = [{"name": "打击"}]
        assert DisplayMixin._pile_summary(pile) == "打击"

    def test_duplicate_cards(self):
        pile = [{"name": "打击"}, {"name": "打击"}, {"name": "防御"}]
        result = DisplayMixin._pile_summary(pile)
        assert "打击×2" in result
        assert "防御" in result

    def test_no_duplicates(self):
        pile = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        result = DisplayMixin._pile_summary(pile)
        # No ×N suffix when count is 1
        assert "×" not in result

    def test_missing_name(self):
        pile = [{}]
        assert "?" in DisplayMixin._pile_summary(pile)


# ── _colorize_desc ───────────────────────────────

class TestColorizeDesc:
    def test_gold(self, display):
        result = display._colorize_desc("150金币")
        assert "color:var(--gold)" in result
        assert "150" in result

    def test_gold_short(self, display):
        result = display._colorize_desc("50金")
        assert "color:var(--gold)" in result

    def test_hp(self, display):
        result = display._colorize_desc("7最大HP")
        assert "color:var(--hp)" in result

    def test_damage(self, display):
        result = display._colorize_desc("13点伤害")
        assert "color:var(--hp)" in result

    def test_damage_short(self, display):
        result = display._colorize_desc("8伤害")
        assert "color:var(--hp)" in result

    def test_lethal(self, display):
        result = display._colorize_desc("致命")
        assert "color:var(--hp)" in result

    def test_block(self, display):
        result = display._colorize_desc("8格挡")
        assert "color:var(--block)" in result

    def test_buff_strength(self, display):
        result = display._colorize_desc("2力量")
        assert "color:var(--buff)" in result

    def test_buff_dexterity(self, display):
        result = display._colorize_desc("3敏捷")
        assert "color:var(--buff)" in result

    def test_debuff_weak(self, display):
        result = display._colorize_desc("2虚弱")
        assert "color:var(--debuff)" in result

    def test_debuff_word(self, display):
        result = display._colorize_desc("虚弱")
        assert "color:var(--debuff)" in result

    def test_heal(self, display):
        result = display._colorize_desc("回复35%最大HP")
        assert "color:var(--buff)" in result

    def test_upgrade(self, display):
        result = display._colorize_desc("升级一张牌")
        assert "color:var(--gold)" in result

    def test_remove(self, display):
        result = display._colorize_desc("移除一张牌")
        assert "color:var(--hp)" in result

    def test_quoted_item(self, display):
        result = display._colorize_desc("获得「旋风斩」")
        assert "color:var(--accent2)" in result
        assert "旋风斩" in result

    def test_enchantment(self, display):
        result = display._colorize_desc("附魔: 涡旋")
        assert "color:var(--accent2)" in result

    def test_enchantment_keyword(self, display):
        result = display._colorize_desc("烈焰伤害")
        assert "color:var(--accent2)" in result

    def test_map_elite(self, display):
        result = display._colorize_desc("精英战斗")
        assert "node-elite" in result

    def test_map_rest(self, display):
        result = display._colorize_desc("篝火")
        assert "node-rest" in result

    def test_map_shop(self, display):
        result = display._colorize_desc("商店")
        assert "node-shop" in result

    def test_map_event(self, display):
        result = display._colorize_desc("未知事件")
        assert "node-event" in result

    def test_plain_text_unchanged(self, display):
        text = "普通的描述文字"
        result = display._colorize_desc(text)
        assert "普通的描述文字" in result
        assert "color:" not in result

    def test_html_escaped(self, display):
        result = display._colorize_desc("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_energy(self, display):
        result = display._colorize_desc("2能量")
        assert "color:var(--buff)" in result


# ── _render_option ───────────────────────────────

class TestRenderOption:
    def test_label_only(self, display):
        result = display._render_option("休息")
        assert "option-block" in result
        assert "option-label" in result
        assert "休息" in result

    def test_with_description(self, display):
        result = display._render_option("休息", "回复30%最大HP")
        assert "option-desc" in result
        assert "30" in result

    def test_html_escape_label(self, display):
        result = display._render_option("<b>test</b>")
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    def test_no_desc_no_option_desc(self, display):
        result = display._render_option("锻造")
        assert "option-desc" not in result
