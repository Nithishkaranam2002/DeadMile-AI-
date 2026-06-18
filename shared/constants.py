"""Trucking industry cost constants — defaults overridden by env via CostSettings."""

FUEL_PRICE_PER_GALLON = 3.90
AVG_MPG_LOADED = 6.0
AVG_MPG_EMPTY = 7.0
AVG_MPG = AVG_MPG_LOADED  # backward compat
DRIVER_CPM = 0.55
INSURANCE_PER_MILE = 0.08
MAINTENANCE_PER_MILE = 0.15
TOLLS_PER_MILE = 0.04
DISPATCH_FEE_PERCENT = 0.05
FACTORING_FEE_PERCENT = 0.03
OVERHEAD_PER_MILE = 0.05
DEADHEAD_FUEL_FACTOR = 1.0
DEADHEAD_DRIVER_FACTOR = 1.0
ROAD_FACTOR = 1.3

HAZMAT_PREMIUM = 0.15
TEAM_DRIVER_MULTIPLIER = 1.8

EQUIPMENT_FUEL_MODIFIER: dict[str, float] = {
    "Dry Van": 1.0,
    "Reefer": 1.15,
    "Flatbed": 0.95,
    "Step Deck": 0.95,
}

EQUIPMENT_MAINTENANCE_MODIFIER: dict[str, float] = {
    "Dry Van": 1.0,
    "Reefer": 1.30,
    "Flatbed": 1.10,
    "Step Deck": 1.10,
}

FLATBED_DEADHEAD_MODIFIER = 1.20

EQUIPMENT_TYPES = ("Dry Van", "Flatbed", "Reefer", "Step Deck")
REQUIREMENT_TYPES = ("None", "Hazmat", "Team", "Liftgate")

MARKET_LABELS = (
    (90, "Hot"),
    (70, "Warm"),
    (50, "Neutral"),
    (30, "Cool"),
    (0, "Dead"),
)

CLUSTER_LABELS = {
    0: "Mega Hub",
    1: "Origin Heavy",
    2: "Destination Heavy",
    3: "Specialty",
    4: "Underserved",
}


def market_label_for_score(score: float) -> str:
    for threshold, label in MARKET_LABELS:
        if score >= threshold:
            return label
    return "Dead"
