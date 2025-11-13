"""
🔮 Spell Casting Logic
Demonstrates production code that should be included in the container.
"""

SPELL_BOOK = {
    "fireball": "🔥 Blazing destruction",
    "heal": "💚 Restoration magic",
    "shield": "🛡️ Protective barrier",
    "teleport": "🌀 Instant transportation",
}


def cast_spell(spell_name: str) -> str:
    """
    Cast a spell from the wizardry spell book.

    This represents actual business logic that MUST be in the container.
    """
    return SPELL_BOOK.get(
        spell_name.lower(), "❌ Unknown spell - check your spellbook!"
    )


def list_available_spells() -> list:
    """Return all known spells"""
    return list(SPELL_BOOK.keys())
