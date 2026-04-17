"""Team name alias configuration for championship aggregation.

Key: alias as it may appear in event data
Value: canonical championship team name
"""

TEAM_NAME_ALIASES = {
    # Example from current data
    "Sphinxi": "Sphinxi und Indiana Jones",
    "Sphinxi & Indiana Jones": "Sphinxi und Indiana Jones",

    # Turboschnecken with soft hyphen (appears in some Excel files)
    "Turbo­schnecken": "Turboschnecken",

    # Optional normalization seen in existing data
    "Orientierungslosen": "Orientierungslose",

    "Mehr oder weniger": "Mehr oder Weniger",

    "Nicht für Elend": "Not für Elend",
}
