"""
🧪 Test Suite for Spells
❌ This file should NOT be copied to the production container!

Notice in the Dockerfile that we copy specific directories (spells/, potions/, enchantments/)
but NOT the tests/ directory. This demonstrates CIS 4.9 best practice.
"""

import pytest
from spells.incantations import cast_spell, list_available_spells


def test_cast_known_spell():
    """Test casting a spell that exists"""
    result = cast_spell("fireball")
    assert "🔥" in result
    assert "destruction" in result.lower()


def test_cast_unknown_spell():
    """Test casting a spell that doesn't exist"""
    result = cast_spell("banana")
    assert "Unknown" in result or "❌" in result


def test_list_spells():
    """Test listing available spells"""
    spells = list_available_spells()
    assert len(spells) > 0
    assert "fireball" in spells


def test_spell_case_insensitive():
    """Test that spell names are case-insensitive"""
    result1 = cast_spell("FIREBALL")
    result2 = cast_spell("fireball")
    assert result1 == result2


# ═══════════════════════════════════════════════════════════════════════
# 🎓 Why this file is NOT in the container:
# • Tests are only needed during development/CI
# • Including them would increase image size unnecessarily
# • Test dependencies (pytest, etc.) aren't needed in production
# • Reduces attack surface by excluding non-essential code
# ═══════════════════════════════════════════════════════════════════════
