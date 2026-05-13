import random
import math
import time as _time
from config import (WORLD_W, WORLD_H, ERAS, TIME_SPEEDS, DEFAULT_SPEED_IDX,
                    TILE_WALKABLE, T_GRASS, T_SAND, T_FOREST, T_HIGHLAND,
                    T_WATER, T_DEEP_WATER,
                    EPOCH_TIMESTAMP, YEARS_PER_SECOND)

# ── Era-based name pools ───────────────────────────────────────────────────
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

# ── Activity descriptions by era ──────────────────────────────────────────
_HUNT_DESC = [
    ["Traque un aurochs","Chasse un mammouth","Guette un cerf","Poursuit un bison"],
    ["Chasse un sanglier","Traque un cerf","Tend un piège","Suit une piste"],
    ["Part à la chasse","Suit une piste de gibier","Chasse avec une lance","Traque au loin"],
    ["Chasse dans la forêt","Part au gibier","Guette au bord du lac","Surveille un terrier"],
    ["Chasse le lièvre","Tend un collet","Part à la chasse au faucon","Traque un cerf"],
    ["Chasse en forêt","Part à la vénerie","Traque le sanglier","Lève le gibier"],
    ["Chasse au fusil","Guette le gibier","Bat les fourrés","Partait à la chasse"],
    ["Pratique le tir sportif","Chasse légalement","Observe la faune","Photographie les animaux"],
    ["Surveille des drones","Gère des bots écologiques","Optimise les écosystèmes","Simule des chasses"],
    ["Interagit avec des hologrammes","Synchronise des IA","Explore la mémoire ancestrale","Rêve de nature"],
]
_DRINK_DESC = [
    ["S'abreuve à la rivière","Boit dans un ruisseau","Se désaltère au lac","Cherche de l'eau fraîche"],
    ["Remplit une outre","Boit à la source","Recueille l'eau de pluie","Va chercher de l'eau"],
    ["Tire de l'eau du puits","Va au puits du village","Remplit une amphore","Porte l'eau au camp"],
    ["Va au puits","Cherche une fontaine","Se rend aux thermes","Se désaltère en chemin"],
    ["Va au puits du château","Cherche la fontaine","Boit à l'auberge","Remplit une gourde"],
    ["Boit à la taverne","Va à la fontaine","Achète de l'eau","Se rafraîchit"],
    ["Boit à la brasserie","Va au café","Se sert de la pompe","Boit un verre"],
    ["Achète une bouteille","Va au café","Commande une boisson","Boit au robinet"],
    ["Se recharge en électrolytes","Absorbe des nutriments","Hydrate ses nano-cellules","Boit à la fontaine"],
    ["Absorbe de l'énergie","Se synchronise au réseau","Recharge ses implants","Fusionne avec le flux"],
]
_GATHER_DESC = [
    ["Cueille des baies","Déterres des racines","Ramasse des herbes","Cherche des champignons"],
    ["Récolte des plantes","Ramasse des graines","Prépare du silex","Cueille des fruits"],
    ["Moissonne du grain","Cueille les olives","Récolte les dattes","Travaille aux champs"],
    ["Travaille aux champs","Récolte les moissons","Ramasse des figues","Taille la vigne"],
    ["Cultive son jardin","Récolte le blé","Cueille des herbes","Glane après la moisson"],
    ["Jardine","Cueille des fleurs","Récolte les vignes","Prépare les épices"],
    ["Travaille aux champs","Récolte le tabac","Ramasse du charbon","Coupe le bois"],
    ["Fait les courses","Ramasse des déchets","Jardine en ville","Cultive en terrasse"],
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
    ["Marche en écoutant","Flâne dans le parc","Consulte son téléphone","Se balade en ville"],
    ["Simule des scenarios","Explore des mondes virtuels","Médite en réalité augmentée","Synchronise ses données"],
    ["Navigue dans l'espace","Médite dans le vide","Contemple les étoiles","Dérive entre les mondes"],
]

# Entity states
S_WANDER  = 0
S_HUNT    = 1
S_DRINK   = 2
S_GATHER  = 3
S_FLEE    = 4   # prey only

_entity_counter = 0


class Entity:
    __slots__ = ['x','y','vx','vy','age','wander_cd','state','target_x','target_y',
                 'state_cd','is_prey','name','eid','activity_desc','vigor']

    def __init__(self, x, y, era_idx=0, is_prey=False):
        global _entity_counter
        _entity_counter += 1

        self.x = float(x)
        self.y = float(y)
        angle  = random.uniform(0, math.tau)
        self.vx = math.cos(angle)
        self.vy = math.sin(angle)
        self.age        = random.uniform(0, 14)
        self.wander_cd  = random.uniform(0, 6)
        self.state      = S_WANDER
        self.target_x   = x
        self.target_y   = y
        self.state_cd   = random.uniform(0, 5)
        self.is_prey    = is_prey
        self.eid        = _entity_counter
        self.vigor      = random.uniform(0.5, 1.0)
        self.activity_desc = ""

        if is_prey:
            self.name = random.choice(["Cerf","Sanglier","Aurochs","Loup","Bison",
                                       "Chamois","Renard","Lynx","Ours","Bouquetin"])
        else:
            pool = _NAMES[min(era_idx, len(_NAMES)-1)]
            self.name = random.choice(pool)
            self._refresh_activity(era_idx)

    def _refresh_activity(self, era_idx):
        era_idx = min(era_idx, 9)
        if self.state == S_HUNT:
            self.activity_desc = random.choice(_HUNT_DESC[era_idx])
        elif self.state == S_DRINK:
            self.activity_desc = random.choice(_DRINK_DESC[era_idx])
        elif self.state == S_GATHER:
            self.activity_desc = random.choice(_GATHER_DESC[era_idx])
        else:
            self.activity_desc = random.choice(_WANDER_DESC[era_idx])

    @property
    def health(self):
        return max(0.0, 1.0 - (self.age / 65.0) ** 1.8)


class Settlement:
    def __init__(self, gx, gy, founded_year):
        self.gx = gx
        self.gy = gy
        self.founded_year = founded_year
        self.population = 0
        self.level = 0


class Simulation:
    def __init__(self, tiles, epoch=False):
        self.tiles   = tiles
        self.epoch   = epoch
        self.paused  = False
        self.speed_idx     = DEFAULT_SPEED_IDX
        self._era_idx      = 0
        self._settle_cd    = 0.0
        self.entities    = []
        self.prey        = []
        self.settlements = []
        self.events      = []
        self._active_events = []

        self._walkable   = [(x,y) for x in range(WORLD_W) for y in range(WORLD_H)
                            if TILE_WALKABLE.get(tiles[x][y], False)]
        self._water_adj  = self._find_water_adjacent()
        self._food_tiles = [(x,y) for x,y in self._walkable
                            if tiles[x][y] in (T_FOREST, T_GRASS)]

        if epoch:
            self._site_schedule = _precompute_sites(tiles)
            self.year = _epoch_year()
            self._bootstrap_epoch()
        else:
            self.year = 0.0
            self._spawn_initial()
            self._spawn_prey(20)

    # ── public ────────────────────────────────────────────────────────────

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
            self.speed_idx = min(len(TIME_SPEEDS)-1, self.speed_idx+1)

    def slow_down(self):
        if not self.epoch:
            self.speed_idx = max(1, self.speed_idx-1)

    def update(self, dt):
        if self.epoch:
            new_year = _epoch_year()
            dy_game  = new_year - self.year
            self._animate_all(dt)
            if dy_game > 0:
                self.year = new_year
                self._epoch_update(dy_game)
        else:
            if self.paused:
                return
            dy_game = dt * TIME_SPEEDS[self.speed_idx]
            self.year += dy_game
            self._update_entities(dy_game)
            self._update_prey(dy_game)
            self._update_reproduction(dy_game)
            self._update_settlements(dy_game)
            self._check_era_transition()
            self._settle_cd = max(0.0, self._settle_cd - dy_game)

        self._active_events = [
            (t, r-dt) for t,r in self._active_events if r-dt > 0
        ]

    # ── real-time animation ────────────────────────────────────────────────

    def _animate_all(self, dt):
        era_idx = self._era_idx
        speed   = 2.5 + era_idx * 0.25
        move_d  = dt * speed
        tiles   = self.tiles
        for e in self.entities:
            self._move_entity(e, move_d, tiles, era_idx, hunt_prey=True)
        for p in self.prey:
            self._move_prey(p, move_d, tiles)

    # ── entity AI ─────────────────────────────────────────────────────────

    def _move_entity(self, e, move_d, tiles, era_idx, hunt_prey=False):
        e.state_cd  -= 0.016
        e.wander_cd -= 0.016

        if e.state_cd <= 0:
            prev_state = e.state
            roll = random.random()
            if hunt_prey and self.prey and era_idx < 7 and roll < 0.20:
                nearest = min(self.prey,
                              key=lambda p: (p.x-e.x)**2+(p.y-e.y)**2, default=None)
                if nearest and (nearest.x-e.x)**2+(nearest.y-e.y)**2 < 100:
                    e.state    = S_HUNT
                    e.target_x = nearest.x
                    e.target_y = nearest.y
                    e.state_cd = random.uniform(5, 12)
                else:
                    e.state = S_WANDER
                    e.state_cd = random.uniform(3, 7)
            elif self._water_adj and roll < 0.38:
                tx, ty = random.choice(self._water_adj[:30])
                e.state    = S_DRINK
                e.target_x = tx + 0.5
                e.target_y = ty + 0.5
                e.state_cd = random.uniform(6, 14)
            elif self._food_tiles and roll < 0.60:
                tx, ty = random.choice(self._food_tiles[:60])
                e.state    = S_GATHER
                e.target_x = tx + 0.5
                e.target_y = ty + 0.5
                e.state_cd = random.uniform(5, 10)
            else:
                e.state    = S_WANDER
                e.state_cd = random.uniform(3, 8)
            if e.state != prev_state:
                e._refresh_activity(era_idx)

        if e.state in (S_HUNT, S_DRINK, S_GATHER):
            dx = e.target_x - e.x
            dy = e.target_y - e.y
            dist = math.sqrt(dx*dx + dy*dy) + 0.001
            if dist < 1.0:
                e.state = S_WANDER
                e._refresh_activity(era_idx)
            else:
                e.vx = dx / dist
                e.vy = dy / dist
        else:
            if e.wander_cd <= 0:
                angle = random.uniform(0, math.tau)
                e.vx = math.cos(angle)
                e.vy = math.sin(angle)
                e.wander_cd = random.uniform(2, 7)

        self._apply_move(e, move_d, tiles)

    def _move_prey(self, p, move_d, tiles):
        for e in self.entities[:8]:
            dx = e.x - p.x
            dy = e.y - p.y
            if dx*dx + dy*dy < 25:
                angle = math.atan2(dy, dx) + math.pi
                p.vx = math.cos(angle)
                p.vy = math.sin(angle)
                p.state    = S_FLEE
                p.state_cd = 4.0
                break
        p.state_cd  -= 0.016
        p.wander_cd -= 0.016
        if p.state == S_FLEE and p.state_cd <= 0:
            p.state = S_WANDER
        if p.state == S_WANDER and p.wander_cd <= 0:
            angle = random.uniform(0, math.tau)
            p.vx = math.cos(angle)
            p.vy = math.sin(angle)
            p.wander_cd = random.uniform(3, 9)
        flee_mult = 1.9 if p.state == S_FLEE else 0.85
        self._apply_move(p, move_d * flee_mult, tiles)

    def _apply_move(self, e, move_d, tiles):
        nx = max(0.5, min(WORLD_W-0.51, e.x + e.vx * move_d))
        ny = max(0.5, min(WORLD_H-0.51, e.y + e.vy * move_d))
        if TILE_WALKABLE.get(tiles[int(nx)][int(ny)], False):
            e.x, e.y = nx, ny
        else:
            angle = random.uniform(0, math.tau)
            e.vx = math.cos(angle)
            e.vy = math.sin(angle)

    # ── free-play simulation ───────────────────────────────────────────────

    def _update_entities(self, dy):
        tiles   = self.tiles
        era_idx = self._era_idx
        move_d  = dy * 0.6
        dead    = []
        for e in self.entities:
            e.age += dy
            self._move_entity(e, move_d, tiles, era_idx, hunt_prey=True)
            if e.age > 55 + random.uniform(-8, 15):
                dead.append(e)
        for e in dead:
            self.entities.remove(e)

    def _update_prey(self, dy):
        tiles   = self.tiles
        move_d  = dy * 0.8
        for p in self.prey:
            self._move_prey(p, move_d, tiles)
        era_idx = self._era_idx
        target  = max(5, 30 - era_idx * 3)
        if len(self.prey) < target:
            self._spawn_prey(1)

    def _update_reproduction(self, dy):
        pop = len(self.entities)
        if pop == 0:
            return
        era_idx, _ = self.get_era()
        carry_cap  = 80 + era_idx * 400
        birth_rate = 0.07 * (1 + era_idx * 0.20)
        expected   = pop * birth_rate * dy * max(0, 1 - pop/carry_cap)
        while expected >= 1.0:
            self._spawn_child()
            expected -= 1.0
        if random.random() < expected:
            self._spawn_child()

    def _spawn_child(self):
        if not self.entities:
            return
        era_idx = self._era_idx
        parent  = random.choice(self.entities)
        x = max(0.5, min(WORLD_W-0.51, parent.x + random.uniform(-2, 2)))
        y = max(0.5, min(WORLD_H-0.51, parent.y + random.uniform(-2, 2)))
        if TILE_WALKABLE.get(self.tiles[int(x)][int(y)], False):
            self.entities.append(Entity(x, y, era_idx))

    def _update_settlements(self, dy):
        era_idx, _ = self.get_era()
        if era_idx < 1 or self._settle_cd > 0:
            return
        density = {}
        for e in self.entities:
            key = (int(e.x), int(e.y))
            density[key] = density.get(key, 0) + 1
        existing  = {(s.gx, s.gy) for s in self.settlements}
        threshold = max(2, 7 - era_idx)
        for (tx, ty) in list(density):
            nbr = sum(density.get((tx+dx, ty+dy_), 0)
                      for dx in range(-4, 5) for dy_ in range(-4, 5))
            if nbr < threshold:
                continue
            if (tx, ty) in existing:
                continue
            if any(abs(s.gx-tx)+abs(s.gy-ty) < 14 for s in self.settlements):
                continue
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
                    s.level = lvl
                    break

    # ── epoch mode ────────────────────────────────────────────────────────

    def _bootstrap_epoch(self):
        for (fy, gx, gy) in self._site_schedule:
            if fy <= self.year:
                s = Settlement(gx, gy, fy)
                s.level = _site_level(fy, self.year, self.get_era()[0])
                self.settlements.append(s)
        self._era_idx = self.get_era()[0]
        self._populate_entities_epoch()
        self._spawn_prey(max(5, 25 - self._era_idx * 2))

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
        current  = len(self.entities)
        if current < expected:
            self._populate_entities_epoch(expected - current)
        elif current > expected + 50:
            del self.entities[expected:]
        prey_target = max(5, 25 - era_idx * 2)
        if len(self.prey) < prey_target:
            self._spawn_prey(prey_target - len(self.prey))
        elif len(self.prey) > prey_target + 5:
            del self.prey[prey_target:]
        self._check_era_transition()

    def _populate_entities_epoch(self, count=None):
        era_idx = self._era_idx
        target  = _expected_population(self.year) if count is None else count
        tiles   = self.tiles
        if self.settlements:
            for _ in range(target):
                s = random.choice(self.settlements)
                angle = random.uniform(0, math.tau)
                r = abs(random.gauss(0, 5))
                x = max(0.5, min(WORLD_W-0.51, s.gx + math.cos(angle)*r))
                y = max(0.5, min(WORLD_H-0.51, s.gy + math.sin(angle)*r))
                if TILE_WALKABLE.get(tiles[int(x)][int(y)], False):
                    self.entities.append(Entity(x, y, era_idx))
        else:
            cx, cy = WORLD_W//2, WORLD_H//2
            for _ in range(target):
                x = max(0.5, min(WORLD_W-0.51, cx + random.uniform(-14, 14)))
                y = max(0.5, min(WORLD_H-0.51, cy + random.uniform(-14, 14)))
                if TILE_WALKABLE.get(tiles[int(x)][int(y)], False):
                    self.entities.append(Entity(x, y, era_idx))

    # ── shared helpers ─────────────────────────────────────────────────────

    def _spawn_initial(self):
        cx, cy = WORLD_W//2, WORLD_H//2
        cands = [(x,y) for x in range(cx-12, cx+12) for y in range(cy-12, cy+12)
                 if 0<=x<WORLD_W and 0<=y<WORLD_H
                 and TILE_WALKABLE.get(self.tiles[x][y], False)]
        random.shuffle(cands)
        for gx, gy in cands[:15]:
            self.entities.append(Entity(gx+0.5, gy+0.5, 0))

    def _spawn_prey(self, n=1):
        for _ in range(n):
            if self._food_tiles:
                gx, gy = random.choice(self._food_tiles)
                self.prey.append(Entity(gx+random.uniform(0.2, 0.8),
                                        gy+random.uniform(0.2, 0.8), is_prey=True))

    def _find_water_adjacent(self):
        # Build water tile set first for O(1) lookup
        water = {(x, y) for x in range(WORLD_W) for y in range(WORLD_H)
                 if self.tiles[x][y] in (T_WATER, T_DEEP_WATER)}
        result = []
        for x, y in self._walkable:
            if any((x+dx, y+dy) in water for dx, dy in ((-1,0),(1,0),(0,-1),(0,1))):
                result.append((x, y))
        return result

    def _check_era_transition(self):
        era_idx, era = self.get_era()
        if era_idx > self._era_idx:
            self._era_idx = era_idx
            self._add_event(f"✦ Nouvelle ère : {era[1]} !")

    def _add_event(self, text):
        self.events.append((self.year, text))
        self._active_events.append((text, 9.0))


# ── narrative settle messages ──────────────────────────────────────────────
_SETTLE_MSGS = [
    ["Un groupe de chasseurs dresse un campement.","Des abris de peaux apparaissent.","Une tribu s'installe près d'un point d'eau."],
    ["Un village de huttes prend forme.","Des greniers sont construits.","Une communauté sédentaire émerge."],
    ["Une cité fortifiée s'élève.","Des artisans fondent une nouvelle ville.","Le commerce attire des colons."],
    ["Une cité-état prospère naît.","Des temples s'élèvent vers le ciel.","Un port commercial est établi."],
    ["Une ville fortifiée de pierre grandit.","Une cathédrale domine le paysage.","Un marché médiéval s'anime."],
    ["Une ville de la Renaissance fleurit.","Savants et artistes s'y réunissent.","Les arts et sciences y prospèrent."],
    ["Une cité industrielle s'étend.","Les cheminées d'usines s'allument.","Les rails unissent les villes."],
    ["Une métropole moderne se développe.","Des gratte-ciel percent les nuages.","Les réseaux numériques s'étendent."],
    ["Un complexe technologique est érigé.","Les nœuds IA se multiplient.","Les mégastructures reconfigurent le paysage."],
    ["Une colonie spatiale est fondée.","Les étoiles accueillent l'humanité.","L'expansion interstellaire commence."],
]


# ── module-level helpers ───────────────────────────────────────────────────
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
        if len(sites) >= max_sites:
            break
        if any(abs(x-ox)+abs(y-oy) < 12 for ox,oy in occupied):
            continue
        sites.append((x, y))
        occupied.append((x, y))
    schedule, year = [], 1000.0
    for x, y in sites:
        schedule.append((year, x, y))
        year += rng.uniform(120, 280)
    return schedule
