"""
renderer_gl.py – moderngl-powered 3D isometric renderer for Jeu Monde.

Architecture
============
• Terrain tiles  → static VBO built once at init.
• Forest trees   → static VBO built once at init.
• Buildings      → semi-static VBO rebuilt when settlement levels / era change.
• Entities/Prey  → persistent pre-allocated VBO, overwritten each frame.
• Campfires      → persistent pre-allocated VBO, overwritten in era-0 frames.
• HUD / UI       → drawn to a CPU pygame.Surface then uploaded as a GL texture
                   and composited as a fullscreen alpha-blended quad.

The vertex shader uses the same isometric projection as renderer.py so that
world_to_screen / screen_to_world remain valid for mouse hit-testing.
"""

import moderngl
import numpy as np
import pygame
import math

from config import (
    SCREEN_W, SCREEN_H, TILE_W, TILE_H, WORLD_W, WORLD_H,
    TILE_COLORS,
    T_DEEP_WATER, T_WATER, T_SAND, T_GRASS, T_FOREST,
    T_HIGHLAND, T_MOUNTAIN, T_SNOW,
)
import renderer as _pr
from simulation import CLAN_COLORS

# ── 3D terrain height per tile type (world-units) ─────────────────────────────
_H3D = {
    T_DEEP_WATER: -0.22,
    T_WATER:       0.00,
    T_SAND:        0.05,
    T_GRASS:       0.10,
    T_FOREST:      0.16,
    T_HIGHLAND:    0.42,
    T_MOUNTAIN:    0.92,
    T_SNOW:        1.32,
}

# Building (body_h, roof_h) in world-units, per blvl 0-5
_BH = [
    (0.00, 0.00),  # 0 campfire / marker
    (0.30, 0.28),  # 1 hut
    (0.46, 0.34),  # 2 village building
    (0.74, 0.14),  # 3 tower/bourg
    (1.12, 0.10),  # 4 city keep
    (1.92, 0.38),  # 5 megacity
]

# Per-face lighting multipliers  (isometric sun from upper-northwest)
_FL = dict(top=0.94, south=0.72, east=0.58, west=0.40, north=0.36)

# Pre-allocation limits
_MAX_ENT_FLOATS  = 2000 * 12 * 6   # 2000 entities × 12 verts × 6 floats
_MAX_FIRE_FLOATS = 200  * 6  * 6   # 200 fires × 6 verts × 6 floats

# ── GLSL shaders ──────────────────────────────────────────────────────────────

_WORLD_VERT = """
#version 330 core
in vec3 in_pos;
in vec3 in_col;
uniform float u_cx, u_cy, u_zoom;
uniform float u_tw, u_th, u_sw, u_sh, u_ww_wh;
out vec3 v_col;
void main() {
    float wx = in_pos.x, wy = in_pos.y, wz = in_pos.z;
    float tw2 = u_tw * u_zoom * 0.5;
    float th2 = u_th * u_zoom * 0.5;
    float th  = u_th * u_zoom;
    // Same isometric formula as renderer.py  world_to_screen()
    float sx  = (wx - wz) * tw2 - u_cx + u_sw * 0.5;
    float sy  = (wx + wz) * th2 - wy * th - u_cy + u_sh / 3.0;
    // depth: larger diagonal = in front = smaller Z
    float diag  = (wx + wz) / u_ww_wh;
    float sub   = (wx - wz) / u_ww_wh;
    float depth = clamp(1.0 - diag * 1.96 - wy * 0.055 + sub * 0.0005,
                        -0.9995, 0.9995);
    gl_Position = vec4(sx / (u_sw * 0.5) - 1.0,
                       1.0 - sy / (u_sh * 0.5),
                       depth, 1.0);
    v_col = in_col;
}
"""

_WORLD_FRAG = """
#version 330 core
in vec3 v_col;
out vec4 f_col;
void main() { f_col = vec4(v_col, 1.0); }
"""

_UI_VERT = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); v_uv = in_uv; }
"""

_UI_FRAG = """
#version 330 core
uniform sampler2D u_tex;
in vec2 v_uv;
out vec4 f_col;
void main() { f_col = texture(u_tex, v_uv); }
"""


# ── CPU-side geometry helpers ──────────────────────────────────────────────────

def _lit(col, factor):
    """Return float RGB tuple (0-1 range) scaled by lighting factor."""
    f = max(0.0, min(1.4, factor))
    return (col[0] / 255.0 * f, col[1] / 255.0 * f, col[2] / 255.0 * f)


def _add_quad(buf, p0, p1, p2, p3, rgb):
    """Append two CCW triangles (= a quad) to buf list."""
    for tri in ((p0, p1, p2), (p0, p2, p3)):
        for p in tri:
            buf.extend(p)
            buf.extend(rgb)


def _add_tri(buf, a, b, c, rgb):
    for p in (a, b, c):
        buf.extend(p)
        buf.extend(rgb)


# ── Terrain geometry ──────────────────────────────────────────────────────────

def _build_tile_data(tiles):
    buf = []
    for gx in range(WORLD_W):
        for gy in range(WORLD_H):
            tt  = tiles[gx][gy]
            h   = _H3D.get(tt, 0.0)
            col = TILE_COLORS[tt]

            # top face
            _add_quad(buf,
                (gx,   h, gy  ), (gx+1, h, gy  ),
                (gx+1, h, gy+1), (gx,   h, gy+1),
                _lit(col, _FL['top']))

            # south cliff (Z+ face) – only when this tile is higher
            if gy < WORLD_H - 1:
                hs = _H3D.get(tiles[gx][gy + 1], 0.0)
                if h > hs + 0.001:
                    _add_quad(buf,
                        (gx,   hs, gy+1), (gx+1, hs, gy+1),
                        (gx+1, h,  gy+1), (gx,   h,  gy+1),
                        _lit(col, _FL['south']))

            # east cliff (X+ face)
            if gx < WORLD_W - 1:
                he = _H3D.get(tiles[gx + 1][gy], 0.0)
                if h > he + 0.001:
                    _add_quad(buf,
                        (gx+1, he, gy  ), (gx+1, he, gy+1),
                        (gx+1, h,  gy+1), (gx+1, h,  gy  ),
                        _lit(col, _FL['east']))

    return np.array(buf, dtype='f4')


# ── Forest tree geometry ───────────────────────────────────────────────────────

def _build_tree_data(tiles):
    buf = []
    for gx in range(WORLD_W):
        for gy in range(WORLD_H):
            if tiles[gx][gy] != T_FOREST:
                continue
            h  = _H3D[T_FOREST]
            cx = gx + 0.5
            cz = gy + 0.5

            # trunk
            tw = 0.055; th = 0.18
            tc = _lit((95, 60, 28), _FL['top'])
            ts = _lit((70, 44, 20), _FL['south'])
            te = _lit((70, 44, 20), _FL['east'])
            _add_quad(buf,
                (cx-tw, h+th, cz-tw), (cx+tw, h+th, cz-tw),
                (cx+tw, h+th, cz+tw), (cx-tw, h+th, cz+tw), tc)
            _add_quad(buf,
                (cx-tw, h, cz+tw), (cx+tw, h, cz+tw),
                (cx+tw, h+th, cz+tw), (cx-tw, h+th, cz+tw), ts)
            _add_quad(buf,
                (cx+tw, h, cz-tw), (cx+tw, h, cz+tw),
                (cx+tw, h+th, cz+tw), (cx+tw, h+th, cz-tw), te)

            # canopy: two pyramid tiers (lower = larger, darker)
            for cr, ch, yb, dark in (
                (0.32, 0.40, h + th * 0.35, 1.00),
                (0.22, 0.32, h + th * 0.78, 0.86),
            ):
                pk = (cx, yb + ch, cz)
                _add_tri(buf, (cx-cr,yb,cz+cr),(cx+cr,yb,cz+cr), pk,
                         _lit((24,106,24), _FL['south']*dark))
                _add_tri(buf, (cx+cr,yb,cz-cr),(cx+cr,yb,cz+cr), pk,
                         _lit((24,106,24), _FL['east']*dark))
                _add_tri(buf, (cx+cr,yb,cz-cr),(cx-cr,yb,cz-cr), pk,
                         _lit((18, 82,18), _FL['north']*dark))
                _add_tri(buf, (cx-cr,yb,cz+cr),(cx-cr,yb,cz-cr), pk,
                         _lit((18, 82,18), _FL['west']*dark))

    return np.array(buf, dtype='f4') if buf else np.zeros(0, dtype='f4')


# ── Building geometry ─────────────────────────────────────────────────────────

def _add_building(buf, gx, gy, h_tile, blvl, era_idx, pal):
    blvl = max(1, min(blvl, 5))
    body_h, roof_h = _BH[blvl]
    if body_h <= 0:
        return

    wl_c, wr_c, wt_c, rf_c, rs_c, ol_c, wn_c = pal
    m   = 0.07
    x0, x1 = gx + m, gx + 1 - m
    z0, z1 = gy + m, gy + 1 - m
    cx  = (x0 + x1) / 2
    cz  = (z0 + z1) / 2
    y0  = h_tile
    y1  = h_tile + body_h

    top_c = _lit(wt_c, _FL['top'])
    sth_c = _lit(wl_c, _FL['south'])  # south = "left wall" in iso
    est_c = _lit(wr_c, _FL['east'])
    wst_c = _lit(wl_c, _FL['west'])
    nth_c = _lit(wt_c, _FL['north'])

    # ── main box ──────────────────────────────────────────────────────────
    _add_quad(buf, (x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1), top_c)
    _add_quad(buf, (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1), sth_c)
    _add_quad(buf, (x1,y0,z0),(x1,y0,z1),(x1,y1,z1),(x1,y1,z0), est_c)
    _add_quad(buf, (x0,y0,z1),(x0,y0,z0),(x0,y1,z0),(x0,y1,z1), wst_c)
    _add_quad(buf, (x1,y0,z0),(x0,y0,z0),(x0,y1,z0),(x1,y1,z0), nth_c)

    # ── windows ───────────────────────────────────────────────────────────
    if blvl >= 2:
        win_c  = _lit((215, 210, 178), 0.92)
        win_d  = 0.006   # slight Z-offset so windows sit on the face
        w_frac = [0.28, 0.62] if blvl <= 3 else [0.15, 0.38, 0.62, 0.85]
        n_rows = 1 if blvl <= 2 else (2 if blvl <= 3 else 3)
        for row in range(n_rows):
            fy  = y0 + body_h * (0.22 + row * (0.65 / max(1, n_rows)))
            fh  = body_h * 0.14
            fw  = (x1 - x0) * 0.11
            for frac in w_frac:
                wx0 = x0 + (x1 - x0) * frac
                # south-face windows
                _add_quad(buf,
                    (wx0,    fy,    z1+win_d), (wx0+fw, fy,    z1+win_d),
                    (wx0+fw, fy+fh, z1+win_d), (wx0,    fy+fh, z1+win_d),
                    win_c)
                # east-face windows
                ez0 = z0 + (z1 - z0) * frac
                _add_quad(buf,
                    (x1+win_d, fy,    ez0),    (x1+win_d, fy,    ez0+fw),
                    (x1+win_d, fy+fh, ez0+fw), (x1+win_d, fy+fh, ez0),
                    win_c)

    # ── roof ──────────────────────────────────────────────────────────────
    if roof_h > 0.001:
        if era_idx >= 7:
            # flat roof + parapet
            _add_quad(buf, (x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1),
                      _lit(rf_c, 0.88))
            ph = max(0.04, roof_h * 0.5)
            _add_quad(buf, (x0,y1,z1),(x1,y1,z1),(x1,y1+ph,z1),(x0,y1+ph,z1),
                      _lit(wl_c, 0.86))
            _add_quad(buf, (x1,y1,z0),(x1,y1,z1),(x1,y1+ph,z1),(x1,y1+ph,z0),
                      _lit(wr_c, 0.72))
        else:
            # hip (pyramid) roof
            pk = (cx, y1 + roof_h, cz)
            _add_tri(buf, (x0,y1,z1),(x1,y1,z1), pk, _lit(rf_c, _FL['south']))
            _add_tri(buf, (x1,y1,z0),(x1,y1,z1), pk, _lit(rs_c, _FL['east']))
            _add_tri(buf, (x1,y1,z0),(x0,y1,z0), pk, _lit(rf_c, _FL['north']))
            _add_tri(buf, (x0,y1,z1),(x0,y1,z0), pk, _lit(rs_c, _FL['west']))

    # ── secondary tower (level 3+) ─────────────────────────────────────────
    if blvl >= 3:
        tw = (x1 - x0) * 0.34
        tz = (z1 - z0) * 0.34
        tx0 = cx - tw; tx1 = cx + tw
        tz0 = cz - tz; tz1 = cz + tz
        ty0 = y1; ty1 = y1 + body_h * 0.48
        _add_quad(buf, (tx0,ty1,tz0),(tx1,ty1,tz0),(tx1,ty1,tz1),(tx0,ty1,tz1),
                  _lit(wt_c, _FL['top'] * 0.90))
        _add_quad(buf, (tx0,ty0,tz1),(tx1,ty0,tz1),(tx1,ty1,tz1),(tx0,ty1,tz1),
                  _lit(wl_c, _FL['south'] * 0.88))
        _add_quad(buf, (tx1,ty0,tz0),(tx1,ty0,tz1),(tx1,ty1,tz1),(tx1,ty1,tz0),
                  _lit(wr_c, _FL['east'] * 0.88))
        tpk = (cx, ty1 + body_h * 0.28, cz)
        _add_tri(buf, (tx0,ty1,tz1),(tx1,ty1,tz1), tpk, _lit(rf_c, _FL['south']))
        _add_tri(buf, (tx1,ty1,tz0),(tx1,ty1,tz1), tpk, _lit(rs_c, _FL['east']))
        _add_tri(buf, (tx1,ty1,tz0),(tx0,ty1,tz0), tpk, _lit(rf_c, _FL['north']))
        _add_tri(buf, (tx0,ty1,tz1),(tx0,ty1,tz0), tpk, _lit(rs_c, _FL['west']))

    # ── battlements (level 4+, medieval/ancient eras) ──────────────────────
    if blvl >= 4 and 2 <= era_idx <= 6:
        bh = 0.065
        n  = 4
        step_s = (x1 - x0) / (n * 2)
        step_e = (z1 - z0) / (n * 2)
        mc_s = _lit(wl_c, _FL['south'])
        mc_e = _lit(wr_c, _FL['east'])
        for i in range(n):
            ts = (i * 2 + 0.3) * step_s
            te = (i * 2 + 0.3) * step_e
            ws = step_s * 0.8
            we = step_e * 0.8
            _add_quad(buf,
                (x0+ts, y1, z1), (x0+ts+ws, y1, z1),
                (x0+ts+ws, y1+bh, z1), (x0+ts, y1+bh, z1), mc_s)
            _add_quad(buf,
                (x1, y1, z0+te), (x1, y1, z0+te+we),
                (x1, y1+bh, z0+te+we), (x1, y1+bh, z0+te), mc_e)

    # ── megacity spire (level 5) ────────────────────────────────────────────
    if blvl == 5:
        sp_r = (x1 - x0) * 0.07
        sp_h = roof_h * 0.85
        spk  = (cx, y1 + roof_h + sp_h, cz)
        _add_tri(buf, (cx-sp_r,y1+roof_h,cz+sp_r),(cx+sp_r,y1+roof_h,cz+sp_r),
                 spk, _lit(rf_c, _FL['south']))
        _add_tri(buf, (cx+sp_r,y1+roof_h,cz-sp_r),(cx+sp_r,y1+roof_h,cz+sp_r),
                 spk, _lit(rs_c, _FL['east']))
        _add_tri(buf, (cx+sp_r,y1+roof_h,cz-sp_r),(cx-sp_r,y1+roof_h,cz-sp_r),
                 spk, _lit(rf_c, _FL['north']))
        _add_tri(buf, (cx-sp_r,y1+roof_h,cz+sp_r),(cx-sp_r,y1+roof_h,cz-sp_r),
                 spk, _lit(rs_c, _FL['west']))


def _build_building_data(settlements, era_idx, tiles):
    buf = []
    ei  = min(era_idx, 9)
    pal = _pr._ERA_PAL[ei]
    for s in settlements:
        if s.level < 1:
            continue
        layout = _pr._SETTLE_LAYOUTS.get(min(s.level, 5), _pr._SETTLE_LAYOUTS[5])
        for dx, dy, blvl in layout:
            bx = max(0, min(WORLD_W - 1, s.gx + dx))
            by = max(0, min(WORLD_H - 1, s.gy + dy))
            h  = _H3D.get(tiles[bx][by], 0.1)
            _add_building(buf, bx, by, h, blvl, era_idx, pal)
    return np.array(buf, dtype='f4') if buf else np.zeros(0, dtype='f4')


# ── Entity geometry (fills pre-allocated buffer each frame) ───────────────────

def _fill_entity_data(out_buf, entities, prey, tiles, era_idx):
    """Write entity vertices into pre-allocated numpy array; returns vertex count."""
    idx = 0
    fl6 = 6   # floats per vertex

    def put_quad(p0, p1, p2, p3, rgb):
        nonlocal idx
        for tri in ((p0,p1,p2),(p0,p2,p3)):
            for p in tri:
                if idx + fl6 > len(out_buf):
                    return
                out_buf[idx:idx+3] = p
                out_buf[idx+3:idx+6] = rgb
                idx += fl6

    for e in entities:
        gx = max(0, min(WORLD_W - 1, int(e.x)))
        gy = max(0, min(WORLD_H - 1, int(e.y)))
        h  = _H3D.get(tiles[gx][gy], 0.1) + 0.015
        cx, cz = float(e.x), float(e.y)
        cc = CLAN_COLORS[e.clan_id % len(CLAN_COLORS)]
        ct = (cc[0]/255*0.92, cc[1]/255*0.92, cc[2]/255*0.92)
        cb = (cc[0]/255*0.70, cc[1]/255*0.70, cc[2]/255*0.70)
        s  = 0.09; bh = 0.22
        put_quad((cx-s,h+bh,cz-s),(cx+s,h+bh,cz-s),(cx+s,h+bh,cz+s),(cx-s,h+bh,cz+s), ct)
        put_quad((cx-s,h,cz+s),(cx+s,h,cz+s),(cx+s,h+bh,cz+s),(cx-s,h+bh,cz+s), cb)

    for p in prey:
        gx = max(0, min(WORLD_W - 1, int(p.x)))
        gy = max(0, min(WORLD_H - 1, int(p.y)))
        h  = _H3D.get(tiles[gx][gy], 0.1) + 0.015
        s  = 0.11; bh = 0.15
        pt = (0.78, 0.57, 0.24)
        pb = (0.55, 0.40, 0.16)
        put_quad((p.x-s,h+bh,p.y-s),(p.x+s,h+bh,p.y-s),(p.x+s,h+bh,p.y+s),(p.x-s,h+bh,p.y+s), pt)
        put_quad((p.x-s,h,p.y+s),(p.x+s,h,p.y+s),(p.x+s,h+bh,p.y+s),(p.x-s,h+bh,p.y+s), pb)

    return idx // fl6   # number of vertices written


# ── Campfire geometry (era 0 only) ────────────────────────────────────────────

def _fill_fire_data(out_buf, settlements, tiles, tick):
    idx = 0
    fl6 = 6
    flicker = (math.sin(tick * 9.0) + 1.0) * 0.5

    def put_tri(a, b, c, rgb):
        nonlocal idx
        for p in (a, b, c):
            if idx + fl6 > len(out_buf):
                return
            out_buf[idx:idx+3] = p
            out_buf[idx+3:idx+6] = rgb
            idx += fl6

    for s in settlements:
        if s.level != 0:
            continue
        gx = max(0, min(WORLD_W - 1, s.gx))
        gy = max(0, min(WORLD_H - 1, s.gy))
        h  = _H3D.get(tiles[gx][gy], 0.1)
        cx = s.gx + 0.5; cz = s.gy + 0.5
        r  = 0.08
        fh = 0.12 + flicker * 0.07
        cb = (0.92, 0.38 + flicker*0.18, 0.04)
        ct = (1.00, 0.88, 0.32)
        put_tri((cx-r,h,cz),(cx+r,h,cz),(cx,h+fh,cz), cb)
        put_tri((cx,h,cz-r),(cx,h,cz+r),(cx,h+fh,cz), ct)

    return idx // fl6


# ── GLRenderer ────────────────────────────────────────────────────────────────

class GLRenderer:

    def __init__(self, ctx, tiles):
        self.ctx    = ctx
        self._tiles = tiles

        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        # ── compile shaders ──────────────────────────────────────────────
        self._prog    = ctx.program(vertex_shader=_WORLD_VERT,
                                    fragment_shader=_WORLD_FRAG)
        self._ui_prog = ctx.program(vertex_shader=_UI_VERT,
                                    fragment_shader=_UI_FRAG)
        self._ui_prog['u_tex'] = 0

        # ── constant uniforms for world shader ───────────────────────────
        self._prog['u_tw']    = float(TILE_W)
        self._prog['u_th']    = float(TILE_H)
        self._prog['u_sw']    = float(SCREEN_W)
        self._prog['u_sh']    = float(SCREEN_H)
        self._prog['u_ww_wh'] = float(WORLD_W + WORLD_H)

        # ── static terrain VBO ───────────────────────────────────────────
        tile_data = _build_tile_data(tiles)
        self._tile_vbo = ctx.buffer(tile_data)
        self._tile_vao = ctx.vertex_array(
            self._prog, [(self._tile_vbo, '3f 3f', 'in_pos', 'in_col')])

        # ── static tree VBO ──────────────────────────────────────────────
        tree_data = _build_tree_data(tiles)
        self._tree_vbo = self._tree_vao = None
        if len(tree_data) > 0:
            self._tree_vbo = ctx.buffer(tree_data)
            self._tree_vao = ctx.vertex_array(
                self._prog, [(self._tree_vbo, '3f 3f', 'in_pos', 'in_col')])

        # ── semi-static building VBO ─────────────────────────────────────
        self._bldg_vbo      = None
        self._bldg_vao      = None
        self._last_bldg_key = None   # (era_idx, sorted settlement levels)

        # ── pre-allocated entity VBO ─────────────────────────────────────
        self._ent_buf = np.zeros(_MAX_ENT_FLOATS, dtype='f4')
        self._ent_vbo = ctx.buffer(self._ent_buf)
        self._ent_vao = ctx.vertex_array(
            self._prog, [(self._ent_vbo, '3f 3f', 'in_pos', 'in_col')])
        self._ent_n   = 0

        # ── pre-allocated campfire VBO ───────────────────────────────────
        self._fire_buf = np.zeros(_MAX_FIRE_FLOATS, dtype='f4')
        self._fire_vbo = ctx.buffer(self._fire_buf)
        self._fire_vao = ctx.vertex_array(
            self._prog, [(self._fire_vbo, '3f 3f', 'in_pos', 'in_col')])
        self._fire_n   = 0

        # ── UI overlay ────────────────────────────────────────────────────
        self._ui_tex  = ctx.texture((SCREEN_W, SCREEN_H), 4)
        self._ui_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._ui_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

        # Fullscreen NDC quad; UV accounts for pygame → OpenGL Y-flip (flip=True)
        ui_quad = np.array([
            -1, -1,   0, 0,
             1, -1,   1, 0,
             1,  1,   1, 1,
            -1, -1,   0, 0,
             1,  1,   1, 1,
            -1,  1,   0, 1,
        ], dtype='f4')
        self._ui_quad_vbo = ctx.buffer(ui_quad)
        self._ui_quad_vao = ctx.vertex_array(
            self._ui_prog,
            [(self._ui_quad_vbo, '2f 2f', 'in_pos', 'in_uv')])

    # ── building management ───────────────────────────────────────────────────

    def _update_buildings(self, settlements, era_idx):
        key = (era_idx,) + tuple((s.level, s.gx, s.gy) for s in settlements)
        if key == self._last_bldg_key:
            return
        data = _build_building_data(settlements, era_idx, self._tiles)
        if self._bldg_vbo is not None:
            self._bldg_vbo.release()
            self._bldg_vao.release()
        self._bldg_vbo = self._bldg_vao = None
        if len(data) > 0:
            self._bldg_vbo = self.ctx.buffer(data)
            self._bldg_vao = self.ctx.vertex_array(
                self._prog, [(self._bldg_vbo, '3f 3f', 'in_pos', 'in_col')])
        self._last_bldg_key = key

    # ── main render ───────────────────────────────────────────────────────────

    def render(self, sim, camera, tick, fonts, selected_entity=None):
        era_idx, era = sim.get_era()
        cam_x, cam_y, zoom = camera.x, camera.y, camera.zoom

        # Day/night sky colour
        dp = sim.day_phase
        if   dp < 0.25: bright = 0.55 + dp / 0.25 * 0.45
        elif dp < 0.50: bright = 1.0
        elif dp < 0.75: bright = 1.0 - (dp - 0.50) / 0.25 * 0.45
        else:           bright = max(0.18, 0.55 - (dp - 0.75) / 0.25 * 0.37)
        sky = era[2]

        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.clear(
            sky[0] / 255.0 * bright,
            sky[1] / 255.0 * bright,
            sky[2] / 255.0 * bright,
            1.0, depth=1.0,
        )

        # Camera uniforms (per-frame)
        self._prog['u_cx']   = cam_x
        self._prog['u_cy']   = cam_y
        self._prog['u_zoom'] = zoom

        # ── terrain ───────────────────────────────────────────────────────
        self._tile_vao.render(moderngl.TRIANGLES)

        # ── trees ─────────────────────────────────────────────────────────
        if self._tree_vao:
            self._tree_vao.render(moderngl.TRIANGLES)

        # ── buildings ─────────────────────────────────────────────────────
        self._update_buildings(sim.settlements, era_idx)
        if self._bldg_vao:
            self._bldg_vao.render(moderngl.TRIANGLES)

        # ── campfires (era 0 only) ────────────────────────────────────────
        if era_idx == 0:
            self._fire_n = _fill_fire_data(
                self._fire_buf, sim.settlements, self._tiles, tick)
            if self._fire_n > 0:
                self._fire_vbo.write(self._fire_buf[:self._fire_n * 6])
                self._fire_vao.render(moderngl.TRIANGLES, vertices=self._fire_n)

        # ── entities ──────────────────────────────────────────────────────
        step = max(1, len(sim.entities) // 500)
        self._ent_n = _fill_entity_data(
            self._ent_buf, sim.entities[::step], sim.prey, self._tiles, era_idx)
        if self._ent_n > 0:
            self._ent_vbo.write(self._ent_buf[:self._ent_n * 6])
            self._ent_vao.render(moderngl.TRIANGLES, vertices=self._ent_n)

        # ── UI overlay ────────────────────────────────────────────────────
        self._render_ui(sim, era_idx, era, camera, fonts, tick, selected_entity)

    # ── UI overlay ────────────────────────────────────────────────────────────

    def _render_ui(self, sim, era_idx, era, camera, fonts, tick, selected_entity):
        ui = self._ui_surf
        ui.fill((0, 0, 0, 0))

        # Settlement name labels
        _pr._draw_settlement_labels(
            ui, sim.settlements, era_idx,
            camera.x, camera.y, camera.zoom, fonts)

        # Selected entity highlight + nametag
        if selected_entity is not None:
            sx, sy = _pr.world_to_screen(
                selected_entity.x, selected_entity.y,
                camera.x, camera.y, camera.zoom)
            ring_r = max(6, int(camera.zoom * 10))
            pygame.draw.circle(ui, (255, 215, 50), (sx, sy),
                               ring_r, max(1, int(camera.zoom * 2)))
            _pr._draw_nametag(ui, sx, sy, selected_entity,
                              era_idx, camera.zoom, fonts)

        # HUD
        _pr._draw_ui(ui, sim, era_idx, era, fonts, camera.zoom)

        # Info panel
        if selected_entity is not None:
            _pr._draw_info_panel(ui, selected_entity, era_idx, sim.year, fonts)

        # Upload surface to GL texture (flip=True: pygame Y-flip → OpenGL convention)
        raw = pygame.image.tostring(ui, 'RGBA', True)
        self._ui_tex.write(raw)

        # Composite as alpha-blended fullscreen quad
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._ui_tex.use(0)
        self._ui_quad_vao.render(moderngl.TRIANGLES)
        self.ctx.enable(moderngl.DEPTH_TEST)

    # ── cleanup ───────────────────────────────────────────────────────────────

    def release(self):
        for obj in [
            self._tile_vbo, self._tile_vao,
            self._tree_vbo, self._tree_vao,
            self._bldg_vbo, self._bldg_vao,
            self._ent_vbo,  self._ent_vao,
            self._fire_vbo, self._fire_vao,
            self._ui_tex,   self._ui_quad_vbo, self._ui_quad_vao,
        ]:
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
