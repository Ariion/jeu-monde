"""
renderer_gl.py – moderngl 3D renderer for Jeu Monde.

Uses a standalone moderngl context (no OPENGL display flag needed) with an
off-screen Framebuffer Object (FBO).  Each frame:
  1.  Render 3D world (terrain + trees + buildings + entities) → FBO.
  2.  Blit FBO pixels to a pre-allocated pygame Surface.
  3.  Caller draws UI on top with normal pygame calls.

Y-flip: the vertex shader uses a flipped NDC-Y so that OpenGL's bottom-to-top
pixel order matches pygame's top-to-bottom order after fbo.read() — no numpy
transpose needed.
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

# ── 3D terrain heights (world-units; 1 unit = 1 tile width) ──────────────────
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

# Building (body_h, roof_h) in world-units per blvl 0-5
_BH = [
    (0.00, 0.00),
    (0.30, 0.28),
    (0.46, 0.34),
    (0.74, 0.14),
    (1.12, 0.10),
    (1.92, 0.38),
]

# Per-face directional lighting (sun from upper-northwest)
_FL = dict(top=0.94, south=0.72, east=0.58, west=0.40, north=0.36)

# Buffer limits
_MAX_ENT_FLOATS  = 2000 * 12 * 6
_MAX_FIRE_FLOATS =  200 *  6 * 6

# ── GLSL shaders ──────────────────────────────────────────────────────────────
# NDC-Y is FLIPPED so that OpenGL's bottom-to-top pixel order comes out as
# pygame's top-to-bottom after fbo.read().  (sy=0 → ndc_y=-1 → bottom of GL
# framebuffer → first bytes of fbo.read() → row 0 in pygame.)

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
    float sx  = (wx - wz) * tw2 - u_cx + u_sw * 0.5;
    float sy  = (wx + wz) * th2 - wy * th - u_cy + u_sh / 3.0;
    float diag  = (wx + wz) / u_ww_wh;
    float sub   = (wx - wz) / u_ww_wh;
    float depth = clamp(1.0 - diag * 1.96 - wy * 0.055 + sub * 0.0005,
                        -0.9995, 0.9995);
    // Y is FLIPPED so fbo.read() bytes match pygame top-to-bottom row order
    float ndc_x =  sx / (u_sw * 0.5) - 1.0;
    float ndc_y =  sy / (u_sh * 0.5) - 1.0;   // flipped vs. standard OpenGL
    gl_Position = vec4(ndc_x, ndc_y, depth, 1.0);
    v_col = in_col;
}
"""

_WORLD_FRAG = """
#version 330 core
in vec3 v_col;
out vec4 f_col;
void main() { f_col = vec4(v_col, 1.0); }
"""

# ── Geometry helpers ──────────────────────────────────────────────────────────

def _lit(col, factor):
    f = max(0.0, min(1.4, factor))
    return (col[0] / 255.0 * f, col[1] / 255.0 * f, col[2] / 255.0 * f)

def _add_quad(buf, p0, p1, p2, p3, rgb):
    for tri in ((p0, p1, p2), (p0, p2, p3)):
        for p in tri:
            buf.extend(p); buf.extend(rgb)

def _add_tri(buf, a, b, c, rgb):
    for p in (a, b, c):
        buf.extend(p); buf.extend(rgb)

# ── Terrain ───────────────────────────────────────────────────────────────────

def _build_tile_data(tiles):
    buf = []
    for gx in range(WORLD_W):
        for gy in range(WORLD_H):
            tt  = tiles[gx][gy]
            h   = _H3D.get(tt, 0.0)
            col = TILE_COLORS[tt]
            _add_quad(buf,
                (gx,  h,gy),(gx+1,h,gy),(gx+1,h,gy+1),(gx,h,gy+1),
                _lit(col, _FL['top']))
            if gy < WORLD_H - 1:
                hs = _H3D.get(tiles[gx][gy+1], 0.0)
                if h > hs + 0.001:
                    _add_quad(buf,
                        (gx,hs,gy+1),(gx+1,hs,gy+1),(gx+1,h,gy+1),(gx,h,gy+1),
                        _lit(col, _FL['south']))
            if gx < WORLD_W - 1:
                he = _H3D.get(tiles[gx+1][gy], 0.0)
                if h > he + 0.001:
                    _add_quad(buf,
                        (gx+1,he,gy),(gx+1,he,gy+1),(gx+1,h,gy+1),(gx+1,h,gy),
                        _lit(col, _FL['east']))
    return np.array(buf, dtype='f4')

# ── Trees ─────────────────────────────────────────────────────────────────────

def _build_tree_data(tiles):
    buf = []
    for gx in range(WORLD_W):
        for gy in range(WORLD_H):
            if tiles[gx][gy] != T_FOREST:
                continue
            h = _H3D[T_FOREST]; cx = gx+0.5; cz = gy+0.5
            tw = 0.055; th = 0.18
            _add_quad(buf,
                (cx-tw,h+th,cz-tw),(cx+tw,h+th,cz-tw),
                (cx+tw,h+th,cz+tw),(cx-tw,h+th,cz+tw),
                _lit((95,60,28), _FL['top']))
            _add_quad(buf,
                (cx-tw,h,cz+tw),(cx+tw,h,cz+tw),(cx+tw,h+th,cz+tw),(cx-tw,h+th,cz+tw),
                _lit((70,44,20), _FL['south']))
            _add_quad(buf,
                (cx+tw,h,cz-tw),(cx+tw,h,cz+tw),(cx+tw,h+th,cz+tw),(cx+tw,h+th,cz-tw),
                _lit((70,44,20), _FL['east']))
            for cr,ch,yb,dk in ((0.32,0.40,h+th*0.35,1.0),(0.22,0.32,h+th*0.78,0.86)):
                pk = (cx,yb+ch,cz)
                _add_tri(buf,(cx-cr,yb,cz+cr),(cx+cr,yb,cz+cr),pk,_lit((24,106,24),_FL['south']*dk))
                _add_tri(buf,(cx+cr,yb,cz-cr),(cx+cr,yb,cz+cr),pk,_lit((24,106,24),_FL['east']*dk))
                _add_tri(buf,(cx+cr,yb,cz-cr),(cx-cr,yb,cz-cr),pk,_lit((18,82,18),_FL['north']*dk))
                _add_tri(buf,(cx-cr,yb,cz+cr),(cx-cr,yb,cz-cr),pk,_lit((18,82,18),_FL['west']*dk))
    return np.array(buf, dtype='f4') if buf else np.zeros(0, dtype='f4')

# ── Buildings ─────────────────────────────────────────────────────────────────

def _add_building(buf, gx, gy, h_tile, blvl, era_idx, pal):
    blvl = max(1, min(blvl, 5))
    body_h, roof_h = _BH[blvl]
    if body_h <= 0:
        return
    wl_c, wr_c, wt_c, rf_c, rs_c, ol_c, wn_c = pal
    m = 0.07
    x0,x1 = gx+m, gx+1-m;  z0,z1 = gy+m, gy+1-m
    cx = (x0+x1)/2;         cz = (z0+z1)/2
    y0 = h_tile;             y1 = h_tile + body_h

    # Box faces
    _add_quad(buf,(x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1), _lit(wt_c,_FL['top']))
    _add_quad(buf,(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1), _lit(wl_c,_FL['south']))
    _add_quad(buf,(x1,y0,z0),(x1,y0,z1),(x1,y1,z1),(x1,y1,z0), _lit(wr_c,_FL['east']))
    _add_quad(buf,(x0,y0,z1),(x0,y0,z0),(x0,y1,z0),(x0,y1,z1), _lit(wl_c,_FL['west']))
    _add_quad(buf,(x1,y0,z0),(x0,y0,z0),(x0,y1,z0),(x1,y1,z0), _lit(wt_c,_FL['north']))

    # Windows
    if blvl >= 2:
        win_c = _lit((215,210,178), 0.92); d = 0.006
        fracs = [0.28,0.62] if blvl <= 3 else [0.15,0.38,0.62,0.85]
        rows  = 1 if blvl <= 2 else (2 if blvl <= 3 else 3)
        for row in range(rows):
            fy = y0 + body_h*(0.22 + row*(0.65/max(1,rows)))
            fh = body_h*0.14
            fw = (x1-x0)*0.11
            for frac in fracs:
                wx0 = x0+(x1-x0)*frac
                _add_quad(buf,(wx0,fy,z1+d),(wx0+fw,fy,z1+d),(wx0+fw,fy+fh,z1+d),(wx0,fy+fh,z1+d),win_c)
                ez0 = z0+(z1-z0)*frac
                _add_quad(buf,(x1+d,fy,ez0),(x1+d,fy,ez0+fw),(x1+d,fy+fh,ez0+fw),(x1+d,fy+fh,ez0),win_c)

    # Roof
    if roof_h > 0.001:
        if era_idx >= 7:
            _add_quad(buf,(x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1),_lit(rf_c,0.88))
            ph = max(0.04, roof_h*0.5)
            _add_quad(buf,(x0,y1,z1),(x1,y1,z1),(x1,y1+ph,z1),(x0,y1+ph,z1),_lit(wl_c,0.86))
            _add_quad(buf,(x1,y1,z0),(x1,y1,z1),(x1,y1+ph,z1),(x1,y1+ph,z0),_lit(wr_c,0.72))
        else:
            pk = (cx, y1+roof_h, cz)
            _add_tri(buf,(x0,y1,z1),(x1,y1,z1),pk,_lit(rf_c,_FL['south']))
            _add_tri(buf,(x1,y1,z0),(x1,y1,z1),pk,_lit(rs_c,_FL['east']))
            _add_tri(buf,(x1,y1,z0),(x0,y1,z0),pk,_lit(rf_c,_FL['north']))
            _add_tri(buf,(x0,y1,z1),(x0,y1,z0),pk,_lit(rs_c,_FL['west']))

    # Secondary tower (level 3+)
    if blvl >= 3:
        tw=(x1-x0)*0.34; tz=(z1-z0)*0.34
        tx0=cx-tw; tx1=cx+tw; tz0=cz-tz; tz1=cz+tz
        ty0=y1; ty1=y1+body_h*0.48
        _add_quad(buf,(tx0,ty1,tz0),(tx1,ty1,tz0),(tx1,ty1,tz1),(tx0,ty1,tz1),_lit(wt_c,_FL['top']*0.90))
        _add_quad(buf,(tx0,ty0,tz1),(tx1,ty0,tz1),(tx1,ty1,tz1),(tx0,ty1,tz1),_lit(wl_c,_FL['south']*0.88))
        _add_quad(buf,(tx1,ty0,tz0),(tx1,ty0,tz1),(tx1,ty1,tz1),(tx1,ty1,tz0),_lit(wr_c,_FL['east']*0.88))
        tpk=(cx,ty1+body_h*0.28,cz)
        _add_tri(buf,(tx0,ty1,tz1),(tx1,ty1,tz1),tpk,_lit(rf_c,_FL['south']))
        _add_tri(buf,(tx1,ty1,tz0),(tx1,ty1,tz1),tpk,_lit(rs_c,_FL['east']))
        _add_tri(buf,(tx1,ty1,tz0),(tx0,ty1,tz0),tpk,_lit(rf_c,_FL['north']))
        _add_tri(buf,(tx0,ty1,tz1),(tx0,ty1,tz0),tpk,_lit(rs_c,_FL['west']))

    # Battlements (level 4+, medieval eras)
    if blvl >= 4 and 2 <= era_idx <= 6:
        bh=0.065; n=4
        ss=(x1-x0)/(n*2); se=(z1-z0)/(n*2)
        for i in range(n):
            ts=(i*2+0.3)*ss; te=(i*2+0.3)*se
            ws=ss*0.8; we=se*0.8
            _add_quad(buf,(x0+ts,y1,z1),(x0+ts+ws,y1,z1),(x0+ts+ws,y1+bh,z1),(x0+ts,y1+bh,z1),_lit(wl_c,_FL['south']))
            _add_quad(buf,(x1,y1,z0+te),(x1,y1,z0+te+we),(x1,y1+bh,z0+te+we),(x1,y1+bh,z0+te),_lit(wr_c,_FL['east']))

    # Megacity spire (level 5)
    if blvl == 5:
        sr=(x1-x0)*0.07; sh_=roof_h*0.85; spk=(cx,y1+roof_h+sh_,cz)
        _add_tri(buf,(cx-sr,y1+roof_h,cz+sr),(cx+sr,y1+roof_h,cz+sr),spk,_lit(rf_c,_FL['south']))
        _add_tri(buf,(cx+sr,y1+roof_h,cz-sr),(cx+sr,y1+roof_h,cz+sr),spk,_lit(rs_c,_FL['east']))
        _add_tri(buf,(cx+sr,y1+roof_h,cz-sr),(cx-sr,y1+roof_h,cz-sr),spk,_lit(rf_c,_FL['north']))
        _add_tri(buf,(cx-sr,y1+roof_h,cz+sr),(cx-sr,y1+roof_h,cz-sr),spk,_lit(rs_c,_FL['west']))


def _build_building_data(settlements, era_idx, tiles):
    buf = []; ei = min(era_idx, 9); pal = _pr._ERA_PAL[ei]
    for s in settlements:
        if s.level < 1: continue
        layout = _pr._SETTLE_LAYOUTS.get(min(s.level,5), _pr._SETTLE_LAYOUTS[5])
        for dx,dy,blvl in layout:
            bx=max(0,min(WORLD_W-1,s.gx+dx)); by=max(0,min(WORLD_H-1,s.gy+dy))
            _add_building(buf, bx, by, _H3D.get(tiles[bx][by],0.1), blvl, era_idx, pal)
    return np.array(buf, dtype='f4') if buf else np.zeros(0, dtype='f4')

# ── Entities (dynamic, pre-allocated buffer) ──────────────────────────────────

def _fill_entity_data(out_buf, entities, prey, tiles, era_idx):
    idx = 0; fl6 = 6
    def put_quad(p0,p1,p2,p3,rgb):
        nonlocal idx
        for tri in ((p0,p1,p2),(p0,p2,p3)):
            for p in tri:
                if idx+fl6 > len(out_buf): return
                out_buf[idx:idx+3]=p; out_buf[idx+3:idx+6]=rgb; idx+=fl6
    for e in entities:
        gx=max(0,min(WORLD_W-1,int(e.x))); gy=max(0,min(WORLD_H-1,int(e.y)))
        h=_H3D.get(tiles[gx][gy],0.1)+0.015
        cx,cz=float(e.x),float(e.y)
        cc=CLAN_COLORS[e.clan_id%len(CLAN_COLORS)]
        ct=(cc[0]/255*0.92,cc[1]/255*0.92,cc[2]/255*0.92)
        cb=(cc[0]/255*0.70,cc[1]/255*0.70,cc[2]/255*0.70)
        s=0.09; bh=0.22
        put_quad((cx-s,h+bh,cz-s),(cx+s,h+bh,cz-s),(cx+s,h+bh,cz+s),(cx-s,h+bh,cz+s),ct)
        put_quad((cx-s,h,cz+s),(cx+s,h,cz+s),(cx+s,h+bh,cz+s),(cx-s,h+bh,cz+s),cb)
    for p in prey:
        gx=max(0,min(WORLD_W-1,int(p.x))); gy=max(0,min(WORLD_H-1,int(p.y)))
        h=_H3D.get(tiles[gx][gy],0.1)+0.015
        s=0.11; bh=0.15
        pt=(0.78,0.57,0.24); pb=(0.55,0.40,0.16)
        put_quad((p.x-s,h+bh,p.y-s),(p.x+s,h+bh,p.y-s),(p.x+s,h+bh,p.y+s),(p.x-s,h+bh,p.y+s),pt)
        put_quad((p.x-s,h,p.y+s),(p.x+s,h,p.y+s),(p.x+s,h+bh,p.y+s),(p.x-s,h+bh,p.y+s),pb)
    return idx//fl6

def _fill_fire_data(out_buf, settlements, tiles, tick):
    idx=0; fl6=6; flicker=(math.sin(tick*9.0)+1.0)*0.5
    def put_tri(a,b,c,rgb):
        nonlocal idx
        for p in(a,b,c):
            if idx+fl6>len(out_buf): return
            out_buf[idx:idx+3]=p; out_buf[idx+3:idx+6]=rgb; idx+=fl6
    for s in settlements:
        if s.level!=0: continue
        gx=max(0,min(WORLD_W-1,s.gx)); gy=max(0,min(WORLD_H-1,s.gy))
        h=_H3D.get(tiles[gx][gy],0.1)
        cx=s.gx+0.5; cz=s.gy+0.5; r=0.08; fh=0.12+flicker*0.07
        put_tri((cx-r,h,cz),(cx+r,h,cz),(cx,h+fh,cz),(0.92,0.38+flicker*0.18,0.04))
        put_tri((cx,h,cz-r),(cx,h,cz+r),(cx,h+fh,cz),(1.00,0.88,0.32))
    return idx//fl6

# ── GLRenderer ────────────────────────────────────────────────────────────────

class GLRenderer:
    """3D renderer using moderngl standalone context + FBO."""

    def __init__(self, ctx, tiles):
        self.ctx    = ctx
        self._tiles = tiles

        ctx.enable(moderngl.DEPTH_TEST)

        # ── shader ───────────────────────────────────────────────────────
        self._prog = ctx.program(vertex_shader=_WORLD_VERT,
                                 fragment_shader=_WORLD_FRAG)
        self._prog['u_tw']    = float(TILE_W)
        self._prog['u_th']    = float(TILE_H)
        self._prog['u_sw']    = float(SCREEN_W)
        self._prog['u_sh']    = float(SCREEN_H)
        self._prog['u_ww_wh'] = float(WORLD_W + WORLD_H)

        # ── off-screen framebuffer ────────────────────────────────────────
        self._fbo_color = ctx.texture((SCREEN_W, SCREEN_H), 3)  # RGB
        self._fbo_depth = ctx.depth_renderbuffer((SCREEN_W, SCREEN_H))
        self._fbo = ctx.framebuffer(
            color_attachments=[self._fbo_color],
            depth_attachment=self._fbo_depth,
        )

        # Pre-allocated pygame surface for blitting FBO pixels
        self._pg_surf = pygame.Surface((SCREEN_W, SCREEN_H))

        # ── static terrain ───────────────────────────────────────────────
        td = _build_tile_data(tiles)
        self._tile_vbo = ctx.buffer(td)
        self._tile_vao = ctx.vertex_array(
            self._prog, [(self._tile_vbo, '3f 3f', 'in_pos', 'in_col')])

        # ── static trees ─────────────────────────────────────────────────
        trd = _build_tree_data(tiles)
        self._tree_vbo = self._tree_vao = None
        if len(trd) > 0:
            self._tree_vbo = ctx.buffer(trd)
            self._tree_vao = ctx.vertex_array(
                self._prog, [(self._tree_vbo, '3f 3f', 'in_pos', 'in_col')])

        # ── semi-static buildings ─────────────────────────────────────────
        self._bldg_vbo = self._bldg_vao = None
        self._last_bldg_key = None

        # ── dynamic entity buffer (pre-allocated, overwritten each frame) ─
        self._ent_buf  = np.zeros(_MAX_ENT_FLOATS,  dtype='f4')
        self._ent_vbo  = ctx.buffer(self._ent_buf)
        self._ent_vao  = ctx.vertex_array(
            self._prog, [(self._ent_vbo, '3f 3f', 'in_pos', 'in_col')])

        # ── dynamic campfire buffer ───────────────────────────────────────
        self._fire_buf = np.zeros(_MAX_FIRE_FLOATS, dtype='f4')
        self._fire_vbo = ctx.buffer(self._fire_buf)
        self._fire_vao = ctx.vertex_array(
            self._prog, [(self._fire_vbo, '3f 3f', 'in_pos', 'in_col')])

    # ── building management ───────────────────────────────────────────────────

    def _update_buildings(self, settlements, era_idx):
        key = (era_idx,) + tuple((s.level, s.gx, s.gy) for s in settlements)
        if key == self._last_bldg_key:
            return
        data = _build_building_data(settlements, era_idx, self._tiles)
        if self._bldg_vbo is not None:
            self._bldg_vbo.release(); self._bldg_vao.release()
            self._bldg_vbo = self._bldg_vao = None
        if len(data) > 0:
            self._bldg_vbo = self.ctx.buffer(data)
            self._bldg_vao = self.ctx.vertex_array(
                self._prog, [(self._bldg_vbo, '3f 3f', 'in_pos', 'in_col')])
        self._last_bldg_key = key

    # ── render ────────────────────────────────────────────────────────────────

    def render_to_surface(self, sim, camera, tick):
        """Render the 3D world to self._pg_surf.  Returns self._pg_surf."""
        era_idx, era = sim.get_era()
        cam_x, cam_y, zoom = camera.x, camera.y, camera.zoom

        # Day/night sky tint
        dp = sim.day_phase
        if   dp < 0.25: bright = 0.55 + dp/0.25*0.45
        elif dp < 0.50: bright = 1.0
        elif dp < 0.75: bright = 1.0 - (dp-0.50)/0.25*0.45
        else:           bright = max(0.18, 0.55 - (dp-0.75)/0.25*0.37)
        sky = era[2]

        # Render into FBO
        self._fbo.use()
        self.ctx.enable(moderngl.DEPTH_TEST)
        self._fbo.clear(
            sky[0]/255.0*bright,
            sky[1]/255.0*bright,
            sky[2]/255.0*bright,
            1.0, depth=1.0,
        )

        self._prog['u_cx']   = cam_x
        self._prog['u_cy']   = cam_y
        self._prog['u_zoom'] = zoom

        # Terrain
        self._tile_vao.render(moderngl.TRIANGLES)

        # Trees
        if self._tree_vao:
            self._tree_vao.render(moderngl.TRIANGLES)

        # Buildings
        self._update_buildings(sim.settlements, era_idx)
        if self._bldg_vao:
            self._bldg_vao.render(moderngl.TRIANGLES)

        # Campfires (era 0)
        if era_idx == 0:
            n = _fill_fire_data(self._fire_buf, sim.settlements, self._tiles, tick)
            if n > 0:
                self._fire_vbo.write(self._fire_buf[:n*6])
                self._fire_vao.render(moderngl.TRIANGLES, vertices=n)

        # Entities
        step = max(1, len(sim.entities) // 500)
        n = _fill_entity_data(self._ent_buf, sim.entities[::step],
                              sim.prey, self._tiles, era_idx)
        if n > 0:
            self._ent_vbo.write(self._ent_buf[:n*6])
            self._ent_vao.render(moderngl.TRIANGLES, vertices=n)

        # Read FBO → pygame surface
        # Because the vertex shader flips NDC-Y, row 0 of fbo.read() = screen top row
        raw = self._fbo.read(components=3)
        # frombuffer: interprets row-major top-to-bottom bytes as a pygame surface
        pygame.surfarray.blit_array(
            self._pg_surf,
            np.frombuffer(raw, dtype='u1')
              .reshape(SCREEN_H, SCREEN_W, 3)
              .transpose(1, 0, 2),   # (H,W,3) → (W,H,3) for pygame surfarray
        )
        return self._pg_surf

    # ── cleanup ───────────────────────────────────────────────────────────────

    def release(self):
        for obj in [
            self._tile_vbo, self._tile_vao,
            self._tree_vbo, self._tree_vao,
            self._bldg_vbo, self._bldg_vao,
            self._ent_vbo,  self._ent_vao,
            self._fire_vbo, self._fire_vao,
            self._fbo_color, self._fbo_depth, self._fbo,
        ]:
            if obj is not None:
                try: obj.release()
                except Exception: pass
