import random
import math
from config import (WORLD_W, WORLD_H, ERAS, TIME_SPEEDS, DEFAULT_SPEED_IDX,
                    TILE_WALKABLE)

_SETTLE_MSGS = [
    ["Un groupe de chasseurs dresse un campement.", "Des abris de peaux apparaissent.",
     "Une tribu s'installe près d'un point d'eau."],
    ["Un village de huttes prend forme.", "Des greniers sont construits.",
     "Une communauté sédentaire émerge."],
    ["Une cité fortifiée s'élève.", "Des artisans fondent une nouvelle ville.",
     "Le commerce attire des colons."],
    ["Une cité-état prospère naît.", "Des temples s'élèvent vers le ciel.",
     "Un port commercial est établi."],
    ["Une ville fortifiée grandit.", "Une cathédrale domine le paysage.",
     "Un marché médiéval s'anime."],
    ["Une ville de la Renaissance fleurit.", "Savants et artistes s'y réunissent.",
     "Les arts et sciences y prospèrent."],
    ["Une cité industrielle s'étend.", "Les cheminées d'usines s'allument.",
     "Les rails unissent les villes."],
    ["Une métropole moderne se développe.", "Des gratte-ciel percent les nuages.",
     "Les réseaux numériques s'étendent."],
    ["Un complexe technologique est érigé.", "Les nœuds IA se multiplient.",
     "Les megastructures reconfigurent le paysage."],
    ["Une colonie spatiale est fondée.", "Les étoiles accueillent l'humanité.",
     "L'expansion interstellaire commence."],
]


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
        self.level = 0   # 0=camp … 5=megalopolis/spaceport


class Simulation:
    def __init__(self, tiles):
        self.tiles    = tiles
        self.year     = 0.0
        self.speed_idx = DEFAULT_SPEED_IDX
        self.paused   = False
        self.entities = []
        self.settlements = []
        self.events   = []          # (year, text) — full history
        self._active_events = []    # (text, remaining_seconds)
        self._era_idx = 0
        self._settle_cooldown = 0.0

        self._spawn_initial()

    # ------------------------------------------------------------------ public

    def get_era(self):
        idx = 0
        for i, era in enumerate(ERAS):
            if self.year >= era[0]:
                idx = i
        return idx, ERAS[idx]

    def population(self):
        return len(self.entities)

    def toggle_pause(self):
        self.paused = not self.paused

    def speed_up(self):
        self.speed_idx = min(len(TIME_SPEEDS) - 1, self.speed_idx + 1)

    def slow_down(self):
        self.speed_idx = max(1, self.speed_idx - 1)

    def update(self, dt):
        if self.paused:
            return

        dy = dt * TIME_SPEEDS[self.speed_idx]
        self.year += dy

        self._update_entities(dy)
        self._update_reproduction(dy)
        self._update_settlements(dy)
        self._check_era_transition()

        # Tick active event timers
        self._active_events = [
            (t, r - dt) for t, r in self._active_events if r - dt > 0
        ]
        self._settle_cooldown = max(0.0, self._settle_cooldown - dy)

    # ----------------------------------------------------------------- private

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
        move_dist = dy * 0.6          # world units per game-year
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

            nx = e.x + e.vx * move_dist
            ny = e.y + e.vy * move_dist
            nx = max(0.5, min(WORLD_W - 0.51, nx))
            ny = max(0.5, min(WORLD_H - 0.51, ny))

            if TILE_WALKABLE.get(tiles[int(nx)][int(ny)], False):
                e.x, e.y = nx, ny
            else:
                angle = random.uniform(0, math.tau)
                e.vx = math.cos(angle)
                e.vy = math.sin(angle)

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
        if era_idx < 1 or self._settle_cooldown > 0:
            return

        # Build density grid (tile resolution)
        density = {}
        for e in self.entities:
            key = (int(e.x), int(e.y))
            density[key] = density.get(key, 0) + 1

        existing = {(s.gx, s.gy) for s in self.settlements}
        threshold = max(2, 7 - era_idx)

        for (tx, ty), _ in density.items():
            nbr = sum(
                density.get((tx + dx, ty + dy_), 0)
                for dx in range(-4, 5)
                for dy_ in range(-4, 5)
            )
            if nbr < threshold:
                continue
            if (tx, ty) in existing:
                continue
            if any(abs(s.gx - tx) + abs(s.gy - ty) < 14 for s in self.settlements):
                continue
            s = Settlement(tx, ty, self.year)
            self.settlements.append(s)
            existing.add((tx, ty))
            self._add_event(random.choice(_SETTLE_MSGS[min(era_idx, len(_SETTLE_MSGS)-1)]))
            self._settle_cooldown = 100.0 + era_idx * 30
            break

        # Update settlement levels
        for s in self.settlements:
            nearby = sum(
                1 for e in self.entities
                if abs(e.x - s.gx) <= 7 and abs(e.y - s.gy) <= 7
            )
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
