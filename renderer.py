import pygame
import math
from config import (SCREEN_W, SCREEN_H, TILE_W, TILE_H, WORLD_W, WORLD_H,
                    TILE_COLORS, TILE_HEIGHTS, TIME_SPEEDS, ERAS)
from simulation import (S_HUNT, S_DRINK, S_GATHER, S_FLEE, S_WANDER,
                        S_CHOP, S_BUILD, S_SHELTER, CLAN_COLORS)

# ── Cached surfaces (allocated once, not every frame) ────────────────────────
_BAR_SURF  = None
_BOT_SURF  = None
_INFO_BG   = None

# ── Settlement multi-building layouts ────────────────────────────────────────
# Each entry: list of (dx, dy, building_variant) relative to settlement center.
# building_variant maps to _draw_building() level parameter.
_SETTLE_LAYOUTS = {
    0: [(0, 0, 0)],
    1: [(0, 0, 1)],
    2: [(-1,  0, 1), ( 1,  1, 1),
        ( 0,  0, 2)],
    3: [(-2, -1, 1), ( 2, -1, 1), ( 0, -2, 1),
        (-1,  2, 1), ( 1,  2, 1),
        ( 0,  0, 3)],
    4: [(-3,  0, 2), ( 3,  0, 2), ( 0, -3, 2), ( 0,  3, 2),
        (-2, -2, 1), ( 2, -2, 1), (-2,  2, 1), ( 2,  2, 1),
        ( 0,  0, 4)],
    5: [(-4, -1, 3), ( 4, -1, 3), (-1, -4, 3), ( 1, -4, 3),
        (-3,  2, 3), ( 3,  2, 3), (-1,  3, 3), ( 1,  3, 3),
        (-2, -2, 2), ( 2, -2, 2), (-2,  1, 2), ( 2,  1, 2),
        ( 0,  0, 5)],
}


# ───────────────────────────── colour helpers ────────────────────────────────

def _dk(c, f):  return (max(0,int(c[0]*f)), max(0,int(c[1]*f)), max(0,int(c[2]*f)))
def _mix(a, b, t): return (int(a[0]+(b[0]-a[0])*t), int(a[1]+(b[1]-a[1])*t), int(a[2]+(b[2]-a[2])*t))


# ───────────────────────────── coordinate system ─────────────────────────────

def world_to_screen(wx, wy, cam_x, cam_y, zoom=1.0):
    tw = TILE_W * zoom
    th = TILE_H * zoom
    sx = (wx - wy) * (tw / 2) - cam_x + SCREEN_W / 2
    sy = (wx + wy) * (th / 2) - cam_y + SCREEN_H / 3
    return int(sx), int(sy)


def screen_to_world(sx, sy, cam_x, cam_y, zoom=1.0):
    tw = TILE_W * zoom
    th = TILE_H * zoom
    a  = (sx - SCREEN_W / 2 + cam_x) / (tw / 2)
    b  = (sy - SCREEN_H / 3 + cam_y) / (th / 2)
    return (a + b) / 2, (b - a) / 2


def find_nearest_entity(mx, my, entities, cam_x, cam_y, zoom):
    """Return the entity closest to screen click (mx, my), or None."""
    wx, wy = screen_to_world(mx, my, cam_x, cam_y, zoom)
    radius = max(1.5, 3.0 / zoom)
    best, best_d = None, radius
    for e in entities:
        d = math.sqrt((e.x - wx)**2 + (e.y - wy)**2)
        if d < best_d:
            best, best_d = e, d
    return best


# ───────────────────────────── camera ────────────────────────────────────────

class Camera:
    SPEED = 340.0

    def __init__(self):
        cx, cy = WORLD_W // 2, WORLD_H // 2
        sx, sy = world_to_screen(cx, cy, 0, 0, 1.0)
        self.x    = float(sx)
        self.y    = float(sy)
        self.zoom = 1.0

    def move(self, dx, dy, dt):
        self.x += dx * self.SPEED * dt
        self.y += dy * self.SPEED * dt

    def zoom_by(self, factor, mx=None, my=None):
        if mx is None: mx = SCREEN_W // 2
        if my is None: my = SCREEN_H // 3
        new_zoom = max(0.30, min(4.0, self.zoom * factor))
        rf = new_zoom / self.zoom
        self.x    = self.x + (self.x + mx - SCREEN_W // 2) * (rf - 1)
        self.y    = self.y + (self.y + my - SCREEN_H // 3) * (rf - 1)
        self.zoom = new_zoom


# ───────────────────────────── tile rendering ────────────────────────────────

def _draw_tile(surface, gx, gy, tile_type, cam_x, cam_y, zoom):
    sx, sy = world_to_screen(gx, gy, cam_x, cam_y, zoom)
    h  = int(TILE_HEIGHTS[tile_type] * zoom)
    w2 = int(TILE_W * zoom / 2)
    h2 = int(TILE_H * zoom / 2)
    th = int(TILE_H * zoom)

    # Frustum cull
    if sx + w2 < -4 or sx - w2 > SCREEN_W + 4: return
    if sy + h2 + h < -4 or sy > SCREEN_H + 4:  return

    base  = TILE_COLORS[tile_type]
    left  = _dk(base, 0.58)
    right = _dk(base, 0.76)

    if h > 0:
        pygame.draw.polygon(surface, left, [
            (sx-w2, sy+h2), (sx, sy+th), (sx, sy+th+h), (sx-w2, sy+h2+h)])
        pygame.draw.polygon(surface, right, [
            (sx, sy+th), (sx+w2, sy+h2), (sx+w2, sy+h2+h), (sx, sy+th+h)])

    top = [(sx, sy-h), (sx+w2, sy+h2-h), (sx, sy+th-h), (sx-w2, sy+h2-h)]
    pygame.draw.polygon(surface, base, top)
    if zoom > 0.5:
        pygame.draw.aalines(surface, _dk(base, 0.82), True, top)


# ───────────────────────────── building rendering ────────────────────────────

def _draw_building(surface, gx, gy, level, era_idx, cam_x, cam_y, zoom, tick):
    sx, sy = world_to_screen(gx+0.5, gy+0.5, cam_x, cam_y, zoom)
    sy -= int(TILE_HEIGHTS.get(3, 6) * zoom) + 2
    z = zoom

    if level == 0:   # campfire
        flicker = int(math.sin(tick*9 + gx)*2)
        r = max(2, int(3*z))
        pygame.draw.circle(surface, (70,40,10),   (sx, sy+r), max(1,r-1))
        pygame.draw.circle(surface, (255, 140+flicker*8, 20), (sx, sy), r)
        pygame.draw.circle(surface, (255, 220, 100), (sx, sy), max(1,r-1))

    elif level == 1:  # hut
        w = max(4, int(8*z)); h = max(3, int(6*z))
        pygame.draw.rect(surface, (155,108,62), (sx-w//2, sy, w, h))
        pygame.draw.polygon(surface, (190,75,50),
            [(sx-w//2-1, sy), (sx+w//2+1, sy), (sx, sy-int(8*z))])

    elif level == 2:  # village
        w = max(6, int(12*z)); h = max(4, int(9*z))
        pygame.draw.rect(surface, (140,132,112), (sx-w//2, sy-2, w, h))
        pygame.draw.polygon(surface, (165,72,52),
            [(sx-w//2-1, sy-2), (sx+w//2+1, sy-2), (sx, sy-2-int(10*z))])

    elif level == 3:  # town
        w = max(8, int(14*z)); h = max(6, int(12*z))
        pygame.draw.rect(surface, (120,114,104), (sx-w//2, sy-4, w, h))
        tw = max(4, int(5*z)); th2 = max(5, int(14*z))
        pygame.draw.rect(surface, (100,95,88), (sx-tw//2, sy-4-th2, tw, th2))
        pygame.draw.polygon(surface, (80,60,40),
            [(sx-tw//2, sy-4-th2), (sx+tw//2, sy-4-th2), (sx, sy-4-th2-int(5*z))])

    elif level == 4:  # city
        w = max(10, int(14*z)); h = max(12, int(22*z))
        pygame.draw.rect(surface, (108,118,142), (sx-w//2, sy-h, w, h))
        pygame.draw.rect(surface, (125,138,162), (sx-w//3, sy-h-int(7*z), w//2, int(7*z)))
        if era_idx >= 6:
            cw = max(2, int(3*z))
            pygame.draw.rect(surface, (75,70,68), (sx+w//2, sy-int(28*z), cw, int(14*z)))
            smoke_y = int(sy - 28*z - int(math.sin(tick*2+gx)*2))
            pygame.draw.circle(surface, (90,88,85), (sx+w//2+cw//2, smoke_y), max(2,int(3*z)))
        step = max(1, int(5*z)); win = max(1, int(2*z))
        for row in range(3):
            for col in range(2):
                wx_ = sx - w//2 + int(3*z) + col*int(6*z)
                wy_ = sy - h + int(3*z) + row*step
                pygame.draw.rect(surface, (255,240,165), (wx_, wy_, win, win))

    elif level == 5:  # megacity / future
        w = max(10, int(12*z)); h = max(18, int(36*z))
        if era_idx >= 9:
            glow_col = (50+int(math.sin(tick*1.5)*15), 90, 220)
            pygame.draw.rect(surface, glow_col, (sx-w//2, sy-h, w, h))
            top_r = max(3, int(5*z))
            pygame.draw.circle(surface, (160,200,255), (sx, sy-h), top_r)
            pygame.draw.circle(surface, (255,255,255), (sx, sy-h), max(1,top_r-2))
        else:
            pygame.draw.rect(surface, (95,110,142), (sx-w//2, sy-h, w, h))
            pygame.draw.rect(surface, (112,128,162), (sx-w//3, sy-h-int(8*z), w//2, int(8*z)))
            step = max(1, int(5*z)); win = max(1, int(2*z))
            for row in range(5):
                for col in range(2):
                    wx_ = sx - w//2 + int(2*z) + col*int(6*z)
                    wy_ = sy - h + int(3*z) + row*step
                    pygame.draw.rect(surface, (255,240,165), (wx_, wy_, win, win))


# ───────────────────────────── character rendering ───────────────────────────

_SKIN = [
    (158,108,62),(172,132,84),(190,154,102),(202,164,114),
    (210,174,130),(215,182,142),(218,188,150),(220,192,158),
    (222,230,250),(212,232,255),
]
_CLOTH = [
    (82,58,36),(103,78,46),(98,73,44),(118,88,54),
    (82,68,138),(78,98,158),(48,78,138),(33,58,118),
    (68,118,208),(88,148,252),
]
_CLOTH2 = [   # highlight / second layer colour
    (110,80,50),(130,100,60),(120,95,58),(148,112,68),
    (110,90,168),(105,128,188),(78,108,168),(58,88,148),
    (98,148,238),(118,178,255),
]


def _draw_character(surface, sx, sy, entity, era_idx, tick, zoom, selected=False):
    r = max(2, int(zoom * 5))          # base unit: head radius
    # Children appear smaller
    if not entity.is_prey and entity.stage == 'child':
        r = max(2, int(r * 0.62))

    ei = min(era_idx, len(_SKIN)-1)
    skin  = _SKIN[ei]
    cloth = _CLOTH[ei]
    c2    = _CLOTH2[ei]

    # Tint cloth with clan colour
    if not entity.is_prey:
        cc    = CLAN_COLORS[entity.clan_id % len(CLAN_COLORS)]
        cloth = _mix(cloth, cc, 0.45)
        c2    = _mix(c2,    cc, 0.35)

    # Phase offset per entity so all don't walk in sync
    phase    = tick * 5.5 + entity.eid * 2.37
    leg_sw   = math.sin(phase) * r * 0.8
    arm_sw   = -math.sin(phase) * r * 0.6

    body_top = sy - r      # top of torso (= bottom of head)
    body_bot = sy + r + r  # bottom of torso

    # ── shadow ──
    pygame.draw.ellipse(surface, (0,0,0),
        (sx - r, body_bot + 1, r*2, max(1, r//2)))

    if zoom < 0.6:
        # Far view: single coloured dot
        pygame.draw.circle(surface, skin, (sx, sy-r//2), max(2, r))
        return

    # ── legs ──
    if zoom >= 0.9:
        lw = max(1, r//2)
        pygame.draw.line(surface, cloth,
            (sx - r//2, body_bot), (sx - r//2 + int(leg_sw), body_bot + r + r//2), lw)
        pygame.draw.line(surface, cloth,
            (sx + r//2, body_bot), (sx + r//2 - int(leg_sw), body_bot + r + r//2), lw)
        # Feet dots
        pygame.draw.circle(surface, _dk(cloth, 0.8),
            (sx - r//2 + int(leg_sw), body_bot + r + r//2), max(1, r//3))
        pygame.draw.circle(surface, _dk(cloth, 0.8),
            (sx + r//2 - int(leg_sw), body_bot + r + r//2), max(1, r//3))

    # ── torso ──
    tw = max(1, r*2 - 1)
    th = max(2, r*2 + 2)
    pygame.draw.rect(surface, cloth, (sx - r + 1, body_top, tw, th))
    # Belt / detail stripe
    if zoom >= 1.4:
        pygame.draw.rect(surface, c2, (sx - r + 1, body_top + th//2 - 1, tw, max(1, r//3)))

    # ── arms ──
    if zoom >= 0.9:
        lw = max(1, r//2)
        arm_y = body_top + r//2
        pygame.draw.line(surface, skin,
            (sx - r, arm_y), (sx - r*2 - int(arm_sw), arm_y + r), lw)
        pygame.draw.line(surface, skin,
            (sx + r, arm_y), (sx + r*2 + int(arm_sw), arm_y + r), lw)

    # ── head ──
    pygame.draw.circle(surface, skin, (sx, body_top - 1), r)

    # ── hair / hat ──
    if zoom >= 1.2:
        if era_idx == 0:   # messy dark hair
            hair = (55, 38, 22)
            pygame.draw.arc(surface, hair,
                (sx-r, body_top-1-r, r*2, r+1), 0, math.pi, max(1, r//2))
        elif era_idx <= 2:  # simple hair
            pygame.draw.arc(surface, (80,55,30),
                (sx-r, body_top-1-r, r*2, r+1), 0, math.pi, max(1, r//2))
        elif era_idx == 4:  # medieval coif/hood
            pygame.draw.polygon(surface, _dk(cloth, 1.1),
                [(sx-r, body_top), (sx+r, body_top),
                 (sx+r-r//2, body_top-r-r//2), (sx-r+r//2, body_top-r-r//2)])
        elif era_idx == 6:  # top hat / cap
            cap_w = max(2, r + r//2)
            pygame.draw.rect(surface, (35,32,30),
                (sx - cap_w//2, body_top - r - r//2, cap_w, r//2))
            pygame.draw.rect(surface, (45,42,40),
                (sx - r//2, body_top - r - r, r, r//2))

    # ── eyes ──
    if zoom >= 2.0:
        eye_r = max(1, r//4)
        pygame.draw.circle(surface, (30,22,14), (sx - r//3, body_top - r//2), eye_r)
        pygame.draw.circle(surface, (30,22,14), (sx + r//3, body_top - r//2), eye_r)
        # white dot
        pygame.draw.circle(surface, (220,220,220),
            (sx - r//3 + max(1,eye_r//2), body_top - r//2 - max(1,eye_r//2)), max(1,eye_r//3))
        pygame.draw.circle(surface, (220,220,220),
            (sx + r//3 + max(1,eye_r//2), body_top - r//2 - max(1,eye_r//2)), max(1,eye_r//3))

    # ── selection ring ──
    if selected:
        ring_r = r + max(3, int(4*zoom))
        pygame.draw.circle(surface, (255, 215, 50), (sx, body_top-1), ring_r, max(1,int(2*zoom)))
        # Name tag above
        pass  # drawn separately in _draw_nametag

    # ── wood bundle on back when carrying ──
    if not entity.is_prey and entity.inv_wood > 0 and zoom >= 0.7:
        wr = max(2, int(3 * zoom))
        # Brown log bundle above right shoulder
        wx_ = sx + r
        wy_ = body_top - wr * 2
        pygame.draw.rect(surface, (115, 78, 38), (wx_, wy_, wr*2, wr*3))
        pygame.draw.rect(surface, (160, 110, 58), (wx_, wy_, wr*2, wr*3), 1)
        # Stack indicator if lots of wood
        if entity.inv_wood >= 3 and zoom >= 1.0:
            pygame.draw.rect(surface, (145, 96, 48),
                             (wx_ - wr//2, wy_ + wr//2, wr*2, wr*2))

    # ── activity icon ──
    if zoom > 0.5:
        ix = sx + r + max(2, int(3*zoom))
        iy = body_top - r - max(2, int(3*zoom))
        icon_r = max(2, int(3*zoom))
        if entity.state == S_HUNT:
            pygame.draw.polygon(surface, (210,45,25),
                [(ix, iy-icon_r), (ix+icon_r, iy+icon_r), (ix-icon_r, iy+icon_r)])
        elif entity.state == S_DRINK:
            pygame.draw.circle(surface, (50,140,215), (ix, iy), icon_r)
            pygame.draw.polygon(surface, (50,140,215),
                [(ix-icon_r//2, iy), (ix+icon_r//2, iy), (ix, iy-icon_r-icon_r//2)])
        elif entity.state == S_GATHER:
            pygame.draw.circle(surface, (55,185,55), (ix, iy), icon_r)
        elif entity.state == S_CHOP:
            # Brown axe shape
            pygame.draw.line(surface, (115,78,38), (ix, iy+icon_r), (ix, iy-icon_r),
                             max(1, icon_r//2))
            pygame.draw.polygon(surface, (185,145,80),
                [(ix, iy-icon_r), (ix+icon_r, iy-icon_r//2), (ix+icon_r//2, iy+icon_r//2)])
        elif entity.state == S_BUILD:
            # Hammer outline
            pygame.draw.rect(surface, (185,155,90),
                             (ix - icon_r//2, iy - icon_r, icon_r, icon_r))
            pygame.draw.line(surface, (150,120,70), (ix, iy), (ix, iy + icon_r),
                             max(1, icon_r//2))
        elif entity.state == S_SHELTER:
            # Green tent / leaf shape
            pygame.draw.polygon(surface, (45, 160, 55),
                [(ix, iy - icon_r), (ix + icon_r, iy + icon_r//2),
                 (ix - icon_r, iy + icon_r//2)])


def _draw_nametag(surface, sx, sy, entity, era_idx, zoom, fonts):
    """Draw floating name above selected entity."""
    r = max(2, int(zoom * 5))
    body_top = sy - r
    name_surf = fonts['sm'].render(entity.name, True, (255, 215, 50))
    nx = sx - name_surf.get_width() // 2
    ny = body_top - r - name_surf.get_height() - max(4, int(5*zoom))
    # background pill
    pad = 4
    bg_rect = (nx-pad, ny-2, name_surf.get_width()+pad*2, name_surf.get_height()+4)
    pygame.draw.rect(surface, (20, 16, 10), bg_rect, border_radius=4)
    pygame.draw.rect(surface, (255, 215, 50), bg_rect, 1, border_radius=4)
    surface.blit(name_surf, (nx, ny))


def _draw_prey(surface, entity, cam_x, cam_y, zoom):
    sx, sy = world_to_screen(entity.x, entity.y, cam_x, cam_y, zoom)
    if sx < -12 or sx > SCREEN_W+12 or sy < -12 or sy > SCREEN_H+12:
        return
    r = max(3, int(zoom * 4.5))    # larger than before
    fleeing = (entity.state == S_FLEE)
    body    = (190, 145, 62) if not fleeing else (215, 80, 40)
    shadow  = _dk(body, 0.55)

    # Shadow
    pygame.draw.ellipse(surface, (0,0,0),
                        (sx - r, sy + r//2, r*2, max(1, r//3)))

    if zoom < 0.5:
        pygame.draw.circle(surface, body, (sx, sy), max(2, r-1))
        return

    # Animated legs
    phase = entity.eid * 1.5 + (entity.x + entity.y) * 0.3
    move_speed = 1.0 if not fleeing else 2.8
    leg_sw = int(math.sin(phase * move_speed) * r * 0.7)
    lw = max(1, r // 3)
    if zoom >= 0.8:
        for ox in (-r//3, r//3):
            pygame.draw.line(surface, shadow,
                (sx+ox, sy+r//2), (sx+ox+leg_sw, sy+r+r//2), lw)
            pygame.draw.line(surface, shadow,
                (sx+ox, sy+r//2), (sx+ox-leg_sw, sy+r+r//2), lw)

    # Body (slightly elongated)
    pygame.draw.ellipse(surface, body, (sx-r, sy-r//2, r*2, int(r*1.2)))

    # Head
    hx = sx - r + r//3
    pygame.draw.circle(surface, _dk(body, 1.12), (hx, sy - r//4), max(2, int(r*0.7)))

    if zoom >= 1.0:
        # Ears
        ear = _dk(body, 1.3)
        pygame.draw.polygon(surface, ear,
            [(hx-r//3, sy-r//4-1), (hx-r//5, sy-r-2), (hx, sy-r//4-1)])
        # Antlers for bucks (eid % 3 == 0)
        if entity.eid % 3 == 0 and zoom >= 1.4:
            ac = _dk(body, 0.7)
            pygame.draw.line(surface, ac, (hx, sy-r//4-r//2),
                             (hx - r//2, sy - r - r//2), max(1, lw-1))
            pygame.draw.line(surface, ac, (hx - r//4, sy-r-r//4),
                             (hx - r//4 - r//3, sy - r - r), max(1, lw-1))


# ───────────────────────────── info panel ────────────────────────────────────

def _draw_info_panel(surface, entity, era_idx, year, fonts):
    if entity is None:
        return

    PW, PH = 280, 195
    px = 14
    py = SCREEN_H - PH - 36   # just above bottom bar

    # Background — cached, created once
    global _INFO_BG
    if _INFO_BG is None:
        _INFO_BG = pygame.Surface((PW, PH))
        _INFO_BG.fill((18, 14, 10))
    surface.blit(_INFO_BG, (px, py))

    era_color = (
        (200,160,80),(200,165,85),(205,168,88),(208,172,95),
        (150,145,170),(165,155,175),(130,130,165),(100,120,175),
        (70,100,200),(55,75,200),
    )[min(era_idx, 9)]
    pygame.draw.rect(surface, era_color, (px, py, PW, PH), 2, border_radius=4)
    pygame.draw.line(surface, era_color, (px, py+42), (px+PW, py+42), 1)
    pygame.draw.line(surface, era_color, (px, py+80), (px+PW, py+80), 1)

    # Name
    name_s = fonts['big'].render(entity.name, True, (255, 215, 80))
    surface.blit(name_s, (px+12, py+8))

    # Age and era
    era_name = ERAS[era_idx][1]
    age_s = fonts['sm'].render(f"{int(entity.age)} ans  •  {era_name}", True, (160,160,180))
    surface.blit(age_s, (px+12, py+26))

    # Activity / state
    state_icons = {0:"✦", 1:"⚔", 2:"💧", 3:"🌿", 4:"💤", 5:"👣", 7:"🪓", 8:"🏗", 9:"🌲"}
    icon = state_icons.get(entity.state, "•")
    act_text = f"{icon}  {entity.activity_desc}" if entity.activity_desc else f"{icon}  Erre..."
    act_s = fonts['sm'].render(act_text[:38], True, (220, 210, 170))
    surface.blit(act_s, (px+10, py+50))

    # Needs summary + wood inventory
    needs_txt = entity.needs_summary()
    if entity.inv_wood > 0:
        needs_txt += f"  ·  bois: {entity.inv_wood}"
    needs_s = fonts['sm'].render(needs_txt, True, (160, 150, 120))
    surface.blit(needs_s, (px+10, py+68))

    # Bars — hunger/thirst inverted (0=good=full bar, 1=bad=empty bar)
    _bar(surface, px+12, py+90,  PW-24, "Faim",    1-min(1.0, entity.hunger), (190,130,50), fonts)
    _bar(surface, px+12, py+116, PW-24, "Soif",    1-min(1.0, entity.thirst), (80, 160,220), fonts)
    _bar(surface, px+12, py+142, PW-24, "Énergie", entity.energy,             (80, 190,80),  fonts)
    _bar(surface, px+12, py+168, PW-24, "Santé",   entity.health,             (60, 190,70),  fonts)

    # Close hint
    hint_s = fonts['sm'].render("clic droit · fermer", True, (70, 68, 62))
    surface.blit(hint_s, (px + PW - hint_s.get_width() - 8, py + PH - 16))


def _bar(surface, x, y, w, label, value, color, fonts):
    lbl_s = fonts['sm'].render(label, True, (140,138,130))
    surface.blit(lbl_s, (x, y))
    bx = x + 72
    bw = w - 72 - 38
    bh = 10
    pygame.draw.rect(surface, (40, 36, 30), (bx, y+2, bw, bh), border_radius=3)
    filled = max(0, int(bw * min(1, value)))
    if filled > 0:
        pygame.draw.rect(surface, color, (bx, y+2, filled, bh), border_radius=3)
    pct = fonts['sm'].render(f"{int(value*100)}%", True, (160,158,148))
    surface.blit(pct, (bx + bw + 4, y))


# ───────────────────────────── era-0 campfires ───────────────────────────────

def _draw_clan_campfires(surface, sim, cam_x, cam_y, zoom, tick, is_night):
    """Draw a small campfire at each clan's anchor (home base).
    Fires are always visible at night; a soft glow during the day."""
    for clan_id, (wx, wy) in sim.clan_anchors.items():
        sx, sy = world_to_screen(wx, wy, cam_x, cam_y, zoom)
        if sx < -20 or sx > SCREEN_W + 20 or sy < -20 or sy > SCREEN_H + 20:
            continue

        z = zoom
        flicker = math.sin(tick * 9.5 + clan_id * 1.7)
        base_r  = max(2, int(4 * z))
        # Glow (bigger at night)
        glow_r = base_r + int(base_r * (1.5 if is_night else 0.5))
        if is_night and zoom >= 0.4:
            glow_surf = pygame.Surface((glow_r*4, glow_r*4), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 160, 40, 55),
                               (glow_r*2, glow_r*2), glow_r*2)
            surface.blit(glow_surf, (sx - glow_r*2, sy - glow_r*2))

        # Embers
        pygame.draw.circle(surface, (70, 40, 10), (sx, sy + base_r), max(1, base_r-1))
        # Flame core
        col_f = (255, max(100, 130 + int(flicker * 20)), 20)
        pygame.draw.circle(surface, col_f, (sx, sy), base_r)
        # Bright tip
        pygame.draw.circle(surface, (255, 230, 120), (sx, sy - base_r//2),
                           max(1, base_r // 2))
        # Smoke wisps at high zoom
        if zoom >= 1.2 and is_night:
            for i in range(2):
                wy_s = sy - base_r * 2 - i * int(3*z)
                wx_s = sx + int(math.sin(tick * 3 + i * 1.2) * z)
                pygame.draw.circle(surface, (80, 78, 75),
                                   (wx_s, wy_s), max(1, int(z * (1.5 - i*0.4))))


# ───────────────────────────── settlement overlays ───────────────────────────

def _draw_settlement_roads(surface, s, cam_x, cam_y, zoom):
    """Dirt roads from center to each satellite building."""
    if s.level < 1 or zoom < 0.35:
        return
    layout = _SETTLE_LAYOUTS.get(min(s.level, 5), _SETTLE_LAYOUTS[5])
    cx, cy = s.gx + 0.5, s.gy + 0.5
    scx, scy = world_to_screen(cx, cy, cam_x, cam_y, zoom)
    road_w = max(1, int(2.5 * zoom))
    road_col = (128, 105, 68)
    for dx, dy, _ in layout:
        if dx == 0 and dy == 0:
            continue
        tx, ty = world_to_screen(cx + dx, cy + dy, cam_x, cam_y, zoom)
        if (-20 < tx < SCREEN_W + 20) or (-20 < scx < SCREEN_W + 20):
            pygame.draw.line(surface, road_col, (scx, scy), (tx, ty), road_w)


def _draw_settlement_walls(surface, s, cam_x, cam_y, zoom):
    """Isometric palisade / stone walls for level 3+."""
    if s.level < 3 or zoom < 0.30:
        return
    wall_r = 3 + s.level
    cx, cy = s.gx + 0.5, s.gy + 0.5
    pts = [
        world_to_screen(cx,        cy - wall_r, cam_x, cam_y, zoom),
        world_to_screen(cx + wall_r, cy,        cam_x, cam_y, zoom),
        world_to_screen(cx,        cy + wall_r, cam_x, cam_y, zoom),
        world_to_screen(cx - wall_r, cy,        cam_x, cam_y, zoom),
    ]
    # Cull if entirely off screen
    if all(sx < -10 or sx > SCREEN_W + 10 for sx, sy in pts):
        return
    wall_w = max(1, int(3 * zoom))
    if s.level == 3:
        col_outer = (105, 90, 68)
        col_inner = (128, 110, 82)
    elif s.level == 4:
        col_outer = (115, 108, 95)
        col_inner = (138, 130, 115)
    else:
        col_outer = (130, 125, 118)
        col_inner = (158, 152, 142)
    pygame.draw.polygon(surface, col_outer, pts, wall_w + 1)
    pygame.draw.polygon(surface, col_inner, pts, max(1, wall_w - 1))
    # Corner towers for level 4+
    if s.level >= 4 and zoom >= 0.5:
        tower_r = max(2, int(4 * zoom))
        for sx, sy in pts:
            pygame.draw.circle(surface, col_inner, (sx, sy), tower_r)
            pygame.draw.circle(surface, (180, 175, 162), (sx, sy), max(1, tower_r - 1))
            if s.level >= 5 and zoom >= 0.8:
                pygame.draw.line(surface, (140, 132, 120),
                                 (sx, sy - tower_r), (sx, sy - tower_r * 3),
                                 max(1, wall_w - 1))


def _draw_settlement_labels(surface, settlements, era_idx, cam_x, cam_y, zoom, fonts):
    """Floating name labels above each settlement of level >= 1."""
    if zoom < 0.4:
        return
    for s in settlements:
        if s.level < 1:
            continue
        scx, scy = world_to_screen(s.gx + 0.5, s.gy + 0.5, cam_x, cam_y, zoom)
        if scx < -80 or scx > SCREEN_W + 80:
            continue
        # Float above the tallest building (rough estimate)
        label_y = scy - int(34 * zoom) - (s.level * max(1, int(5 * zoom)))
        if label_y < -20 or label_y > SCREEN_H + 20:
            continue
        name_s = fonts['sm'].render(s.name, True, (240, 225, 170))
        nx = scx - name_s.get_width() // 2
        pad = 4
        bg = (nx - pad, label_y - 2,
              name_s.get_width() + pad * 2, name_s.get_height() + 4)
        pygame.draw.rect(surface, (15, 12, 8), bg, border_radius=3)
        pygame.draw.rect(surface, (180, 155, 90), bg, 1, border_radius=3)
        surface.blit(name_s, (nx, label_y))
        # Population dot indicator
        if zoom >= 0.7 and s.population > 0:
            pop_txt = f"♟ {s.population}"
            pop_s = fonts['sm'].render(pop_txt, True, (160, 190, 140))
            surface.blit(pop_s, (scx - pop_s.get_width() // 2,
                                 label_y + name_s.get_height() + 2))


# ───────────────────────────── main render ───────────────────────────────────

def render(surface, sim, tiles, camera, fonts, tick, selected_entity=None):
    era_idx, era = sim.get_era()

    # ── day / night sky tint ──
    dp      = sim.day_phase                   # 0..1
    # brightness: dawn 0.55, noon 1.0, dusk 0.55, midnight 0.18
    if dp < 0.25:                             # dawn
        bright = 0.55 + dp / 0.25 * 0.45
    elif dp < 0.5:                            # day
        bright = 1.0
    elif dp < 0.75:                           # dusk
        bright = 1.0 - (dp - 0.5) / 0.25 * 0.45
    else:                                     # night
        bright = max(0.18, 0.55 - (dp - 0.75) / 0.25 * 0.37)
    sky = era[2]
    sky_b = (max(0, int(sky[0]*bright)), max(0, int(sky[1]*bright)),
             max(0, int(sky[2]*bright)))
    surface.fill(sky_b)

    cam_x, cam_y, zoom = camera.x, camera.y, camera.zoom
    is_night = dp > 0.65 or dp < 0.1

    # ── tiles ──
    for diag in range(WORLD_W + WORLD_H - 1):
        x0 = max(0, diag - WORLD_H + 1)
        x1 = min(WORLD_W, diag + 1)
        for gx in range(x0, x1):
            gy = diag - gx
            _draw_tile(surface, gx, gy, tiles[gx][gy], cam_x, cam_y, zoom)

    # ── expand settlement layouts into per-tile building map ──
    building_map = {}   # (gx, gy) → (settlement, building_variant_level)
    for s in sim.settlements:
        layout = _SETTLE_LAYOUTS.get(min(s.level, 5), _SETTLE_LAYOUTS[5])
        for dx, dy, blvl in layout:
            bx = max(0, min(WORLD_W - 1, s.gx + dx))
            by = max(0, min(WORLD_H - 1, s.gy + dy))
            if (bx, by) not in building_map:
                building_map[(bx, by)] = (s, blvl)

    # ── roads (drawn under buildings so buildings overlap them) ──
    for s in sim.settlements:
        _draw_settlement_roads(surface, s, cam_x, cam_y, zoom)

    # ── buildings in diagonal painter-algorithm order ──
    for diag in range(WORLD_W + WORLD_H - 1):
        x0 = max(0, diag - WORLD_H + 1)
        x1 = min(WORLD_W, diag + 1)
        for gx in range(x0, x1):
            gy = diag - gx
            entry = building_map.get((gx, gy))
            if entry:
                s, blvl = entry
                _draw_building(surface, gx, gy, blvl, era_idx, cam_x, cam_y, zoom, tick)

    # ── settlement walls (drawn over buildings, under entities) ──
    for s in sim.settlements:
        _draw_settlement_walls(surface, s, cam_x, cam_y, zoom)

    # ── era-0 campfires: drawn at clan anchor spots when it's night ──
    if era_idx == 0:
        _draw_clan_campfires(surface, sim, cam_x, cam_y, zoom, tick, is_night)

    # ── stumps (recently cleared forest tiles) ──
    if zoom >= 0.5:
        stump_r = max(1, int(2.5 * zoom))
        for (cx, cy, t_rem) in sim.cleared_tiles:
            sx, sy = world_to_screen(cx + 0.5, cy + 0.5, cam_x, cam_y, zoom)
            if -8 < sx < SCREEN_W + 8 and -8 < sy < SCREEN_H + 8:
                lw = max(1, stump_r // 2)
                pygame.draw.circle(surface, (110, 80, 45), (sx, sy), stump_r)
                if zoom >= 0.9:
                    pygame.draw.line(surface, (75, 52, 28),
                                     (sx - stump_r, sy), (sx + stump_r, sy), lw)
                    pygame.draw.line(surface, (75, 52, 28),
                                     (sx, sy - stump_r), (sx, sy + stump_r), lw)

    # ── prey ──
    for p in sim.prey:
        _draw_prey(surface, p, cam_x, cam_y, zoom)

    # ── entities (subsample when dense) ──
    entities = sim.entities
    step = max(1, len(entities) // 500)
    for e in entities[::step]:
        _draw_character(surface, *world_to_screen(e.x, e.y, cam_x, cam_y, zoom),
                        e, era_idx, tick, zoom, selected=(e is selected_entity))

    # ── selected nametag ──
    if selected_entity is not None:
        sx, sy = world_to_screen(selected_entity.x, selected_entity.y, cam_x, cam_y, zoom)
        _draw_nametag(surface, sx, sy, selected_entity, era_idx, zoom, fonts)

    # ── settlement name labels (always on top of entities) ──
    _draw_settlement_labels(surface, sim.settlements, era_idx, cam_x, cam_y, zoom, fonts)

    # ── UI ──
    _draw_ui(surface, sim, era_idx, era, fonts, camera.zoom)

    # ── info panel ──
    if selected_entity is not None:
        _draw_info_panel(surface, selected_entity, era_idx, sim.year, fonts)


# ───────────────────────────── HUD ───────────────────────────────────────────

def _draw_ui(surface, sim, era_idx, era, fonts, zoom=1.0):
    global _BAR_SURF, _BOT_SURF
    # top bar — cached
    if _BAR_SURF is None:
        _BAR_SURF = pygame.Surface((SCREEN_W, 52), pygame.SRCALPHA)
        _BAR_SURF.fill((0, 0, 0, 155))
    surface.blit(_BAR_SURF, (0, 0))

    era_s = fonts['big'].render(era[1], True, (255, 218, 140))
    surface.blit(era_s, (18, 10))

    yr_s = fonts['med'].render(f"Année  {int(sim.year):,}", True, (200,200,200))
    surface.blit(yr_s, (320, 16))

    pop_s = fonts['med'].render(f"Population  {sim.population():,}", True, (155,218,155))
    surface.blit(pop_s, (530, 16))

    if sim.epoch:
        spd_str, spd_col = "⬤  EN DIRECT", (255, 80, 80)
    elif sim.paused:
        spd_str, spd_col = "⏸  PAUSE",     (255,150, 50)
    else:
        spd_str = f"▶  {TIME_SPEEDS[sim.speed_idx]:,} ans/s"
        spd_col = (140, 215, 140)
    spd_s = fonts['med'].render(spd_str, True, spd_col)
    surface.blit(spd_s, (SCREEN_W - spd_s.get_width() - 18, 16))

    # era progress bar
    if era_idx < len(ERAS)-1:
        ny, ty = ERAS[era_idx+1][0], ERAS[era_idx][0]
        prog = min(1.0, (sim.year - ty) / max(1, ny - ty))
        bw   = SCREEN_W - 36
        pygame.draw.rect(surface, (45,42,38),    (18, 48, bw, 4))
        pygame.draw.rect(surface, (255,200,80),  (18, 48, int(bw*prog), 4))

    # bottom bar — cached
    if _BOT_SURF is None:
        _BOT_SURF = pygame.Surface((SCREEN_W, 28), pygame.SRCALPHA)
        _BOT_SURF.fill((0, 0, 0, 140))
    surface.blit(_BOT_SURF, (0, SCREEN_H-28))

    desc_s = fonts['sm'].render(era[3], True, (150,150,182))
    surface.blit(desc_s, (18, SCREEN_H-22))

    if sim.epoch:
        hint = "Z Q S D / flèches : caméra  ·  molette : zoom  ·  clic : sélectionner"
    else:
        hint = "ESPACE pause  ·  + - vitesse  ·  Z Q S D caméra  ·  molette zoom  ·  clic sélectionner"
    hint_s = fonts['sm'].render(hint, True, (85,85,85))
    surface.blit(hint_s, (SCREEN_W - hint_s.get_width()-18, SCREEN_H-22))

    # event log
    y_ev = 62
    for text, rem in list(reversed(sim._active_events))[:5]:
        is_era = "✦" in text
        col = (255, 212, 70) if is_era else (195,195,195)
        ev_s = fonts['sm'].render(text, True, col)
        if rem < 2.0:
            ev_s.set_alpha(int(rem / 2.0 * 255))
        surface.blit(ev_s, (18, y_ev))
        y_ev += 20

    # zoom indicator (bottom right above hint)
    zoom_s = fonts['sm'].render(f"zoom  {zoom:.1f}×", True, (90,88,82))
    surface.blit(zoom_s, (SCREEN_W - zoom_s.get_width()-18, SCREEN_H-46))
