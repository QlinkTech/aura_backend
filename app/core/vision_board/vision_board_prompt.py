def build_prompt(vibe: dict, answers: dict) -> str:
    """
    Dynamically builds a vision board prompt based on vibe and user answers.
    """

    # user answers
    name = answers.get("name", "")
    limitless_identity = answers.get("limitless_identity", "")
    goals = answers.get("goals", "")
    success_metrics = answers.get("success_metrics", "")
    pinch_moment = answers.get("pinch_moment", "")
    feelings = answers.get("feelings", "")
    frequency_anchor = answers.get("frequency_anchor", "")
    secret_craving = answers.get("secret_craving", "")
    north_star = answers.get("north_star", "")

    # which vibe is chosen
    key = (vibe.get("key") or "").lower()

    # style + text dictionary for each vibe
    vibe_styles = {
        "boss": {
            "background": "deep burgundy #4C1F26",
            "palette": "Gold, Jet Black, Champagne",
            "header_font": "gold serif",
            "visuals": [
                f"Identity – Symbol of {limitless_identity} in a luxury-office vibe (designer bag, stilettos, red lips props).",
                f"Goals montage – Images for {goals}; overlay '{success_metrics}' on a wealth dashboard.",
                f"Luxury milestone – Photo of {pinch_moment}.",
                "Relationships – Hands or silhouettes celebrating; tie in Jet-Black & gold.",
                f"Wellness – Still-life for {feelings} with champagne notebook, candle.",
                "Work-life shift – Visual metaphor for letting go of what no longer serves.",
                f"Wealth anchor – Gold card / cash stack for {frequency_anchor}.",
            ],
            "texts": [
                "Money flows to me in wildly luxurious and effortless ways.",
                f"I fully own my desire for {secret_craving}.",
                f"When I've manifested this life I will feel {north_star}.",
            ]
        },
        "motherhood": {
            "background": "warm ivory #F6F3EF",
            "palette": "Sage Green, Terracotta, Dusty Rose, touches of Gold",
            "header_font": "sage serif",
            "visuals": [
                f"Identity – {limitless_identity} symbol in a cosy, sunlit setting (knit sweater, legacy books).",
                f"Goals montage – Images for {goals} with trust-fund ledger overlay '{success_metrics}'.",
                f"Luxury milestone – Photo of {pinch_moment}.",
                "Relationships – Family hands, baby feet, garden scene.",
                f"Wellness – Tea, journal, barefoot grass for {feelings}.",
                "Visual metaphor for clearing space and welcoming harmony.",
                f"Frequency anchor – Abundant greenery symbolising {frequency_anchor}.",
            ],
            "texts": [
                "I am building a legacy of love, wealth, and wisdom—one soft moment at a time.",
                f"I fully own my desire for {secret_craving}.",
                f"When I've manifested this life I will feel {north_star}.",
            ]
        },
        "business": {
            "background": "rich navy #0F223C",
            "palette": "Emerald, White, Metallic Silver",
            "header_font": "silver serif",
            "visuals": [
                f"Identity – {limitless_identity} symbol in high-tech office (MacBook, AirPods, emerald plant).",
                f"Goals montage – Images for {goals} with launch calendar overlay '{success_metrics}'.",
                f"Luxury milestone – Photo of {pinch_moment}.",
                "Relationships – Handshake silhouette / partnership contract.",
                f"Wellness – Minimalist diffuser, matcha, reflecting {feelings}.",
                "Visual metaphor for releasing overwhelm and embracing clarity.",
                f"Frequency anchor – Sales chart arrow up for {frequency_anchor}.",
            ],
            "texts": [
                "My work expands with ease, grace, and massive results.",
                f"I fully own my desire for {secret_craving}.",
                f"When I've manifested this life I will feel {north_star}.",
            ]
        },
        "healing": {
            "background": "soft lavender #D9C8F0",
            "palette": "Blush Pink, Water Blue, Mocha, Gold sparks",
            "header_font": "lavender serif",
            "visuals": [
                f"Identity – {limitless_identity} symbol cocooned in candlelight.",
                f"Goals montage – Images for {goals} (rivers, breathwork mat) with '{success_metrics}' in moon-script.",
                f"Luxury milestone – Photo of {pinch_moment}.",
                "Inner child / security – Soft toy or child photo silhouette.",
                f"Wellness – Journals, cacao mug, crystals for {feelings}.",
                "Visual metaphor for transformation and healing.",
                f"Frequency anchor – Flowing water or butterfly for {frequency_anchor}.",
            ],
            "texts": [
                "I'm safe to slow down, to feel, and to rise again in wholeness.",
                f"I fully own my desire for {secret_craving}.",
                f"When I've manifested this life I will feel {north_star}.",
            ]
        },
        "magnetic": {
            "background": "deep rose #6B2C3A",
            "palette": "Gold, Nude, Plum highlights",
            "header_font": "gold cursive serif",
            "visuals": [
                f"Identity – {limitless_identity} symbol in satin gown & mirror glow.",
                f"Goals montage – Images for {goals} with '{success_metrics}' in gold callout.",
                f"Luxury milestone – Photo of {pinch_moment} (romantic dinner, jewel).",
                "Relationships – Interlaced hands with roses.",
                f"Wellness – Perfume bottle, dance shoes representing {feelings}.",
                "Visual metaphor for breaking free from limitations and stepping into radiance.",
                f"Frequency anchor – Radiant candle halo for {frequency_anchor}.",
            ],
            "texts": [
                "I'm magnetic, radiant, and deeply loved just as I am.",
                f"I fully own my desire for {secret_craving}.",
                f"When I've manifested this life I will feel {north_star}.",
            ]
        },
        "minimalist": {
            "background": "clean white #FFFFFF",
            "palette": "Sand, Eucalyptus, Greige, Clear Glass highlights",
            "header_font": "greige serif",
            "visuals": [
                f"Identity – {limitless_identity} symbol (capsule wardrobe, glass water bottle).",
                f"Goals montage – Flat-lay of {goals} with minimalist overlay '{success_metrics}'.",
                f"Luxury milestone – Photo of {pinch_moment} (open-space home, Tesla key fob).",
                "Relationships – Two ceramic mugs on a blank table.",
                f"Wellness – Time-block calendar, clear desk for {feelings}.",
                "Visual metaphor for clearing digital and mental clutter.",
                f"Frequency anchor – Open window & fresh air symbolising {frequency_anchor}.",
            ],
            "texts": [
                "Clarity is my currency. I only do what lights me up.",
                f"I fully own my desire for {secret_craving}.",
                f"When I've manifested this life I will feel {north_star}.",
            ]
        }
    }

    # pick selected vibe style
    style = vibe_styles.get(key)

    if not style:
        return """Create an ultra-realistic 4-image collage arranged in a 2×2 grid with a thin gold border and a white backdrop.
        Place a round badge at the center that contains the affirmation in an elegant serif font.

        Quadrant mapping (clockwise from top-left):
        1. Top-Left – Identity & Self-Worth
        2. Top-Right – Business, Wealth & Expansion
        3. Bottom-Right – Wellness, Rituals & Emotional Regulation
        4. Bottom-Left – Relationships & Security"""

    # assemble final prompt
    visuals_block = "\n".join([f"{i+1}. {v}" for i, v in enumerate(style["visuals"])])
    texts_block = "\n• ".join(style["texts"])

    return f"""Create an ultra-realistic Pinterest-style vision board in 9:16 format (1080x1920 px).

        STYLE
        • Background: {style['background']}  
        • Palette: {style['palette']}  
        • Overlapping visuals; no visible faces.

        HEADER
        "{name}'s vision board" ({style['header_font']}, centred top; appears only once).

        VISUALS
        {visuals_block}

        TEXT STRIPS
        • {texts_block}

        Ensure all text is sharp and aesthetic."""
