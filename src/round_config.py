"""Round names configuration for PubQuiz reporting."""

PUZZLE_NAME = "Puzzle"

ROUND_NAMES = {
    1: "Allgemeinwissen",
    2: "Geographie",
    3: "Entertainment",
    4: "Sport",
    5: "Linz/OÖ",
    6: "Geschichte",
    7: "Bilderrunde",
    8: "Interessantes",
    9: "Überraschung",
    10: "Musik",
}

CATEGORY_NAMES = (PUZZLE_NAME, *ROUND_NAMES.values())
CATEGORY_ORDER = {name: index for index, name in enumerate(CATEGORY_NAMES)}
