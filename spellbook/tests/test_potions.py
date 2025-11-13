"""
🧪 Test Suite for Potions
❌ Another test file that stays OUT of the production container!
"""

import pytest
from potions.brewing import brew_potion, get_recipe_count


def test_brew_known_potion():
    """Test brewing a potion with a known recipe"""
    ingredients = brew_potion("healing")
    assert len(ingredients) > 0
    assert "phoenix_tear" in ingredients


def test_brew_unknown_potion():
    """Test brewing with an unknown recipe"""
    ingredients = brew_potion("rocket_fuel")
    assert "disappointment" in ingredients


def test_recipe_count():
    """Test counting available recipes"""
    count = get_recipe_count()
    assert count >= 4


# 💡 Note: This entire tests/ directory is excluded from the Docker image
# to keep it lean and secure!
