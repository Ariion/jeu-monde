import sys
import asyncio
import pygame
from config import SCREEN_W, SCREEN_H, FPS, WORLD_W, WORLD_H
from terrain import build_noise_grids, compute_row, finalize_terrain
from simulation import Simulation
from renderer import Camera, render, find_nearest_entity

IS_WEB = sys.platform == "emscripten"


def make_fonts():
    families = ["segoeui", "arial", "freesans", "dejavusans", ""]
    def best(size, bold=False):
        for fam in families:
            try:
                f = pygame.font.SysFont(fam, size, bold=bold)
                if f: return f
            except Exception:
                pass
        return pygame.font.Font(None, size)
    return {'big': best(26, bold=True), 'med': best(20), 'sm': best(15)}


def _draw_loading(screen, fonts, message, pct):
    """Draw loading screen with progress bar — called between async yields."""
    screen.fill((10, 8, 5))
    # Title
    title = fonts['big'].render("Jeu Monde", True, (200, 170, 100))
    screen.blit(title, (SCREEN_W//2 - title.get_width()//2, SCREEN_H//2 - 70))
    # Message
    msg = fonts['med'].render(message, True, (160, 150, 120))
    screen.blit(msg, (SCREEN_W//2 - msg.get_width()//2, SCREEN_H//2 - 20))
    # Progress bar
    bw, bh = 400, 12
    bx = SCREEN_W//2 - bw//2
    by = SCREEN_H//2 + 20
    pygame.draw.rect(screen, (40, 36, 30), (bx, by, bw, bh), border_radius=6)
    filled = int(bw * pct / 100)
    if filled > 0:
        pygame.draw.rect(screen, (200, 160, 60), (bx, by, filled, bh), border_radius=6)
    pygame.draw.rect(screen, (80, 70, 50), (bx, by, bw, bh), 1, border_radius=6)
    # Percentage
    pct_s = fonts['sm'].render(f"{pct}%", True, (120, 110, 80))
    screen.blit(pct_s, (SCREEN_W//2 - pct_s.get_width()//2, by + bh + 8))
    pygame.display.flip()


async def generate_world_async(screen, fonts, seed=42):
    """Generate terrain asynchronously, yielding to the browser every few columns."""
    _draw_loading(screen, fonts, "Calcul des grilles de bruit…", 2)
    await asyncio.sleep(0)

    h_grids, m_grids = build_noise_grids(seed)

    height_map   = [[0.0] * WORLD_H for _ in range(WORLD_W)]
    moisture_map = [[0.0] * WORLD_H for _ in range(WORLD_W)]

    # Yield every CHUNK columns so the browser stays responsive (~16ms per chunk in WASM)
    CHUNK = 2
    for x in range(WORLD_W):
        h_row, m_row = compute_row(x, h_grids, m_grids)
        height_map[x]   = h_row
        moisture_map[x] = m_row
        if x % CHUNK == 0:
            pct = 5 + int(x / WORLD_W * 65)
            _draw_loading(screen, fonts, f"Façonnage du relief… ({x}/{WORLD_W})", pct)
            await asyncio.sleep(0)

    _draw_loading(screen, fonts, "Application du masque île…", 72)
    await asyncio.sleep(0)

    tiles, _, _ = finalize_terrain(height_map, moisture_map)

    _draw_loading(screen, fonts, "Peuplement du monde…", 82)
    await asyncio.sleep(0)

    return tiles


async def main():
    pygame.init()
    flags  = pygame.SCALED if IS_WEB else 0
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    pygame.display.set_caption("Jeu Monde — L'Évolution de l'Humanité")
    clock  = pygame.time.Clock()
    fonts  = make_fonts()

    # ── Async world generation ──
    tiles = await generate_world_async(screen, fonts, seed=42)

    _draw_loading(screen, fonts, "Initialisation de la simulation…", 90)
    await asyncio.sleep(0)

    sim    = Simulation(tiles, epoch=IS_WEB)

    _draw_loading(screen, fonts, "Prêt !", 100)
    await asyncio.sleep(0)

    camera = Camera()
    tick   = 0.0
    selected_entity = None

    running = True
    while running:
        dt   = min(clock.tick(FPS) / 1000.0, 0.1)
        tick += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if selected_entity:
                        selected_entity = None
                    elif not IS_WEB:
                        running = False
                elif event.key == pygame.K_SPACE:
                    sim.toggle_pause()
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS,
                                   pygame.K_KP_PLUS, pygame.K_PAGEUP):
                    sim.speed_up()
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS,
                                   pygame.K_PAGEDOWN):
                    sim.slow_down()

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                camera.zoom_by(1.18 if event.y > 0 else 1/1.18, mx, my)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    hit = find_nearest_entity(
                        event.pos[0], event.pos[1],
                        sim.entities, camera.x, camera.y, camera.zoom)
                    selected_entity = hit
                elif event.button == 3:
                    selected_entity = None

        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:                     dx += 1
        if keys[pygame.K_LEFT]  or keys[pygame.K_a] or keys[pygame.K_q]: dx -= 1
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]:                     dy += 1
        if keys[pygame.K_UP]    or keys[pygame.K_z] or keys[pygame.K_w]: dy -= 1
        camera.move(dx, dy, dt)

        sim.update(dt)
        render(screen, sim, tiles, camera, fonts, tick, selected_entity)
        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()
    if not IS_WEB:
        sys.exit()


asyncio.run(main())
