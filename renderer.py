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

def _dk(c, f):  return (max(0,min(255,int(c[0]*f))), max(0,min(255,int(c[1]*f))), max(0,min(255,int(c[2]*f))))
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

# Per-era color palettes: (wall_left, wall_right, wall_top, roof_front, roof_side, outline, window)
_ERA_PAL = [
    # 0 Préhistoire – peau / écorce sombre
    ((105,72,38),(122,86,48),(88,60,30),(72,48,25),(58,38,18),(48,32,15),(200,158,78)),
    # 1 Néolithique – torchis ocre
    ((148,112,72),(168,130,88),(135,102,62),(152,96,48),(118,78,38),(98,72,42),(252,198,115)),
    # 2 Antiquité – brique crue
    ((188,155,108),(208,175,128),(198,165,118),(178,138,82),(155,115,65),(142,112,72),(255,218,148)),
    # 3 Classique – marbre ivoire
    ((175,168,152),(198,190,175),(208,202,188),(158,98,48),(130,80,35),(125,118,108),(195,215,252)),
    # 4 Moyen Âge – pierre grise
    ((102,98,90),(118,112,104),(108,104,96),(80,66,50),(62,52,40),(58,55,50),(172,158,115)),
    # 5 Renaissance – pierre chaude + tuile
    ((165,148,118),(185,168,138),(175,158,128),(178,78,48),(148,62,35),(125,112,85),(205,218,252)),
    # 6 Industrie – brique rouge + acier
    ((142,68,44),(162,82,54),(128,60,38),(48,46,42),(38,36,32),(98,48,30),(172,152,88)),
    # 7 Moderne – béton + verre
    ((128,132,140),(148,152,158),(142,146,152),(105,108,112),(88,90,95),(82,84,88),(148,192,232)),
    # 8 Futur proche – blanc nacré
    ((182,188,202),(202,208,222),(215,220,230),(72,168,212),(48,138,178),(142,150,165),(88,188,252)),
    # 9 Futur lointain – cristal lumineux
    ((35,45,88),(50,65,118),(65,95,155),(15,170,248),(12,130,195),(68,108,192),(168,212,252)),
]


def _draw_building(surface, gx, gy, level, era_idx, cam_x, cam_y, zoom, tick):
    cx, cy = world_to_screen(gx + 0.5, gy + 0.5, cam_x, cam_y, zoom)
    cy -= int(TILE_HEIGHTS.get(3, 6) * zoom) + 2

    if cx < -140 or cx > SCREEN_W + 140: return
    if cy > SCREEN_H + 100: return

    z   = zoom
    htw = TILE_W * z / 2   # half-tile width  ≈ 32z px
    hth = TILE_H * z / 2   # half-tile height ≈ 16z px

    ei  = min(era_idx, 9)
    pal = _ERA_PAL[ei]
    wl, wr, wt, rf, rs, ol, wn = pal

    def ip(p):          return (int(p[0]), int(p[1]))
    def up(p, h):       return (p[0], p[1] - h)
    def lrp(a, b, t):   return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)
    def poly(col, pts):
        if len(pts) < 3: return
        pygame.draw.polygon(surface, col, [ip(p) for p in pts])
    def lpoly(col, pts, lw=1):
        if len(pts) < 3: return
        pygame.draw.polygon(surface, col, [ip(p) for p in pts], max(1,lw))

    # Iso-tile base diamond (south tip = front of building)
    pf = (cx,        cy + hth)  # south / front
    pl = (cx - htw,  cy)        # west  / left
    pr = (cx + htw,  cy)        # east  / right
    pb = (cx,        cy - hth)  # north / back (hidden)

    def box(h, cl, cr, ct, outline=None):
        """3-face isometric box of height h pixels."""
        lf = [pl, pf, up(pf, h), up(pl, h)]
        rf = [pr, pf, up(pf, h), up(pr, h)]
        tf = [up(pl, h), up(pf, h), up(pr, h), up(pb, h)]
        poly(cl, lf); poly(cr, rf); poly(ct, tf)
        if outline:
            lw = max(1, int(z * 0.85))
            lpoly(outline, lf, lw); lpoly(outline, rf, lw); lpoly(outline, tf, lw)

    def hip_roof(wh, rh, col_f, col_s, col_o=None):
        """4-sided hip (pyramid) roof above wall-height wh, roof-height rh."""
        pk = (cx, cy - wh - rh)
        poly(col_f, [up(pl,wh), up(pf,wh), pk])
        poly(col_s, [up(pr,wh), up(pf,wh), pk])
        if col_o and z >= 0.55:
            lw = max(1, int(z))
            pygame.draw.line(surface, col_o, ip(up(pf,wh)), ip(pk), lw)

    def gabled_roof(wh, rh, col_f, col_s, col_o=None):
        """Ridge-gabled roof: ridge runs front→back, visible slopes left+right."""
        pk_front = (cx, cy - wh - rh)
        pk_back  = (cx, cy - wh - rh + int(hth * 0.5))
        poly(col_f, [up(pl,wh), up(pf,wh), pk_front, pk_back])
        poly(col_s, [up(pr,wh), up(pf,wh), pk_front])
        if col_o and z >= 0.5:
            lw = max(1, int(z))
            pygame.draw.line(surface, col_o, ip(pk_front), ip(pk_back), lw)
            pygame.draw.line(surface, col_o, ip(up(pf,wh)), ip(pk_front), lw)

    def win_face(bl, br, tl, tr, fx, fy, fw, fh, col):
        """Draw a window quad on a parallelogram face defined by 4 corners."""
        if z < 0.55: return
        def pt(x, y): return lrp(lrp(bl,br,x), lrp(tl,tr,x), y)
        pts = [pt(fx,fy), pt(fx+fw,fy), pt(fx+fw,fy+fh), pt(fx,fy+fh)]
        poly(col, pts)
        if z >= 1.0:  # bright glint at high zoom
            glint = (min(255,col[0]+60), min(255,col[1]+60), min(255,col[2]+60))
            pygame.draw.line(surface, glint, ip(pts[0]), ip(pts[1]), max(1,int(z*0.5)))

    def battlement(wh, bh, col):
        """Crenellated parapet on top of wall-height wh."""
        if z < 0.4: return
        mw = 0.12; gap = 0.22
        for t in [0.05, 0.05+gap, 0.05+gap*2, 0.05+gap*3]:
            # Left face merlon
            a = lrp(up(pl,wh), up(pf,wh), t)
            b = lrp(up(pl,wh), up(pf,wh), t+mw)
            poly(col, [a, b, up(b,bh), up(a,bh)])
        for t in [0.05, 0.05+gap, 0.05+gap*2, 0.05+gap*3]:
            # Right face merlon
            a = lrp(up(pr,wh), up(pf,wh), t)
            b = lrp(up(pr,wh), up(pf,wh), t+mw)
            poly(col, [a, b, up(b,bh), up(a,bh)])

    # ── Level 0: campfire ──────────────────────────────────────────────────
    if level == 0:
        flicker = math.sin(tick * 9.5 + gx * 1.3)
        r = max(2, int(3 * z))
        pygame.draw.circle(surface, (60, 36, 10),   ip((cx, cy + r)),     max(1, r-1))
        col_f = (255, max(100, int(132 + flicker*22)), 15)
        pygame.draw.circle(surface, col_f,           ip((cx, cy)),          r)
        pygame.draw.circle(surface, (255, 228, 105), ip((cx, cy - r//2)),   max(1, r//2))
        return

    # ── Level 1: hutte (era-aware) ─────────────────────────────────────────
    if level == 1:
        wh = max(5, int(9 * z))
        rh = max(4, int(10 * z))
        if ei <= 1:
            # Peau / torchis rond → conical roof
            box(wh, wl, wr, wt, ol)
            hip_roof(wh, rh, rf, rs, ol)
            # Entrée (ouverture sombre)
            if z >= 0.7:
                dw = max(1, int(htw * 0.22))
                dh = max(2, int(wh * 0.55))
                door_bl = lrp(pl, pf, 0.45)
                door_br = lrp(pl, pf, 0.55)
                poly(_dk(ol, 0.5), [door_bl, door_br,
                                    (door_br[0], door_br[1]-dh),
                                    (door_bl[0], door_bl[1]-dh)])
        elif ei <= 3:
            # Maison antique en torchis / briques
            box(wh, wl, wr, wt, ol)
            gabled_roof(wh, rh, rf, rs, ol)
            if z >= 0.65:
                win_face(pl, pf, up(pl,wh), up(pf,wh), 0.2, 0.3, 0.2, 0.35, wn)
                win_face(pr, pf, up(pr,wh), up(pf,wh), 0.2, 0.3, 0.2, 0.35, wn)
        elif ei <= 6:
            # Maison en pierre / brique
            box(wh, wl, wr, wt, ol)
            gabled_roof(wh, rh, rf, rs, _dk(rf, 0.7))
            if z >= 0.6:
                win_face(pl, pf, up(pl,wh), up(pf,wh), 0.18, 0.25, 0.22, 0.38, wn)
                win_face(pr, pf, up(pr,wh), up(pf,wh), 0.62, 0.25, 0.22, 0.38, wn)
        else:
            # Futur: module préfab
            box(wh, wl, wr, wt, ol)
            # Toit plat avec bande lumineuse
            poly(rf, [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])
            if z >= 0.7:
                pygame.draw.line(surface, wn,
                    ip(lrp(up(pl,wh), up(pf,wh), 0.1)),
                    ip(lrp(up(pl,wh), up(pf,wh), 0.9)), max(1,int(z)))
        return

    # ── Level 2: bâtiment de village ──────────────────────────────────────
    if level == 2:
        wh = max(7, int(13 * z))
        rh = max(5, int(11 * z))
        box(wh, wl, wr, wt, ol)
        if ei <= 2:
            # Toit en chaume long
            gabled_roof(wh, rh, rf, rs, ol)
        elif ei <= 5:
            # Toit à 4 pans en tuiles
            hip_roof(wh, rh, rf, rs, _dk(ol, 0.8))
            # Petite cheminée
            if z >= 0.55:
                ch_bl = lrp(up(pl,wh), up(pf,wh), 0.65)
                ch_h  = max(2, int(5*z)); ch_w = max(1, int(3*z))
                pygame.draw.rect(surface, wl,
                    (int(ch_bl[0])-ch_w//2, int(ch_bl[1])-ch_h, ch_w, ch_h))
        elif ei <= 7:
            # Toit plat industriel / moderne
            poly(rf, [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])
            lpoly(_dk(rf,0.7), [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)], max(1,int(z)))
        else:
            # Futur: dôme
            dome_r = max(4, int(htw * 0.8))
            pygame.draw.circle(surface, rf, ip((cx, cy - wh)), dome_r)
            pygame.draw.circle(surface, (min(255,rf[0]+40),min(255,rf[1]+40),min(255,rf[2]+60)),
                               ip((cx, cy - wh - dome_r//3)), max(1, dome_r//2))
        # Fenêtres
        if z >= 0.6:
            win_face(pl, pf, up(pl,wh), up(pf,wh), 0.15, 0.25, 0.18, 0.32, wn)
            win_face(pl, pf, up(pl,wh), up(pf,wh), 0.62, 0.25, 0.18, 0.32, wn)
            win_face(pr, pf, up(pr,wh), up(pf,wh), 0.15, 0.25, 0.18, 0.32, wn)
            win_face(pr, pf, up(pr,wh), up(pf,wh), 0.62, 0.25, 0.18, 0.32, wn)
        # Porte
        if z >= 0.75:
            poly(_dk(ol, 0.55), [
                lrp(pl, pf, 0.42), lrp(pl, pf, 0.58),
                lrp(lrp(pl,pf,0.58), lrp(up(pl,wh),up(pf,wh),0.58), 0.48),
                lrp(lrp(pl,pf,0.42), lrp(up(pl,wh),up(pf,wh),0.42), 0.48),
            ])
        return

    # ── Level 3: bâtiment de bourg / tour ─────────────────────────────────
    if level == 3:
        wh = max(10, int(18 * z))
        rh = max(5, int(9  * z))
        box(wh, wl, wr, wt, ol)

        if ei <= 1:
            gabled_roof(wh, rh, rf, rs, ol)
        elif ei <= 3:
            # Temple / colonnes
            hip_roof(wh, rh, rf, rs, _dk(ol,0.8))
            if z >= 0.7:
                for t in [0.15, 0.5, 0.85]:
                    col_pt = lrp(pl, pf, t)
                    pygame.draw.line(surface, _dk(wl,1.2),
                        ip(col_pt), ip((col_pt[0], col_pt[1]-wh)), max(1, int(z*0.7)))
        elif ei == 4:
            # Tour médiévale avec créneaux
            battlement(wh, max(2, int(4*z)), _dk(wl,1.1))
        elif ei == 5:
            # Façade Renaissance + fronton
            hip_roof(wh, rh, rf, rs, _dk(ol,0.8))
            if z >= 0.65:
                arch_y = cy - int(wh * 0.3)
                pygame.draw.arc(surface, wn,
                    (int(cx-htw*0.25), arch_y-int(htw*0.25),
                     int(htw*0.5), int(htw*0.5)), 0, math.pi, max(1,int(z)))
        elif ei <= 7:
            poly(rf, [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])
        else:
            # Tour futuriste
            poly(rf, [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])
            spire_h = max(4, int(12*z))
            poly(wn, [up(pl,wh), up(pf,wh), ip((cx, cy-wh-spire_h))])
            poly(_dk(wn,0.7), [up(pr,wh), up(pf,wh), ip((cx, cy-wh-spire_h))])

        # Fenêtres (2 rangées)
        if z >= 0.5:
            for row_y in [0.25, 0.65]:
                for tx in [0.18, 0.5, 0.78]:
                    wh_row = int(wh * row_y)
                    win_face(pl, pf, up(pl, wh_row + int(4*z)), up(pf, wh_row + int(4*z)),
                             tx, 0.05, 0.16, 0.90, wn)
                    win_face(pr, pf, up(pr, wh_row + int(4*z)), up(pf, wh_row + int(4*z)),
                             tx, 0.05, 0.16, 0.90, wn)

        # Tour secondaire au centre-arrière
        if z >= 0.45:
            tw2 = int(htw * 0.38); th2 = int(hth * 0.38)
            tp_f  = (cx,       cy - wh + th2)
            tp_l  = (cx - tw2, cy - wh)
            tp_r  = (cx + tw2, cy - wh)
            tp_b  = (cx,       cy - wh - th2)
            th_h  = max(5, int(12 * z))
            poly(_dk(wl, 0.88), [tp_l, tp_f, up(tp_f,th_h), up(tp_l,th_h)])
            poly(_dk(wr, 0.88), [tp_r, tp_f, up(tp_f,th_h), up(tp_r,th_h)])
            poly(_dk(wt, 1.05), [up(tp_l,th_h), up(tp_f,th_h), up(tp_r,th_h), up(tp_b,th_h)])
            # Toit de la tour
            pk_t = ip((cx, cy - wh - th_h - max(3, int(6*z))))
            poly(rf, [ip(up(tp_l,th_h)), ip(up(tp_f,th_h)), pk_t])
            poly(rs, [ip(up(tp_r,th_h)), ip(up(tp_f,th_h)), pk_t])
        return

    # ── Level 4: grande cité ──────────────────────────────────────────────
    if level == 4:
        wh = max(14, int(28 * z))
        box(wh, wl, wr, wt, ol)

        if ei <= 3:
            # Acropole / forum colonnade
            battlement(wh, max(2, int(5*z)), _dk(wl,1.15))
            if z >= 0.6:
                for t in [0.1, 0.3, 0.5, 0.7, 0.9]:
                    col_pt = lrp(pl, pf, t)
                    pygame.draw.line(surface, _dk(wl,1.25), ip(col_pt),
                        ip((col_pt[0], col_pt[1]-wh)), max(1, int(z*0.8)))
                    col_pt_r = lrp(pr, pf, t)
                    pygame.draw.line(surface, _dk(wr,1.25), ip(col_pt_r),
                        ip((col_pt_r[0], col_pt_r[1]-wh)), max(1, int(z*0.8)))
        elif ei == 4:
            # Cathédrale / château fort
            battlement(wh, max(2, int(5*z)), _dk(wl,1.1))
            if z >= 0.5:
                # Grande tour centrale
                btw = int(htw * 0.45); bth = int(hth * 0.45)
                bp_f = (cx, cy - wh + bth); bp_l = (cx-btw, cy-wh); bp_r = (cx+btw, cy-wh); bp_b=(cx,cy-wh-bth)
                bh2 = max(8, int(20*z))
                poly(_dk(wl,.85), [bp_l,bp_f,up(bp_f,bh2),up(bp_l,bh2)])
                poly(_dk(wr,.85), [bp_r,bp_f,up(bp_f,bh2),up(bp_r,bh2)])
                poly(_dk(wt,1.05),[up(bp_l,bh2),up(bp_f,bh2),up(bp_r,bh2),up(bp_b,bh2)])
                battlement(wh+bh2, max(2,int(3*z)), _dk(wl,1.2))
        elif ei == 5:
            # Palais Renaissance
            hip_roof(wh, max(5,int(10*z)), rf, rs, _dk(ol,0.75))
        elif ei == 6:
            # Usine / complexe industriel
            poly((48,46,42), [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])
            for ch_t in [0.25, 0.65]:
                ch_pt = lrp(up(pl,wh), up(pr,wh), ch_t)
                ch_h  = max(5, int(16*z)); ch_w = max(1, int(3*z))
                pygame.draw.rect(surface, (72,68,64),
                    (int(ch_pt[0])-ch_w//2, int(ch_pt[1])-ch_h, ch_w, ch_h))
                smoke_x = int(ch_pt[0]) + int(math.sin(tick*1.8+ch_t*3)*z)
                smoke_y = int(ch_pt[1]) - ch_h - int(math.sin(tick*1.2)*2)
                pygame.draw.circle(surface, (88,85,82), (smoke_x, smoke_y), max(2,int(3.5*z)))
        else:
            # Tour moderne / futuriste
            poly(rf, [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])

        # Grille de fenêtres sur toute la hauteur
        if z >= 0.45:
            for row_frac in [0.12, 0.32, 0.52, 0.72, 0.88]:
                wh_r = int(wh * row_frac)
                for tx in [0.12, 0.35, 0.60, 0.83]:
                    win_face(pl, pf, up(pl,wh_r+int(3.5*z)), up(pf,wh_r+int(3.5*z)),
                             tx, 0.05, 0.14, 0.90, wn)
                    win_face(pr, pf, up(pr,wh_r+int(3.5*z)), up(pf,wh_r+int(3.5*z)),
                             tx, 0.05, 0.14, 0.90, wn)
        return

    # ── Level 5: mégapole / futur ─────────────────────────────────────────
    if level == 5:
        wh = max(20, int(46 * z))

        if ei >= 9:
            # Cité cristalline lumineuse
            pulse = (math.sin(tick * 1.4 + gx * 0.4) + 1) * 0.5
            glow  = (int(28+pulse*28), int(55+pulse*45), int(165+pulse*45))
            box(wh, _dk(glow,0.65), glow, (min(255,int(glow[0]*1.4)),min(255,int(glow[1]*1.4)),255),
                (72,112,200))
            # Anneau d'énergie
            if z >= 0.5:
                for rr in [int(htw*0.55), int(htw*0.85), int(htw*1.1)]:
                    ey = cy - wh - int(rr * 0.35)
                    pygame.draw.ellipse(surface, (55,115,218,0),
                        (cx-rr, ey-rr//4, rr*2, rr//2), max(1,int(z)))
            # Flèche lumineuse
            spire = max(8, int(20*z))
            pk = ip((cx, cy-wh-spire))
            poly((168,218,255), [ip(up(pl,wh)), ip(up(pf,wh)), pk])
            poly((120,168,232), [ip(up(pr,wh)), ip(up(pf,wh)), pk])
            glow_r = max(3, int(5*z))
            pygame.draw.circle(surface, (200,232,255), ip((cx, cy-wh-spire)), glow_r)
            pygame.draw.circle(surface, (255,255,255), ip((cx, cy-wh-spire)), max(1,glow_r-2))
        elif ei >= 7:
            # Gratte-ciel moderne
            box(wh, wl, wr, wt, ol)
            poly(rf, [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])
            # Antenne
            ant_h = max(5, int(14*z))
            pygame.draw.line(surface, _dk(wl,1.2),
                ip((cx, cy-wh)), ip((cx, cy-wh-ant_h)), max(1,int(z*0.8)))
            pygame.draw.circle(surface, wn, ip((cx, cy-wh-ant_h)), max(1,int(z*1.2)))
            # Grille fenêtres dense
            if z >= 0.4:
                for rf_ in [0.08,0.18,0.28,0.38,0.48,0.58,0.68,0.78,0.90]:
                    wh_r = int(wh*rf_)
                    for tx in [0.1,0.28,0.48,0.68,0.88]:
                        win_face(pl,pf,up(pl,wh_r+int(3*z)),up(pf,wh_r+int(3*z)),tx,0.05,0.12,0.90,wn)
                        win_face(pr,pf,up(pr,wh_r+int(3*z)),up(pf,wh_r+int(3*z)),tx,0.05,0.12,0.90,wn)
        elif ei == 6:
            # Complexe industriel massif
            box(wh, wl, wr, wt, ol)
            poly((45,42,38), [up(pl,wh), up(pf,wh), up(pr,wh), up(pb,wh)])
            for ch_t, ch_mult in [(0.2,1.0),(0.5,1.3),(0.8,1.0)]:
                ch_h = max(6, int(22*z*ch_mult)); ch_w = max(2, int(4*z))
                ch_pt = lrp(up(pl,wh), up(pr,wh), ch_t)
                pygame.draw.rect(surface, (65,60,55),
                    (int(ch_pt[0])-ch_w//2, int(ch_pt[1])-ch_h, ch_w, ch_h))
                sx_, sy_ = int(ch_pt[0])+int(math.sin(tick*1.5+ch_t*4)*z*0.8), int(ch_pt[1])-ch_h
                pygame.draw.circle(surface, (92,88,84),(sx_,sy_-int(3*z)), max(2,int(4*z)))
            if z >= 0.45:
                for rf_ in [0.15,0.40,0.65,0.85]:
                    wh_r = int(wh*rf_)
                    for tx in [0.1,0.35,0.65,0.9]:
                        win_face(pl,pf,up(pl,wh_r+int(4*z)),up(pf,wh_r+int(4*z)),tx,0.05,0.15,0.90,wn)
                        win_face(pr,pf,up(pr,wh_r+int(4*z)),up(pf,wh_r+int(4*z)),tx,0.05,0.15,0.90,wn)
        else:
            # Citadelle / acropole / cathédrale monumentale
            box(wh, wl, wr, wt, ol)
            battlement(wh, max(2, int(5*z)), _dk(wl,1.15))
            if z >= 0.45:
                # Tour centrale massive
                tw3 = int(htw * 0.52); th3 = int(hth * 0.52)
                tp3_f=(cx,cy-wh+th3); tp3_l=(cx-tw3,cy-wh); tp3_r=(cx+tw3,cy-wh); tp3_b=(cx,cy-wh-th3)
                th3_h = max(10, int(28*z))
                poly(_dk(wl,.82),[tp3_l,tp3_f,up(tp3_f,th3_h),up(tp3_l,th3_h)])
                poly(_dk(wr,.82),[tp3_r,tp3_f,up(tp3_f,th3_h),up(tp3_r,th3_h)])
                poly(_dk(wt,1.08),[up(tp3_l,th3_h),up(tp3_f,th3_h),up(tp3_r,th3_h),up(tp3_b,th3_h)])
                battlement(wh+th3_h, max(2,int(3*z)), _dk(wl,1.25))
                pk3 = ip((cx, cy-wh-th3_h-max(5,int(12*z))))
                poly(rf, [ip(up(tp3_l,th3_h)), ip(up(tp3_f,th3_h)), pk3])
                poly(rs, [ip(up(tp3_r,th3_h)), ip(up(tp3_f,th3_h)), pk3])
            if z >= 0.45:
                for rf_ in [0.15,0.40,0.68]:
                    wh_r = int(wh*rf_)
                    for tx in [0.1,0.35,0.65,0.9]:
                        win_face(pl,pf,up(pl,wh_r+int(3*z)),up(pf,wh_r+int(3*z)),tx,0.05,0.14,0.90,wn)
                        win_face(pr,pf,up(pr,wh_r+int(3*z)),up(pf,wh_r+int(3*z)),tx,0.05,0.14,0.90,wn)


def _draw_construction_site(surface, gx, gy, progress, cam_x, cam_y, zoom):
    """Scaffolding for in-progress build sites (progress 0-7 wood deposited)."""
    cx, cy = world_to_screen(gx + 0.5, gy + 0.5, cam_x, cam_y, zoom)
    cy -= int(TILE_HEIGHTS.get(3, 6) * zoom) + 2
    if cx < -60 or cx > SCREEN_W + 60 or cy > SCREEN_H + 60: return
    z = zoom
    htw = TILE_W * z / 2
    hth = TILE_H * z / 2
    pf = (cx, cy + hth); pl = (cx - htw, cy); pr = (cx + htw, cy)

    frac   = min(1.0, progress / 8.0)
    site_h = max(2, int(frac * 14 * z))
    if site_h < 1: return

    # Foundation stones
    pygame.draw.polygon(surface, (110,98,82),
        [(int(pl[0]),int(pl[1])), (int(pf[0]),int(pf[1])),
         (int(pr[0]),int(pr[1])), (int(cx),int(cy-hth))])
    # Partial walls
    if frac > 0.1:
        pygame.draw.polygon(surface, (132,118,95),
            [int_pt(pl), int_pt(pf), int_pt((pf[0],pf[1]-site_h)), int_pt((pl[0],pl[1]-site_h))])
    # Scaffolding poles
    if z >= 0.55:
        sc = (175, 148, 98)
        for t in [0.2, 0.6, 0.9]:
            pt = (int(pl[0]+(pf[0]-pl[0])*t), int(pl[1]+(pf[1]-pl[1])*t))
            pygame.draw.line(surface, sc, pt, (pt[0], pt[1]-site_h-int(3*z)), max(1,int(z*0.7)))
        pygame.draw.line(surface, sc,
            (int(pl[0]),int(pl[1]-site_h)), (int(pf[0]),int(pf[1]-site_h)),
            max(1, int(z*0.7)))
    # Progress indicator
    if z >= 0.7:
        bar_w = max(4, int(htw))
        bar_h = max(2, int(3*z))
        bx = cx - bar_w//2; by = int(cy - hth - int(8*z))
        pygame.draw.rect(surface, (50,40,30), (bx, by, bar_w, bar_h))
        pygame.draw.rect(surface, (185,148,55), (bx, by, int(bar_w*frac), bar_h))


def int_pt(p): return (int(p[0]), int(p[1]))


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


# ───────────────────────── rivers / roads / caravans / boats ─────────────────

def _draw_rivers(surface, rivers, cam_x, cam_y, zoom):
    """Blue river lines flowing from mountains to sea."""
    if not rivers or zoom < 0.22:
        return
    w     = max(1, int(2.5 * zoom))
    col   = (65, 115, 210)
    col_d = (40,  80, 160)
    for path in rivers:
        if len(path) < 2:
            continue
        pts = [world_to_screen(x + 0.5, y + 0.5, cam_x, cam_y, zoom) for x, y in path]
        xs = [p[0] for p in pts]
        if max(xs) < -10 or min(xs) > SCREEN_W + 10:
            continue
        if w >= 3:
            pygame.draw.lines(surface, col_d, False, pts, w + 2)
        pygame.draw.lines(surface, col, False, pts, max(1, w))


def _draw_trade_routes(surface, settlements, era_idx, cam_x, cam_y, zoom, tick):
    """Roads between nearby settlements + animated caravans/ships."""
    if not settlements or zoom < 0.18:
        return

    # Road visual style per era
    if era_idx <= 1:
        road_col, road_w = (148, 118, 75), 1.5     # dirt track
    elif era_idx <= 3:
        road_col, road_w = (162, 145, 110), 2.0    # cobblestone
    elif era_idx <= 6:
        road_col, road_w = (175, 165, 148), 2.5    # paved road
    elif era_idx <= 8:
        road_col, road_w = (145, 145, 160), 3.0    # asphalt / highway
    else:
        road_col, road_w = (100, 210, 255), 2.5    # future hyperloop

    rw = max(1, int(road_w * zoom))

    # Connect settlements within proximity
    n = len(settlements)
    connected = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = settlements[i], settlements[j]
            dist2 = (a.gx - b.gx) ** 2 + (a.gy - b.gy) ** 2
            if dist2 < 30 ** 2 and (a.level >= 1 or b.level >= 1):
                connected.append((a, b, math.sqrt(dist2)))

    for a, b, dist in connected:
        ax, ay = world_to_screen(a.gx + 0.5, a.gy + 0.5, cam_x, cam_y, zoom)
        bx, by = world_to_screen(b.gx + 0.5, b.gy + 0.5, cam_x, cam_y, zoom)
        if (ax < -20 and bx < -20) or (ax > SCREEN_W + 20 and bx > SCREEN_W + 20):
            continue
        pygame.draw.line(surface, road_col, (int(ax), int(ay)), (int(bx), int(by)), rw)

        # Caravans (era 2+)
        if era_idx >= 2 and zoom >= 0.30:
            n_vans = 1 + min(a.level, b.level) // 2
            speed  = 0.35 / max(1.0, dist * 0.06)
            for k in range(n_vans):
                t = (tick * speed + k / max(1, n_vans)) % 1.0
                cx_f = ax + (bx - ax) * t
                cy_f = ay + (by - ay) * t
                r    = max(2, int(3.5 * zoom))
                pygame.draw.circle(surface, (55, 45, 30),
                                   (int(cx_f), int(cy_f)), r + 1)
                pygame.draw.circle(surface, (210, 175, 90),
                                   (int(cx_f), int(cy_f)), r)
                if zoom >= 0.7 and r >= 3:
                    pygame.draw.circle(surface, (245, 218, 140),
                                       (int(cx_f), int(cy_f)), max(1, r - 1))


def _draw_boats(surface, settlements, tiles, era_idx, cam_x, cam_y, zoom, tick):
    """Animated boats near coastal settlements (era 2+)."""
    if era_idx < 2 or zoom < 0.25 or not settlements:
        return

    WATER = {0, 1}  # T_DEEP_WATER, T_WATER

    # Era-based boat colour
    if era_idx <= 4:
        hull  = (140, 100, 60)   # wooden galley
        sail  = (220, 205, 175)
    elif era_idx <= 7:
        hull  = (80,  80,  90)   # iron/steel ship
        sail  = (190, 190, 200)
    else:
        hull  = (50,  200, 240)  # futuristic craft
        sail  = (180, 240, 255)

    for s in settlements:
        # Find water tile near this settlement
        water_x = water_y = None
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                wx2, wy2 = s.gx + dx, s.gy + dy
                if 0 <= wx2 < WORLD_W and 0 <= wy2 < WORLD_H:
                    if tiles[wx2][wy2] in WATER:
                        water_x, water_y = wx2, wy2
                        break
            if water_x is not None:
                break
        if water_x is None:
            continue

        # Animate boat in a small ellipse on the water
        n_boats = 1 + s.level // 2
        for k in range(min(n_boats, 3)):
            angle = tick * 0.28 + k * (math.tau / max(1, n_boats))
            bwx   = water_x + 0.5 + math.cos(angle) * 1.2
            bwy   = water_y + 0.5 + math.sin(angle) * 0.7
            sx2, sy2 = world_to_screen(bwx, bwy, cam_x, cam_y, zoom)
            if sx2 < -10 or sx2 > SCREEN_W + 10:
                continue
            r = max(2, int(3.0 * zoom))
            # Hull
            pygame.draw.ellipse(surface, hull,
                                (sx2 - r, sy2, r * 2, max(2, r)))
            # Mast + sail (era <= 7, not futuristic)
            if era_idx <= 7 and zoom >= 0.45 and r >= 3:
                pygame.draw.line(surface, (80, 65, 48),
                                 (sx2, sy2), (sx2, sy2 - r * 2), max(1, r // 2))
                pygame.draw.polygon(surface, sail, [
                    (sx2, sy2 - r * 2),
                    (sx2 + r, sy2 - r),
                    (sx2, sy2 - r // 2),
                ])


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

    # ── rivers (on terrain, under buildings) ──
    _draw_rivers(surface, sim.rivers, cam_x, cam_y, zoom)

    # ── inter-settlement trade routes (under buildings) ──
    _draw_trade_routes(surface, sim.settlements, era_idx, cam_x, cam_y, zoom, tick)

    # ── expand settlement layouts into per-tile building map ──
    building_map = {}   # (gx, gy) → (settlement, building_variant_level)
    for s in sim.settlements:
        layout = _SETTLE_LAYOUTS.get(min(s.level, 5), _SETTLE_LAYOUTS[5])
        for dx, dy, blvl in layout:
            bx = max(0, min(WORLD_W - 1, s.gx + dx))
            by = max(0, min(WORLD_H - 1, s.gy + dy))
            if (bx, by) not in building_map:
                building_map[(bx, by)] = (s, blvl)

    # ── intra-settlement roads (drawn under buildings) ──
    for s in sim.settlements:
        _draw_settlement_roads(surface, s, cam_x, cam_y, zoom)

    # ── construction sites (scaffolding for in-progress buildings) ──
    for (bx, by), wood in sim._build_progress.items():
        _draw_construction_site(surface, bx, by, wood, cam_x, cam_y, zoom)

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

    # ── boats near coastal settlements ──
    _draw_boats(surface, sim.settlements, tiles, era_idx, cam_x, cam_y, zoom, tick)

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
