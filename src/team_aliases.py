"""Team name alias configuration for championship aggregation.

Key: alias as it may appear in event data
Value: canonical championship team name
"""

TEAM_NAME_ALIASES = {
    # Example from current data
    "Sphinxi": "Sphinxi und Indiana Jones",
    "Sphinxi & Indiana Jones": "Sphinxi und Indiana Jones",

    # Lavezzi variants seen in imported event data
    "Lavezzi‘s verschwörung": "Lavezzi's Verschwörung",
    "Lavezzis Erben": "Lavezzi's Erben",

    # Turboschnecken with soft hyphen (appears in some Excel files)
    "Turbo­schnecken": "Turboschnecken",

    # Optional normalization seen in existing data
    "Orientierungslosen": "Orientierungslose",

    "Mehr oder weniger": "Mehr oder Weniger",

    "Nicht für Elend": "Not für Elend",

    "katzbach": "Katzbach",

    "Quiz(n)losen": "Die Quiz(n)losen",

    "Und am letzten Platz*": "Und am letzten Platz",

    "Wigl Wogl": "Wiglwogl",

    "Zimmermann's Friends": "Zimmerman's Friends",

    "Schmeckt ein bisschen nussig": "schmeckt ein bisschen nussig",
}
