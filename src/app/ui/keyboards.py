from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ── Callback data constants ──────────────────────────────────
CB_START_SIGN   = "start_sign"
CB_ZONE_TOGGLE  = "zt"
CB_ZONE_ALL     = "za"
CB_ZONE_CONFIRM = "zc"


def _tier_label(conf: float) -> str:
    """Helper to label match quality tiers."""
    if conf >= 0.95: return "exact"
    if conf >= 0.85: return "case-insensitive"
    return "partial"


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Return the primary 'Start' button keyboard."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✍️  Mulai tanda tangan", callback_data=CB_START_SIGN),
    ]])


def get_zone_selection_keyboard(zones: list, selected: set) -> InlineKeyboardMarkup:
    """
    Build the multi-select keyboard for DOCX zones.
    
    Args:
        zones: List of detected zone dictionaries.
        selected: Set of indices representing currently selected zones.
    """
    rows = []
    for i, z in enumerate(zones):
        name  = (z.get("matched_name") or z.get("keyword") or f"Zona {i+1}")[:35]
        conf  = z["confidence"]
        check = "✅" if i in selected else "⬜"
        label = f"{check} {name} ({conf:.0%} · {_tier_label(conf)})"
        rows.append([InlineKeyboardButton(label, callback_data=f"{CB_ZONE_TOGGLE}:{i}")])

    rows.append([
        InlineKeyboardButton("☑️  Pilih semua", callback_data=CB_ZONE_ALL),
        InlineKeyboardButton(
            f"✍️  Proses ({len(selected)} zona)",
            callback_data=CB_ZONE_CONFIRM,
        ),
    ])
    return InlineKeyboardMarkup(rows)
