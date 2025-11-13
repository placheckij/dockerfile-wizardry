# 📚 Architecture Documentation

❌ **This documentation file should NOT be in the production container!**

## Why?
- Documentation is for developers, not runtime
- Increases image size unnecessarily
- May contain internal architectural details
- Not needed by the running application

## How is it excluded?
In the Dockerfile, we use:
```dockerfile
COPY --chown=wizard:wizards ./spellbook/spells ./spells
COPY --chown=wizard:wizards ./spellbook/potions ./potions
COPY --chown=wizard:wizards ./spellbook/enchantments ./enchantments
```

Notice we're **NOT** copying:
- `./spellbook/docs` ← This directory
- `./spellbook/tests` ← Test files
- `./spellbook/.env.example` ← Example configs
- Any other non-essential files

This is **CIS 4.9**: Only copy what you need!
