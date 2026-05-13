import sys
import asyncio
import pygame
from config import SCREEN_W, SCREEN_H, FPS
from terrain import generate_terrain
from simulation import Simulation
from renderer import Camera, render

# Detect browser environment (Pygbag sets platform to "emscripten")
IS_WEB = sys.platform == "emscripten"


def make_fonts():
    families = ["segoeui", "arial", "freesans", "dejavusans", ""]
    def best(size, bold=False):
        for fam in families:
            try:
                f = pygame.font.SysFont(fam, size, bold=bold)
                if f:
                    return f
            except Exception:
                pass
        return pygame.font.Font(None, size)
    return {'big': best(26, bold=True), 'med': best(20), 'sm': best(15)}


async def main():
    pygame.init()

    flags = 0
    if IS_WEB:
        # Pygbag: use the canvas size provided by the HTML page
        flags = pygame.SCALED
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    pygame.display.set_caption("Jeu Monde — L'Évolution de l'Humanité")
    clock  = pygame.time.Clock()
    fonts  = make_fonts()

    # Loading screen
    screen.fill((10, 8, 5))
    msg = fonts['big'].render("Génération du monde…", True, (200, 180, 120))
    screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2,
                      SCREEN_H // 2 - msg.get_height() // 2))
    pygame.display.flip()
    await asyncio.sleep(0)   # yield so browser can paint the loading screen

    tiles, _, _ = generate_terrain(seed=42)
    # Web: epoch mode (real-time persistent world). Desktop: free-play.
    sim    = Simulation(tiles, epoch=IS_WEB)
    camera = Camera()
    tick   = 0.0

    running = True
    while running:
        dt   = min(clock.tick(FPS) / 1000.0, 0.1)
        tick += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE and not IS_WEB:
                    running = False
                elif event.key == pygame.K_SPACE:
                    sim.toggle_pause()
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS,
                                   pygame.K_KP_PLUS, pygame.K_PAGEUP):
                    sim.speed_up()
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS,
                                   pygame.K_PAGEDOWN):
                    sim.slow_down()

        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:                    dx += 1
        if keys[pygame.K_LEFT]  or keys[pygame.K_a] or keys[pygame.K_q]: dx -= 1
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]:                    dy += 1
        if keys[pygame.K_UP]    or keys[pygame.K_z] or keys[pygame.K_w]: dy -= 1
        camera.move(dx, dy, dt)

        sim.update(dt)
        render(screen, sim, tiles, camera, fonts, tick)
        pygame.display.flip()

        await asyncio.sleep(0)   # required by Pygbag / browser event loop

    pygame.quit()
    if not IS_WEB:
        sys.exit()


asyncio.run(main())
