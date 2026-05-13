import random
import math
import time as _time
from config import (WORLD_W, WORLD_H, ERAS, TIME_SPEEDS, DEFAULT_SPEED_IDX,
                    TILE_WALKABLE, T_GRASS, T_SAND, T_FOREST, T_HIGHLAND,
                    EPOCH_TIMESTAMP, YEARS_PER_SECOND)


# ── Narrative event messages per era ──────────────────────────────────────
_SETTLE_MSGS = [
    ["Un groupe de chasseurs dresse un campement.",
     "Des abris de peaux et de bois apparaissent.",
     "Une tribu s'installe près d'un point d'eau."],
    ["Un village de huttes prend forme.",
     "Des greniers de terre et de paille sont construits.",
     "Une communauté sédentaire émerge."],
    ["Une cité fortifiée s'élève.",
     "Des artisans fondent une nouvelle ville.",
     "Le commerce attire des colons sur ces terres."],
    ["Une cité-état prospère naît.",
     "Des temples s'élèvent vers le ciel.",
     "Un port commercial est établi sur la côte."],
    ["Une ville fortifiée de pierre grandit.",
     "Une cathédrale domine le paysage.",
     "Un marché médiéval s'anime au carrefour des routes."],
    ["Une ville de la Renaissance fleurit.",
     "Savants et artistes s'y réunissent.",
     "Les arts et les sciences y prospèrent."],
    ["Une cité industrielle s'étend.",
     "Les cheminées d'usines s'allument.",
     "Les rails relient les villes entre elles."],
    ["Une métropole moderne se développe.",
     "Des gratte-ciel percent les nuages.",
     "Les réseaux numériques s'étendent."],
    ["Un complexe technologique est érigé.",
     "Les nœuds d'IA se multiplient.",
     "Des mégastructures reconfigurent le paysage."],
    ["Une colonie spatiale est fondée.",
     "Les étoiles accueillent l'humanité.",
     "L'expansion interstellaire commence."],
]


# ── Entity (visual only in epoch mode) ────────────────────────────────────
class Entity:
    __slots__ = ['x', 'y', 'vx', 'vy', 'age', 'wander_cd']

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        angle = random.uniform(0, math.tau)
        self.vx = math.cos(angle)
        self.vy = math.sin(angle)
        self.age = random.uniform(0, 15)
        self.wander_cd = random.uniform(0, 6)


class Settlement:
    def __init__(self, gx, gy, founded_year):
        self.gx = gx
        self.gy = gy
        self.founded_year = founded_year
        self.population = 0
        self.level = 0


# ── Main simulation class ──────────────────────────────────────────────────
class Simulation:
    """
    Two modes:
      epoch=False  (default) — interactive desktop, manual time control.
      epoch=True             — persistent web mode, year driven by real clock.
                               All viewers see the same year simultaneously.
    """

    def __init__(self, tiles, epoch=False):
        self.tiles   = tiles
        self.epoch   = epoch
        self.paused  = False

        # free-play controls
        self.speed_idx     = DEFAULT_SPEED_IDX
        self._era_idx      = 0
        self._settle_cd    = 0.0

        self.entities    = []
        self.settlements = []
        self.events      = []          # (year, text) full history
        self._active_events = []       # (text, remaining_sec) for HUD

        if epoch:
            self._site_schedule = _precompute_sites(tiles)
            self.year = _epoch_year()
            self._bootstrap_epoch()
        else:
            self.year = 0.0
            self._spawn_initial()

    # ── public ──────────────────────────────────────────────────────────

    def get_era(self):
        idx = 0
        for i, era in enumerate(ERAS):
            if self.year >= era[0]:
                idx = i
        return idx, ERAS[idx]

    def population(self):
        return len(self.entities)

    def toggle_pause(self):
        if not self.epoch:
            self.paused = not self.paused

    def speed_up(self):
        if not self.epoch:
            self.speed_idx = min(len(TIME_SPEEDS) - 1, self.speed_idx + 1)

    def slow_down(self):
        if not self.epoch:
            self.speed_idx = max(1, self.speed_idx - 1)

    def update(self, dt):
        if self.epoch:
            new_year = _epoch_year()
            dy = new_year - self.year
            if dy <= 0:
                # still animate entities even if year hasn't changed
                self._animate_entities(0.016)
                return
            self.year = new_year
            self._epoch_update(dy)
        else:
            if self.paused:
                return
            dy = dt * TIME_SPEEDS[self.speed_idx]
            self.year += dy
            self._update_entities(dy)
            self._update_reproduction(dy)
            self._update_settlements(dy)
            self._check_era_transition()

        self._active_events = [
            (t, r - dt) for t, r in self._active_events if r - dt > 0
        ]

    # ── epoch-mode helpers ────────────────────────────────────────────────

    def _bootstrap_epoch(self):
        """Activate all settlements that should already exist at current year."""
        for (fy, gx, gy) in self._site_schedule:
            if fy <= self.year:
                s = Settlement(gx, gy, fy)
                s.level = _site_level(fy, self.year, self.get_era()[0])
                self.settlements.append(s)

        self._populate_entities_epoch()
        era_idx = self.get_era()[0]
        self._era_idx = era_idx

    def _epoch_update(self, dy):
        era_idx, _ = self.get_era()

        # Activate newly founded settlements
        for (fy, gx, gy) in self._site_schedule:
            if self.year - dy < fy <= self.year:
                s = Settlement(gx, gy, fy)
                s.level = 0
                self.settlements.append(s)
                msg = random.choice(_SETTLE_MSGS[min(era_idx, len(_SETTLE_MSGS)-1)])
                self._add_event(msg)

        # Update settlement levels
        for s in self.settlements:
            s.level = _site_level(s.founded_year, self.year, era_idx)

        # Sync entity count to expected population
        expected = _expected_population(self.year)
        current  = len(self.entities)
        if current < expected:
            self._populate_entities_epoch(expected - current)
        elif current > expected + 50:
            del self.entities[expected:]

        self._animate_entities(dy * 0.005)   # slow drift
        self._check_era_transition()

    def _populate_entities_epoch(self, count=None):
        """Spawn entities near active settlements (or scattered if none)."""
        target = _expected_population(self.year) if count is None else count
        tiles  = self.tiles

        if self.settlements:
            for _ in range(target):
                s = random.choice(self.settlements)
                r = random.gauss(0, 5)
                angle = random.uniform(0, math.tau)
                x = max(0.5, min(WORLD_W - 0.51, s.gx + math.cos(angle) * abs(r)))
                y = max(0.5, min(WORLD_H - 0.51, s.gy + math.sin(angle) * abs(r)))
                if TILE_WALKABLE.get(tiles[int(x)][int(y)], False):
                    self.entities.append(Entity(x, y))
        else:
            cx, cy = WORLD_W // 2, WORLD_H // 2
            for _ in range(target):
                x = max(0.5, min(WORLD_W - 0.51, cx + random.uniform(-12, 12)))
                y = max(0.5, min(WORLD_H - 0.51, cy + random.uniform(-12, 12)))
                if TILE_WALKABLE.get(tiles[int(x)][int(y)], False):
                    self.entities.append(Entity(x, y))

    def _animate_entities(self, move_dist):
        """Visually drift entities — cosmetic only, no birth/death in epoch mode."""
        tiles = self.tiles
        for e in self.entities:
            e.wander_cd -= 0.016
            if e.wander_cd <= 0:
                angle = random.uniform(0, math.tau)
                e.vx = math.cos(angle)
                e.vy = math.sin(angle)
                e.wander_cd = random.uniform(3, 9)
            nx = max(0.5, min(WORLD_W - 0.51, e.x + e.vx * move_dist))
            ny = max(0.5, min(WORLD_H - 0.51, e.y + e.vy * move_dist))
            if TILE_WALKABLE.get(tiles[int(nx)][int(ny)], False):
                e.x, e.y = nx, ny
            else:
                angle = random.uniform(0, math.tau)
                e.vx, e.vy = math.cos(angle), math.sin(angle)

    # ── free-play helpers ─────────────────────────────────────────────────

    def _spawn_initial(self):
        cx, cy = WORLD_W // 2, WORLD_H // 2
        candidates = [
            (x, y)
            for x in range(cx - 12, cx + 12)
            for y in range(cy - 12, cy + 12)
            if (0 <= x < WORLD_W and 0 <= y < WORLD_H
                and TILE_WALKABLE.get(self.tiles[x][y], False))
        ]
        random.shuffle(candidates)
        for gx, gy in candidates[:15]:
            self.entities.append(Entity(gx + 0.5, gy + 0.5))

    def _update_entities(self, dy):
        move_dist = dy * 0.6
        tiles = self.tiles
        dead  = []
        for e in self.entities:
            e.age += dy
            e.wander_cd -= dy
            if e.wander_cd <= 0:
                angle = random.uniform(0, math.tau)
                e.vx = math.cos(angle)
                e.vy = math.sin(angle)
                e.wander_cd = random.uniform(3, 9)
            nx = max(0.5, min(WORLD_W - 0.51, e.x + e.vx * move_dist))
            ny = max(0.5, min(WORLD_H - 0.51, e.y + e.vy * move_dist))
            if TILE_WALKABLE.get(tiles[int(nx)][int(ny)], False):
                e.x, e.y = nx, ny
            else:
                angle = random.uniform(0, math.tau)
                e.vx, e.vy = math.cos(angle), math.sin(angle)
            if e.age > 55 + random.uniform(-8, 15):
                dead.append(e)
        for e in dead:
            self.entities.remove(e)

    def _update_reproduction(self, dy):
        pop = len(self.entities)
        if pop == 0:
            return
        era_idx, _ = self.get_era()
        carry_cap  = 80 + era_idx * 400
        birth_rate = 0.07 * (1 + era_idx * 0.20)
        expected   = pop * birth_rate * dy * max(0, 1 - pop / carry_cap)
        while expected >= 1.0:
            self._spawn_child()
            expected -= 1.0
        if random.random() < expected:
            self._spawn_child()

    def _spawn_child(self):
        if not self.entities:
            return
        parent = random.choice(self.entities)
        x = max(0.5, min(WORLD_W - 0.51, parent.x + random.uniform(-2, 2)))
        y = max(0.5, min(WORLD_H - 0.51, parent.y + random.uniform(-2, 2)))
        if TILE_WALKABLE.get(self.tiles[int(x)][int(y)], False):
            self.entities.append(Entity(x, y))

    def _update_settlements(self, dy):
        era_idx, _ = self.get_era()
        if era_idx < 1 or self._settle_cd > 0:
            self._settle_cd = max(0.0, self._settle_cd - dy)
            return
        density = {}
        for e in self.entities:
            key = (int(e.x), int(e.y))
            density[key] = density.get(key, 0) + 1
        existing  = {(s.gx, s.gy) for s in self.settlements}
        threshold = max(2, 7 - era_idx)
        for (tx, ty) in list(density):
            nbr = sum(density.get((tx + dx, ty + dy_), 0)
                      for dx in range(-4, 5) for dy_ in range(-4, 5))
            if nbr < threshold:
                continue
            if (tx, ty) in existing:
                continue
            if any(abs(s.gx - tx) + abs(s.gy - ty) < 14 for s in self.settlements):
                continue
            s = Settlement(tx, ty, self.year)
            self.settlements.append(s)
            existing.add((tx, ty))
            msg = random.choice(_SETTLE_MSGS[min(era_idx, len(_SETTLE_MSGS)-1)])
            self._add_event(msg)
            self._settle_cd = 100.0 + era_idx * 30
            break
        for s in self.settlements:
            nearby = sum(1 for e in self.entities
                         if abs(e.x - s.gx) <= 7 and abs(e.y - s.gy) <= 7)
            s.population = nearby
            thresholds = [0, 4, 12, 35, 90, 200]
            for lvl in range(len(thresholds) - 1, -1, -1):
                if nearby >= thresholds[lvl] and era_idx >= lvl:
                    s.level = lvl
                    break

    def _check_era_transition(self):
        era_idx, era = self.get_era()
        if era_idx > self._era_idx:
            self._era_idx = era_idx
            self._add_event(f"✦ Nouvelle ère : {era[1]} !")

    def _add_event(self, text):
        self.events.append((self.year, text))
        self._active_events.append((text, 9.0))


# ── module-level helpers ───────────────────────────────────────────────────

def _epoch_year():
    return (_time.time() - EPOCH_TIMESTAMP) * YEARS_PER_SECOND


def _expected_population(year):
    """Smooth logistic formula for visual population count."""
    max_pop = 600
    k       = 0.0006
    mid     = 5000
    return max(8, int(max_pop / (1 + math.exp(-k * (year - mid)))))


def _site_level(founded_year, current_year, era_idx):
    age = current_year - founded_year
    if   age > 5000 and era_idx >= 5: return 5
    elif age > 2000 and era_idx >= 4: return 4
    elif age > 1000 and era_idx >= 3: return 3
    elif age >  400 and era_idx >= 2: return 2
    elif age >  100 and era_idx >= 1: return 1
    return 0


def _precompute_sites(tiles, seed=42, max_sites=45):
    """
    Deterministically pre-generate settlement positions and founding years.
    Everyone running with the same seed sees the same world.
    """
    rng = random.Random(seed + 0xDEAD)

    candidates = [
        (x, y)
        for x in range(WORLD_W)
        for y in range(WORLD_H)
        if tiles[x][y] in (T_GRASS, T_SAND, T_FOREST, T_HIGHLAND)
    ]
    rng.shuffle(candidates)

    sites = []
    occupied = []
    for x, y in candidates:
        if len(sites) >= max_sites:
            break
        if any(abs(x - ox) + abs(y - oy) < 12 for ox, oy in occupied):
            continue
        sites.append((x, y))
        occupied.append((x, y))

    # Assign founding years: first at year 1000, then every ~150-300 years
    schedule = []
    year = 1000.0
    for (x, y) in sites:
        schedule.append((year, x, y))
        year += rng.uniform(120, 280)

    return schedule
