import random
import math
from config import WORLD_W, WORLD_H, T_DEEP_WATER, T_WATER, T_SAND, T_GRASS, \
                   T_FOREST, T_HIGHLAND, T_MOUNTAIN, T_SNOW


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def _lerp(a, b, t):
    return a + (b - a) * t


def _sample(grid, gw, gh, fx, fy):
    x0 = int(fx) % gw
    y0 = int(fy) % gh
    x1 = (x0 + 1) % gw
    y1 = (y0 + 1) % gh
    u  = _smooth(fx - int(fx))
    v  = _smooth(fy - int(fy))
    return _lerp(
        _lerp(grid[x0][y0], grid[x1][y0], u),
        _lerp(grid[x0][y1], grid[x1][y1], u),
        v,
    )


# ── Phase 1 : build random grid objects (very fast) ──────────────────────

def build_noise_grids(seed=42):
    """Return pre-built grid objects for height and moisture — no heavy loops."""
    rng_h = random.Random(seed)
    rng_m = random.Random(seed + 0xBEEF)

    # (scale, amplitude, grid_data)
    octaves = [(4, 0.50), (8, 0.25), (16, 0.125), (32, 0.0625)]

    def make(rng):
        result = []
        for scale, amp in octaves:
            gw = WORLD_W  // scale + 2
            gh = WORLD_H  // scale + 2
            grid = [[rng.random() for _ in range(gh)] for _ in range(gw)]
            result.append((scale, amp, grid, gw, gh))
        return result

    return make(rng_h), make(rng_m)


# ── Phase 2 : compute one row at a time (yielded from main.py) ────────────

def compute_row(x, h_grids, m_grids):
    """Sample noise for one column x → returns (h_row, m_row) lists."""
    h_row = [0.0] * WORLD_H
    m_row = [0.0] * WORLD_H
    for y in range(WORLD_H):
        for scale, amp, grid, gw, gh in h_grids:
            h_row[y] += _sample(grid, gw, gh, x / scale, y / scale) * amp
        for scale, amp, grid, gw, gh in m_grids:
            m_row[y] += _sample(grid, gw, gh, x / scale, y / scale) * amp
    return h_row, m_row


# ── Phase 3 : normalise, island-mask, classify ────────────────────────────

def finalize_terrain(height_map, moisture_map):
    """From raw float maps → tile-type 2D array."""
    def normalize(m):
        flat = [m[x][y] for x in range(WORLD_W) for y in range(WORLD_H)]
        lo, hi = min(flat), max(flat)
        span = hi - lo or 1.0
        for x in range(WORLD_W):
            for y in range(WORLD_H):
                m[x][y] = (m[x][y] - lo) / span

    normalize(height_map)
    normalize(moisture_map)

    cx, cy = WORLD_W / 2.0, WORLD_H / 2.0
    for x in range(WORLD_W):
        for y in range(WORLD_H):
            dx   = (x - cx) / (WORLD_W / 2.0)
            dy_  = (y - cy) / (WORLD_H / 2.0)
            dist = math.sqrt(dx*dx + dy_*dy_)
            mask = max(0.0, 1.0 - dist * 1.25) ** 2
            height_map[x][y] = height_map[x][y] * 0.45 + height_map[x][y] * mask * 0.55

    normalize(height_map)

    tiles = [[T_GRASS] * WORLD_H for _ in range(WORLD_W)]
    for x in range(WORLD_W):
        for y in range(WORLD_H):
            h = height_map[x][y]
            m = moisture_map[x][y]
            if   h < 0.22:  tiles[x][y] = T_DEEP_WATER
            elif h < 0.33:  tiles[x][y] = T_WATER
            elif h < 0.41:  tiles[x][y] = T_SAND
            elif h < 0.70:  tiles[x][y] = T_FOREST if m > 0.52 else T_GRASS
            elif h < 0.80:  tiles[x][y] = T_HIGHLAND
            elif h < 0.91:  tiles[x][y] = T_MOUNTAIN
            else:           tiles[x][y] = T_SNOW

    return tiles, height_map, moisture_map


# ── River generation ──────────────────────────────────────────────────────

def generate_rivers(tiles, height_map, seed=42):
    """Trace rivers from highland sources downhill to water.
    Returns a list of paths; each path is a list of (x, y) tile coords."""
    rng   = random.Random(seed ^ 0xCAFE_BABE)
    WATER = {T_DEEP_WATER, T_WATER}
    HIGH  = {T_MOUNTAIN, T_SNOW, T_HIGHLAND}

    sources = [(x, y) for x in range(2, WORLD_W - 2)
                       for y in range(2, WORLD_H - 2)
                       if tiles[x][y] in HIGH]
    rng.shuffle(sources)

    river_paths = []
    used_tiles  = set()

    for sx, sy in sources:
        if len(river_paths) >= 8:
            break
        if (sx, sy) in used_tiles:
            continue

        path    = []
        visited = set()
        cx, cy  = sx, sy

        for _ in range(180):
            if (cx, cy) in visited:
                break
            visited.add((cx, cy))
            path.append((cx, cy))
            if tiles[cx][cy] in WATER:
                break

            nbrs = []
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx2, ny2 = cx + dx, cy + dy
                if 0 <= nx2 < WORLD_W and 0 <= ny2 < WORLD_H and (nx2, ny2) not in visited:
                    nbrs.append((height_map[nx2][ny2], nx2, ny2))
            if not nbrs:
                break

            nbrs.sort()
            min_h = nbrs[0][0]
            low   = [(h, nx2, ny2) for h, nx2, ny2 in nbrs if h <= min_h + 0.04]
            _, cx, cy = rng.choice(low)

        if len(path) >= 7 and tiles[path[-1][0]][path[-1][1]] in WATER:
            for p in path:
                used_tiles.add(p)
            river_paths.append(path)

    return river_paths


# ── Legacy sync wrapper (desktop / tests) ────────────────────────────────

def generate_terrain(seed=42):
    h_grids, m_grids = build_noise_grids(seed)
    height_map   = [[0.0] * WORLD_H for _ in range(WORLD_W)]
    moisture_map = [[0.0] * WORLD_H for _ in range(WORLD_W)]
    for x in range(WORLD_W):
        h_row, m_row = compute_row(x, h_grids, m_grids)
        height_map[x]   = h_row
        moisture_map[x] = m_row
    return finalize_terrain(height_map, moisture_map)
