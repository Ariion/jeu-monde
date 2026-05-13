SCREEN_W = 1280
SCREEN_H = 720
FPS = 60

TILE_W = 64
TILE_H = 32

WORLD_W = 80
WORLD_H = 80

T_DEEP_WATER = 0
T_WATER      = 1
T_SAND       = 2
T_GRASS      = 3
T_FOREST     = 4
T_HIGHLAND   = 5
T_MOUNTAIN   = 6
T_SNOW       = 7

TILE_COLORS = {
    T_DEEP_WATER: (15,  48, 120),
    T_WATER:      (30,  85, 175),
    T_SAND:       (205, 185, 110),
    T_GRASS:      (65,  140,  55),
    T_FOREST:     (25,   80,  25),
    T_HIGHLAND:   (105, 100,  90),
    T_MOUNTAIN:   (130, 122, 112),
    T_SNOW:       (222, 232, 248),
}

TILE_HEIGHTS = {
    T_DEEP_WATER: 0,
    T_WATER:      2,
    T_SAND:       4,
    T_GRASS:      6,
    T_FOREST:     8,
    T_HIGHLAND:   13,
    T_MOUNTAIN:   19,
    T_SNOW:       24,
}

TILE_WALKABLE = {
    T_DEEP_WATER: False,
    T_WATER:      False,
    T_SAND:       True,
    T_GRASS:      True,
    T_FOREST:     True,
    T_HIGHLAND:   True,
    T_MOUNTAIN:   False,
    T_SNOW:       False,
}

# (start_year, display_name, sky_rgb, short_description)
ERAS = [
    (0,     "Préhistoire",              (35,  25, 15),
     "Les premiers hominidés arpentent la Terre..."),
    (1000,  "Âge de Pierre",            (42,  33, 20),
     "Les outils de silex transforment la survie."),
    (3500,  "Âge du Bronze",            (48,  40, 22),
     "Le métal soude les premières cités."),
    (6000,  "Antiquité",                (58,  50, 35),
     "Empires et philosophes façonnent l'humanité."),
    (7800,  "Moyen-Âge",                (38,  42, 52),
     "Châteaux et cathédrales s'élèvent vers les cieux."),
    (8600,  "Renaissance",              (50,  48, 58),
     "L'art et la science renaissent en splendeur."),
    (9100,  "Révolution Industrielle",  (44,  44, 54),
     "La vapeur et l'acier transforment le monde."),
    (9700,  "Ère Moderne",              (28,  38, 68),
     "La technologie redessine la planète entière."),
    (10100, "Futur Proche",             (14,  18, 62),
     "Intelligence artificielle et transhumanisme émergent."),
    (10600, "Futur Lointain",           ( 7,   9, 38),
     "L'humanité conquiert les étoiles."),
]

TIME_SPEEDS = [0, 1, 5, 20, 100, 500, 2000]
DEFAULT_SPEED_IDX = 2  # 5 years/sec  (desktop free-play mode)

# ── Persistent world (epoch mode) ──────────────────────────────────────────
# The world "started" at this Unix timestamp and has been running ever since.
# 2026-05-13 00:00:00 UTC
EPOCH_TIMESTAMP    = 1778630400   # 2026-05-13 00:00:00 UTC
YEARS_PER_SECOND   = 1.0 / 60.0   # 1 real minute = 1 game year
#   → 1 real day  ≈ 1 440 game years
#   → 1 real week ≈ 10 080 game years  (reaches Modern era)

