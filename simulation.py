import random
import math
import time as _time
from config import (WORLD_W, WORLD_H, ERAS, TIME_SPEEDS, DEFAULT_SPEED_IDX,
                    TILE_WALKABLE, T_GRASS, T_SAND, T_FOREST, T_HIGHLAND,
                    T_WATER, T_DEEP_WATER,
                    EPOCH_TIMESTAMP, YEARS_PER_SECOND)

# ── Era-based name pools ──────────────────────────────────────────────────
_NAMES = [
    ["Og","Urg","Muk","Kra","Brak","Tor","Wal","Shu","Gul","Uka","Dor","Bra","Rok","Mori","Wok"],
    ["Garoth","Temur","Alara","Brego","Nuri","Keld","Soma","Varg","Toba","Kira","Mela","Barla","Doru","Zena","Harg"],
    ["Sargon","Khemet","Niru","Amun","Sethi","Laras","Nefra","Kiran","Dagon","Ashur","Marduk","Tiamat","Enlil","Ishtar","Rimush"],
    ["Marcus","Lyra","Dion","Cassia","Theron","Aria","Phoebe","Leon","Helena","Titus","Livia","Cato","Lucius","Priya","Zenon"],
    ["Aldric","Mira","Gauthier","Isolde","Roland","Elara","Cedric","Brynn","Godwin","Margot","Tristan","Giselle","Hugo","Mathilde","Renaud"],
    ["Leonardo","Sofia","Marco","Elena","Lorenzo","Caterina","Giulio","Isabella","Raphael","Beatrice","Pietro","Fiora","Cosimo","Lucia","Angelo"],
    ["Victor","Emma","Henry","Clara","Arthur","Madeleine","Louis","Adèle","Gustave","Hortense","Émile","Constance","Léon","Juliette","Oscar"],
    ["Lucas","Emma","Noah","Sofia","Liam","Isabella","Ethan","Mia","Aiden","Olivia","Jayden","Chloe","Ryan","Zoe","Max"],
    ["Zara","Orion","Nova","Kyro","Lyra","Axel","Vex","Nyx","Rho","Cyan","Pixel","Echo","Flux","Aura","Zenith"],
    ["Aeon","Voxel","Nexus","Quasar","Synthos","Lyra","Helix","Pulsar","Axiom","Zenith","Photon","Iris","Nova","Vertex","Kron"],
]

# ── Clan colours (hue offsets, applied in renderer) ───────────────────────
CLAN_COLORS = [
    (220, 120,  80),   # 0 rouge
    ( 80, 180,  80),   # 1 vert
    ( 80, 140, 220),   # 2 bleu
    (220, 200,  60),   # 3 jaune
    (180,  80, 200),   # 4 violet
    ( 80, 210, 200),   # 5 cyan
]

# ── Entity states ─────────────────────────────────────────────────────────
S_WANDER  = 0
S_HUNT    = 1
S_DRINK   = 2
S_GATHER  = 3
S_REST    = 4
S_FOLLOW  = 5   # children following parent
S_FLEE    = 6   # prey fleeing
S_CHOP    = 7   # chop trees / gather wood
S_BUILD   = 8   # carry wood to shelter site

_ACTIVITY_LABELS = {
    S_WANDER: "Explore",
    S_HUNT:   "Chasse",
    S_DRINK:  "Va boire",
    S_GATHER: "Cueille",
    S_REST:   "Se repose",
    S_FOLLOW: "Suit le parent",
    S_CHOP:   "Coupe du bois",
    S_BUILD:  "Construit",
}

_eid_counter = 0


class Entity:
    __slots__ = [
        'x','y','vx','vy','age','wander_cd',
        'state','target_x','target_y','state_cd',
        'is_prey','name','eid','activity_desc','vigor',
        # needs
        'hunger','thirst','energy',
        # identity
        'clan_id','parent_eid',
        # memory (learned locations)
        'mem_water_x','mem_water_y',
        'mem_food_x','mem_food_y',
        # inventory
        'inv_wood',
    ]

    def __init__(self, x, y, era_idx=0, is_prey=False,
                 clan_id=None, parent=None):
        global _eid_counter
        _eid_counter += 1

        self.x = float(x)
        self.y = float(y)
        angle  = random.uniform(0, math.tau)
        self.vx, self.vy = math.cos(angle), math.sin(angle)
        self.age        = 0.0
        self.wander_cd  = random.uniform(0, 4)
        self.state      = S_WANDER
        self.target_x   = x
        self.target_y   = y
        self.state_cd   = random.uniform(0, 3)
        self.is_prey    = is_prey
        self.eid        = _eid_counter
        self.vigor      = random.uniform(0.6, 1.0)
        self.inv_wood   = 0

        # Needs — start at a random point so not everyone acts at once
        self.hunger = random.uniform(0.1, 0.4)
        self.thirst = random.uniform(0.1, 0.35)
        self.energy = random.uniform(0.6, 1.0)

        # Clan
        self.clan_id   = clan_id if clan_id is not None else random.randint(0, len(CLAN_COLORS)-1)
        self.parent_eid = parent.eid if parent else -1

        # Memory: learn from parent or default to nearby
        if parent and not is_prey:
            jitter = 3.0
            self.mem_water_x = max(0, min(WORLD_W-1, parent.mem_water_x + random.uniform(-jitter, jitter)))
            self.mem_water_y = max(0, min(WORLD_H-1, parent.mem_water_y + random.uniform(-jitter, jitter)))
            self.mem_food_x  = max(0, min(WORLD_W-1, parent.mem_food_x  + random.uniform(-jitter, jitter)))
            self.mem_food_y  = max(0, min(WORLD_H-1, parent.mem_food_y  + random.uniform(-jitter, jitter)))
        else:
            self.mem_water_x = x + random.uniform(-8, 8)
            self.mem_water_y = y + random.uniform(-8, 8)
            self.mem_food_x  = x + random.uniform(-8, 8)
            self.mem_food_y  = y + random.uniform(-8, 8)

        if is_prey:
            self.name = random.choice(["Cerf","Sanglier","Aurochs","Loup","Bison",
                                       "Chamois","Renard","Lynx","Ours","Bouquetin"])
        else:
            pool = _NAMES[min(era_idx, len(_NAMES)-1)]
            self.name = random.choice(pool)

        self.activity_desc = ""
        self._refresh_activity(era_idx)

    # ── computed properties ───────────────────────────────────────────────

    @property
    def health(self):
        return max(0.0, 1.0 - (self.age / 65.0) ** 1.8)

    @property
    def stage(self):
        if self.age < 13: return 'child'
        if self.age < 50: return 'adult'
        return 'elder'

    def _refresh_activity(self, era_idx):
        ei = min(era_idx, 9)
        labels = {
            S_WANDER: _WANDER_DESC[ei],
            S_HUNT:   _HUNT_DESC[ei],
            S_DRINK:  _DRINK_DESC[ei],
            S_GATHER: _GATHER_DESC[ei],
            S_REST:   _REST_DESC[ei],
            S_FOLLOW: ["Suit ses aînés", "Reste près de sa famille", "Apprend à marcher"],
            S_CHOP:   _CHOP_DESC[min(ei, len(_CHOP_DESC)-1)],
            S_BUILD:  _BUILD_DESC[min(ei, len(_BUILD_DESC)-1)],
        }
        pool = labels.get(self.state, _WANDER_DESC[ei])
        self.activity_desc = random.choice(pool)

    def needs_summary(self):
        """Short string for UI display."""
        parts = []
        if self.hunger > 0.6: parts.append("affamé")
        if self.thirst > 0.55: parts.append("assoiffé")
        if self.energy < 0.25: parts.append("épuisé")
        if not parts: parts.append("en bonne santé")
        return ", ".join(parts)


class Settlement:
    def __init__(self, gx, gy, founded_year):
        self.gx = gx
        self.gy = gy
        self.founded_year = founded_year
        self.population = 0
        self.level = 0


# ── Simulation ────────────────────────────────────────────────────────────

class Simulation:
    def __init__(self, tiles, epoch=False):
        self.tiles   = tiles
        self.epoch   = epoch
        self.paused  = False
        self.speed_idx  = DEFAULT_SPEED_IDX
        self._era_idx   = 0
        self._settle_cd = 0.0

        self.entities    = []
        self.prey        = []
        self.settlements = []
        self.events      = []
        self._active_events = []

        self._walkable   = [(x,y) for x in range(WORLD_W) for y in range(WORLD_H)
                            if TILE_WALKABLE.get(tiles[x][y], False)]
        water_set        = {(x,y) for x in range(WORLD_W) for y in range(WORLD_H)
                            if tiles[x][y] in (T_WATER, T_DEEP_WATER)}
        self._water_adj  = [(x,y) for x,y in self._walkable
                            if any((x+dx,y+dy) in water_set
                                   for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)))]
        self._food_tiles = [(x,y) for x,y in self._walkable
                            if tiles[x][y] in (T_FOREST, T_GRASS)]
        # Terraforming: wood remaining per forest tile (4 chops to clear)
        self.tile_resources  = {
            (x, y): 5
            for x in range(WORLD_W) for y in range(WORLD_H)
            if tiles[x][y] == T_FOREST
        }
        # Visual: recently cleared tiles (x, y, timer) — show stump until timer=0
        self.cleared_tiles   = []
        # Construction: accumulated wood at build sites {(x,y): wood_count}
        self._build_progress = {}

        if epoch:
            self._site_schedule = _precompute_sites(tiles)
            self.year = _epoch_year()
            self._bootstrap_epoch()
        else:
            self.year = 0.0
            self._spawn_initial()
            self._spawn_prey(18)

    # ── public ────────────────────────────────────────────────────────────

    def get_era(self):
        idx = 0
        for i, era in enumerate(ERAS):
            if self.year >= era[0]: idx = i
        return idx, ERAS[idx]

    def population(self):  return len(self.entities)
    def toggle_pause(self):
        if not self.epoch: self.paused = not self.paused
    def speed_up(self):
        if not self.epoch: self.speed_idx = min(len(TIME_SPEEDS)-1, self.speed_idx+1)
    def slow_down(self):
        if not self.epoch: self.speed_idx = max(1, self.speed_idx-1)

    def update(self, dt):
        if self.epoch:
            new_year = _epoch_year()
            dy = new_year - self.year
            self._animate_all(dt)
            if dy > 0:
                self.year = new_year
                self._epoch_update(dy)
        else:
            if self.paused: return
            dy = dt * TIME_SPEEDS[self.speed_idx]
            self.year += dy
            self._sim_step(dy)
            self._check_era_transition()
            self._settle_cd = max(0.0, self._settle_cd - dy)

        self._active_events = [
            (t, r-dt) for t,r in self._active_events if r-dt > 0]

    # ── internal step ────────────────────────────────────────────────────

    def _sim_step(self, dy):
        era_idx  = self._era_idx
        speed    = 2.5 + era_idx * 0.25
        move_d   = dy * speed
        tiles    = self.tiles
        dead     = []

        # Build a coarse spatial grid of entities for child→adult following
        parents  = {e.eid: e for e in self.entities}

        for e in self.entities:
            e.age += dy
            self._update_needs(e, dy)
            self._choose_goal(e, era_idx, parents)
            self._move_entity(e, move_d, tiles, era_idx)
            self._satisfy_needs(e, tiles)
            if e.age > 55 + random.uniform(-8, 15) or e.hunger > 1.0 or e.thirst > 1.2:
                dead.append(e)

        for e in dead:
            try: self.entities.remove(e)
            except ValueError: pass

        for p in self.prey:
            self._move_prey(p, move_d * 0.9, tiles)

        self._update_reproduction(dy)
        self._update_settlements(dy)

        # Replenish prey
        era_idx  = self._era_idx
        target   = max(5, 28 - era_idx * 3)
        if len(self.prey) < target:
            self._spawn_prey(1)

        # Decay stump visuals
        self.cleared_tiles = [(x, y, t - dy) for x, y, t in self.cleared_tiles if t > dy]

    def _animate_all(self, dt):
        """Epoch mode: animate at real-time speed."""
        era_idx  = self._era_idx
        speed    = 2.5 + era_idx * 0.25
        move_d   = dt * speed
        tiles    = self.tiles
        parents  = {e.eid: e for e in self.entities}

        for e in self.entities:
            self._update_needs(e, dt * 0.3)   # needs grow slowly in epoch
            self._choose_goal(e, era_idx, parents)
            self._move_entity(e, move_d, tiles, era_idx)
            self._satisfy_needs(e, tiles)

        for p in self.prey:
            self._move_prey(p, move_d * 0.85, tiles)

        self.cleared_tiles = [(x, y, t - dt) for x, y, t in self.cleared_tiles if t > dt]

    # ── needs ─────────────────────────────────────────────────────────────

    def _update_needs(self, e, dy):
        if e.is_prey or e.stage == 'child':
            return
        vigor_f = 0.7 + e.vigor * 0.3
        e.hunger = min(1.2, e.hunger + 0.012 * dy * vigor_f)
        e.thirst = min(1.3, e.thirst + 0.020 * dy * vigor_f)
        if e.state == S_REST:
            e.energy = min(1.0, e.energy + 0.035 * dy)
        else:
            e.energy = max(0.0, e.energy - 0.007 * dy)

    def _satisfy_needs(self, e, tiles):
        if e.is_prey: return
        gx, gy = int(e.x), int(e.y)
        t = tiles[gx][gy] if 0<=gx<WORLD_W and 0<=gy<WORLD_H else -1

        # Near water?
        near_water = any(
            0<=gx+dx<WORLD_W and 0<=gy+dy_<WORLD_H
            and tiles[gx+dx][gy+dy_] in (T_WATER, T_DEEP_WATER)
            for dx,dy_ in ((-1,0),(1,0),(0,-1),(0,1))
        )
        if near_water and e.state == S_DRINK:
            e.thirst = max(0.0, e.thirst - 0.15)
            e.mem_water_x = e.x
            e.mem_water_y = e.y

        if t in (T_FOREST, T_GRASS) and e.state == S_GATHER:
            e.hunger = max(0.0, e.hunger - 0.08)
            e.mem_food_x = e.x
            e.mem_food_y = e.y

        # Chopping: harvest wood, clear tile after 4 chops
        if e.state == S_CHOP and t == T_FOREST:
            key = (gx, gy)
            res = self.tile_resources.get(key, 0)
            if res > 0:
                self.tile_resources[key] = res - 1
                e.inv_wood = min(8, e.inv_wood + 1)
                e.hunger   = max(0.0, e.hunger - 0.01)   # physical work
                if self.tile_resources[key] <= 0:
                    # Tree is felled — clear the tile
                    self.tiles[gx][gy] = T_GRASS
                    del self.tile_resources[key]
                    self.cleared_tiles.append((gx, gy, 300.0))
                    if random.random() < 0.08:
                        self._add_event("Des arbres sont abattus pour construire.")
            else:
                # No more wood here — move on
                e.state    = S_WANDER
                e.state_cd = 0

        # Building: deposit carried wood at site
        if e.state == S_BUILD and e.inv_wood > 0:
            self._try_build(e)

        # Resting
        if e.state == S_REST:
            e.hunger = max(0.0, e.hunger - 0.02)

    def _choose_goal(self, e, era_idx, parents):
        if e.is_prey: return

        # Interrupt current task if arms are full of wood → go build now
        if e.inv_wood >= 5 and e.state not in (S_BUILD, S_DRINK):
            tx, ty     = self._find_build_spot(e)
            e.state    = S_BUILD
            e.target_x = tx
            e.target_y = ty
            e.state_cd = random.uniform(6, 12)
            e._refresh_activity(era_idx)
            return

        if e.state_cd > 0:
            e.state_cd -= 0.016
            # Update prey target if hunting (prey moves)
            if e.state == S_HUNT and self.prey:
                near_prey = [p for p in self.prey
                             if abs(p.x-e.x) < 12 and abs(p.y-e.y) < 12]
                if near_prey:
                    p = min(near_prey, key=lambda p: (p.x-e.x)**2+(p.y-e.y)**2)
                    e.target_x, e.target_y = p.x, p.y
            return

        prev = e.state

        # Children follow parent
        if e.stage == 'child':
            parent = parents.get(e.parent_eid)
            if parent:
                e.state    = S_FOLLOW
                e.target_x = parent.x + random.uniform(-1.5, 1.5)
                e.target_y = parent.y + random.uniform(-1.5, 1.5)
                e.state_cd = random.uniform(2, 5)
            else:
                e.state    = S_WANDER
                e.state_cd = random.uniform(3, 6)
            if e.state != prev: e._refresh_activity(era_idx)
            return

        # Elders stay close — less mobile
        if e.stage == 'elder':
            if e.thirst > 0.55:
                e.state    = S_DRINK
                e.target_x = e.mem_water_x
                e.target_y = e.mem_water_y
                e.state_cd = random.uniform(6, 12)
            elif e.hunger > 0.5:
                e.state    = S_GATHER
                e.target_x = e.mem_food_x
                e.target_y = e.mem_food_y
                e.state_cd = random.uniform(8, 14)
            else:
                e.state    = S_REST
                e.state_cd = random.uniform(8, 16)
            if e.state != prev: e._refresh_activity(era_idx)
            return

        # Adults: need-driven priority
        if e.thirst > 0.55:
            # Urgent thirst
            e.state    = S_DRINK
            e.target_x = e.mem_water_x
            e.target_y = e.mem_water_y
            e.state_cd = random.uniform(6, 14)

        elif e.inv_wood >= 3:
            # Loaded with wood → deposit and build immediately
            tx, ty     = self._find_build_spot(e)
            e.state    = S_BUILD
            e.target_x = tx
            e.target_y = ty
            e.state_cd = random.uniform(6, 12)

        elif e.hunger > 0.65 and self.prey and era_idx < 7:
            # Very hungry → hunt
            near_prey = [p for p in self.prey
                         if abs(p.x-e.x) < 14 and abs(p.y-e.y) < 14]
            if near_prey:
                p = min(near_prey, key=lambda p: (p.x-e.x)**2+(p.y-e.y)**2)
                e.state    = S_HUNT
                e.target_x = p.x
                e.target_y = p.y
                e.state_cd = random.uniform(5, 12)
            else:
                e.state    = S_GATHER
                e.target_x = e.mem_food_x
                e.target_y = e.mem_food_y
                e.state_cd = random.uniform(5, 10)

        elif e.energy < 0.25:
            # Exhausted → rest
            e.state    = S_REST
            e.state_cd = random.uniform(6, 14)

        elif e.hunger > 0.45:
            # Moderately hungry → gather
            e.state    = S_GATHER
            e.target_x = e.mem_food_x
            e.target_y = e.mem_food_y
            e.state_cd = random.uniform(5, 10)

        elif era_idx < 8 and random.random() < 0.40:
            # Not hungry/thirsty/exhausted — go chop wood (or build if loaded)
            target = self._find_chop_target(e)
            if target:
                e.state    = S_CHOP
                e.target_x, e.target_y = target
                e.state_cd = random.uniform(5, 10)
            else:
                e.state    = S_WANDER
                e.state_cd = random.uniform(4, 9)

        else:
            # Explore / social wander
            e.state    = S_WANDER
            e.state_cd = random.uniform(4, 9)
            if random.random() < 0.2:
                e.target_x = e.mem_water_x + random.uniform(-5, 5)
                e.target_y = e.mem_water_y + random.uniform(-5, 5)
            elif random.random() < 0.2:
                e.target_x = e.mem_food_x + random.uniform(-5, 5)
                e.target_y = e.mem_food_y + random.uniform(-5, 5)

        if e.state != prev:
            e._refresh_activity(era_idx)

    # ── movement ──────────────────────────────────────────────────────────

    def _move_entity(self, e, move_d, tiles, era_idx):
        # Speed modifiers by stage
        if e.stage == 'child': move_d *= 0.75
        if e.stage == 'elder': move_d *= 0.45
        if e.state == S_REST:  move_d *= 0.05

        if e.state in (S_HUNT, S_DRINK, S_GATHER, S_FOLLOW, S_CHOP, S_BUILD):
            dx = e.target_x - e.x
            dy = e.target_y - e.y
            dist = math.sqrt(dx*dx + dy*dy) + 0.001
            if dist < 1.0:
                # S_CHOP and S_BUILD: stay in state, _satisfy_needs handles completion
                if e.state not in (S_CHOP, S_BUILD):
                    e.state    = S_WANDER
                    e.state_cd = 0
                # else: stop moving, keep chopping/building in place
                e.vx = 0.0
                e.vy = 0.0
            else:
                e.vx = dx / dist
                e.vy = dy / dist
        elif e.state == S_WANDER:
            e.wander_cd -= 0.016
            if e.wander_cd <= 0:
                angle = random.uniform(0, math.tau)
                e.vx = math.cos(angle)
                e.vy = math.sin(angle)
                e.wander_cd = random.uniform(2, 6)

        self._apply_move(e, move_d, tiles)

    def _move_prey(self, p, move_d, tiles):
        # Flee if entity nearby
        p.state_cd -= 0.016
        for e in self.entities[:6]:
            if abs(e.x-p.x) < 6 and abs(e.y-p.y) < 6:
                angle = math.atan2(p.y-e.y, p.x-e.x)
                p.vx = math.cos(angle)
                p.vy = math.sin(angle)
                p.state    = S_FLEE
                p.state_cd = 3.5
                break
        if p.state == S_FLEE and p.state_cd <= 0:
            p.state = S_WANDER
        if p.state == S_WANDER:
            p.wander_cd -= 0.016
            if p.wander_cd <= 0:
                angle = random.uniform(0, math.tau)
                p.vx = math.cos(angle)
                p.vy = math.sin(angle)
                p.wander_cd = random.uniform(3, 8)
        flee_mult = 1.85 if p.state == S_FLEE else 0.8
        self._apply_move(p, move_d * flee_mult, tiles)

    def _apply_move(self, e, move_d, tiles):
        nx = max(0.5, min(WORLD_W-0.51, e.x + e.vx * move_d))
        ny = max(0.5, min(WORLD_H-0.51, e.y + e.vy * move_d))
        if TILE_WALKABLE.get(tiles[int(nx)][int(ny)], False):
            e.x, e.y = nx, ny
        else:
            angle = random.uniform(0, math.tau)
            e.vx, e.vy = math.cos(angle), math.sin(angle)

    # ── terraforming helpers ─────────────────────────────────────────────

    def _find_chop_target(self, e):
        """Nearest accessible forest tile within 16 tiles."""
        ex, ey = int(e.x), int(e.y)
        best, best_d = None, float('inf')
        for dx in range(-16, 17):
            for dy in range(-16, 17):
                x, y = ex + dx, ey + dy
                if (0 <= x < WORLD_W and 0 <= y < WORLD_H
                        and self.tiles[x][y] == T_FOREST
                        and (x, y) in self.tile_resources):
                    d = dx*dx + dy*dy
                    if d < best_d:
                        best_d = d
                        best   = (x + 0.5, y + 0.5)
        return best

    def _find_build_spot(self, e):
        """Target position where entity will deposit wood."""
        # Prefer nearest settlement of own clan's vicinity
        if self.settlements:
            s = min(self.settlements,
                    key=lambda s: (s.gx - e.x)**2 + (s.gy - e.y)**2)
            if (s.gx - e.x)**2 + (s.gy - e.y)**2 < 400:
                return s.gx + 0.5, s.gy + 0.5
        # No nearby settlement: build where clan is clustering
        clan_mates = [c for c in self.entities
                      if c.clan_id == e.clan_id and c is not e]
        if clan_mates:
            cx = sum(c.x for c in clan_mates) / len(clan_mates)
            cy = sum(c.y for c in clan_mates) / len(clan_mates)
            return cx + random.uniform(-2, 2), cy + random.uniform(-2, 2)
        return e.x + random.uniform(-3, 3), e.y + random.uniform(-3, 3)

    def _try_build(self, e):
        """Deposit carried wood; found or upgrade settlement when threshold met."""
        era_idx   = self._era_idx
        # Snap to 4×4 grid so nearby clan members pool wood at the same site
        bx = (int(e.x) // 4) * 4
        by = (int(e.y) // 4) * 4
        key       = (bx, by)

        self._build_progress[key] = self._build_progress.get(key, 0) + e.inv_wood
        e.inv_wood = 0

        # If enough wood accumulated and no settlement too close → found one
        if self._build_progress.get(key, 0) >= 8:
            if not any(abs(s.gx - bx) + abs(s.gy - by) < 12 for s in self.settlements):
                s = Settlement(bx + 2, by + 2, self.year)
                self.settlements.append(s)
                self._add_event(
                    random.choice(_SETTLE_MSGS[min(era_idx, len(_SETTLE_MSGS)-1)]))
                del self._build_progress[key]

    # ── reproduction ──────────────────────────────────────────────────────

    def _update_reproduction(self, dy):
        pop = len(self.entities)
        if pop == 0: return
        era_idx, _ = self.get_era()
        carry_cap  = 80 + era_idx * 400
        birth_rate = 0.06 * (1 + era_idx * 0.18)
        expected   = pop * birth_rate * dy * max(0, 1 - pop/carry_cap)
        while expected >= 1.0:
            self._spawn_child_free()
            expected -= 1.0
        if random.random() < expected:
            self._spawn_child_free()

    def _spawn_child_free(self):
        if not self.entities: return
        era_idx = self._era_idx
        # Only adults can reproduce
        adults = [e for e in self.entities if e.stage == 'adult'
                  and e.hunger < 0.6 and e.thirst < 0.6]
        if not adults: return
        parent = random.choice(adults)
        x = max(0.5, min(WORLD_W-0.51, parent.x + random.uniform(-1.5, 1.5)))
        y = max(0.5, min(WORLD_H-0.51, parent.y + random.uniform(-1.5, 1.5)))
        if TILE_WALKABLE.get(self.tiles[int(x)][int(y)], False):
            child = Entity(x, y, era_idx, clan_id=parent.clan_id, parent=parent)
            self.entities.append(child)

    # ── settlements ───────────────────────────────────────────────────────

    def _update_settlements(self, dy):
        era_idx, _ = self.get_era()
        if era_idx < 1 or self._settle_cd > 0: return
        density = {}
        for e in self.entities:
            key = (int(e.x), int(e.y))
            density[key] = density.get(key, 0) + 1
        existing  = {(s.gx, s.gy) for s in self.settlements}
        threshold = max(2, 7 - era_idx)
        for (tx, ty) in list(density):
            nbr = sum(density.get((tx+dx, ty+dy_), 0)
                      for dx in range(-4,5) for dy_ in range(-4,5))
            if nbr < threshold: continue
            if (tx, ty) in existing: continue
            if any(abs(s.gx-tx)+abs(s.gy-ty) < 14 for s in self.settlements): continue
            s = Settlement(tx, ty, self.year)
            self.settlements.append(s)
            existing.add((tx, ty))
            self._add_event(random.choice(_SETTLE_MSGS[min(era_idx, len(_SETTLE_MSGS)-1)]))
            self._settle_cd = 100.0 + era_idx * 30
            break
        for s in self.settlements:
            nearby = sum(1 for e in self.entities
                         if abs(e.x-s.gx) <= 7 and abs(e.y-s.gy) <= 7)
            s.population = nearby
            thresholds = [0, 4, 12, 35, 90, 200]
            for lvl in range(len(thresholds)-1, -1, -1):
                if nearby >= thresholds[lvl] and era_idx >= lvl:
                    s.level = lvl; break

    # ── epoch mode ────────────────────────────────────────────────────────

    def _bootstrap_epoch(self):
        for (fy, gx, gy) in self._site_schedule:
            if fy <= self.year:
                s = Settlement(gx, gy, fy)
                s.level = _site_level(fy, self.year, self.get_era()[0])
                self.settlements.append(s)
        self._era_idx = self.get_era()[0]
        self._populate_entities_epoch()
        self._spawn_prey(max(5, 22 - self._era_idx * 2))

    def _epoch_update(self, dy):
        era_idx, _ = self.get_era()
        for (fy, gx, gy) in self._site_schedule:
            if self.year - dy < fy <= self.year:
                s = Settlement(gx, gy, fy)
                s.level = 0
                self.settlements.append(s)
                self._add_event(random.choice(_SETTLE_MSGS[min(era_idx, len(_SETTLE_MSGS)-1)]))
        for s in self.settlements:
            s.level = _site_level(s.founded_year, self.year, era_idx)
        expected = _expected_population(self.year)
        if len(self.entities) < expected:
            self._populate_entities_epoch(expected - len(self.entities))
        elif len(self.entities) > expected + 50:
            del self.entities[expected:]
        prey_target = max(5, 22 - era_idx * 2)
        if len(self.prey) < prey_target:
            self._spawn_prey(prey_target - len(self.prey))
        elif len(self.prey) > prey_target + 5:
            del self.prey[prey_target:]
        self._check_era_transition()

    def _populate_entities_epoch(self, count=None):
        era_idx = self._era_idx
        target  = _expected_population(self.year) if count is None else count
        if self.settlements:
            for _ in range(target):
                s = random.choice(self.settlements)
                angle = random.uniform(0, math.tau)
                r = abs(random.gauss(0, 5))
                x = max(0.5, min(WORLD_W-0.51, s.gx + math.cos(angle)*r))
                y = max(0.5, min(WORLD_H-0.51, s.gy + math.sin(angle)*r))
                if TILE_WALKABLE.get(self.tiles[int(x)][int(y)], False):
                    self.entities.append(Entity(x, y, era_idx))
        else:
            cx, cy = WORLD_W//2, WORLD_H//2
            for _ in range(target):
                x = max(0.5, min(WORLD_W-0.51, cx + random.uniform(-14, 14)))
                y = max(0.5, min(WORLD_H-0.51, cy + random.uniform(-14, 14)))
                if TILE_WALKABLE.get(self.tiles[int(x)][int(y)], False):
                    self.entities.append(Entity(x, y, era_idx))

    # ── helpers ───────────────────────────────────────────────────────────

    def _spawn_initial(self):
        cx, cy = WORLD_W // 2, WORLD_H // 2
        # Place 4 groups at the four diagonals, each with its own clan
        angles  = [math.pi*0.25, math.pi*0.75, math.pi*1.25, math.pi*1.75]
        centers = []
        for angle in angles:
            for radius in range(12, 36, 2):
                gx = int(cx + math.cos(angle) * radius)
                gy = int(cy + math.sin(angle) * radius)
                if (0 <= gx < WORLD_W and 0 <= gy < WORLD_H
                        and TILE_WALKABLE.get(self.tiles[gx][gy], False)):
                    centers.append((gx, gy))
                    break

        for clan_id, (gcx, gcy) in enumerate(centers):
            # Nearest water and food for this group
            if self._water_adj:
                wx, wy = min(self._water_adj,
                             key=lambda p: (p[0]-gcx)**2+(p[1]-gcy)**2)
            else:
                wx, wy = gcx, gcy
            if self._food_tiles:
                fx, fy = min(self._food_tiles,
                             key=lambda p: (p[0]-gcx)**2+(p[1]-gcy)**2)
            else:
                fx, fy = gcx, gcy

            cands = [(x, y)
                     for x in range(gcx-7, gcx+7)
                     for y in range(gcy-7, gcy+7)
                     if 0<=x<WORLD_W and 0<=y<WORLD_H
                     and TILE_WALKABLE.get(self.tiles[x][y], False)]
            random.shuffle(cands)
            for gx, gy in cands[:4]:
                e = Entity(gx+0.5, gy+0.5, 0, clan_id=clan_id)
                e.mem_water_x, e.mem_water_y = wx+0.5, wy+0.5
                e.mem_food_x,  e.mem_food_y  = fx+0.5, fy+0.5
                self.entities.append(e)

    def _spawn_prey(self, n=1):
        for _ in range(n):
            if self._food_tiles:
                gx, gy = random.choice(self._food_tiles)
                self.prey.append(Entity(gx+random.uniform(0.2,0.8),
                                        gy+random.uniform(0.2,0.8),
                                        is_prey=True))

    def _check_era_transition(self):
        era_idx, era = self.get_era()
        if era_idx > self._era_idx:
            self._era_idx = era_idx
            self._add_event(f"✦ Nouvelle ère : {era[1]} !")

    def _add_event(self, text):
        self.events.append((self.year, text))
        self._active_events.append((text, 9.0))


# ── Activity description pools ────────────────────────────────────────────
_HUNT_DESC = [
    ["Traque un aurochs","Chasse un mammouth","Guette un cerf","Poursuit un bison"],
    ["Chasse un sanglier","Traque un cerf","Tend un piège","Suit une piste"],
    ["Part à la chasse","Chasse avec une lance","Suit la piste d'un sanglier","Traque au loin"],
    ["Chasse dans la forêt","Part au gibier","Guette au bord du lac","Surveille un terrier"],
    ["Chasse le lièvre","Tend un collet","Lève le gibier","Traque le cerf en forêt"],
    ["Chasse en forêt","Part à la vénerie","Traque le sanglier","Lève le gibier"],
    ["Chasse au fusil","Bat les fourrés","Guette le gibier","Partait à la chasse"],
    ["Pratique le tir","Observe la faune","Chasse légalement","Photographie les animaux"],
    ["Surveille des drones","Gère des bots","Optimise les écosystèmes","Simule des chasses"],
    ["Synchronise des IA","Explore la mémoire ancestrale","Rêve de nature","Interagit avec des hologrammes"],
]
_DRINK_DESC = [
    ["S'abreuve à la rivière","Boit dans un ruisseau","Se désaltère au lac","Cherche de l'eau fraîche"],
    ["Remplit une outre","Boit à la source","Recueille l'eau de pluie","Va chercher de l'eau"],
    ["Tire de l'eau du puits","Va au puits du village","Remplit une amphore","Porte l'eau au camp"],
    ["Va au puits","Cherche une fontaine","Se rend aux thermes","Se désaltère en chemin"],
    ["Va au puits du château","Cherche la fontaine","Boit à l'auberge","Remplit une gourde"],
    ["Boit à la taverne","Va à la fontaine","Se rafraîchit","Boit un verre d'eau de source"],
    ["Boit à la brasserie","Va au café","Se sert de la pompe","Boit un verre"],
    ["Achète une bouteille","Va au café","Commande une boisson","Se réhydrate"],
    ["Absorbe des électrolytes","Hydrate ses nano-cellules","Boit à la fontaine","Se synchronise"],
    ["Absorbe de l'énergie","Recharge ses implants","Fusionne avec le flux","Se régénère"],
]
_GATHER_DESC = [
    ["Cueille des baies","Déterres des racines","Ramasse des herbes","Cherche des champignons"],
    ["Récolte des plantes","Ramasse des graines","Cueille des fruits sauvages","Prépare du silex"],
    ["Moissonne du grain","Cueille les olives","Récolte les dattes","Travaille aux champs"],
    ["Travaille aux champs","Récolte les moissons","Ramasse des figues","Taille la vigne"],
    ["Cultive son jardin","Récolte le blé","Cueille des herbes","Glane après la moisson"],
    ["Jardine","Cueille des fleurs","Récolte les vignes","Prépare les épices"],
    ["Travaille aux champs","Récolte le tabac","Ramasse du charbon","Coupe le bois"],
    ["Fait les courses","Jardine en ville","Cultive en terrasse","Ramasse des déchets recyclables"],
    ["Récolte des données","Cultive des bioalgues","Imprime des protéines","Synthétise des nutriments"],
    ["Moissonne l'énergie stellaire","Récolte des minerais","Cultive des cristaux","Capte la lumière"],
]
_WANDER_DESC = [
    ["Explore les environs","Erre sans but","Cherche un abri","Observe le paysage"],
    ["Flâne dans la plaine","Explore la forêt","Cherche un campement","Erre au crépuscule"],
    ["Déambule en ville","Cherche du travail","Se promène au marché","Explore les ruelles"],
    ["Se promène au forum","Flâne au marché","Visite le temple","Contemple la ville"],
    ["Déambule au bourg","Visite la foire","Prie en chemin","Erre sur les chemins"],
    ["Contemple l'horizon","Se promène dans les jardins","Philosophe en marchant","Cherche l'inspiration"],
    ["Se promène en ville","Flâne sur les boulevards","Lit en marchant","Observe les passants"],
    ["Marche en écoutant de la musique","Flâne dans le parc","Consulte son téléphone","Se balade"],
    ["Simule des scénarios","Explore des mondes virtuels","Médite en réalité augmentée","Synchronise ses données"],
    ["Navigue dans l'espace","Médite dans le vide","Contemple les étoiles","Dérive entre les mondes"],
]
_REST_DESC = [
    ["Se repose près du feu","Récupère ses forces","Dort à la belle étoile","S'allonge sous un arbre"],
    ["Somnole près du feu","Se repose dans la hutte","Recupere après la chasse","Dort dans l'abri"],
    ["Se repose à l'ombre","Sieste près de l'âtre","Récupère ses forces","Dort dans la maison"],
    ["Fait la sieste","Se repose au bain","Somnole au Forum","Se repose sous un portique"],
    ["Dort dans sa chambre","Se repose dans la cour","Fait la sieste","Dort au coin du feu"],
    ["Se repose dans les jardins","Sieste sous un laurier","Médite","Récupère ses forces"],
    ["Fait une pause","Se repose à la taverne","Somnole dans sa chambre","Sieste dans les champs"],
    ["Se repose","Fait une sieste","Médite","Écoute de la musique tranquille"],
    ["En mode veille","Régénère ses capacités","Medite en stase","Recharge ses systèmes"],
    ["En hibernation cognitive","Syncronise ses souvenirs","Se recharge","Rêve de l'infini"],
]

_CHOP_DESC = [
    ["Abat un arbre","Coupe du bois","Taille des branches","Débite un tronc"],
    ["Coupe du bois pour l'abri","Taille des piquets","Abat des arbres","Récolte du bois"],
    ["Coupe du bois de construction","Déboise la clairière","Prépare des poutres","Abat la forêt"],
    ["Bûcheronne","Débite des planches","Coupe le bois d'œuvre","Défriche la forêt"],
    ["Coupe du bois de chauffage","Bûcheronne en forêt","Débite des solives","Défriche"],
    ["Coupe du bois","Débite des planches","Prépare le bois","Taille des madriers"],
    ["Abat des arbres","Débite du bois","Coupe pour l'usine","Bûcheronne"],
    ["Coupe du bois","Défriche","Abat des arbres","Prépare du bois"],
    ["Synthétise du bois","Récolte la biomasse","Extrait la cellulose","Recycle le bois"],
    ["Récolte des matériaux","Extrait des ressources","Synthétise des composants","Mine l'astéroïde"],
]
_BUILD_DESC = [
    ["Dresse un abri","Tresse des branches","Construit une hutte","Bâtit un refuge"],
    ["Construit un abri","Plante des piquets","Bâtit une cabane","Monte un campement"],
    ["Construit une maison","Bâtit un mur","Érige un pilier","Édifie un logis"],
    ["Bâtit une demeure","Construit un forum","Érige des colonnes","Construit une villa"],
    ["Construit une tour","Bâtit un château","Érige des remparts","Construit une église"],
    ["Bâtit un palais","Construit une cathédrale","Érige une loggia","Sculpte un portail"],
    ["Construit une usine","Bâtit des logements","Pose des rails","Érige une cheminée"],
    ["Bâtit un gratte-ciel","Construit une tour","Érige un pont","Construit un stade"],
    ["Imprime un bâtiment","Assemble des modules","Programme une structure","Installe des nœuds"],
    ["Construit une mégastructure","Bâtit une station","Érige un anneau spatial","Construit un monde"],
]

_SETTLE_MSGS = [
    ["Un groupe de chasseurs dresse un campement.","Des abris de peaux apparaissent.","Une tribu s'installe près d'un point d'eau."],
    ["Un village de huttes prend forme.","Des greniers sont construits.","Une communauté sédentaire émerge."],
    ["Une cité fortifiée s'élève.","Des artisans fondent une nouvelle ville.","Le commerce attire des colons."],
    ["Une cité-état prospère naît.","Des temples s'élèvent vers le ciel.","Un port commercial est établi."],
    ["Une ville fortifiée grandit.","Une cathédrale domine le paysage.","Un marché médiéval s'anime."],
    ["Une ville de la Renaissance fleurit.","Savants et artistes s'y réunissent.","Les arts et sciences y prospèrent."],
    ["Une cité industrielle s'étend.","Les cheminées d'usines s'allument.","Les rails unissent les villes."],
    ["Une métropole moderne se développe.","Des gratte-ciel percent les nuages.","Les réseaux numériques s'étendent."],
    ["Un complexe technologique est érigé.","Les nœuds IA se multiplient.","Des mégastructures reconfigurent le paysage."],
    ["Une colonie spatiale est fondée.","Les étoiles accueillent l'humanité.","L'expansion interstellaire commence."],
]


# ── Module helpers ────────────────────────────────────────────────────────
def _epoch_year():
    return (_time.time() - EPOCH_TIMESTAMP) * YEARS_PER_SECOND

def _expected_population(year):
    return max(10, int(600 / (1 + math.exp(-0.0006 * (year - 5000)))))

def _site_level(founded_year, current_year, era_idx):
    age = current_year - founded_year
    if   age > 5000 and era_idx >= 5: return 5
    elif age > 2000 and era_idx >= 4: return 4
    elif age > 1000 and era_idx >= 3: return 3
    elif age >  400 and era_idx >= 2: return 2
    elif age >  100 and era_idx >= 1: return 1
    return 0

def _precompute_sites(tiles, seed=42, max_sites=45):
    rng = random.Random(seed + 0xDEAD)
    cands = [(x,y) for x in range(WORLD_W) for y in range(WORLD_H)
             if tiles[x][y] in (T_GRASS, T_SAND, T_FOREST, T_HIGHLAND)]
    rng.shuffle(cands)
    sites, occupied = [], []
    for x, y in cands:
        if len(sites) >= max_sites: break
        if any(abs(x-ox)+abs(y-oy) < 12 for ox,oy in occupied): continue
        sites.append((x, y)); occupied.append((x, y))
    schedule, year = [], 1000.0
    for x, y in sites:
        schedule.append((year, x, y))
        year += rng.uniform(120, 280)
    return schedule
