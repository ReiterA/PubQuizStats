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
    "Mehr oder weniget": "Mehr oder Weniger",

    "Nicht für Elend": "Not für Elend",

    "katzbach": "Katzbach",

    "Quiz(n)losen": "Die Quiz(n)losen",

    "Und am letzten Platz*": "Und am letzten Platz",

    "Wigl Wogl": "Wiglwogl",

    "Zimmermann's Friends": "Zimmerman's Friends",

    "Die Quirligen Quiz Hühner": "Die quirligen Quizhühner",
    "Die quirligem Quizhühner": "Die quirligen Quizhühner",

    "Schmeckt ein bisschen nussig": "schmeckt ein bisschen nussig",

    "Team Nonsense": "Nonsense",

    "Die Woikis": "Die Wolki's",
    "die Woiki's": "Die Wolki's",
    "Woikis": "Die Wolki's",

    "Out of control": "Out of Control",

    "Man bringe denn Spritzwein": "Man bringe den Spritzwein",

    "Cpqc": "CPQC",

    "Schaukels­tuhlöl": "Schaukelstuhlöl",
}
