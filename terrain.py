import random
import math
from config import (WORLD_W, WORLD_H,
                    T_DEEP_WATER, T_WATER, T_SAND, T_GRASS,
                    T_FOREST, T_HIGHLAND, T_MOUNTAIN, T_SNOW)


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def _lerp(a, b, t):
    return a + (b - a) * t


def _sample(grid, gw, gh, fx, fy):
    x0 = int(fx) % gw
    y0 = int(fy) % gh
    x1 = (x0 + 1) % gw
    y1 = (y0 + 1) % gh
    u = _smooth(fx - int(fx))
    v = _smooth(fy - int(fy))
    return _lerp(
        _lerp(grid[x0][y0], grid[x1][y0], u),
        _lerp(grid[x0][y1], grid[x1][y1], u),
        v,
    )


def _fbm(width, height, rng, octaves=((4, 0.50), (8, 0.25), (16, 0.125), (32, 0.0625))):
    result = [[0.0] * height for _ in range(width)]
    for scale, amp in octaves:
        gw = width  // scale + 2
        gh = height // scale + 2
        grid = [[rng.random() for _ in range(gh)] for _ in range(gw)]
        for x in range(width):
            for y in range(height):
                result[x][y] += _sample(grid, gw, gh, x / scale, y / scale) * amp
    return result


def _normalize(m, w, h):
    flat = [m[x][y] for x in range(w) for y in range(h)]
    lo, hi = min(flat), max(flat)
    span = hi - lo or 1.0
    for x in range(w):
        for y in range(h):
            m[x][y] = (m[x][y] - lo) / span


def generate_terrain(seed=42):
    rng_h = random.Random(seed)
    rng_m = random.Random(seed + 0xBEEF)

    height_map   = _fbm(WORLD_W, WORLD_H, rng_h)
    moisture_map = _fbm(WORLD_W, WORLD_H, rng_m)

    _normalize(height_map,   WORLD_W, WORLD_H)
    _normalize(moisture_map, WORLD_W, WORLD_H)

    # Island mask: fade height toward edges so the world is surrounded by water
    cx, cy = WORLD_W / 2.0, WORLD_H / 2.0
    for x in range(WORLD_W):
        for y in range(WORLD_H):
            dx = (x - cx) / (WORLD_W / 2.0)
            dy = (y - cy) / (WORLD_H / 2.0)
            dist = math.sqrt(dx * dx + dy * dy)
            mask = max(0.0, 1.0 - dist * 1.25)
            mask = mask * mask
            height_map[x][y] = height_map[x][y] * 0.45 + height_map[x][y] * mask * 0.55

    _normalize(height_map, WORLD_W, WORLD_H)

    tiles = [[T_GRASS] * WORLD_H for _ in range(WORLD_W)]
    for x in range(WORLD_W):
        for y in range(WORLD_H):
            h = height_map[x][y]
            m = moisture_map[x][y]
            if   h < 0.22:               tiles[x][y] = T_DEEP_WATER
            elif h < 0.33:               tiles[x][y] = T_WATER
            elif h < 0.41:               tiles[x][y] = T_SAND
            elif h < 0.70:
                tiles[x][y] = T_FOREST if m > 0.52 else T_GRASS
            elif h < 0.80:               tiles[x][y] = T_HIGHLAND
            elif h < 0.91:               tiles[x][y] = T_MOUNTAIN
            else:                        tiles[x][y] = T_SNOW

    return tiles, height_map, moisture_map
