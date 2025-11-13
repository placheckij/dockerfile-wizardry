"""
🧙‍♂️ Dockerfile Wizardry - Main Application Entry Point
This demonstrates the main application file that gets copied to the container.
"""

from fastapi import FastAPI
from spells.incantations import cast_spell
from potions.brewing import brew_potion
from enchantments.protective import shield_charm

app = FastAPI(
    title="Dockerfile Wizardry API",
    description="A magical example of Docker best practices",
    version="1.0.0"
)


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker HEALTHCHECK"""
    return {"status": "healthy", "magic_level": "maximum"}


@app.get("/")
async def root():
    """Welcome to the wizardry!"""
    return {
        "message": "Welcome to Dockerfile Wizardry!",
        "tip": "Check out the Dockerfile to learn security best practices"
    }


@app.get("/spell/{spell_name}")
async def cast(spell_name: str):
    """Cast a spell - demonstrates modular code organization"""
    result = cast_spell(spell_name)
    return {"spell": spell_name, "effect": result}


@app.get("/potion/{potion_type}")
async def brew(potion_type: str):
    """Brew a potion - shows how modules are imported"""
    potion = brew_potion(potion_type)
    return {"potion": potion_type, "ingredients": potion}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
