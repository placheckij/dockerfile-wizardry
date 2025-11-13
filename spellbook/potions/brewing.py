"""
🧪 Potion Brewing Utilities
More production code that's essential for the application.
"""

POTION_RECIPES = {
    "healing": ["phoenix_tear", "unicorn_hair", "moonwater"],
    "strength": ["giant_toe", "iron_dust", "fire_salts"],
    "invisibility": ["chameleon_scale", "void_essence", "ghost_pepper"],
    "speed": ["lightning_essence", "hummingbird_feather", "quicksilver"]
}


def brew_potion(potion_type: str) -> list:
    """
    Brew a magical potion.
    
    This represents utility code that MUST be in the container.
    """
    return POTION_RECIPES.get(
        potion_type.lower(),
        ["water", "hope", "disappointment"]  # Failed potion
    )


def get_recipe_count() -> int:
    """Count available recipes"""
    return len(POTION_RECIPES)
