import pygame
import math
import random
from config import (SCREEN_W, SCREEN_H, TILE_W, TILE_H, WORLD_W, WORLD_H,
                    TILE_COLORS, TILE_HEIGHTS, TIME_SPEEDS, ERAS)


# ───────────────────────────── helpers ──────────────────────────────────────

def _darken(color, f):
    return (max(0, int(color[0] * f)),
            max(0, int(color[1] * f)),
            max(0, int(color[2] * f)))


def _mix(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def world_to_screen(wx, wy, cam_x, cam_y):
    sx = (wx - wy) * (TILE_W // 2) - cam_x + SCREEN_W // 2
    sy = (wx + wy) * (TILE_H // 2) - cam_y + SCREEN_H // 3
    return int(sx), int(sy)


# ─────────────────────────── tile drawing ───────────────────────────────────

def _draw_tile(surface, gx, gy, tile_type, cam_x, cam_y):
    sx, sy = world_to_screen(gx, gy, cam_x, cam_y)
    h  = TILE_HEIGHTS[tile_type]
    w2 = TILE_W // 2
    h2 = TILE_H // 2

    # Frustum cull
    if sx + w2 < -4 or sx - w2 > SCREEN_W + 4:
        return
    if sy + h2 + h < -4 or sy > SCREEN_H + 4:
        return

    base  = TILE_COLORS[tile_type]
    left  = _darken(base, 0.60)
    right = _darken(base, 0.78)

    if h > 0:
        pygame.draw.polygon(surface, left, [
            (sx - w2, sy + h2),
            (sx,      sy + TILE_H),
            (sx,      sy + TILE_H + h),
            (sx - w2, sy + h2 + h),
        ])
        pygame.draw.polygon(surface, right, [
            (sx,      sy + TILE_H),
            (sx + w2, sy + h2),
            (sx + w2, sy + h2 + h),
            (sx,      sy + TILE_H + h),
        ])

    top = [
        (sx,      sy - h),
        (sx + w2, sy + h2 - h),
        (sx,      sy + TILE_H - h),
        (sx - w2, sy + h2 - h),
    ]
    pygame.draw.polygon(surface, base, top)
    pygame.draw.aalines(surface, _darken(base, 0.85), True, top)


# ─────────────────────────── building drawing ───────────────────────────────

def _draw_building(surface, gx, gy, level, era_idx, cam_x, cam_y, tick):
    sx, sy = world_to_screen(gx + 0.5, gy + 0.5, cam_x, cam_y)
    sy -= TILE_HEIGHTS.get(3, 6) + 2   # sit on grass height

    if level == 0:                          # campfire
        flicker = int(math.sin(tick * 8 + gx) * 1.5)
        pygame.draw.circle(surface, (70, 40, 10),   (sx, sy + 2), 2)
        pygame.draw.circle(surface, (255, 140+flicker*10, 20), (sx, sy), 2)

    elif level == 1:                        # hut / tente
        pygame.draw.rect(surface, (160, 110, 65), (sx - 4, sy,     8, 5))
        pygame.draw.polygon(surface, (200, 80, 50),
                            [(sx - 5, sy), (sx + 5, sy), (sx, sy - 7)])

    elif level == 2:                        # village en pierre
        pygame.draw.rect(surface, (145, 135, 115), (sx - 6, sy - 2, 12, 8))
        pygame.draw.polygon(surface, (170, 75, 55),
                            [(sx - 6, sy - 2), (sx + 6, sy - 2), (sx, sy - 9)])

    elif level == 3:                        # bourg — tour + maison
        pygame.draw.rect(surface, (120, 115, 105), (sx - 7, sy - 4, 14, 10))
        pygame.draw.rect(surface, (100, 95,  88),  (sx - 3, sy - 12, 6, 9))
        pygame.draw.polygon(surface, (80, 60, 40),
                            [(sx - 3, sy - 12), (sx + 3, sy - 12), (sx, sy - 17)])

    elif level == 4:                        # ville industrielle / moderne
        pygame.draw.rect(surface, (110, 120, 140), (sx - 6, sy - 18, 12, 20))
        pygame.draw.rect(surface, (130, 140, 155), (sx - 4, sy - 23, 8, 6))
        if era_idx >= 6:                    # cheminée industrielle
            pygame.draw.rect(surface, (80, 75, 70), (sx + 4, sy - 26, 3, 10))
        for row in range(3):
            for col in range(2):
                wx_ = sx - 4 + col * 6
                wy_ = sy - 16 + row * 6
                pygame.draw.rect(surface, (255, 235, 150), (wx_, wy_, 2, 3))

    elif level == 5:                        # mégacité / futur
        if era_idx >= 9:
            glow = (60 + int(math.sin(tick * 2) * 20), 100, 220)
            pygame.draw.rect(surface, glow,           (sx - 4, sy - 28, 8, 30))
            pygame.draw.circle(surface, (180, 210, 255), (sx, sy - 29), 4)
            pygame.draw.circle(surface, (255, 255, 255), (sx, sy - 29), 2)
        else:
            pygame.draw.rect(surface, (100, 115, 145), (sx - 5, sy - 28, 10, 30))
            pygame.draw.rect(surface, (120, 135, 165), (sx - 3, sy - 34, 6,  7))
            for row in range(5):
                for col in range(2):
                    wx_ = sx - 3 + col * 5
                    wy_ = sy - 26 + row * 6
                    pygame.draw.rect(surface, (255, 240, 170), (wx_, wy_, 2, 3))


# ─────────────────────────── entity drawing ─────────────────────────────────

def _draw_entity(surface, ex, ey, era_idx, cam_x, cam_y):
    sx, sy = world_to_screen(ex, ey, cam_x, cam_y)
    if sx < -4 or sx > SCREEN_W + 4 or sy < -4 or sy > SCREEN_H + 4:
        return

    if era_idx == 0:
        body = (155, 105, 65)
        pygame.draw.circle(surface, body, (sx, sy - 2), 2)
        pygame.draw.line(surface, body, (sx, sy), (sx - 1, sy + 3))

    elif era_idx <= 2:
        body = (175, 135, 85)
        pygame.draw.circle(surface, body, (sx, sy - 2), 2)
        pygame.draw.line(surface, body, (sx, sy), (sx, sy + 3))

    elif era_idx <= 4:
        pygame.draw.circle(surface, (195, 160, 105), (sx, sy - 2), 2)
        pygame.draw.line(surface, (110, 80, 45), (sx, sy), (sx, sy + 4))

    elif era_idx <= 6:
        pygame.draw.circle(surface, (210, 175, 130), (sx, sy - 2), 2)
        pygame.draw.rect(surface, (60, 85, 140), (sx - 1, sy + 1, 3, 4))

    elif era_idx <= 7:
        pygame.draw.circle(surface, (215, 190, 155), (sx, sy - 1), 2)
        pygame.draw.rect(surface, (40, 60, 120), (sx - 1, sy + 1, 3, 4))

    else:
        col = (200, 220, 255) if era_idx == 9 else (215, 225, 255)
        pygame.draw.circle(surface, col, (sx, sy - 1), 2)
        pygame.draw.rect(surface, (70, 110, 210), (sx - 1, sy + 1, 3, 4))


# ─────────────────────────── camera ─────────────────────────────────────────

class Camera:
    SPEED = 320.0   # screen-pixels per second

    def __init__(self):
        cx, cy = WORLD_W // 2, WORLD_H // 2
        sx, sy = world_to_screen(cx, cy, 0, 0)
        self.x = float(sx)
        self.y = float(sy)

    def move(self, dx, dy, dt):
        self.x += dx * self.SPEED * dt
        self.y += dy * self.SPEED * dt


# ────────────────────────── main render call ────────────────────────────────

def render(surface, sim, tiles, camera, fonts, tick):
    era_idx, era = sim.get_era()
    sky = era[2]
    surface.fill(sky)

    cam_x, cam_y = camera.x, camera.y

    # Draw tiles — diagonal-stripe order (correct painter's algorithm)
    for diag in range(WORLD_W + WORLD_H - 1):
        x0 = max(0, diag - WORLD_H + 1)
        x1 = min(WORLD_W, diag + 1)
        for gx in range(x0, x1):
            gy = diag - gx
            _draw_tile(surface, gx, gy, tiles[gx][gy], cam_x, cam_y)

    # Draw settlements (same diagonal order)
    settle_map = {(s.gx, s.gy): s for s in sim.settlements}
    for diag in range(WORLD_W + WORLD_H - 1):
        x0 = max(0, diag - WORLD_H + 1)
        x1 = min(WORLD_W, diag + 1)
        for gx in range(x0, x1):
            gy = diag - gx
            s = settle_map.get((gx, gy))
            if s:
                _draw_building(surface, gx, gy, s.level, era_idx, cam_x, cam_y, tick)

    # Draw entities (subsample when many for performance)
    entities = sim.entities
    step = max(1, len(entities) // 600)
    for e in entities[::step]:
        _draw_entity(surface, e.x, e.y, era_idx, cam_x, cam_y)

    _draw_ui(surface, sim, era_idx, era, fonts)


# ─────────────────────────── UI overlay ─────────────────────────────────────

def _draw_ui(surface, sim, era_idx, era, fonts):
    # ── top bar ──
    bar = pygame.Surface((SCREEN_W, 52), pygame.SRCALPHA)
    bar.fill((0, 0, 0, 160))
    surface.blit(bar, (0, 0))

    era_surf = fonts['big'].render(era[1], True, (255, 218, 140))
    surface.blit(era_surf, (18, 10))

    year_surf = fonts['med'].render(f"Année  {int(sim.year):,}", True, (200, 200, 200))
    surface.blit(year_surf, (320, 16))

    pop_surf = fonts['med'].render(f"Population  {sim.population():,}", True, (160, 220, 160))
    surface.blit(pop_surf, (530, 16))

    if sim.epoch:
        spd_str   = "⬤  EN DIRECT"
        spd_color = (255, 90, 90)
    elif sim.paused:
        spd_str   = "⏸  PAUSE"
        spd_color = (255, 150, 50)
    else:
        spd_str   = f"▶  {TIME_SPEEDS[sim.speed_idx]:,} ans/s"
        spd_color = (140, 215, 140)
    spd_surf = fonts['med'].render(spd_str, True, spd_color)
    surface.blit(spd_surf, (SCREEN_W - spd_surf.get_width() - 18, 16))

    # ── era progress bar ──
    if era_idx < len(ERAS) - 1:
        next_yr  = ERAS[era_idx + 1][0]
        this_yr  = ERAS[era_idx][0]
        progress = min(1.0, (sim.year - this_yr) / max(1, next_yr - this_yr))
        bar_w    = SCREEN_W - 36
        pygame.draw.rect(surface, (50, 50, 50),  (18, 48, bar_w, 4))
        pygame.draw.rect(surface, (255, 200, 80), (18, 48, int(bar_w * progress), 4))

    # ── bottom description ──
    bot = pygame.Surface((SCREEN_W, 28), pygame.SRCALPHA)
    bot.fill((0, 0, 0, 140))
    surface.blit(bot, (0, SCREEN_H - 28))

    desc_surf = fonts['sm'].render(era[3], True, (155, 155, 185))
    surface.blit(desc_surf, (18, SCREEN_H - 22))

    if sim.epoch:
        hint_text = "Z Q S D / flèches : déplacer la caméra  ·  monde en temps réel"
    else:
        hint_text = "ESPACE pause  ·  + - vitesse  ·  Z Q S D / flèches caméra  ·  ÉCHAP quitter"
    hint_surf = fonts['sm'].render(hint_text, True, (90, 90, 90))
    surface.blit(hint_surf, (SCREEN_W - hint_surf.get_width() - 18, SCREEN_H - 22))

    # ── event log (left side) ──
    y_ev = 65
    for text, remaining in list(reversed(sim._active_events))[:5]:
        alpha = min(255, int(remaining * 30))
        is_era = "ère" in text.lower() or "✦" in text
        color  = (255, 215, 80) if is_era else (200, 200, 200)
        ev_surf = fonts['sm'].render(text, True, color)
        # Fade by blending toward sky color
        if alpha < 200:
            faded = pygame.Surface(ev_surf.get_size(), pygame.SRCALPHA)
            faded.blit(ev_surf, (0, 0))
            faded.set_alpha(alpha)
            surface.blit(faded, (18, y_ev))
        else:
            surface.blit(ev_surf, (18, y_ev))
        y_ev += 21
