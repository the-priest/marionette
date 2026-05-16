#!/usr/bin/env python3
"""
MARIONETTE - a troll platformer

A diabolical 2D platformer in the spirit of Level Devil, but cranked up:
72 hand-crafted levels across 6 chapters of escalating cruelty, story
beats between acts, an unhinged narrator, and 25+ unique troll mechanics
that the level designer (the Warden) uses to make your existence hell.

You are a little black stickman. The Warden is the unseen entity that
designs each room. The Warden hates you.

Install:  pip install pygame
Run:      python3 marionette.py

Keyboard:
  A / D / arrows .......... move
  Space / W / Up .......... jump
  R ....................... restart current level
  Esc / Q ................. quit
  F ....................... toggle fullscreen
  F1 ...................... skip dialogue
  F2 ...................... level select (after first death)

Save: ~/.local/share/marionette/save.json
Reset: rm -f ~/.local/share/marionette/save.json

Set MARIONETTE_WINDOW=1 to start windowed instead of fullscreen.
"""
import pygame, sys, math, random, os, json, time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable

pygame.init()

# ─── Display ──────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1280, 720
TILE = 40
GRID_W, GRID_H = WIDTH // TILE, HEIGHT // TILE   # 32 x 18

flags = pygame.SCALED
if os.environ.get("MARIONETTE_WINDOW") != "1":
    flags |= pygame.FULLSCREEN
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT), flags)
pygame.display.set_caption("MARIONETTE")
pygame.mouse.set_visible(False)
CLOCK = pygame.time.Clock()
FPS = 60
DT = 1.0 / FPS

# ─── Physics ──────────────────────────────────────────────────────────────────
GRAVITY = 2000.0
JUMP_V = -720.0
MOVE_V = 340.0
MAX_FALL = 1300.0
COYOTE = 0.10
JBUF = 0.12
AIR_DRAG = 0.92

# ─── Difficulty ───────────────────────────────────────────────────────────────
# Lower = faster trolls = harder. Applied to time-based hazard delays.
DIFF = 0.70   # 30% faster than baseline. Set 1.0 to soften, 0.5 for masochism.

# ─── Colors ───────────────────────────────────────────────────────────────────
WHITE = (240, 240, 240)
PAPER = (228, 226, 220)
LIGHT = (200, 200, 195)
GREY = (140, 140, 138)
DARK = (60, 60, 60)
INK = (15, 15, 18)
BLOOD = (170, 28, 28)
WARN = (200, 80, 30)
EXIT_C = (35, 35, 35)
ACCENT = (180, 60, 60)

# ─── Save ─────────────────────────────────────────────────────────────────────
SAVE_DIR = Path.home() / ".local/share/marionette"
SAVE_DIR.mkdir(parents=True, exist_ok=True)
SAVE_FILE = SAVE_DIR / "save.json"

def load_save():
    try:
        return json.loads(SAVE_FILE.read_text())
    except Exception:
        return {"highest_unlocked": 0, "deaths": 0, "completed": False}

def write_save(d):
    try:
        SAVE_FILE.write_text(json.dumps(d))
    except Exception:
        pass

# ─── Fonts ────────────────────────────────────────────────────────────────────
def font(sz, bold=False):
    try:
        f = pygame.font.SysFont("dejavusansmono,liberationmono,monospace", sz, bold=bold)
    except Exception:
        f = pygame.font.Font(None, sz)
    return f

F_TITLE = font(96, bold=True)
F_BIG = font(56, bold=True)
F_MID = font(34)
F_SMALL = font(22)
F_TINY = font(16)
F_NARR = font(28)

# ─── Gamepad ──────────────────────────────────────────────────────────────────
# Xbox / 8BitDo / generic SDL layout button map.
PAD_A      = 0   # jump / confirm
PAD_B      = 1   # restart / back
PAD_X      = 2   # restart (alt) / quick
PAD_Y      = 3   # level select
PAD_LB     = 4   # prev (in select)
PAD_RB     = 5   # next (in select)
PAD_BACK   = 6   # quit
PAD_START  = 7   # menu / select toggle
DEADZONE   = 0.35

class Pad:
    """Joystick aggregator. ORs gamepad into keyboard. Safe if no pad present."""
    def __init__(self):
        try:
            pygame.joystick.init()
        except Exception:
            pass
        self.joy = None
        self._refresh()
        # edge-trigger button presses captured from JOYBUTTONDOWN events
        self.button_edges = set()

    def _refresh(self):
        try:
            if pygame.joystick.get_count() > 0:
                if self.joy is None:
                    self.joy = pygame.joystick.Joystick(0)
                    self.joy.init()
            else:
                self.joy = None
        except Exception:
            self.joy = None

    def attach(self, idx):
        try:
            self.joy = pygame.joystick.Joystick(idx)
            self.joy.init()
        except Exception:
            self.joy = None

    def detach(self):
        self.joy = None

    def axis_x(self):
        if not self.joy:
            return 0.0
        try:
            ax = self.joy.get_axis(0)
        except Exception:
            ax = 0.0
        try:
            hx, _ = self.joy.get_hat(0)
        except Exception:
            hx = 0
        if hx != 0:
            return float(hx)
        if abs(ax) > DEADZONE:
            return -1.0 if ax < 0 else 1.0
        return 0.0

    def axis_y(self):
        if not self.joy:
            return 0.0
        try:
            ay = self.joy.get_axis(1)
        except Exception:
            ay = 0.0
        try:
            _, hy = self.joy.get_hat(0)
        except Exception:
            hy = 0
        # SDL hats: up = +1, down = -1
        if hy != 0:
            return -float(hy)
        if abs(ay) > DEADZONE:
            return -1.0 if ay < 0 else 1.0
        return 0.0

    def held(self, btn):
        if not self.joy:
            return False
        try:
            return bool(self.joy.get_button(btn))
        except Exception:
            return False

    def consume(self, btn):
        """Edge-triggered press; clears flag."""
        if btn in self.button_edges:
            self.button_edges.discard(btn)
            return True
        return False

    def consume_any(self, *btns):
        for b in btns:
            if b in self.button_edges:
                self.button_edges.discard(b)
                return True
        return False

PAD = Pad()

def input_left(keys):
    return keys[pygame.K_a] or keys[pygame.K_LEFT] or PAD.axis_x() < -0.5

def input_right(keys):
    return keys[pygame.K_d] or keys[pygame.K_RIGHT] or PAD.axis_x() > 0.5

def input_jump(keys):
    return (keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]
            or PAD.held(PAD_A))

# ─── Visual overlays (pre-built once) ─────────────────────────────────────────
def _build_vignette():
    s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    cx, cy = WIDTH // 2, HEIGHT // 2
    max_r = math.hypot(cx, cy)
    # darken edges with concentric rings
    for r in range(int(max_r), int(max_r * 0.55), -8):
        t = (r - max_r * 0.55) / (max_r - max_r * 0.55)
        a = int(t * 110)
        pygame.draw.circle(s, (0, 0, 0, a), (cx, cy), r, 9)
    return s

def _build_grain():
    s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    rng = random.Random(1337)
    pa = pygame.PixelArray(s)
    for _ in range(7000):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, HEIGHT - 1)
        v = rng.randint(0, 70)
        pa[x, y] = (0, 0, 0, v)
    for _ in range(3000):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, HEIGHT - 1)
        v = rng.randint(0, 60)
        pa[x, y] = (255, 255, 255, v)
    del pa
    return s

VIGNETTE = _build_vignette()
GRAIN = _build_grain()

def _build_floor_shade():
    """Subtle darkening from sky to floor — added to bg as alpha overlay."""
    s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for y in range(HEIGHT):
        t = y / HEIGHT
        a = int(t * 30)        # 0..30 alpha
        pygame.draw.line(s, (0, 0, 0, a), (0, y), (WIDTH, y))
    return s

FLOOR_SHADE = _build_floor_shade()

# ─── Narrator ─────────────────────────────────────────────────────────────────
class Narrator:
    """Typewriter text overlay. Mocking commentary from the Warden."""
    def __init__(self):
        self.queue: List[str] = []
        self.current = ""
        self.shown = 0
        self.hold = 0.0
        self.speed = 38.0   # chars per second
        self.color = INK
        self.position = "top"   # "top" | "center" | "bottom"
        self.persistent = False  # if True, line stays until cleared

    def say(self, text, position="top", color=None, hold=2.0):
        self.queue.append(("line", text, position, color or INK, hold))

    def clear(self):
        self.queue.clear()
        self.current = ""
        self.shown = 0
        self.hold = 0.0
        self.persistent = False

    def skip(self):
        if self.current and self.shown < len(self.current):
            self.shown = len(self.current)
        else:
            self.hold = 0

    def busy(self):
        return bool(self.queue) or bool(self.current)

    def update(self, dt):
        if not self.current and self.queue:
            kind, text, pos, col, hold = self.queue.pop(0)
            self.current = text
            self.shown = 0
            self.position = pos
            self.color = col
            self.hold = hold
        if self.current:
            if self.shown < len(self.current):
                self.shown = min(len(self.current),
                                 self.shown + self.speed * dt)
            else:
                self.hold -= dt
                if self.hold <= 0:
                    self.current = ""
                    self.shown = 0

    def draw(self, surf):
        if not self.current:
            return
        text = self.current[:int(self.shown)]
        if not text:
            return
        s = F_NARR.render(text, True, self.color)
        w, h = s.get_size()
        pad = 18
        bg = pygame.Surface((w + pad * 2, h + pad), pygame.SRCALPHA)
        pygame.draw.rect(bg, (240, 238, 232, 220), bg.get_rect(), border_radius=4)
        pygame.draw.rect(bg, (60, 60, 60, 80), bg.get_rect(), 2, border_radius=4)
        if self.position == "top":
            y = 40
        elif self.position == "bottom":
            y = HEIGHT - h - pad - 60
        else:
            y = HEIGHT // 2 - h // 2
        x = WIDTH // 2 - bg.get_width() // 2
        surf.blit(bg, (x, y))
        surf.blit(s, (x + pad, y + pad // 2))

# ─── Particles ────────────────────────────────────────────────────────────────
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color", "grav")
    def __init__(self, x, y, vx, vy, life, size, color, grav=True):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life
        self.size = size; self.color = color
        self.grav = grav
    def update(self, dt):
        if self.grav:
            self.vy += 1600 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
    def alive(self):
        return self.life > 0
    def draw(self, surf):
        a = max(0.0, min(1.0, self.life / self.max_life))
        r = max(1, int(self.size * a))
        pygame.draw.circle(surf, self.color,
                           (int(self.x), int(self.y)), r)

def blood_burst(particles, x, y, n=22):
    for _ in range(n):
        ang = random.uniform(-math.pi, 0)
        spd = random.uniform(120, 480)
        vx = math.cos(ang) * spd
        vy = math.sin(ang) * spd
        life = random.uniform(0.4, 0.9)
        particles.append(Particle(x, y, vx, vy, life,
                                  random.uniform(2.5, 5.5), BLOOD))
    for _ in range(8):
        ang = random.uniform(-math.pi, 0)
        spd = random.uniform(60, 200)
        vx = math.cos(ang) * spd
        vy = math.sin(ang) * spd
        life = random.uniform(0.3, 0.6)
        particles.append(Particle(x, y, vx, vy, life,
                                  random.uniform(1.5, 3), (90, 12, 12)))

def dust_puff(particles, x, y, n=6):
    for _ in range(n):
        vx = random.uniform(-60, 60)
        vy = random.uniform(-120, -20)
        life = random.uniform(0.2, 0.45)
        particles.append(Particle(x, y, vx, vy, life,
                                  random.uniform(2, 4),
                                  (180, 178, 170), grav=False))

# ─── Player (the Marionette) ──────────────────────────────────────────────────
class Marionette:
    """Little black stickman. ~28px wide, 56px tall."""
    W = 22
    H = 50

    def __init__(self, x, y):
        self.x = float(x); self.y = float(y)
        self.vx = 0.0; self.vy = 0.0
        self.on_ground = False
        self.face = 1            # 1 right, -1 left
        self.coyote = 0.0
        self.jbuf = 0.0
        self.dead = False
        self.death_t = 0.0
        self.anim_t = 0.0
        self.head_off_x = 0.0    # head dangle for trolls
        self.head_off_y = 0.0
        self.body_squash = 1.0
        self.invert = False      # control inversion troll
        self.gravity_dir = 1     # 1 normal, -1 inverted
        self.string_phase = 0.0  # marionette "strings" sway
        self.trail = []          # afterimage positions when moving fast
        self.string_snap = False # whether strings snapped at death
        self.snap_dx = [0, 0, 0] # head/lhand/rhand horizontal sway at snap

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.W / 2), int(self.y - self.H),
                           self.W, self.H)

    def feet(self):
        return (self.x, self.y)

    def head(self):
        return (self.x + self.head_off_x, self.y - self.H + 6 + self.head_off_y)

    def kill(self, particles, sound_cb=None):
        if self.dead:
            return
        self.dead = True
        self.death_t = 0.0
        self.string_snap = True
        # random horizontal drift on the snapped string ends
        self.snap_dx = [random.uniform(-30, 30) for _ in range(3)]
        hx, hy = self.head()
        blood_burst(particles, self.x, self.y - self.H * 0.5, 28)
        blood_burst(particles, hx, hy, 12)
        if sound_cb: sound_cb("death")

    def update(self, dt, level, particles, narrator):
        if self.dead:
            self.death_t += dt
            return

        # Apply input (keyboard + gamepad)
        keys = pygame.key.get_pressed()
        left = bool(input_left(keys))
        right = bool(input_right(keys))
        jump = bool(input_jump(keys))
        if self.invert:
            left, right = right, left

        target_vx = 0.0
        if left:  target_vx -= MOVE_V; self.face = -1
        if right: target_vx += MOVE_V; self.face = 1
        # accelerate toward target
        self.vx += (target_vx - self.vx) * (0.35 if self.on_ground else 0.18)

        # Gravity
        g = GRAVITY * self.gravity_dir
        self.vy += g * dt
        max_fall = MAX_FALL
        if self.gravity_dir > 0:
            self.vy = min(self.vy, max_fall)
        else:
            self.vy = max(self.vy, -max_fall)

        # Jump buffer / coyote
        if jump:
            self.jbuf = JBUF
        else:
            self.jbuf -= dt
        self.coyote -= dt

        can_jump = self.coyote > 0
        if self.jbuf > 0 and can_jump:
            self.vy = JUMP_V * self.gravity_dir
            self.jbuf = 0; self.coyote = 0
            dust_puff(particles, self.x, self.y, 5)

        # Move + collide axis-by-axis
        self._move_axis(self.vx * dt, 0, level)
        was_grounded = self.on_ground
        self.on_ground = False
        self._move_axis(0, self.vy * dt, level)

        if self.on_ground and not was_grounded:
            dust_puff(particles, self.x, self.y, 4)

        if self.on_ground:
            self.coyote = COYOTE

        # Bounds: kill on falling off-screen (top/bottom).
        if self.y > HEIGHT + 80 or self.y < -120:
            self.kill(particles)

        # Horizontal world clamp — Level-Devil style: you can't leave the
        # room sideways. Pin the player inside the playfield instead of
        # letting them walk off into the void.
        if self.x < self.W / 2:
            self.x = self.W / 2
            self.vx = 0
        elif self.x > WIDTH - self.W / 2:
            self.x = WIDTH - self.W / 2
            self.vx = 0

        # Squeeze death: if a troll spawned a solid tile on top of us
        # (wall_slam, crushing_ceiling, falling_block landing, etc.) the
        # axis-by-axis collision resolution alone can leave the player
        # pinned inside a tile. Detect overlap with any solid tile and die.
        if not self.dead:
            pr = self.rect
            for tile_rect, _kind in level.solid_tiles():
                if pr.colliderect(tile_rect):
                    # require non-trivial overlap to avoid false positives
                    overlap_w = min(pr.right, tile_rect.right) - max(pr.left, tile_rect.left)
                    overlap_h = min(pr.bottom, tile_rect.bottom) - max(pr.top, tile_rect.top)
                    if overlap_w > 4 and overlap_h > 4:
                        self.kill(particles)
                        break

        # Animation
        if self.on_ground and abs(self.vx) > 30:
            self.anim_t += dt * (abs(self.vx) / 60)
        else:
            self.anim_t += dt * 2

        # Head dangle relaxes
        self.head_off_x *= 0.92
        self.head_off_y *= 0.92
        self.body_squash += (1.0 - self.body_squash) * 0.2
        self.string_phase += dt

        # Trail samples (afterimage) when moving fast
        speed_sq = self.vx * self.vx + self.vy * self.vy
        if speed_sq > 120000:
            self.trail.append((self.x, self.y, 0.22))
        # decay
        new = []
        for tx, ty, life in self.trail:
            life -= dt
            if life > 0:
                new.append((tx, ty, life))
        self.trail = new[-8:]

    def _move_axis(self, dx, dy, level):
        self.x += dx
        self.y += dy
        r = self.rect
        for tile_rect, kind in level.solid_tiles():
            if r.colliderect(tile_rect):
                if dx > 0:
                    self.x -= r.right - tile_rect.left
                    self.vx = 0
                elif dx < 0:
                    self.x += tile_rect.right - r.left
                    self.vx = 0
                if dy > 0:
                    self.y -= r.bottom - tile_rect.top
                    if self.gravity_dir > 0:
                        self.on_ground = True
                    self.vy = 0
                elif dy < 0:
                    self.y += tile_rect.bottom - r.top
                    if self.gravity_dir < 0:
                        self.on_ground = True
                    self.vy = 0
                r = self.rect

    def draw(self, surf):
        # Afterimage trail (rendered behind body)
        for (tx, ty, life) in self.trail:
            a = int(80 * (life / 0.22))
            ts = pygame.Surface((self.W + 8, self.H + 4), pygame.SRCALPHA)
            pygame.draw.line(ts, (15, 15, 18, a),
                             (ts.get_width()//2, 6),
                             (ts.get_width()//2, ts.get_height() - 4), 4)
            pygame.draw.circle(ts, (15, 15, 18, a),
                               (ts.get_width()//2, 6), 7)
            surf.blit(ts, (int(tx - ts.get_width()//2),
                           int(ty - ts.get_height())))

        if self.dead:
            self._draw_dead(surf)
            return
        # Strings (vertical lines from top of screen to limbs - the puppet motif)
        head_x, head_y = self.head()
        # subtle sway
        sway = math.sin(self.string_phase * 1.6) * 1.2
        pygame.draw.line(surf, (180, 178, 168),
                         (head_x + sway, 0), (head_x, head_y - 6), 1)
        pygame.draw.line(surf, (180, 178, 168),
                         (self.x - 8 + sway, 0), (self.x - 8, self.y - self.H * 0.55), 1)
        pygame.draw.line(surf, (180, 178, 168),
                         (self.x + 8 + sway, 0), (self.x + 8, self.y - self.H * 0.55), 1)

        # Stickman geometry
        cx, cy = self.x, self.y
        body_top = cy - self.H + 12
        body_bot = cy - 8
        # squash applied to body length
        body_top_sq = cy - self.H * self.body_squash + 12
        # legs/arms swing
        walk = math.sin(self.anim_t * 8) if self.on_ground else 0
        air = self.vy * 0.001
        leg_a = walk * 8
        arm_a = -walk * 6

        # legs
        pygame.draw.line(surf, INK, (cx, body_bot), (cx - 6 - leg_a, cy + 2), 4)
        pygame.draw.line(surf, INK, (cx, body_bot), (cx + 6 + leg_a, cy + 2), 4)
        # body
        pygame.draw.line(surf, INK, (cx, body_top_sq), (cx, body_bot), 5)
        # arms
        pygame.draw.line(surf, INK, (cx, body_top_sq + 6),
                         (cx - 9 + arm_a, body_top_sq + 16 + air), 4)
        pygame.draw.line(surf, INK, (cx, body_top_sq + 6),
                         (cx + 9 - arm_a, body_top_sq + 16 + air), 4)
        # head
        pygame.draw.circle(surf, INK, (int(head_x), int(head_y)), 9)

    def _draw_dead(self, surf):
        # Snapped strings — fall from above, drift to random horizontal
        if self.string_snap:
            t = min(1.0, self.death_t * 1.4)
            for i, (sx_off, target_y) in enumerate([
                (0, self.y - self.H + 6),       # head string
                (-8, self.y - self.H * 0.55),    # left arm
                (8, self.y - self.H * 0.55),     # right arm
            ]):
                end_x = self.x + sx_off + self.snap_dx[i] * t
                end_y = target_y + t * 36
                pygame.draw.line(surf, (180, 178, 168, 120),
                                 (self.x + sx_off, 0), (end_x, end_y), 1)
        # body collapses
        t = min(1.0, self.death_t * 2.5)
        cx, cy = self.x, self.y
        # fallen lines on the ground
        pygame.draw.line(surf, INK, (cx - 12, cy - 2), (cx + 12, cy - 2), 4)
        pygame.draw.line(surf, INK, (cx - 14, cy + 1), (cx - 8, cy + 1), 3)
        pygame.draw.line(surf, INK, (cx + 8, cy + 1), (cx + 14, cy + 1), 3)
        # head rolled
        hx = cx + 18 + t * 12
        pygame.draw.circle(surf, INK, (int(hx), int(cy - 4)), 8)
        # blood pool grows
        pool_r = int(6 + t * 14)
        pygame.draw.ellipse(surf, BLOOD,
                            (int(cx - pool_r - 4), int(cy - 4), pool_r * 2 + 8, 8))
        # blood streak from head to body
        if t > 0.3:
            pygame.draw.line(surf, BLOOD, (cx + 6, cy - 2), (int(hx - 6), int(cy - 4)), 2)

# ─── Level & Tile System ─────────────────────────────────────────────────────
#
# Tile chars used in level layouts (each char = TILE px):
#   '.' empty
#   '#' solid block (dark)
#   '=' solid block (light, for visual variety)
#   '^' upward spike (kills on touch)
#   'v' downward spike (from ceiling)
#   '<' left-facing spike (on a wall)
#   '>' right-facing spike (on a wall)
#   'P' player spawn
#   'E' exit door
#   'X' fake exit (looks like E, actually kills)
#   'D' disappearing platform (vanishes after stepping)
#   'I' invisible platform (only solid, drawn only on contact)
#   '~' saw blade (animated)
#   'L' lava tile
#   '?' decoy / shows as exit but does nothing
#   ' ' empty (alias for .)
#
# Trolls add dynamic behavior on top of static tiles.

SOLID_CHARS = "#="
SPIKE_CHARS = "^v<>"
LIQUID_CHARS = "L"

class Tile:
    __slots__ = ("ch", "x", "y", "rect", "alive", "phase")
    def __init__(self, ch, gx, gy):
        self.ch = ch
        self.x = gx; self.y = gy
        self.rect = pygame.Rect(gx * TILE, gy * TILE, TILE, TILE)
        self.alive = True
        self.phase = 0.0

class Level:
    def __init__(self, data):
        self.name = data.get("name", "")
        self.chapter = data.get("chapter", 1)
        self.intro = data.get("intro", "")
        self.outro = data.get("outro", "")
        self.bg = data.get("bg", PAPER)
        self.tile_grid: List[List[Optional[Tile]]] = []
        self.spawn = (WIDTH / 2, HEIGHT / 2)
        self.exit_pos = (WIDTH / 2, HEIGHT / 2)
        self.fake_exits: List[Tuple[float, float]] = []
        self.decoy_exits: List[Tuple[float, float]] = []
        self.parse_layout(data.get("tiles", []))
        self.trolls: List["Troll"] = []
        for tspec in data.get("trolls", []):
            cls = TROLL_REGISTRY[tspec[0]]
            self.trolls.append(cls(*tspec[1:]))
        self.t = 0.0
        # one-shot triggers
        self.triggered = set()
        # exit can be moved dynamically (MovingExit)
        self.exit_visible = True
        self.exit_pos_dyn = self.exit_pos

    def parse_layout(self, rows):
        # Pad rows to GRID_W and grid to GRID_H
        rows = [r.ljust(GRID_W)[:GRID_W] for r in rows]
        while len(rows) < GRID_H:
            rows.insert(0, "." * GRID_W)
        rows = rows[-GRID_H:]
        self.tile_grid = [[None] * GRID_W for _ in range(GRID_H)]
        for gy, row in enumerate(rows):
            for gx, ch in enumerate(row):
                if ch == "P":
                    self.spawn = (gx * TILE + TILE / 2, gy * TILE + TILE - 1)
                elif ch == "E":
                    self.exit_pos = (gx * TILE + TILE / 2, gy * TILE + TILE / 2)
                    self.exit_pos_dyn = self.exit_pos
                elif ch == "X":
                    self.fake_exits.append((gx * TILE + TILE / 2,
                                            gy * TILE + TILE / 2))
                elif ch == "?":
                    self.decoy_exits.append((gx * TILE + TILE / 2,
                                             gy * TILE + TILE / 2))
                elif ch not in (".", " "):
                    self.tile_grid[gy][gx] = Tile(ch, gx, gy)

    def all_tiles(self):
        for row in self.tile_grid:
            for t in row:
                if t is not None and t.alive:
                    yield t

    def solid_tiles(self):
        """Yields (rect, kind) for collidable tiles."""
        for t in self.all_tiles():
            if t.ch in SOLID_CHARS or t.ch == "D" or t.ch == "I":
                # disappearing/invisible platforms: solid while alive
                yield (t.rect, t.ch)

    def remove_tile(self, gx, gy):
        if 0 <= gy < GRID_H and 0 <= gx < GRID_W:
            self.tile_grid[gy][gx] = None

    def set_tile(self, gx, gy, ch):
        if 0 <= gy < GRID_H and 0 <= gx < GRID_W:
            self.tile_grid[gy][gx] = Tile(ch, gx, gy)

    def get_tile(self, gx, gy):
        if 0 <= gy < GRID_H and 0 <= gx < GRID_W:
            return self.tile_grid[gy][gx]
        return None

    def hazard_hit(self, player_rect):
        for t in self.all_tiles():
            if t.ch in SPIKE_CHARS or t.ch in LIQUID_CHARS:
                # spikes hitbox is smaller (90% of tile)
                pad = 6
                hr = t.rect.inflate(-pad, -pad)
                if player_rect.colliderect(hr):
                    return True
        return False

    def update(self, dt, player, particles, narrator, game):
        self.t += dt
        for t in self.all_tiles():
            t.phase += dt
        for troll in self.trolls:
            troll.update(dt, self, player, particles, narrator, game)

    def draw_tiles(self, surf):
        for t in self.all_tiles():
            self._draw_tile(surf, t)

    def _draw_tile(self, surf, t):
        r = t.rect
        ch = t.ch
        if ch == "#":
            pygame.draw.rect(surf, DARK, r)
            pygame.draw.rect(surf, INK, r, 2)
        elif ch == "=":
            pygame.draw.rect(surf, GREY, r)
            pygame.draw.rect(surf, DARK, r, 2)
        elif ch == "^":
            self._draw_spike(surf, r, "up")
        elif ch == "v":
            self._draw_spike(surf, r, "down")
        elif ch == "<":
            self._draw_spike(surf, r, "left")
        elif ch == ">":
            self._draw_spike(surf, r, "right")
        elif ch == "D":
            # disappearing platform - dashed look
            pygame.draw.rect(surf, (110, 110, 110), r)
            for i in range(0, TILE, 8):
                pygame.draw.line(surf, INK,
                                 (r.x + i, r.y), (r.x + i + 4, r.y), 2)
            pygame.draw.rect(surf, INK, r, 1)
        elif ch == "I":
            # invisible — only render very faintly when contacted
            pass
        elif ch == "~":
            cx, cy = r.center
            ang = (t.phase * 8) % (2 * math.pi)
            pygame.draw.circle(surf, (90, 90, 90), (cx, cy), TILE // 2 - 2)
            for i in range(8):
                a = ang + i * math.pi / 4
                p1 = (cx + math.cos(a) * (TILE // 2 - 2),
                      cy + math.sin(a) * (TILE // 2 - 2))
                p2 = (cx + math.cos(a) * (TILE // 2 + 4),
                      cy + math.sin(a) * (TILE // 2 + 4))
                pygame.draw.line(surf, INK, p1, p2, 3)
            pygame.draw.circle(surf, INK, (cx, cy), 4)
        elif ch == "L":
            # lava
            wob = math.sin(t.phase * 4 + r.x) * 2
            pygame.draw.rect(surf, (180, 50, 30),
                             (r.x, r.y + 4 + wob, r.w, r.h - 4))
            pygame.draw.rect(surf, (240, 120, 60),
                             (r.x, r.y + 4 + wob, r.w, 4))

    def _draw_spike(self, surf, r, direction):
        n = 3
        pts_sets = []
        if direction == "up":
            base = r.bottom
            top = r.top + 2
            for i in range(n):
                x0 = r.x + i * (r.w / n)
                x1 = x0 + r.w / n
                pts_sets.append([(x0, base), ((x0 + x1) / 2, top), (x1, base)])
        elif direction == "down":
            base = r.top
            tip = r.bottom - 2
            for i in range(n):
                x0 = r.x + i * (r.w / n)
                x1 = x0 + r.w / n
                pts_sets.append([(x0, base), ((x0 + x1) / 2, tip), (x1, base)])
        elif direction == "left":
            base = r.right
            tip = r.left + 2
            for i in range(n):
                y0 = r.y + i * (r.h / n)
                y1 = y0 + r.h / n
                pts_sets.append([(base, y0), (tip, (y0 + y1) / 2), (base, y1)])
        elif direction == "right":
            base = r.left
            tip = r.right - 2
            for i in range(n):
                y0 = r.y + i * (r.h / n)
                y1 = y0 + r.h / n
                pts_sets.append([(base, y0), (tip, (y0 + y1) / 2), (base, y1)])
        for pts in pts_sets:
            pygame.draw.polygon(surf, INK, pts)
            pygame.draw.polygon(surf, (40, 40, 40), pts, 1)

    def draw_exit(self, surf):
        if not self.exit_visible:
            return
        ex, ey = self.exit_pos_dyn
        # door shape — drawn identically to fake exits so you can't tell
        w, h = 30, 48
        r = pygame.Rect(int(ex - w / 2), int(ey - h / 2), w, h)
        pygame.draw.rect(surf, EXIT_C, r)
        pygame.draw.rect(surf, INK, r, 2)
        # door knob (same dull ink color on every door, real or fake)
        pygame.draw.circle(surf, INK, (int(ex + 7), int(ey)), 3)

    def draw_fake_exits(self, surf):
        for ex, ey in self.fake_exits:
            w, h = 30, 48
            r = pygame.Rect(int(ex - w / 2), int(ey - h / 2), w, h)
            pygame.draw.rect(surf, EXIT_C, r)
            pygame.draw.rect(surf, INK, r, 2)
            pygame.draw.circle(surf, INK, (int(ex + 7), int(ey)), 3)
        for ex, ey in self.decoy_exits:
            w, h = 30, 48
            r = pygame.Rect(int(ex - w / 2), int(ey - h / 2), w, h)
            pygame.draw.rect(surf, EXIT_C, r)
            pygame.draw.rect(surf, INK, r, 2)
            pygame.draw.circle(surf, INK, (int(ex + 7), int(ey)), 3)

    def exit_rect(self):
        ex, ey = self.exit_pos_dyn
        return pygame.Rect(int(ex - 15), int(ey - 24), 30, 48)

    def fake_exit_rects(self):
        out = []
        for ex, ey in self.fake_exits:
            out.append(pygame.Rect(int(ex - 15), int(ey - 24), 30, 48))
        return out


# ─── Trolls ───────────────────────────────────────────────────────────────────
# Each troll is a small class with update(dt, level, player, particles, narrator, game).
# They register by name in TROLL_REGISTRY so levels can name them as data.

TROLL_REGISTRY = {}

def register(name):
    def deco(cls):
        TROLL_REGISTRY[name] = cls
        return cls
    return deco

class Troll:
    """Base."""
    def update(self, dt, level, player, particles, narrator, game): ...

@register("floor_drop")
class FloorDrop(Troll):
    """The floor tiles between gx1..gx2 at gy disappear after `delay` seconds
    once the player moves. Or immediately if delay=0."""
    def __init__(self, gx1, gx2, gy, delay=0.6):
        self.gx1, self.gx2, self.gy = gx1, gx2, gy
        self.delay = delay * DIFF
        self.t = 0.0
        self.done = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.done: return
        # start countdown once player has moved any amount
        if abs(player.vx) > 1 or abs(player.vy) > 1 or self.t > 0:
            self.t += dt
        if self.t >= self.delay:
            for gx in range(self.gx1, self.gx2 + 1):
                level.remove_tile(gx, self.gy)
            self.done = True

@register("spike_drop")
class SpikeDrop(Troll):
    """When player x crosses trigger_x (in tiles), spawn downward spikes
    in column gx (or columns gx_list) at gy."""
    def __init__(self, trigger_x, gx_list, gy):
        self.tx = trigger_x
        self.gx_list = gx_list if isinstance(gx_list, list) else [gx_list]
        self.gy = gy
        self.done = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.done: return
        if player.x / TILE >= self.tx:
            for gx in self.gx_list:
                level.set_tile(gx, self.gy, "v")
            self.done = True

@register("spike_after")
class SpikeAfter(Troll):
    """Spawn upward spikes BEHIND the player at gy once they pass column tx."""
    def __init__(self, trigger_x, gx_list, gy):
        self.tx = trigger_x
        self.gx_list = gx_list if isinstance(gx_list, list) else [gx_list]
        self.gy = gy
        self.done = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.done: return
        if player.x / TILE >= self.tx:
            for gx in self.gx_list:
                level.set_tile(gx, self.gy, "^")
            self.done = True

@register("spike_rise")
class SpikeRise(Troll):
    """Spikes rise from the floor at a time after spawn."""
    def __init__(self, delay, gx_list, gy):
        self.delay = delay * DIFF
        self.gx_list = gx_list if isinstance(gx_list, list) else [gx_list]
        self.gy = gy
        self.t = 0.0; self.done = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.done: return
        self.t += dt
        if self.t >= self.delay:
            for gx in self.gx_list:
                level.set_tile(gx, self.gy, "^")
            self.done = True

@register("crushing_ceiling")
class CrushingCeiling(Troll):
    """Ceiling tiles drop straight down N tiles after trigger_x crossed."""
    def __init__(self, trigger_x, gx1, gx2, gy_start, fall_tiles, speed=14):
        self.tx = trigger_x
        self.gx1, self.gx2 = gx1, gx2
        self.gy = gy_start
        self.remaining = fall_tiles
        self.speed = speed / max(0.4, DIFF)   # tiles/sec
        self.t = 0.0
        self.armed = False
    def update(self, dt, level, player, particles, narrator, game):
        if not self.armed:
            if player.x / TILE >= self.tx:
                self.armed = True
        if self.armed and self.remaining > 0:
            self.t += dt * self.speed
            while self.t >= 1.0 and self.remaining > 0:
                self.t -= 1.0
                # move tiles down one row
                for gx in range(self.gx1, self.gx2 + 1):
                    level.remove_tile(gx, self.gy)
                    level.set_tile(gx, self.gy + 1, "#")
                    # crush kill if the new tile overlaps the player
                    tile_rect = pygame.Rect(gx * TILE,
                                            (self.gy + 1) * TILE,
                                            TILE, TILE)
                    if tile_rect.colliderect(player.rect):
                        player.kill(particles)
                self.gy += 1
                self.remaining -= 1

@register("wall_slam")
class WallSlam(Troll):
    """Spawns a column of wall tiles that slide in from `side` to gx_target."""
    def __init__(self, trigger_x, side, gx_target, gy1, gy2, speed=20):
        self.tx = trigger_x
        self.side = side  # "left" or "right"
        self.gx = -1 if side == "left" else GRID_W
        self.target = gx_target
        self.gy1, self.gy2 = gy1, gy2
        self.speed = speed / max(0.4, DIFF)
        self.t = 0.0
        self.armed = False
        self.done = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.done: return
        if not self.armed:
            if player.x / TILE >= self.tx:
                self.armed = True
        if not self.armed:
            return
        self.t += dt * self.speed
        while self.t >= 1.0:
            self.t -= 1.0
            old = self.gx
            if self.side == "left":
                if old >= 0:
                    for gy in range(self.gy1, self.gy2 + 1):
                        level.remove_tile(old, gy)
                self.gx += 1
                if self.gx > self.target:
                    self.done = True; return
            else:
                if old < GRID_W:
                    for gy in range(self.gy1, self.gy2 + 1):
                        level.remove_tile(old, gy)
                self.gx -= 1
                if self.gx < self.target:
                    self.done = True; return
            for gy in range(self.gy1, self.gy2 + 1):
                level.set_tile(self.gx, gy, "#")
                # if a wall tile spawns on top of the player, crush them
                tile_rect = pygame.Rect(self.gx * TILE, gy * TILE, TILE, TILE)
                if tile_rect.colliderect(player.rect):
                    player.kill(particles)

@register("moving_exit")
class MovingExit(Troll):
    """The exit slides away from the player horizontally with cap."""
    def __init__(self, speed=120, min_x=2, max_x=None):
        self.speed = speed
        self.min_x = min_x * TILE
        self.max_x = (max_x * TILE) if max_x else (WIDTH - TILE)
    def update(self, dt, level, player, particles, narrator, game):
        ex, ey = level.exit_pos_dyn
        dx = ex - player.x
        # push away from player
        if abs(dx) < 220:
            push = self.speed * dt * (1 if dx > 0 else -1)
            ex = max(self.min_x, min(self.max_x, ex + push))
        level.exit_pos_dyn = (ex, ey)

@register("exit_hop")
class ExitHop(Troll):
    """Exit jumps up when player comes near."""
    def __init__(self, trigger_dist=120, hop_h=160):
        self.td = trigger_dist
        self.hop_h = hop_h
        self.t = 0.0; self.hopping = False; self.armed = True
        self.base_y = None
    def update(self, dt, level, player, particles, narrator, game):
        ex, ey = level.exit_pos_dyn
        if self.base_y is None:
            self.base_y = ey
        if self.armed and abs(ex - player.x) < self.td and abs(ey - player.y) < 200:
            self.hopping = True; self.armed = False
            self.t = 0
        if self.hopping:
            self.t += dt
            # parabolic hop
            phase = min(1.0, self.t * 1.8)
            offset = -math.sin(phase * math.pi) * self.hop_h
            level.exit_pos_dyn = (ex, self.base_y + offset)
            if phase >= 1.0:
                self.hopping = False
                self.armed = True
                level.exit_pos_dyn = (ex, self.base_y)

@register("gravity_flip")
class GravityFlip(Troll):
    """Flips player gravity when crossing trigger_x. Once or repeating."""
    def __init__(self, trigger_x, repeat=False, period=2.0):
        self.tx = trigger_x
        self.repeat = repeat
        self.period = period
        self.t = 0.0
        self.done = False
    def update(self, dt, level, player, particles, narrator, game):
        if not self.repeat:
            if not self.done and player.x / TILE >= self.tx:
                player.gravity_dir = -player.gravity_dir
                narrator.say("up is down.", "top", INK, 1.4)
                self.done = True
        else:
            self.t += dt
            if self.t >= self.period:
                self.t = 0
                player.gravity_dir = -player.gravity_dir

@register("invert_controls")
class InvertControls(Troll):
    """Inverts left/right after trigger_x crossed."""
    def __init__(self, trigger_x, message=None):
        self.tx = trigger_x
        self.done = False
        self.message = message
    def update(self, dt, level, player, particles, narrator, game):
        if self.done: return
        if player.x / TILE >= self.tx:
            player.invert = True
            if self.message:
                narrator.say(self.message, "top", INK, 2.0)
            self.done = True

@register("saw_path")
class SawPath(Troll):
    """A saw blade that travels along a path of (gx,gy) points, looping."""
    def __init__(self, points, speed=140, radius=18):
        self.pts = [(p[0] * TILE + TILE/2, p[1] * TILE + TILE/2) for p in points]
        self.speed = speed / max(0.5, DIFF)
        self.radius = radius
        self.i = 0
        self.x, self.y = self.pts[0]
        self.angle = 0.0
    def update(self, dt, level, player, particles, narrator, game):
        if len(self.pts) < 2:
            return
        nx, ny = self.pts[(self.i + 1) % len(self.pts)]
        dx, dy = nx - self.x, ny - self.y
        dist = math.hypot(dx, dy)
        if dist < 4:
            self.i = (self.i + 1) % len(self.pts)
            return
        step = self.speed * dt
        if step > dist:
            self.x, self.y = nx, ny
            self.i = (self.i + 1) % len(self.pts)
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step
        self.angle += dt * 12
        # collision with player
        pr = player.rect
        if pr.collidepoint(self.x, self.y) or \
           math.hypot(pr.centerx - self.x, pr.centery - self.y) < self.radius:
            player.kill(particles)
    def draw(self, surf):
        cx, cy = int(self.x), int(self.y)
        pygame.draw.circle(surf, (90, 90, 90), (cx, cy), self.radius - 2)
        for i in range(8):
            a = self.angle + i * math.pi / 4
            p1 = (cx + math.cos(a) * (self.radius - 2),
                  cy + math.sin(a) * (self.radius - 2))
            p2 = (cx + math.cos(a) * (self.radius + 5),
                  cy + math.sin(a) * (self.radius + 5))
            pygame.draw.line(surf, INK, p1, p2, 3)
        pygame.draw.circle(surf, INK, (cx, cy), 4)

@register("falling_block")
class FallingBlock(Troll):
    """A large block falls from above when player crosses trigger_x."""
    def __init__(self, trigger_x, gx, gy_start, width=2, speed=900):
        self.tx = trigger_x
        self.gx = gx; self.gy = gy_start
        self.width = width
        self.x = gx * TILE
        self.y = -TILE * 2
        self.speed = speed
        self.target_y = gy_start * TILE
        self.armed = False
        self.dropped = False
        self.landed = False
    def update(self, dt, level, player, particles, narrator, game):
        if not self.armed:
            if player.x / TILE >= self.tx:
                self.armed = True
        if self.armed and not self.landed:
            self.y += self.speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.landed = True
                # place as solid tiles
                for i in range(self.width):
                    level.set_tile(self.gx + i, self.gy, "#")
                dust_puff(particles, self.x + self.width * TILE / 2,
                          self.target_y + TILE, 12)
            else:
                # kill if player overlaps
                br = pygame.Rect(int(self.x), int(self.y),
                                 self.width * TILE, TILE)
                if br.colliderect(player.rect):
                    player.kill(particles)
    def draw(self, surf):
        if self.armed and not self.landed:
            r = pygame.Rect(int(self.x), int(self.y),
                            self.width * TILE, TILE)
            pygame.draw.rect(surf, DARK, r)
            pygame.draw.rect(surf, INK, r, 2)

@register("spring_trap")
class SpringTrap(Troll):
    """A spring that throws player straight up into a hazard."""
    def __init__(self, gx, gy, power=-1300):
        self.gx, self.gy = gx, gy
        self.power = power
        self.x = gx * TILE
        self.y = gy * TILE
        self.cooldown = 0.0
        self.compress = 0.0
    def update(self, dt, level, player, particles, narrator, game):
        r = pygame.Rect(self.x, self.y, TILE, TILE)
        self.cooldown = max(0, self.cooldown - dt)
        self.compress = max(0, self.compress - dt * 4)
        if self.cooldown == 0:
            if r.colliderect(player.rect) and player.vy > 0:
                player.vy = self.power
                self.cooldown = 0.4
                self.compress = 1.0
    def draw(self, surf):
        c = int(8 * self.compress)
        r = pygame.Rect(self.x + 4, self.y + 12 + c, TILE - 8, TILE - 12 - c)
        pygame.draw.rect(surf, (180, 50, 70), r)
        pygame.draw.rect(surf, INK, r, 2)
        # spring lines
        for i in range(3):
            y = r.y + 4 + i * 6
            pygame.draw.line(surf, INK,
                             (r.x + 4, y), (r.x + r.w - 4, y), 2)

@register("disappear_after_step")
class DisappearAfterStep(Troll):
    """Tiles at positions vanish after player steps on them, with delay."""
    def __init__(self, positions, delay=0.3):
        self.positions = positions  # list of (gx, gy)
        self.delay = delay * DIFF
        self.timers = {}  # (gx,gy) -> remaining
        self.dead = set()
    def update(self, dt, level, player, particles, narrator, game):
        # which positions are immediately under player
        feet_gx = int(player.x // TILE)
        feet_gy = int((player.y + 1) // TILE)
        for p in self.positions:
            if p in self.dead: continue
            if p == (feet_gx, feet_gy) and player.on_ground:
                if p not in self.timers:
                    self.timers[p] = self.delay
        for p, t in list(self.timers.items()):
            t -= dt
            if t <= 0:
                level.remove_tile(*p)
                self.dead.add(p)
                del self.timers[p]
            else:
                self.timers[p] = t

@register("invisible_solid")
class InvisibleSolid(Troll):
    """Tiles that exist but are only drawn faintly when player is near."""
    def __init__(self, positions):
        self.positions = positions
        for p in positions: pass  # placed via tile data 'I'
    def update(self, dt, level, player, particles, narrator, game):
        pass

@register("warden_hand")
class WardenHand(Troll):
    """A large hand reaches in from a side and tries to grab the player."""
    def __init__(self, trigger_x, from_side="top", speed=900):
        self.tx = trigger_x
        self.side = from_side
        self.speed = speed
        self.armed = False
        self.t = 0.0
        self.attacking = False
        self.done = False
        self.x = 0; self.y = -200
    def update(self, dt, level, player, particles, narrator, game):
        if not self.armed:
            if player.x / TILE >= self.tx:
                self.armed = True
                self.attacking = True
                if self.side == "top":
                    self.x = player.x
                    self.y = -200
                self.t = 0
        if self.attacking:
            self.t += dt
            if self.side == "top":
                self.y += self.speed * dt
                hand_rect = pygame.Rect(int(self.x - 60), int(self.y - 80), 120, 160)
                if hand_rect.colliderect(player.rect):
                    player.kill(particles)
                if self.y > HEIGHT + 100:
                    self.done = True; self.attacking = False
    def draw(self, surf):
        if not self.attacking: return
        if self.side == "top":
            # arm coming down
            arm_r = pygame.Rect(int(self.x - 30), -200, 60, int(self.y))
            pygame.draw.rect(surf, INK, arm_r)
            # hand (oval) + fingers
            pygame.draw.ellipse(surf, INK,
                                (int(self.x - 60), int(self.y - 40), 120, 80))
            for fi in range(4):
                fx = self.x - 50 + fi * 30
                pygame.draw.rect(surf, INK,
                                 (int(fx) - 6, int(self.y + 30), 12, 50))

@register("screen_tilt")
class ScreenTilt(Troll):
    """Tilts the rendered screen by N degrees. Used by Game.draw."""
    def __init__(self, degrees=8, oscillate=False, period=2.0):
        self.deg = degrees
        self.osc = oscillate
        self.period = period
        self.t = 0.0
    def update(self, dt, level, player, particles, narrator, game):
        self.t += dt
        if self.osc:
            game.screen_tilt = math.sin(self.t * 2 * math.pi / self.period) * self.deg
        else:
            game.screen_tilt = self.deg

@register("camera_shake_constant")
class CameraShakeConstant(Troll):
    def __init__(self, magnitude=4):
        self.mag = magnitude
    def update(self, dt, level, player, particles, narrator, game):
        game.shake = max(game.shake, self.mag / 6.0)

@register("narrate")
class Narrate(Troll):
    """Narrator says something after a trigger (time or x-cross)."""
    def __init__(self, trigger, value, text, position="top", hold=2.4):
        self.trigger = trigger  # "time" or "x"
        self.value = value
        self.text = text
        self.position = position
        self.hold = hold
        self.t = 0.0
        self.done = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.done: return
        if self.trigger == "time":
            self.t += dt
            if self.t >= self.value:
                narrator.say(self.text, self.position, INK, self.hold)
                self.done = True
        elif self.trigger == "x":
            if player.x / TILE >= self.value:
                narrator.say(self.text, self.position, INK, self.hold)
                self.done = True
        elif self.trigger == "death":
            if player.dead:
                narrator.say(self.text, self.position, INK, self.hold)
                self.done = True

@register("fake_floor")
class FakeFloor(Troll):
    """Tiles that LOOK solid but kill on touch (drawn as #, behave as spike)."""
    def __init__(self, positions):
        self.positions = positions
    def update(self, dt, level, player, particles, narrator, game):
        pr = player.rect
        for gx, gy in self.positions:
            r = pygame.Rect(gx * TILE, gy * TILE, TILE, TILE)
            if pr.colliderect(r):
                player.kill(particles)

@register("moving_platform")
class MovingPlatform(Troll):
    """Solid platform that moves along (gx,gy) waypoints. Width in tiles."""
    def __init__(self, points, speed=120, width=2):
        self.points = [(p[0] * TILE, p[1] * TILE) for p in points]
        self.speed = speed
        self.w = width * TILE
        self.h = TILE
        self.i = 0
        self.x, self.y = self.points[0]
        self.prev_x, self.prev_y = self.x, self.y
    def update(self, dt, level, player, particles, narrator, game):
        self.prev_x, self.prev_y = self.x, self.y
        if len(self.points) < 2: return
        nx, ny = self.points[(self.i + 1) % len(self.points)]
        dx, dy = nx - self.x, ny - self.y
        dist = math.hypot(dx, dy)
        if dist < 2:
            self.i = (self.i + 1) % len(self.points)
            return
        step = self.speed * dt
        if step >= dist:
            self.x, self.y = nx, ny
            self.i = (self.i + 1) % len(self.points)
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step
        # crude push: if player overlaps from above, set them on top
        r = pygame.Rect(int(self.x), int(self.y), self.w, self.h)
        pr = player.rect
        if r.colliderect(pr):
            # if player is mostly above the platform
            if pr.bottom - r.top < 18 and player.vy >= 0:
                player.y = r.top
                player.vy = 0
                player.on_ground = True
                # carry
                player.x += (self.x - self.prev_x)
            else:
                # side push
                if pr.centerx < r.centerx:
                    player.x -= (pr.right - r.left)
                else:
                    player.x += (r.right - pr.left)
    def draw(self, surf):
        r = pygame.Rect(int(self.x), int(self.y), self.w, self.h)
        pygame.draw.rect(surf, DARK, r)
        pygame.draw.rect(surf, INK, r, 2)
        # marking line
        pygame.draw.line(surf, GREY,
                         (r.x + 4, r.centery), (r.right - 4, r.centery), 2)

@register("rising_lava")
class RisingLava(Troll):
    """Lava floor rises from the bottom at `rate` tiles/sec, after delay."""
    def __init__(self, rate=0.8, start_gy=GRID_H, delay=0.5):
        self.rate = rate / max(0.4, DIFF)   # faster lava when DIFF<1
        self.gy = float(start_gy)
        self.delay = delay * DIFF
        self.t = 0.0
    def update(self, dt, level, player, particles, narrator, game):
        self.t += dt
        if self.t < self.delay: return
        self.gy -= self.rate * dt
        # kill if player below lava surface
        if player.y > self.gy * TILE:
            player.kill(particles)
    def draw(self, surf):
        top = int(self.gy * TILE)
        if top >= HEIGHT: return
        # wobbly top
        for x in range(0, WIDTH, 12):
            wob = int(math.sin((self.t + x) * 4) * 3)
            pygame.draw.rect(surf, (180, 50, 30),
                             (x, top + wob, 12, HEIGHT - top))
        pygame.draw.line(surf, (240, 120, 60),
                         (0, top), (WIDTH, top), 3)

@register("spike_rain")
class SpikeRain(Troll):
    """Periodic vertical spikes drop from random columns."""
    def __init__(self, interval=0.55, columns=None, after=0.0, count=24):
        self.interval = interval * DIFF
        self.t = -after * DIFF
        self.cols = columns
        self.count = count
        self.dropped = 0
        self.falls = []  # list of (gx, y, vy)
    def update(self, dt, level, player, particles, narrator, game):
        self.t += dt
        if self.t >= 0 and self.dropped < self.count:
            if self.t >= self.interval:
                self.t = 0
                cols = self.cols if self.cols else list(range(2, GRID_W - 2))
                gx = random.choice(cols)
                self.falls.append([gx, -TILE, 0])
                self.dropped += 1
        # update falling spikes
        new_falls = []
        for f in self.falls:
            f[2] += 1800 * dt
            f[1] += f[2] * dt
            spike_rect = pygame.Rect(f[0] * TILE, int(f[1]), TILE, TILE)
            if spike_rect.colliderect(player.rect):
                player.kill(particles)
            if f[1] > HEIGHT + TILE:
                continue
            new_falls.append(f)
        self.falls = new_falls
    def draw(self, surf):
        for gx, y, vy in self.falls:
            r = pygame.Rect(gx * TILE, int(y), TILE, TILE)
            # downward spike polygon
            pts = [(r.x, r.y), (r.right, r.y),
                   (r.centerx, r.bottom)]
            pygame.draw.polygon(surf, INK, pts)

@register("mirror_world")
class MirrorWorld(Troll):
    """Flips the level visual L-R (cosmetic), inverting controls subtly."""
    def __init__(self, on=True):
        self.on = on
    def update(self, dt, level, player, particles, narrator, game):
        game.flip_h = self.on

@register("teleport_loop")
class TeleportLoop(Troll):
    """Teleport player back to spawn when crossing trigger_x N times before
    spawning the real exit somewhere unexpected."""
    def __init__(self, trigger_x, loops_needed, hint=None):
        self.tx = trigger_x
        self.left = loops_needed
        self.hint = hint
        self.cooldown = 0.0
    def update(self, dt, level, player, particles, narrator, game):
        self.cooldown = max(0, self.cooldown - dt)
        if self.left > 0 and self.cooldown == 0:
            if player.x / TILE >= self.tx:
                player.x, player.y = level.spawn
                player.vx = player.vy = 0
                self.left -= 1
                self.cooldown = 0.4
                if self.hint and self.left == 0:
                    narrator.say(self.hint, "top", INK, 3.0)

@register("exit_swap")
class ExitSwap(Troll):
    """Periodically swaps real exit and a fake exit position."""
    def __init__(self, fake_idx=0, period=1.8):
        self.fake_idx = fake_idx
        self.period = period
        self.t = 0.0
    def update(self, dt, level, player, particles, narrator, game):
        self.t += dt
        if self.t >= self.period and level.fake_exits:
            self.t = 0
            i = self.fake_idx % len(level.fake_exits)
            f = level.fake_exits[i]
            level.fake_exits[i] = level.exit_pos_dyn
            level.exit_pos_dyn = f

@register("bg_color")
class BgColor(Troll):
    """Change background color (atmosphere)."""
    def __init__(self, color):
        self.color = tuple(color)
    def update(self, dt, level, player, particles, narrator, game):
        game.bg_override = self.color

@register("hint_text")
class HintText(Troll):
    """Persistent on-screen hint in a corner. Mocking."""
    def __init__(self, text, position=(20, HEIGHT - 50), color=INK):
        self.text = text
        self.pos = position
        self.color = color
    def update(self, dt, level, player, particles, narrator, game):
        game.persistent_hints.append((self.text, self.pos, self.color))


@register("heckle")
class Heckle(Troll):
    """Warden mid-level distraction. Fires when player crosses trigger_x
    (or at level start if trigger_x is None). Picks a random line from
    one of three tone banks; rotates which bank each fire."""
    _rotation_idx = 0
    def __init__(self, trigger_x=None, tone="random",
                 position="top", duration=2.0):
        # tone: "whisper" | "mock" | "threat" | "random"
        self.tx = trigger_x
        self.tone = tone
        self.pos = position
        self.dur = duration
        self.fired = False
        self.delay = 0.0
    def update(self, dt, level, player, particles, narrator, game):
        if self.fired: return
        if self.tx is None:
            self.delay += dt
            if self.delay < 0.4: return
        else:
            if player.x / TILE < self.tx: return
        # pick a bank
        if self.tone == "whisper":
            bank = HECKLE_WHISPER
        elif self.tone == "mock":
            bank = HECKLE_MOCK
        elif self.tone == "threat":
            bank = HECKLE_THREAT
        else:
            # rotating mix
            Heckle._rotation_idx = (Heckle._rotation_idx + 1) % 3
            bank = [HECKLE_WHISPER, HECKLE_MOCK, HECKLE_THREAT][Heckle._rotation_idx]
        line = random.choice(bank)
        narrator.say(line, self.pos, INK, self.dur)
        self.fired = True


@register("ambush_spike")
class AmbushSpike(Troll):
    """A spike that pops up at a grid cell the instant the player is within
    `radius` tiles. No warning, no telegraph — pure last-second."""
    def __init__(self, gx, gy, radius=2, direction="up"):
        self.gx = gx; self.gy = gy
        self.radius = radius
        self.direction = direction
        self.fired = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.fired: return
        pgx = player.x / TILE
        pgy = player.y / TILE
        if (abs(pgx - self.gx) <= self.radius
                and abs(pgy - self.gy) <= self.radius):
            ch = {"up": "^", "down": "v",
                  "left": "<", "right": ">"}[self.direction]
            level.set_tile(self.gx, self.gy, ch)
            self.fired = True


@register("ambush_row")
class AmbushRow(Troll):
    """A row of spikes pops up across columns gx1..gx2 at row gy as soon
    as the player crosses trigger_x. Used to punish forward momentum."""
    def __init__(self, trigger_x, gx1, gx2, gy, direction="up"):
        self.tx = trigger_x
        self.gx1 = gx1; self.gx2 = gx2; self.gy = gy
        self.direction = direction
        self.fired = False
    def update(self, dt, level, player, particles, narrator, game):
        if self.fired: return
        if player.x / TILE >= self.tx:
            ch = {"up": "^", "down": "v",
                  "left": "<", "right": ">"}[self.direction]
            for gx in range(self.gx1, self.gx2 + 1):
                level.set_tile(self.gx if False else gx, self.gy, ch)
            self.fired = True


@register("ambush_floor_drop")
class AmbushFloorDrop(Troll):
    """The tile directly under the player drops out the instant they step
    on it (or get within `lookahead` tiles forward). Last-second pit."""
    def __init__(self, gx1, gx2, gy, lookahead=0):
        self.gx1 = gx1; self.gx2 = gx2; self.gy = gy
        self.lookahead = lookahead
        self.dropped = set()
    def update(self, dt, level, player, particles, narrator, game):
        pgx = int(player.x / TILE) + self.lookahead
        if self.gx1 <= pgx <= self.gx2 and pgx not in self.dropped:
            # check player is roughly above row self.gy
            if abs(player.y / TILE - (self.gy - 1)) < 1.5:
                level.remove_tile(pgx, self.gy)
                self.dropped.add(pgx)


@register("ambush_saw")
class AmbushSaw(Troll):
    """A saw blade materializes at (gx,gy) the moment player is within
    `arm_radius`, then patrols a short path. Snappy, mean."""
    def __init__(self, gx, gy, patrol_dx=4, arm_radius=4, speed=260):
        self.spawn_pos = (gx * TILE + TILE / 2, gy * TILE + TILE / 2)
        self.gx = gx; self.gy = gy
        self.patrol_dx = patrol_dx
        self.arm_radius = arm_radius
        self.speed = speed
        self.armed = False
        self.x, self.y = self.spawn_pos
        self.dir = 1
        self.t = 0
    def update(self, dt, level, player, particles, narrator, game):
        self.t += dt
        if not self.armed:
            pgx = player.x / TILE
            pgy = player.y / TILE
            if (abs(pgx - self.gx) <= self.arm_radius
                    and abs(pgy - self.gy) <= self.arm_radius):
                self.armed = True
        if self.armed:
            self.x += self.dir * self.speed * dt
            left = self.spawn_pos[0] - self.patrol_dx * TILE / 2
            right = self.spawn_pos[0] + self.patrol_dx * TILE / 2
            if self.x > right: self.x = right; self.dir = -1
            if self.x < left: self.x = left; self.dir = 1
            # hit-check
            sr = pygame.Rect(int(self.x - 16), int(self.y - 16), 32, 32)
            if sr.colliderect(player.rect):
                player.kill(particles)
    def draw(self, surf):
        if not self.armed: return
        # saw blade
        ang = self.t * 16
        cx, cy = int(self.x), int(self.y)
        pygame.draw.circle(surf, (90, 90, 90), (cx, cy), 18)
        for i in range(8):
            a = ang + i * math.pi / 4
            p1 = (cx + math.cos(a) * 16, cy + math.sin(a) * 16)
            p2 = (cx + math.cos(a) * 24, cy + math.sin(a) * 24)
            pygame.draw.line(surf, INK, p1, p2, 3)
        pygame.draw.circle(surf, INK, (cx, cy), 4)


@register("ambush_ceiling")
class AmbushCeiling(Troll):
    """Ceiling spikes appear above the player the moment they cross
    trigger_x, then a crushing ceiling drops moments later."""
    def __init__(self, trigger_x, gx1, gx2, gy, fall_speed=12, delay=0.5):
        self.tx = trigger_x
        self.gx1 = gx1; self.gx2 = gx2; self.gy_init = gy
        self.gy = gy
        self.fall_speed = fall_speed / max(0.4, DIFF)
        self.delay = delay
        self.armed = False
        self.spawned = False
        self.t = 0
    def update(self, dt, level, player, particles, narrator, game):
        if not self.armed:
            if player.x / TILE >= self.tx:
                self.armed = True
                # spawn ceiling spikes pointing down
                for gx in range(self.gx1, self.gx2 + 1):
                    level.set_tile(gx, self.gy, "v")
                self.spawned = True
        if self.armed and self.spawned:
            self.t += dt
            if self.t > self.delay:
                # drop the ceiling
                inc = dt * self.fall_speed
                self.t -= 0
                # drop one row at a time when accumulated enough
                self._accum = getattr(self, "_accum", 0.0) + inc
                while self._accum >= 1.0 and self.gy < GRID_H - 1:
                    self._accum -= 1.0
                    for gx in range(self.gx1, self.gx2 + 1):
                        level.remove_tile(gx, self.gy)
                        level.set_tile(gx, self.gy + 1, "v")
                        tile_rect = pygame.Rect(gx * TILE,
                                                (self.gy + 1) * TILE,
                                                TILE, TILE)
                        if tile_rect.colliderect(player.rect):
                            player.kill(particles)
                    self.gy += 1


@register("snap_kill")
class SnapKill(Troll):
    """Kill the player instantly if they linger in a zone too long.
    Forces forward motion without visible warning."""
    def __init__(self, gx1, gy1, gx2, gy2, dwell=1.2):
        self.r = pygame.Rect(gx1 * TILE, gy1 * TILE,
                             (gx2 - gx1 + 1) * TILE, (gy2 - gy1 + 1) * TILE)
        self.dwell = dwell
        self.t = 0
    def update(self, dt, level, player, particles, narrator, game):
        if self.r.colliderect(player.rect):
            self.t += dt
            if self.t >= self.dwell:
                player.kill(particles)
        else:
            self.t = max(0, self.t - dt * 2)


# ─── Game ─────────────────────────────────────────────────────────────────────
class Game:
    """Main state machine and loop."""
    STATE_TITLE = "title"
    STATE_INTRO = "intro"        # chapter intro
    STATE_PLAY = "play"
    STATE_DEATH = "death"
    STATE_OUTRO = "outro"
    STATE_END = "end"
    STATE_SELECT = "select"

    def __init__(self):
        self.save = load_save()
        self.deaths = self.save.get("deaths", 0)
        self.unlocked = self.save.get("highest_unlocked", 0)
        self.completed = self.save.get("completed", False)
        self.idx = 0
        self.level: Optional[Level] = None
        self.player: Optional[Marionette] = None
        self.particles: List[Particle] = []
        self.narrator = Narrator()
        self.state = Game.STATE_TITLE
        self.state_t = 0.0
        self.shake = 0.0
        self.screen_tilt = 0.0
        self.flip_h = False
        self.bg_override = None
        self.persistent_hints: List[Tuple[str, Tuple[int,int], Tuple[int,int,int]]] = []
        self.last_chapter_announced = -1
        self.intro_text_index = 0
        self.title_phase = 0.0
        self.select_cursor = 0
        self.blood_pools: List[Tuple[float, float]] = []  # persistent death marks
        self.hit_stop = 0.0                               # freeze-frame on death

    # ---- Lifecycle ----
    def save_progress(self):
        self.save["deaths"] = self.deaths
        self.save["highest_unlocked"] = max(self.unlocked, self.idx)
        self.save["completed"] = self.completed
        write_save(self.save)

    def load_level(self, i):
        self.idx = i
        data = LEVELS[i]
        self.level = Level(data)
        self.player = Marionette(*self.level.spawn)
        self.particles.clear()
        self.shake = 0.0
        self.screen_tilt = 0.0
        self.flip_h = False
        self.bg_override = None
        self.persistent_hints = []
        self.blood_pools = []
        self.hit_stop = 0.0
        # intro text
        intro = data.get("intro")
        if intro:
            self.narrator.clear()
            self.narrator.say(intro, "top", INK, 2.6)
        # chapter announcement
        ch = data.get("chapter", 1)
        if ch != self.last_chapter_announced and data.get("chapter_intro"):
            self.state = Game.STATE_INTRO
            self.state_t = 0.0
            self.last_chapter_announced = ch
            self.chapter_intro_lines = data.get("chapter_intro", [])
            self.intro_text_index = 0
        else:
            self.state = Game.STATE_PLAY

    def next_level(self):
        # mark current as cleared
        self.unlocked = max(self.unlocked, self.idx + 1)
        self.save_progress()
        if self.idx + 1 >= len(LEVELS):
            self.state = Game.STATE_END
            self.state_t = 0.0
            self.completed = True
            self.save_progress()
        else:
            self.load_level(self.idx + 1)

    def restart_level(self):
        self.load_level(self.idx)

    def die(self):
        # Called by external death triggers (hazards, fake exits).
        # If player isn't dead yet, kill them. Then in all cases promote
        # the game to DEATH state — so deaths that happen inside
        # player.update() (off-screen bounds, squeeze-by-tile, etc.) still
        # end the round instead of leaving the game frozen.
        if not self.player.dead:
            self.player.kill(self.particles)
        if self.state == Game.STATE_DEATH:
            return  # already transitioning
        self.deaths += 1
        self.shake = 1.4
        self.hit_stop = 0.09     # freeze ~90ms on death
        self.blood_pools.append((self.player.x, self.player.y))
        # only keep last ~6 pools to not visually clutter
        if len(self.blood_pools) > 8:
            self.blood_pools = self.blood_pools[-8:]
        self.state = Game.STATE_DEATH
        self.state_t = 0.0
        # mocking death lines
        if random.random() < 0.30:
            lines = DEATH_QUIPS.get(self.level.chapter, DEATH_QUIPS[1])
            self.narrator.say(random.choice(lines),
                              "bottom", INK, 1.6)

    # ---- Loop ----
    def run(self):
        while True:
            dt = CLOCK.tick(FPS) / 1000.0
            dt = min(dt, 1.0 / 30)  # clamp big stalls
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.save_progress(); pygame.quit(); sys.exit(0)
            # ── gamepad hot-plug ──
            if e.type == pygame.JOYDEVICEADDED:
                PAD._refresh()
            elif e.type == pygame.JOYDEVICEREMOVED:
                PAD._refresh()
            # ── gamepad button presses (edge-triggered) ──
            if e.type == pygame.JOYBUTTONDOWN:
                btn = e.button
                # Universal: BACK = quit
                if btn == PAD_BACK:
                    self.save_progress(); pygame.quit(); sys.exit(0)
                if self.state == Game.STATE_TITLE:
                    if btn in (PAD_A, PAD_START):
                        self.load_level(0)
                    elif btn == PAD_Y and self.unlocked > 0:
                        self.state = Game.STATE_SELECT
                        self.select_cursor = self.unlocked
                elif self.state == Game.STATE_INTRO:
                    if btn in (PAD_A, PAD_START, PAD_X):
                        self.intro_text_index += 1
                        if self.intro_text_index >= len(self.chapter_intro_lines):
                            self.state = Game.STATE_PLAY
                            self.narrator.clear()
                            intro = LEVELS[self.idx].get("intro")
                            if intro:
                                self.narrator.say(intro, "top", INK, 2.6)
                elif self.state == Game.STATE_PLAY:
                    if btn in (PAD_B, PAD_X):
                        self.restart_level()
                    elif btn == PAD_START:
                        self.narrator.skip()
                    elif btn == PAD_Y and self.unlocked > 0:
                        self.state = Game.STATE_SELECT
                        self.select_cursor = self.idx
                elif self.state == Game.STATE_DEATH:
                    if btn in (PAD_A, PAD_B, PAD_X, PAD_START):
                        self.restart_level()
                elif self.state == Game.STATE_END:
                    if btn in (PAD_A, PAD_START):
                        self.state = Game.STATE_TITLE
                elif self.state == Game.STATE_SELECT:
                    if btn == PAD_B:
                        self.state = Game.STATE_TITLE
                    elif btn == PAD_LB:
                        self.select_cursor = max(0, self.select_cursor - 1)
                    elif btn == PAD_RB:
                        self.select_cursor = min(self.unlocked, self.select_cursor + 1)
                    elif btn in (PAD_A, PAD_START):
                        self.load_level(self.select_cursor)
            # ── gamepad d-pad / stick for menu navigation ──
            if e.type == pygame.JOYHATMOTION and self.state == Game.STATE_SELECT:
                hx, hy = e.value
                if hx < 0:
                    self.select_cursor = max(0, self.select_cursor - 1)
                elif hx > 0:
                    self.select_cursor = min(self.unlocked, self.select_cursor + 1)
                if hy > 0:
                    self.select_cursor = max(0, self.select_cursor - 12)
                elif hy < 0:
                    self.select_cursor = min(self.unlocked, self.select_cursor + 12)
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.save_progress(); pygame.quit(); sys.exit(0)
                if e.key == pygame.K_F11 or e.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                if self.state == Game.STATE_TITLE:
                    if e.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.load_level(0)
                    elif e.key == pygame.K_F2 and self.unlocked > 0:
                        self.state = Game.STATE_SELECT
                        self.select_cursor = self.unlocked
                elif self.state == Game.STATE_INTRO:
                    if e.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_F1):
                        self.intro_text_index += 1
                        if self.intro_text_index >= len(self.chapter_intro_lines):
                            self.state = Game.STATE_PLAY
                            self.narrator.clear()
                            intro = LEVELS[self.idx].get("intro")
                            if intro:
                                self.narrator.say(intro, "top", INK, 2.6)
                elif self.state == Game.STATE_PLAY:
                    if e.key == pygame.K_r:
                        self.restart_level()
                    if e.key == pygame.K_F1:
                        self.narrator.skip()
                    if e.key == pygame.K_F2 and self.unlocked > 0:
                        self.state = Game.STATE_SELECT
                        self.select_cursor = self.idx
                elif self.state == Game.STATE_DEATH:
                    if e.key in (pygame.K_r, pygame.K_SPACE, pygame.K_RETURN):
                        self.restart_level()
                elif self.state == Game.STATE_END:
                    if e.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.state = Game.STATE_TITLE
                elif self.state == Game.STATE_SELECT:
                    if e.key == pygame.K_ESCAPE:
                        self.state = Game.STATE_TITLE
                    elif e.key in (pygame.K_LEFT, pygame.K_a):
                        self.select_cursor = max(0, self.select_cursor - 1)
                    elif e.key in (pygame.K_RIGHT, pygame.K_d):
                        self.select_cursor = min(self.unlocked, self.select_cursor + 1)
                    elif e.key in (pygame.K_UP, pygame.K_w):
                        self.select_cursor = max(0, self.select_cursor - 12)
                    elif e.key in (pygame.K_DOWN, pygame.K_s):
                        self.select_cursor = min(self.unlocked, self.select_cursor + 12)
                    elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.load_level(self.select_cursor)

    # ---- Update ----
    def update(self, dt):
        self.persistent_hints = []
        self.shake = max(0, self.shake - dt * 4)
        self.narrator.update(dt)
        self.title_phase += dt
        self.state_t += dt

        if self.state == Game.STATE_TITLE:
            return

        if self.state == Game.STATE_INTRO:
            return

        if self.state == Game.STATE_SELECT:
            return

        if self.state == Game.STATE_END:
            return

        # Hit-stop: freeze gameplay updates briefly after death
        if self.hit_stop > 0:
            self.hit_stop -= dt
            if self.state == Game.STATE_PLAY or self.state == Game.STATE_DEATH:
                return

        # update particles always (so death debris flies)
        new_particles = []
        for p in self.particles:
            p.update(dt)
            if p.alive(): new_particles.append(p)
        self.particles = new_particles

        if self.state == Game.STATE_DEATH:
            self.player.death_t += dt
            if self.state_t > 0.65:
                self.restart_level()
            return

        if self.state == Game.STATE_PLAY:
            self.level.update(dt, self.player, self.particles, self.narrator, self)
            self.player.update(dt, self.level, self.particles, self.narrator)

            # Player may have died during update (off-screen bounds, squeeze,
            # rising_lava etc.). Make sure the game promotes to DEATH state.
            if self.player.dead and self.state == Game.STATE_PLAY:
                self.die()
                return

            # check hazards
            if not self.player.dead and self.level.hazard_hit(self.player.rect):
                self.die()
            # check fake exits
            if not self.player.dead:
                pr = self.player.rect
                for fr in self.level.fake_exit_rects():
                    if pr.colliderect(fr):
                        # turn into spikes visually before dying
                        self.die()
                        break
            # check real exit
            if not self.player.dead:
                if self.player.rect.colliderect(self.level.exit_rect()):
                    outro = LEVELS[self.idx].get("outro")
                    if outro:
                        self.narrator.say(outro, "top", INK, 1.6)
                    # advance after a small beat
                    self.state = Game.STATE_OUTRO
                    self.state_t = 0.0

        if self.state == Game.STATE_OUTRO:
            if self.state_t > 0.6 and not self.narrator.busy():
                self.next_level()

    # ---- Draw ----
    def draw(self):
        if self.state == Game.STATE_TITLE:
            self._draw_title(); return
        if self.state == Game.STATE_INTRO:
            self._draw_chapter_intro(); return
        if self.state == Game.STATE_END:
            self._draw_end(); return
        if self.state == Game.STATE_SELECT:
            self._draw_select(); return

        # draw to a buffer (in case of tilt/flip)
        buf = SCREEN if (self.screen_tilt == 0 and not self.flip_h) \
              else pygame.Surface((WIDTH, HEIGHT))

        bg = self.bg_override or self.level.bg
        buf.fill(bg)

        # cached darkening overlay (sky → floor)
        buf.blit(FLOOR_SHADE, (0, 0))

        # subtle grid/dust pattern
        self._draw_bg_pattern(buf)

        # persistent blood pools from previous deaths
        for (bx, by) in self.blood_pools:
            pygame.draw.ellipse(buf, (140, 22, 22),
                                (int(bx - 18), int(by - 5), 36, 10))
            pygame.draw.ellipse(buf, (90, 15, 15),
                                (int(bx - 14), int(by - 3), 28, 6))

        # tiles
        self.level.draw_tiles(buf)
        # exit
        self.level.draw_fake_exits(buf)
        self.level.draw_exit(buf)

        # special drawables on trolls (saws, hands, falling blocks, lava, etc.)
        for tr in self.level.trolls:
            if hasattr(tr, "draw"):
                tr.draw(buf)

        # player
        self.player.draw(buf)

        # particles
        for p in self.particles:
            p.draw(buf)

        # death red flash overlay
        if self.state == Game.STATE_DEATH and self.state_t < 0.18:
            flash_a = int(120 * (1 - self.state_t / 0.18))
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((180, 30, 30, flash_a))
            buf.blit(flash, (0, 0))

        # vignette + grain (atmospheric overlay)
        buf.blit(GRAIN, (0, 0))
        buf.blit(VIGNETTE, (0, 0))

        # HUD
        self._draw_hud(buf)

        # narrator overlay
        self.narrator.draw(buf)

        # transfer with optional tilt / mirror / shake
        if buf is not SCREEN:
            surf = buf
            if self.flip_h:
                surf = pygame.transform.flip(surf, True, False)
            if self.screen_tilt != 0:
                surf = pygame.transform.rotate(surf, self.screen_tilt)
            r = surf.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            sx, sy = self._shake_offset()
            SCREEN.fill(INK)
            SCREEN.blit(surf, (r.x + sx, r.y + sy))
        else:
            sx, sy = self._shake_offset()
            if sx or sy:
                tmp = SCREEN.copy()
                SCREEN.fill(self.bg_override or self.level.bg)
                SCREEN.blit(tmp, (sx, sy))

    def _shake_offset(self):
        if self.shake <= 0: return (0, 0)
        m = self.shake * 14
        return (random.randint(-int(m), int(m)),
                random.randint(-int(m), int(m)))

    def _draw_bg_pattern(self, surf):
        # faint vertical lines (the strings of the marionette stage)
        for x in range(0, WIDTH, 40):
            pygame.draw.line(surf, (215, 213, 207), (x, 0), (x, HEIGHT), 1)
        # horizon line
        pygame.draw.line(surf, (210, 208, 200), (0, HEIGHT - 80), (WIDTH, HEIGHT - 80), 1)

    def _draw_hud(self, surf):
        # level number top-left
        ch_label = f"act {self.level.chapter}  ·  {self.idx + 1:02d} / {len(LEVELS)}"
        s = F_SMALL.render(ch_label, True, INK)
        surf.blit(s, (20, 14))
        # death counter top-right
        d = F_SMALL.render(f"deaths: {self.deaths}", True, INK)
        surf.blit(d, (WIDTH - d.get_width() - 20, 14))
        # level name center top
        if self.level.name:
            n = F_TINY.render(self.level.name, True, GREY)
            surf.blit(n, (WIDTH // 2 - n.get_width() // 2, 18))
        # persistent hints
        for txt, pos, col in self.persistent_hints:
            s = F_SMALL.render(txt, True, col)
            surf.blit(s, pos)
        # controls hint on first level
        if self.idx == 0:
            hint = "← →  /  A D  ·  ↑ / W / SPACE  ·  R restart"
            s = F_SMALL.render(hint, True, GREY)
            surf.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT - 36))

    # ---- Title ----
    def _draw_title(self):
        SCREEN.fill(PAPER)
        # vertical strings
        for x in range(120, WIDTH, 160):
            pygame.draw.line(SCREEN, (210, 208, 200), (x, 0), (x, HEIGHT - 100), 1)
        # title
        t = F_TITLE.render("MARIONETTE", True, INK)
        SCREEN.blit(t, (WIDTH // 2 - t.get_width() // 2, 140))
        sub = F_MID.render("a play in six acts", True, GREY)
        SCREEN.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 240))

        # swaying puppet
        cx, cy = WIDTH // 2, 430
        sway = math.sin(self.title_phase * 1.4) * 14
        # strings
        for off in (-12, 0, 12):
            pygame.draw.line(SCREEN, (200, 198, 190),
                             (cx + off + sway * 0.4, 0), (cx + off, cy - 45), 1)
        # body
        pygame.draw.circle(SCREEN, INK, (cx, cy - 45), 12)
        pygame.draw.line(SCREEN, INK, (cx, cy - 33), (cx, cy + 10), 6)
        pygame.draw.line(SCREEN, INK, (cx, cy - 26),
                         (cx - 16, cy - 10 + math.sin(self.title_phase * 2) * 3), 5)
        pygame.draw.line(SCREEN, INK, (cx, cy - 26),
                         (cx + 16, cy - 10 - math.sin(self.title_phase * 2) * 3), 5)
        pygame.draw.line(SCREEN, INK, (cx, cy + 10),
                         (cx - 10, cy + 35 + math.cos(self.title_phase * 2) * 3), 5)
        pygame.draw.line(SCREEN, INK, (cx, cy + 10),
                         (cx + 10, cy + 35 - math.cos(self.title_phase * 2) * 3), 5)

        # prompts
        prompt = F_MID.render("press space to begin", True, INK)
        if int(self.title_phase * 2) % 2 == 0:
            SCREEN.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, HEIGHT - 130))
        if self.unlocked > 0:
            s = F_SMALL.render(
                f"F2: select level   ·   progress: {self.unlocked}/{len(LEVELS)}   ·   deaths: {self.deaths}",
                True, GREY)
            SCREEN.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT - 80))
        # credit line
        c = F_TINY.render(
            "the Warden is watching.", True, GREY)
        SCREEN.blit(c, (WIDTH // 2 - c.get_width() // 2, HEIGHT - 40))

    # ---- Chapter intro ----
    def _draw_chapter_intro(self):
        SCREEN.fill(INK)
        ch = self.level.chapter
        title = CHAPTER_TITLES[ch]
        t = F_BIG.render(title, True, PAPER)
        SCREEN.blit(t, (WIDTH // 2 - t.get_width() // 2, 220))
        sub = F_MID.render(f"act {ch}", True, GREY)
        SCREEN.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 170))
        # lines so far
        if self.intro_text_index < len(self.chapter_intro_lines):
            line = self.chapter_intro_lines[self.intro_text_index]
            shown = min(len(line),
                        int((self.state_t * 38)))
            s = F_MID.render(line[:shown], True, PAPER)
            SCREEN.blit(s, (WIDTH // 2 - s.get_width() // 2, 360))
        prompt = F_SMALL.render("space to continue", True, GREY)
        if int(self.state_t * 2) % 2 == 0:
            SCREEN.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, HEIGHT - 80))

    # ---- End ----
    def _draw_end(self):
        SCREEN.fill(INK)
        t = F_TITLE.render("YOU ARE THE WARDEN NOW.", True, PAPER)
        SCREEN.blit(t, (WIDTH // 2 - t.get_width() // 2, 250))
        s = F_MID.render(f"deaths inflicted on you: {self.deaths}", True, GREY)
        SCREEN.blit(s, (WIDTH // 2 - s.get_width() // 2, 380))
        s2 = F_SMALL.render("press space", True, GREY)
        if int(self.state_t * 2) % 2 == 0:
            SCREEN.blit(s2, (WIDTH // 2 - s2.get_width() // 2, HEIGHT - 100))

    # ---- Level select ----
    def _draw_select(self):
        SCREEN.fill(PAPER)
        title = F_BIG.render("select level", True, INK)
        SCREEN.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
        # grid 12 cols x 6 rows
        cols = 12
        cell = 76
        gw = cols * cell
        gx0 = WIDTH // 2 - gw // 2
        gy0 = 150
        n = len(LEVELS)
        for i in range(n):
            cx = gx0 + (i % cols) * cell
            cy = gy0 + (i // cols) * cell
            r = pygame.Rect(cx + 4, cy + 4, cell - 8, cell - 8)
            unlocked = i <= self.unlocked
            color = DARK if unlocked else (190, 188, 180)
            pygame.draw.rect(SCREEN, color, r)
            if i == self.select_cursor:
                pygame.draw.rect(SCREEN, ACCENT, r, 3)
            else:
                pygame.draw.rect(SCREEN, INK, r, 1)
            num = F_SMALL.render(f"{i + 1:02d}", True,
                                 PAPER if unlocked else GREY)
            SCREEN.blit(num, (r.centerx - num.get_width() // 2,
                              r.centery - num.get_height() // 2))
        hint = F_SMALL.render("arrows / WASD to move, enter to play, esc to back", True, GREY)
        SCREEN.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 60))


# ─── Chapter titles, narrator banks, story ───────────────────────────────────
CHAPTER_TITLES = {
    1: "AWAKENING",
    2: "AMUSEMENT",
    3: "BOREDOM",
    4: "CRUELTY",
    5: "RECOGNITION",
    6: "BECOMING",
}

DEATH_QUIPS = {
    1: [
        "oh.",
        "try again.",
        "i'll wait.",
        "hm.",
    ],
    2: [
        "did you see that coming?",
        "i did.",
        "amusing.",
        "again. faster.",
        "you bleed in such a small way.",
    ],
    3: [
        "i'm bored. you're not helping.",
        "this used to be fun.",
        "another one.",
        "they all break.",
        "you are very predictable.",
    ],
    4: [
        "good.",
        "more.",
        "i want to see it again.",
        "press R like a good little doll.",
        "you do this to yourself.",
        "smaller. smaller.",
    ],
    5: [
        "you should know me by now.",
        "i was you, once.",
        "you don't remember, do you.",
        "you will.",
    ],
    6: [
        "almost.",
        "one more.",
        "soon.",
    ],
    7: [
        "i thought we were past this.",
        "i'm running out of patience.",
        "you keep wasting my time.",
        "stop. think. you can't.",
        "this isn't a learning experience.",
        "the room is laughing at you.",
    ],
    8: [
        "you understand now, don't you.",
        "i used to scream at this part.",
        "we're the same. say it.",
        "the door isn't real either.",
        "i'm sorry.",
        "...",
    ],
}

# ── In-level heckle lines (warden interrupts mid-play to distract).
# Three tones. Picked randomly when a level fires a `heckle` troll.
HECKLE_WHISPER = [
    "behind you.",
    "the room is wrong.",
    "you missed it.",
    "i see you.",
    "blink.",
    "look up.",
    "they're watching.",
    "you're slower today.",
    "your hand is shaking.",
    "wait — was that always there?",
    "the floor doesn't trust you.",
    "shhh.",
    "your strings are fraying.",
]

HECKLE_MOCK = [
    "really? that's your plan?",
    "ha.",
    "oh wonderful.",
    "stunning footwork.",
    "what a brave little doll.",
    "you're trying. that's enough.",
    "do you NEED a map?",
    "the slow way, then.",
    "i'd help but i'm enjoying this.",
    "embarrassing.",
    "is that a strategy?",
    "tell me when you give up.",
    "your hands are clumsy.",
]

HECKLE_THREAT = [
    "i'm losing patience.",
    "the room is closing.",
    "don't make me come down there.",
    "i can end you faster than this.",
    "you don't get to pause.",
    "i'm tired of carrying you.",
    "the next mistake costs more.",
    "stop hesitating.",
    "i decide when this ends.",
    "you don't deserve careful.",
    "i remember every death.",
    "you owe me a clean run.",
]

# the chapter intro text appears on the first level of each chapter
CHAPTER_INTROS = {
    1: [
        "a white room. you wake in it.",
        "you have no name. you have strings.",
        "i am the Warden. i made this place for you.",
        "walk."
    ],
    2: [
        "did you enjoy that? i did.",
        "let's play a real game.",
    ],
    3: [
        "you've broken so many times now.",
        "i need something new.",
        "i hope you don't mind."
    ],
    4: [
        "i don't want you to leave.",
        "i want you to suffer correctly."
    ],
    5: [
        "have you wondered who i am?",
        "i'll tell you a story.",
        "once there was a little doll like you.",
        "they reached the end."
    ],
    6: [
        "you're almost done.",
        "you should know what happens next.",
        "i did, when it was my turn."
    ],
    7: [
        "i lied. you weren't almost done.",
        "i needed you to believe it.",
        "now the room knows your shape.",
        "now we begin properly."
    ],
    8: [
        "the strings aren't holding you up.",
        "they never were.",
        "you are doing this to yourself.",
        "let's finish."
    ],
}



# ─── LEVELS ───────────────────────────────────────────────────────────────────
# Layouts are 32 wide. 18 tall (top-padded automatically).
# Tile chars: . empty  # solid  = lighter solid  ^ spike-up  v spike-down
#             < spike-left  > spike-right  P spawn  E exit  X fake exit
#             ? decoy exit  D disappear platform  I invisible platform
#             ~ saw blade  L lava

def _L(**kw):
    """Helper: produce a level dict with sane defaults."""
    kw.setdefault("tiles", [])
    kw.setdefault("trolls", [])
    return kw

LEVELS = [
    # ════════════════════════════════════════════════════════════════════
    # ACT 1: AWAKENING (12)
    # ════════════════════════════════════════════════════════════════════

    # 01 — purely a tutorial
    _L(
        name="01 — first step",
        chapter=1,
        chapter_intro=CHAPTER_INTROS[1],
        intro="walk.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "....P.......................E...",
            "================================",
            "################################",
            "################################",
        ],
    ),

    # 02
    _L(
        name="02 — good",
        chapter=1,
        intro="good.",
        outro="see?",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
    ),

    # 03 — first jump
    _L(
        name="03 — over",
        chapter=1,
        intro="jump.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "========......===================",
            "############..##################",
            "############..##################",
        ],
    ),

    # 04 — bigger jump
    _L(
        name="04 — again",
        chapter=1,
        intro="again.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "======.....====.....============",
            "######.....####.....############",
            "######.....####.....############",
        ],
    ),

    # 05 — the floor leaves
    _L(
        name="05 — oh.",
        chapter=1,
        intro="don't stop.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("floor_drop", 2, 6, 15, 0.5),
            ("floor_drop", 2, 6, 16, 0.5),
            ("floor_drop", 2, 6, 17, 0.5),
            ("narrate", "death", 0, "i did warn you.", "top", 1.6),
        ],
    ),

    # 06 — spike rises
    _L(
        name="06 — mind your step",
        chapter=1,
        intro="mind your step.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_rise", 0.9, [14, 15], 14),
            ("spike_rise", 1.6, [18, 19], 14),
        ],
    ),

    # 07 — side spike
    _L(
        name="07 — walls",
        chapter=1,
        intro="watch the walls.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..............>.................",
            "..............>.................",
            "...........====.................",
            "...........####.................",
            "..P........####.............E...",
            "================================",
            "################################",
            "################################",
        ],
    ),

    # 08 — spike from above
    _L(
        name="08 — from above",
        chapter=1,
        intro="and the ceiling.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_drop", 10, [14, 15, 16], 13),
        ],
    ),

    # 09 — moving exit
    _L(
        name="09 — slippery",
        chapter=1,
        intro="don't be slow.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("moving_exit", 60, 25, 30),
        ],
    ),

    # 10 — moving platform
    _L(
        name="10 — passage",
        chapter=1,
        intro="trust the platform.",
        outro="should you?",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..............................E.",
            "..........................######",
            "..........................######",
            "..P.............................",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("moving_platform", [(8, 13), (22, 11)], 100, 3),
        ],
    ),

    # 11 — disappear-after-step
    _L(
        name="11 — light steps",
        chapter=1,
        intro="lightly, lightly.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.DDDDDDDDDDDDDDDDDDDDDDDDE...",
            "...^^^^^^^^^^^^^^^^^^^^^^^^^####",
            "###############################.",
            "###############################.",
        ],
        trolls=[
            ("disappear_after_step",
             [(x, 14) for x in range(4, 28)], 0.25),
        ],
    ),

    # 12 — act 1 finale: combine
    _L(
        name="12 — act one ends",
        chapter=1,
        intro="end of the warm-up.",
        outro="that was the easy half. you understand that now.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "...........================.....",
            "...........################.....",
            "...........################.....",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_drop", 6, [12, 13, 14], 13),
            ("spike_after", 18, [10, 11, 12], 14),
            ("moving_exit", 80, 25, 30),
        ],
    ),

    # ════════════════════════════════════════════════════════════════════
    # ACT 2: AMUSEMENT (12)
    # ════════════════════════════════════════════════════════════════════

    # 13 — crushing ceiling
    _L(
        name="13 — pressed",
        chapter=2,
        chapter_intro=CHAPTER_INTROS[2],
        intro="don't dawdle.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("crushing_ceiling", 6, 0, 31, 3, 9, 6),
        ],
    ),

    # 14 — saw on a line
    _L(
        name="14 — circling",
        chapter=2,
        intro="round and round.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("saw_path", [(8, 14), (22, 14)], 240, 18),
            ("falling_block", 10, 12, 14, 2, 1100),
            ("falling_block", 18, 16, 14, 2, 1300),
            ("spike_drop", 14, [14], 13),
        ],
    ),

    # 15 — falling block
    _L(
        name="15 — duck",
        chapter=2,
        intro="incoming.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("falling_block", 8, 12, 14, 3, 1200),
            ("falling_block", 16, 20, 14, 2, 1400),
            ("saw_path", [(6, 11), (24, 11)], 280, 14),
        ],
    ),

    # 16 — fake exits
    _L(
        name="16 — choose",
        chapter=2,
        intro="pick one.",
        outro="lucky.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.....X........E........X.....",
            "================================",
            "################################",
            "################################",
        ],
    ),

    # 17 — spike rain begins
    _L(
        name="17 — rain",
        chapter=2,
        intro="weather report.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_rain", 0.7, None, 0.5, 12),
            ("wall_slam", 5, "left", 18, 13, 14, 10),
        ],
    ),

    # 18 — wall slams
    _L(
        name="18 — close in",
        chapter=2,
        intro="cozy.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("wall_slam", 6, "right", 24, 11, 14, 14),
        ],
    ),

    # 19 — spring into spikes
    _L(
        name="19 — high jump",
        chapter=2,
        intro="up you go.",
        outro="hm.",
        tiles=[
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "............................E...",
            "..........................######",
            "..P............................",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spring_trap", 8, 14, -1100),
            ("hint_text", "(don't use the spring.)", (20, 660), GREY),
        ],
    ),

    # 20 — warden hand
    _L(
        name="20 — hand",
        chapter=2,
        intro="i'm reaching down.",
        outro="just to say hello.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("warden_hand", 12, "top", 1100),
        ],
    ),

    # 21 — invisible platforms (with hint)
    _L(
        name="21 — faith",
        chapter=2,
        intro="believe.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            ".......IIII.....IIII............",
            "................................",
            "..P...........................E.",
            "======................==========",
            "######................##########",
            "######................##########",
        ],
        trolls=[
            ("hint_text",
             "the gaps are kind. trust them.",
             (20, 660), GREY),
        ],
    ),

    # 22 — gravity flip
    _L(
        name="22 — up is down",
        chapter=2,
        intro="watch this.",
        tiles=[
            "################################",
            "################################",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P............................E",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("gravity_flip", 14, False, 2.0),
            ("gravity_flip", 24, False, 2.0),
        ],
    ),

    # 23 — spike rain dense
    _L(
        name="23 — heavy rain",
        chapter=2,
        intro="put a coat on.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_rain", 0.45, None, 0.3, 22),
        ],
    ),

    # 24 — act 2 finale
    _L(
        name="24 — act two ends",
        chapter=2,
        intro="entertain me.",
        outro="that wasn't even close to enough.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.....X........E........X.....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_rain", 0.6, None, 0.5, 16),
            ("saw_path", [(10, 13), (22, 13)], 220, 18),
            ("warden_hand", 16, "top", 1200),
        ],
    ),

    # ════════════════════════════════════════════════════════════════════
    # ACT 3: BOREDOM (12)
    # ════════════════════════════════════════════════════════════════════

    # 25 — multiple spike drops
    _L(
        name="25 — sequencing",
        chapter=3,
        chapter_intro=CHAPTER_INTROS[3],
        intro="i made something new.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_drop", 6, [10], 13),
            ("spike_drop", 12, [16], 13),
            ("spike_drop", 18, [22], 13),
            ("spike_after", 8, [8], 14),
            ("spike_after", 14, [14], 14),
            ("wall_slam", 5, "left", 20, 12, 14, 8),
        ],
    ),

    # 26 — spike rain + rising lava
    _L(
        name="26 — climb",
        chapter=3,
        intro="up.",
        tiles=[
            "................................",
            "................................",
            "..............................E.",
            "................================",
            "................................",
            "................................",
            "================................",
            "................................",
            "................................",
            "................================",
            "................................",
            "................................",
            "================................",
            "................................",
            "..P.............................",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.7, GRID_H, 1.5),
            ("spike_rain", 0.85, None, 1.0, 14),
        ],
    ),

    # 27 — saw gauntlet
    _L(
        name="27 — gauntlet",
        chapter=3,
        intro="walk past my friends.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("saw_path", [(8, 12), (8, 14)], 200, 18),
            ("saw_path", [(14, 14), (14, 12)], 220, 18),
            ("saw_path", [(20, 12), (20, 14)], 240, 18),
        ],
    ),

    # 28 — disappearing chain
    _L(
        name="28 — quickly now",
        chapter=3,
        intro="don't stop. don't think.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "............................E...",
            ".........................#######",
            "................DDDDDD..........",
            "............................^^^^",
            "........DDDDD...................",
            "....DDDDD.......................",
            "................................",
            "..P.............................",
            "======..........................",
            "######..........................",
            "######..........................",
        ],
        trolls=[
            ("disappear_after_step",
             [(x, 12) for x in range(4, 9)] +
             [(x, 11) for x in range(8, 13)] +
             [(x, 9) for x in range(16, 22)], 0.3),
        ],
    ),

    # 29 — moving exit + saws
    _L(
        name="29 — chase",
        chapter=3,
        intro="catch it.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("moving_exit", 90, 22, 30),
            ("saw_path", [(10, 13), (16, 13), (22, 13)], 160, 16),
            ("spike_rain", 1.2, None, 0.7, 14),
        ],
    ),

    # 30 — gravity flip with ceiling spikes
    _L(
        name="30 — inverted",
        chapter=3,
        intro="hold on.",
        tiles=[
            "################################",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P............................E",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("gravity_flip", 10, False, 2.0),
            ("gravity_flip", 22, False, 2.0),
        ],
    ),

    # 31 — wall slam + spike drop
    _L(
        name="31 — pinned",
        chapter=3,
        intro="stay there.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("wall_slam", 6, "right", 26, 10, 14, 18),
            ("spike_drop", 10, [12, 13, 14], 12),
            ("spike_drop", 16, [18, 19, 20], 12),
        ],
    ),

    # 32 — multiple hands
    _L(
        name="32 — many hands",
        chapter=3,
        intro="i grew more.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("warden_hand", 6, "top", 1100),
            ("warden_hand", 12, "top", 1150),
            ("warden_hand", 18, "top", 1200),
        ],
    ),

    # 33 — mirror world
    _L(
        name="33 — looking glass",
        chapter=3,
        intro="see yourself.",
        outro="that wasn't you. that was me.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("mirror_world", True),
            ("invert_controls", 0,
             "your reflection moves how you'd expect."),
        ],
    ),

    # 34 — exit hop + saws
    _L(
        name="34 — jump for it",
        chapter=3,
        intro="catch it if you can.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("exit_hop", 120, 150),
            ("saw_path", [(14, 13), (22, 13)], 180, 16),
        ],
    ),

    # 35 — moving platforms maze
    _L(
        name="35 — passage two",
        chapter=3,
        intro="ride.",
        tiles=[
            "................................",
            "................................",
            "..............................E.",
            "..........................######",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.............................",
            "==========......................",
            "##########......................",
            "##########......................",
        ],
        trolls=[
            ("moving_platform", [(11, 13), (11, 6)], 100, 2),
            ("moving_platform", [(16, 6), (24, 6)], 130, 2),
            ("spike_rain", 1.0, [13, 14, 15, 16, 17, 18], 1.0, 10),
        ],
    ),

    # 36 — act 3 finale
    _L(
        name="36 — act three ends",
        chapter=3,
        intro="i'm getting better at this.",
        outro="i am, you know. it shows.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.....X........E........X.....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("moving_exit", 90, 14, 22),
            ("warden_hand", 8, "top", 1200),
            ("warden_hand", 18, "top", 1200),
            ("saw_path", [(12, 13), (20, 13)], 220, 18),
            ("spike_rain", 0.55, None, 1.0, 14),
        ],
    ),

    # ════════════════════════════════════════════════════════════════════
    # ACT 4: CRUELTY (12)
    # ════════════════════════════════════════════════════════════════════

    # 37 — invert controls intro
    _L(
        name="37 — left is right",
        chapter=4,
        chapter_intro=CHAPTER_INTROS[4],
        intro="figure it out.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("invert_controls", 0, "your hands aren't yours."),
        ],
    ),

    # 38 — invert + spikes from above
    _L(
        name="38 — bad hands",
        chapter=4,
        intro="and i'm dropping spikes.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("invert_controls", 0),
            ("spike_drop", 6, [10, 11], 13),
            ("spike_drop", 12, [16, 17], 13),
            ("spike_drop", 18, [22, 23], 13),
        ],
    ),

    # 39 — crushing + lava
    _L(
        name="39 — squeeze",
        chapter=4,
        intro="hurry.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("crushing_ceiling", 4, 0, 31, 3, 8, 5),
            ("rising_lava", 0.65, GRID_H, 1.6),
        ],
    ),

    # 40 — wall slams both sides
    _L(
        name="40 — together now",
        chapter=4,
        intro="meet me in the middle.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P............E................",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("wall_slam", 4, "left", 6, 10, 14, 14),
            ("wall_slam", 4, "right", 26, 10, 14, 14),
        ],
    ),

    # 41 — fake exits that swap
    _L(
        name="41 — pick again",
        chapter=4,
        intro="i'll keep moving them.",
        outro="lucky again. interesting.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P...X.....X......X......E.....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("exit_swap", 0, 1.4),
            ("exit_swap", 1, 1.7),
            ("exit_swap", 2, 2.0),
            ("spike_after", 6, [6], 14),
            ("spike_after", 12, [12], 14),
            ("spike_after", 18, [19], 14),
        ],
    ),

    # 42 — teleport loop
    _L(
        name="42 — somewhere else",
        chapter=4,
        intro="don't go right.",
        outro="learning.",
        tiles=[
            "................................",
            "................................",
            "..............................E.",
            "..........................######",
            ".........................====...",
            "................................",
            "....................====........",
            "................................",
            "................====............",
            "................................",
            "...........====.................",
            "................................",
            "......====......................",
            "................................",
            "..P............................X",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("teleport_loop", 24, 3, "the wall isn't the exit. up is."),
        ],
    ),

    # 43 — disappear under feet + spikes
    _L(
        name="43 — drop",
        chapter=4,
        intro="don't stay still.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..PDDDDDDDDDDDDDDDDDDDDDDDDE....",
            "==.^^^^^^^^^^^^^^^^^^^^^^^^^....",
            "..##############################",
            "..##############################",
        ],
        trolls=[
            ("disappear_after_step",
             [(x, 14) for x in range(3, 27)], 0.15),
        ],
    ),

    # 44 — saw + spike rain + lava
    _L(
        name="44 — full house",
        chapter=4,
        intro="everything i have.",
        tiles=[
            "................................",
            "................................",
            "..............................E.",
            "..........................######",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.............................",
            "==========......................",
            "##########......................",
            "##########......................",
        ],
        trolls=[
            ("moving_platform", [(11, 13), (24, 4)], 110, 2),
            ("saw_path", [(13, 6), (20, 6), (20, 10), (13, 10)],
             220, 18),
            ("spike_rain", 0.6, None, 0.5, 16),
            ("rising_lava", 0.4, GRID_H, 4.0),
        ],
    ),

    # 45 — falling blocks rain
    _L(
        name="45 — hailstones",
        chapter=4,
        intro="hold still.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("falling_block", 4, 8, 14, 2, 1200),
            ("falling_block", 9, 14, 14, 2, 1300),
            ("falling_block", 14, 20, 14, 2, 1100),
            ("falling_block", 19, 24, 14, 2, 1400),
        ],
    ),

    # 46 — constant shake
    _L(
        name="46 — earthquake",
        chapter=4,
        intro="it shakes when i'm angry.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P............................E",
            "===..DDDD..DDDD..DDDD..DDDD.====",
            "###..####..####..####..####.####",
            "###..####..####..####..####.####",
        ],
        trolls=[
            ("camera_shake_constant", 5),
            ("disappear_after_step",
             [(x, 15) for x in range(5, 9)] +
             [(x, 15) for x in range(11, 15)] +
             [(x, 15) for x in range(17, 21)] +
             [(x, 15) for x in range(23, 27)], 0.4),
        ],
    ),

    # 47 — spikes from everywhere
    _L(
        name="47 — surrounded",
        chapter=4,
        intro="don't look up. or down. or sideways.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_drop", 5, [8, 9, 10], 13),
            ("spike_after", 7, [4, 5, 6], 14),
            ("spike_drop", 12, [14, 15, 16], 13),
            ("spike_after", 14, [10, 11, 12], 14),
            ("spike_drop", 19, [20, 21, 22], 13),
        ],
    ),

    # 48 — act 4 finale
    _L(
        name="48 — act four ends",
        chapter=4,
        intro="you're doing well.",
        outro="that wasn't a compliment.",
        tiles=[
            "................................",
            "................................",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.....X........E........X.....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("invert_controls", 4),
            ("crushing_ceiling", 6, 0, 31, 2, 5, 4),
            ("warden_hand", 12, "top", 1200),
            ("exit_swap", 0, 1.2),
            ("exit_swap", 1, 1.5),
            ("spike_rain", 0.7, None, 0.8, 14),
        ],
    ),

    # ════════════════════════════════════════════════════════════════════
    # ACT 5: RECOGNITION (12)
    # ════════════════════════════════════════════════════════════════════

    # 49 — quiet again
    _L(
        name="49 — a pause",
        chapter=5,
        chapter_intro=CHAPTER_INTROS[5],
        intro="rest a moment.",
        outro="now keep going.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("narrate", "spawn", 1.0, "rest, then.", "top", 1.6),
            ("crushing_ceiling", 8, 4, 27, 0, 6, 10),
            ("wall_slam", 14, "left", 24, 12, 14, 7),
        ],
    ),

    # 50 — screen tilt + saws
    _L(
        name="50 — tilted",
        chapter=5,
        intro="hold on to something.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("screen_tilt", 8, True, 4.0),
            ("saw_path", [(10, 13), (22, 13)], 200, 16),
        ],
    ),

    # 51 — gravity flip + invert
    _L(
        name="51 — confused",
        chapter=5,
        intro="and your hands are wrong.",
        tiles=[
            "################################",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P............................E",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("gravity_flip", 10, False, 2.0),
            ("invert_controls", 0),
        ],
    ),

    # 52 — the hand chases
    _L(
        name="52 — i'm coming",
        chapter=5,
        intro="don't stop moving.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("warden_hand", 4, "top", 800),
            ("warden_hand", 8, "top", 850),
            ("warden_hand", 12, "top", 900),
            ("warden_hand", 16, "top", 950),
            ("warden_hand", 20, "top", 1000),
        ],
    ),

    # 53 — story beat: the warden's confession
    _L(
        name="53 — i was you",
        chapter=5,
        intro="i wasn't always this.",
        outro="and then there was an after.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("narrate", "x", 6,
             "there was a little doll like you.", "top", 2.6),
            ("narrate", "x", 14,
             "they reached the end. there was an after.", "top", 2.6),
            ("narrate", "x", 22,
             "and the next doll came.", "top", 2.4),
        ],
    ),

    # 54 — disappearing everything
    _L(
        name="54 — falling apart",
        chapter=5,
        intro="don't look down.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
            "################################",
            "################################",
        ],
        trolls=[
            ("disappear_after_step",
             [(x, 15) for x in range(0, 32)], 0.18),
            ("spike_drop", 8, [12, 16, 20], 13),
        ],
    ),

    # 55 — exit moves, vanishes, returns
    _L(
        name="55 — peek-a-boo",
        chapter=5,
        intro="now you see it.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("exit_swap", 0, 1.2),
            ("exit_swap", 1, 1.5),
            ("moving_exit", 70, 16, 30),
        ],
    ),

    # 56 — moving platforms with hands
    _L(
        name="56 — held",
        chapter=5,
        intro="i'll hold this for you.",
        tiles=[
            "................................",
            "................................",
            "..............................E.",
            "..........................######",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.............................",
            "==========......................",
            "##########......................",
            "##########......................",
        ],
        trolls=[
            ("moving_platform", [(11, 13), (22, 6)], 120, 2),
            ("warden_hand", 14, "top", 1100),
        ],
    ),

    # 57 — tiny chamber with a hidden exit
    _L(
        name="57 — small room",
        chapter=5,
        intro="there is no exit visible.",
        outro="i hid it. you found it.",
        tiles=[
            "................................",
            "................................",
            "............########............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#......#............",
            "............#P...E.#............",
            "............########............",
            "................................",
            "................................",
        ],
        trolls=[
            ("hint_text",
             "look closely. it's right next to you.",
             (20, 660), GREY),
        ],
    ),

    # 58 — story heavy, level shape resembles a face
    _L(
        name="58 — a face",
        chapter=5,
        intro="this is the first one of you i ever made.",
        outro="they are still here, somewhere.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "........##############..........",
            "........#............#..........",
            "........#..==....==..#..........",
            "........#............#..........",
            "........#............#..........",
            "........#....====....#..........",
            "........#............#..........",
            "........##############..........",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
    ),

    # 59 — the puppet sees itself
    _L(
        name="59 — reflection",
        chapter=5,
        intro="that's not me. that's you.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("mirror_world", True),
            ("invert_controls", 0),
            ("screen_tilt", 4, True, 3.0),
        ],
    ),

    # 60 — act 5 finale
    _L(
        name="60 — act five ends",
        chapter=5,
        intro="we are nearly done.",
        outro="not because i am tired. because you are.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........================.E...",
            "===..DDDDD..................====",
            "###..#####..................####",
            "###..#####..................####",
        ],
        trolls=[
            ("disappear_after_step",
             [(x, 15) for x in range(5, 10)], 0.2),
            ("spike_drop", 11, [12, 14, 16, 18], 13),
            ("warden_hand", 20, "top", 1200),
            ("rising_lava", 0.5, GRID_H, 2.0),
        ],
    ),

    # ════════════════════════════════════════════════════════════════════
    # ACT 6: BECOMING (12)
    # ════════════════════════════════════════════════════════════════════

    # 61 — calm
    _L(
        name="61 — calm",
        chapter=6,
        chapter_intro=CHAPTER_INTROS[6],
        intro="walk with me.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
    ),

    # 62 — stairway down
    _L(
        name="62 — descent",
        chapter=6,
        intro="this way.",
        tiles=[
            "................................",
            "..P.............................",
            "===.............................",
            "###=============................",
            "##############==................",
            "################=...............",
            "#################=..............",
            "##################=.............",
            "###################=............",
            "####################=...........",
            "#####################=..........",
            "######################=.........",
            "#######################=........",
            "########################=.......",
            "#########################=.E....",
            "#########################=######",
            "################################",
            "################################",
        ],
    ),

    # 63 — warden's chamber
    _L(
        name="63 — i live here",
        chapter=6,
        intro="this is where i sit.",
        outro="i watch you from above.",
        tiles=[
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("bg_color", [220, 218, 215]),
            ("hint_text",
             "this room is older than you.",
             (20, 660), GREY),
        ],
    ),

    # 64 — you are the victim
    _L(
        name="64 — already dead",
        chapter=6,
        intro="this happened a long time ago.",
        outro="you don't remember. you can't.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.....X.....X......X.....E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("warden_hand", 9, "top", 1200),
            ("spike_drop", 14, [22, 23], 13),
        ],
    ),

    # 65 — a test you can't fail
    _L(
        name="65 — you cannot fail",
        chapter=6,
        intro="just walk.",
        outro="see? not a trick.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
    ),

    # 66 — a test you can't pass
    _L(
        name="66 — you cannot pass",
        chapter=6,
        intro="now this one is.",
        outro="i lied. of course you could. you just did.",
        tiles=[
            "................................",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "................................",
            "................................",
            "................................",
            "................................",
            "================================",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "................................",
            "................................",
            "................................",
            "................................",
            "================================",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("hint_text",
             "the spikes only kill if you jump.",
             (20, 660), GREY),
        ],
    ),

    # 67 — strings cut
    _L(
        name="67 — strings cut",
        chapter=6,
        intro="i'm letting go.",
        outro="now the world holds you.",
        tiles=[
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("crushing_ceiling", 4, 0, 31, 0, 4, 3),
            ("rising_lava", 0.5, GRID_H, 1.5),
            ("warden_hand", 14, "top", 1100),
        ],
    ),

    # 68 — many puppets
    _L(
        name="68 — others",
        chapter=6,
        intro="they're all yours. all of them.",
        outro="that one was the first. the next was the one after.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P..X..X..X..X..X..X..X..XE....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("narrate", "x", 6,
             "this is doll one.", "top", 1.6),
            ("narrate", "x", 10,
             "this is doll seventeen.", "top", 1.6),
            ("narrate", "x", 18,
             "this is doll two hundred.", "top", 1.6),
            ("narrate", "x", 24,
             "you are doll something. i lost count.", "top", 2.4),
        ],
    ),

    # 69 — the mirror
    _L(
        name="69 — the mirror",
        chapter=6,
        intro="look.",
        outro="that is what i look like to me.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("mirror_world", True),
            ("screen_tilt", 2, True, 4.0),
            ("bg_color", [200, 198, 195]),
            ("hint_text",
             "the doll on the right is you. the one on the left is me.",
             (20, 660), GREY),
        ],
    ),

    # 70 — climb
    _L(
        name="70 — up to me",
        chapter=6,
        intro="come up.",
        tiles=[
            "..............................E.",
            "..........................######",
            "................................",
            "................================",
            "................................",
            "==========......................",
            "................................",
            "................================",
            "................................",
            "==========......................",
            "................................",
            "................================",
            "................................",
            "................................",
            "..P.............................",
            "==========......................",
            "##########......................",
            "##########......................",
        ],
        trolls=[
            ("moving_platform", [(11, 13), (12, 5)], 90, 2),
            ("saw_path", [(18, 6), (24, 6)], 200, 16),
            ("rising_lava", 0.45, GRID_H, 2.0),
        ],
    ),

    # 71 — penultimate
    _L(
        name="71 — almost",
        chapter=6,
        intro="just one room left after this.",
        outro="i will not be here for that one.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P.....X........E........X.....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("warden_hand", 4, "top", 1100),
            ("warden_hand", 12, "top", 1150),
            ("warden_hand", 20, "top", 1200),
            ("spike_rain", 0.5, None, 0.3, 22),
            ("rising_lava", 0.5, GRID_H, 3.0),
        ],
    ),

    # 72 — becoming
    _L(
        name="72 — your room now",
        chapter=6,
        intro="walk in.",
        outro="welcome, Warden.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("bg_color", [220, 218, 212]),
            ("narrate", "x", 6,
             "i was you. you are me.", "top", 2.4),
            ("narrate", "x", 14,
             "soon a doll will wake up where you woke.", "top", 2.6),
            ("narrate", "x", 22,
             "you will know what to do.", "top", 2.4),
        ],
    ),

    # ════════════════════════════════════════════════════════════════════
    # ACT 7: TANGLED (24)  —  the warden gets feral; everything is reactive
    # ════════════════════════════════════════════════════════════════════

    # 73 — false restart
    _L(
        name="73 — wake up",
        chapter=7,
        chapter_intro=CHAPTER_INTROS[7],
        intro="oh. you're back.",
        outro="we were just getting started.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_row", 8, 12, 18, 14, "up"),
            ("heckle", 4, "whisper", "top", 2.0),
        ],
    ),

    # 74 — landings hurt
    _L(
        name="74 — landings",
        chapter=7,
        intro="careful where you put your feet.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "======...====...====..==========",
            "######...####...####..##########",
            "######...####...####..##########",
        ],
        trolls=[
            ("ambush_spike", 12, 14, 3, "up"),
            ("ambush_spike", 18, 14, 3, "up"),
            ("heckle", None, "mock", "top", 2.2),
        ],
    ),

    # 75 — the path drops
    _L(
        name="75 — disappearing path",
        chapter=7,
        intro="don't trust the floor.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_floor_drop", 4, 25, 15, 0),
            ("heckle", 10, "threat", "top", 2.2),
        ],
    ),

    # 76 — ceiling drops
    _L(
        name="76 — overhead",
        chapter=7,
        intro="don't look up.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_ceiling", 8, 10, 20, 6, 14, 0.4),
            ("heckle", 4, "whisper", "top", 2.0),
        ],
    ),

    # 77 — don't stop
    _L(
        name="77 — don't stop",
        chapter=7,
        intro="if you slow down you die.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("snap_kill", 4, 12, 12, 16, 1.0),
            ("snap_kill", 14, 12, 22, 16, 1.0),
            ("heckle", None, "threat", "top", 2.2),
        ],
    ),

    # 78 — ambush saws
    _L(
        name="78 — they were there",
        chapter=7,
        intro="they were always there.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_saw", 10, 14, 4, 5, 280),
            ("ambush_saw", 18, 14, 4, 5, 320),
            ("heckle", 6, "mock", "top", 2.2),
        ],
    ),

    # 79 — combined first
    _L(
        name="79 — choir",
        chapter=7,
        intro="all together now.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_floor_drop", 4, 26, 15, 1),
            ("ambush_spike", 18, 14, 4, "up"),
            ("heckle", 8, "random", "top", 2.0),
        ],
    ),

    # 80 — mirror with ambush
    _L(
        name="80 — your other side",
        chapter=7,
        intro="left is right. right is wrong.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("invert_controls", 5),
            ("ambush_row", 12, 14, 20, 14, "up"),
            ("heckle", 3, "whisper", "top", 2.0),
        ],
    ),

    # 81 — high ground
    _L(
        name="81 — up where it's safe",
        chapter=7,
        intro="climb. don't trust the height.",
        tiles=[
            "................................",
            "................................",
            "..............................E.",
            "................================",
            "................................",
            "................................",
            "================................",
            "................................",
            "................................",
            "................================",
            "................................",
            "................................",
            "================................",
            "................................",
            "..P.............................",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("heckle", None, "mock", "top", 2.0),
        ],
    ),

    # 82 — all the ambushes
    _L(
        name="82 — collected",
        chapter=7,
        intro="my favourites, all at once.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_row", 6, 10, 14, 14, "up"),
            ("ambush_saw", 14, 14, 3, 5, 300),
            ("ambush_ceiling", 18, 18, 24, 6, 16, 0.3),
            ("heckle", None, "threat", "top", 2.0),
        ],
    ),

    # 83 — false hint
    _L(
        name="83 — a kind warning",
        chapter=7,
        intro="i'm being helpful.",
        outro="i was lying.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("hint_text", "the right side is safe.", (20, 60), INK),
            ("ambush_row", 22, 22, 30, 14, "up"),
            ("ambush_floor_drop", 18, 22, 15, 0),
        ],
    ),

    # 84 — four doors, three traps
    _L(
        name="84 — choose poorly",
        chapter=7,
        intro="one of them is real.",
        outro="that was the one.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P...X.....X.....X.......E.....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("exit_swap", 0, 1.2),
            ("exit_swap", 1, 1.5),
            ("exit_swap", 2, 1.8),
            ("heckle", None, "mock", "top", 2.0),
        ],
    ),

    # 85 — lava + ambush
    _L(
        name="85 — rising",
        chapter=7,
        intro="don't dawdle.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.0, GRID_H, 1.2),
            ("ambush_row", 14, 14, 22, 14, "up"),
            ("heckle", 8, "threat", "top", 1.8),
        ],
    ),

    # 86 — disappearing corridor
    _L(
        name="86 — pace",
        chapter=7,
        intro="every step costs.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..PDDDDDDDDDDDDDDDDDDDDDDDDE....",
            "==.^^^^^^^^^^^^^^^^^^^^^^^^^^^^^",
            "..##############################",
            "..##############################",
        ],
        trolls=[
            ("disappear_after_step",
             [(x, 14) for x in range(3, 27)], 0.12),
            ("heckle", 14, "threat", "top", 1.6),
        ],
    ),

    # 87 — high jump trap
    _L(
        name="87 — apex",
        chapter=7,
        intro="up. then everything happens.",
        tiles=[
            "................................",
            "................................",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_spike", 12, 14, 5, "up"),
            ("ambush_spike", 18, 14, 5, "up"),
            ("heckle", 5, "whisper", "top", 2.0),
        ],
    ),

    # 88 — density
    _L(
        name="88 — packed",
        chapter=7,
        intro="i squeezed them all in.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("saw_path", [(8, 14), (14, 14)], 220, 18),
            ("saw_path", [(18, 14), (24, 14)], 240, 18),
            ("spike_rain", 0.8, None, 0.8, 14),
            ("ambush_floor_drop", 6, 26, 15, 0),
        ],
    ),

    # 89 — the warden monologues
    _L(
        name="89 — listen",
        chapter=7,
        intro="i need to tell you something.",
        outro="don't think about it too much.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("narrate", "x", 5,
             "you weren't the first.", "top", 2.2),
            ("narrate", "x", 12,
             "i kept the others' strings.", "top", 2.2),
            ("narrate", "x", 19,
             "they're in the walls now.", "top", 2.4),
            ("ambush_row", 24, 24, 28, 14, "up"),
        ],
    ),

    # 90 — gauntlet
    _L(
        name="90 — through it",
        chapter=7,
        intro="don't stop. don't think.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_row", 6, 8, 11, 14, "up"),
            ("ambush_row", 12, 14, 17, 14, "up"),
            ("ambush_row", 18, 20, 23, 14, "up"),
            ("ambush_saw", 16, 13, 3, 6, 340),
            ("heckle", None, "threat", "top", 2.0),
        ],
    ),

    # 91 — inverted gravity ambush
    _L(
        name="91 — upside down",
        chapter=7,
        intro="ceiling is floor now.",
        tiles=[
            "################################",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P............................E",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("gravity_flip", 8, False, 3.0),
            ("gravity_flip", 24, False, 3.0),
            ("ambush_row", 18, 12, 20, 2, "down"),
            ("heckle", 6, "mock", "top", 2.0),
        ],
    ),

    # 92 — speed run
    _L(
        name="92 — fast",
        chapter=7,
        intro="quickly.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.0, GRID_H, 0.9),
            ("wall_slam", 4, "left", 27, 12, 14, 9),
            ("heckle", None, "threat", "top", 1.8),
        ],
    ),

    # 93 — tight
    _L(
        name="93 — narrow",
        chapter=7,
        intro="thread the needle.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "....========..==========........",
            "................................",
            "================....============",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_saw", 14, 6, 3, 5, 260),
            ("ambush_spike", 10, 6, 3, "down"),
            ("heckle", 6, "whisper", "top", 1.8),
        ],
    ),

    # 94 — invisible path
    _L(
        name="94 — by feel",
        chapter=7,
        intro="trust.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            ".......IIII.....IIII............",
            "..P...........................E.",
            "==========............==========",
            "##########............##########",
            "##########............##########",
        ],
        trolls=[
            ("ambush_spike", 18, 13, 3, "down"),
            ("hint_text", "trust nothing visible.", (20, 80), GREY),
            ("heckle", None, "whisper", "top", 2.2),
        ],
    ),

    # 95 — total assault
    _L(
        name="95 — everything",
        chapter=7,
        intro="i'm using everything.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.0, GRID_H, 1.4),
            ("spike_rain", 0.6, None, 0.7, 14),
            ("ambush_saw", 12, 13, 3, 5, 320),
            ("ambush_floor_drop", 6, 26, 15, 0),
            ("heckle", None, "random", "top", 1.8),
        ],
    ),

    # 96 — act 7 finale
    _L(
        name="96 — act seven ends",
        chapter=7,
        intro="last room of this set.",
        outro="i'm not done with you.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("crushing_ceiling", 8, 8, 24, 0, 8, 8),
            ("wall_slam", 6, "left", 26, 13, 14, 8),
            ("rising_lava", 0.3, GRID_H, 1.2),
            ("narrate", "x", 14,
             "this is the part where you almost feel proud.", "top", 2.2),
        ],
    ),

    # ════════════════════════════════════════════════════════════════════
    # ACT 8: STRINGS (24)  —  the warden is unraveling
    # ════════════════════════════════════════════════════════════════════

    # 97 — quiet
    _L(
        name="97 — quiet again",
        chapter=8,
        chapter_intro=CHAPTER_INTROS[8],
        intro="...",
        outro="that was for me, not you.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("bg_color", [218, 214, 208]),
            ("narrate", "spawn", 1.0,
             "i won't speak this room.", "top", 2.0),
            ("ambush_spike", 22, 14, 3, "up"),
        ],
    ),

    # 98 — mirror
    _L(
        name="98 — same room",
        chapter=8,
        intro="have we been here?",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("mirror_world",),
            ("ambush_floor_drop", 6, 26, 15, 0),
            ("heckle", 8, "whisper", "top", 2.0),
        ],
    ),

    # 99 — all paths trapped
    _L(
        name="99 — every way",
        chapter=8,
        intro="every path. i tried.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "...........================.....",
            "...........################.....",
            "...........################.....",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("spike_drop", 5, [11, 12, 13, 14, 15], 4),
            ("spike_drop", 14, [16, 17, 18, 19, 20], 4),
            ("ambush_row", 8, 11, 22, 14, "up"),
            ("heckle", None, "threat", "top", 2.0),
        ],
    ),

    # 100 — only narration
    _L(
        name="100 — a hundred",
        chapter=8,
        intro="round number. round room.",
        outro="you're doing better than i thought.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("narrate", "x", 4, "do you count, too?", "top", 2.2),
            ("narrate", "x", 12, "i counted you 247 times.", "top", 2.4),
            ("narrate", "x", 20, "you didn't notice the others.", "top", 2.4),
        ],
    ),

    # 101 — chase
    _L(
        name="101 — running",
        chapter=8,
        intro="don't look back.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("wall_slam", 4, "left", 28, 12, 14, 10),
            ("ambush_saw", 18, 13, 4, 6, 300),
            ("heckle", None, "threat", "top", 1.8),
        ],
    ),

    # 102 — silence
    _L(
        name="102 — silent",
        chapter=8,
        intro="",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_spike", 8, 14, 2, "up"),
            ("ambush_spike", 14, 14, 2, "up"),
            ("ambush_spike", 20, 14, 2, "up"),
            ("ambush_spike", 26, 14, 2, "up"),
        ],
    ),

    # 103 — warden hostile
    _L(
        name="103 — bared",
        chapter=8,
        intro="i'm not pretending anymore.",
        tiles=[
            "################################",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("warden_hand", 8, "top", 1100),
            ("warden_hand", 16, "top", 1150),
            ("warden_hand", 22, "top", 1200),
        ],
    ),

    # 104 — exit elsewhere
    _L(
        name="104 — not where you look",
        chapter=8,
        intro="you'll find it.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "..............................E.",
            "..........................######",
            "................................",
            "................................",
            "................................",
            "................................",
            "..............======............",
            "..............######............",
            "................................",
            "................................",
            "................................",
            "..P.............................",
            "==============..................",
            "##############..................",
            "##############..................",
        ],
        trolls=[
            ("moving_platform", [(15, 9), (15, 5)], 90, 2),
            ("ambush_spike", 16, 9, 3, "up"),
            ("heckle", 6, "whisper", "top", 2.0),
        ],
    ),

    # 105 — endless climb
    _L(
        name="105 — climb",
        chapter=8,
        intro="up. always up.",
        tiles=[
            "................................",
            "................................",
            "..............................E.",
            "................================",
            "................................",
            "................................",
            "================................",
            "................................",
            "................................",
            "................================",
            "................................",
            "................................",
            "================................",
            "................................",
            "..P.............................",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.0, GRID_H, 1.2),
        ],
    ),

    # 106 — dropdown
    _L(
        name="106 — fall",
        chapter=8,
        intro="straight down.",
        tiles=[
            "..P.............................",
            "==============.......===========",
            "##############.......###########",
            "##############.......###########",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "...........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_row", 16, 14, 18, 1, "down"),
            ("ambush_row", 22, 24, 28, 14, "up"),
            ("heckle", None, "mock", "top", 2.0),
        ],
    ),

    # 107 — dense
    _L(
        name="107 — packed again",
        chapter=8,
        intro="more, but tighter.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_row", 6, 6, 9, 14, "up"),
            ("ambush_row", 12, 11, 14, 14, "up"),
            ("ambush_row", 18, 16, 19, 14, "up"),
            ("ambush_row", 24, 21, 24, 14, "up"),
            ("saw_path", [(8, 13), (24, 13)], 360, 18),
        ],
    ),

    # 108 — more threats
    _L(
        name="108 — pressure",
        chapter=8,
        intro="i'm impatient now.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("wall_slam", 3, "left", 27, 12, 14, 8),
            ("ambush_ceiling", 12, 12, 22, 6, 16, 0.3),
            ("heckle", None, "threat", "top", 1.6),
        ],
    ),

    # 109 — dialog level
    _L(
        name="109 — what i wanted to say",
        chapter=8,
        intro="...",
        outro="...thanks for listening.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("narrate", "x", 4, "i was a child.", "top", 2.0),
            ("narrate", "x", 8, "i had strings too.", "top", 2.0),
            ("narrate", "x", 14, "the warden before me said the same things.", "top", 2.6),
            ("narrate", "x", 22, "you'll say them too.", "top", 2.4),
        ],
    ),

    # 110 — fake mercy
    _L(
        name="110 — i give up",
        chapter=8,
        intro="i'm done. walk to the door.",
        outro="of course i lied.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("hint_text", "the door is unlocked. you've earned it.",
             (20, 80), INK),
            ("ambush_row", 26, 26, 30, 14, "up"),
            ("heckle", 22, "threat", "top", 1.5),
        ],
    ),

    # 111 — speed test
    _L(
        name="111 — quick now",
        chapter=8,
        intro="fast or not at all.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.0, GRID_H, 0.75),
            ("snap_kill", 4, 12, 8, 16, 0.7),
            ("snap_kill", 14, 12, 18, 16, 0.7),
            ("snap_kill", 22, 12, 26, 16, 0.7),
        ],
    ),

    # 112 — test of everything
    _L(
        name="112 — exam",
        chapter=8,
        intro="show me what you learned.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("invert_controls", 4),
            ("gravity_flip", 10, False, 2.0),
            ("ambush_saw", 16, 13, 3, 5, 320),
            ("ambush_row", 22, 22, 26, 14, "up"),
        ],
    ),

    # 113 — gauntlet two
    _L(
        name="113 — running again",
        chapter=8,
        intro="like before. worse.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_row", 6, 7, 10, 14, "up"),
            ("ambush_saw", 14, 13, 3, 4, 360),
            ("ambush_row", 20, 18, 22, 14, "up"),
            ("ambush_floor_drop", 22, 28, 15, 0),
        ],
    ),

    # 114 — choice with cost
    _L(
        name="114 — pay attention",
        chapter=8,
        intro="watch carefully.",
        outro="that one always was real.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P...X.....X......X......E.....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("exit_swap", 0, 0.8),
            ("exit_swap", 1, 1.1),
            ("exit_swap", 2, 1.4),
            ("spike_after", 6, [6], 14),
            ("spike_after", 12, [12], 14),
            ("spike_after", 18, [19], 14),
        ],
    ),

    # 115 — inverted everything
    _L(
        name="115 — wrong way up",
        chapter=8,
        intro="all of it. backwards.",
        tiles=[
            "################################",
            "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
            "================================",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P............................E",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("gravity_flip", 6, False, 4.0),
            ("gravity_flip", 26, False, 4.0),
            ("invert_controls", 8),
            ("ambush_row", 18, 14, 22, 2, "down"),
            ("heckle", None, "mock", "top", 2.0),
        ],
    ),

    # 116 — lava sprint
    _L(
        name="116 — burn",
        chapter=8,
        intro="hot.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.0, GRID_H, 0.65),
            ("ambush_spike", 12, 14, 3, "up"),
            ("ambush_spike", 22, 14, 3, "up"),
        ],
    ),

    # 117 — reverse
    _L(
        name="117 — backwards",
        chapter=8,
        intro="exit's on the left now.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..E........................P....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("ambush_row", 25, 6, 25, 14, "up"),
            ("ambush_saw", 14, 13, 4, 6, 280),
            ("heckle", None, "whisper", "top", 2.0),
        ],
    ),

    # 118 — true gauntlet
    _L(
        name="118 — gauntlet",
        chapter=8,
        intro="all my best work.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("rising_lava", 0.0, GRID_H, 1.0),
            ("wall_slam", 4, "left", 27, 12, 14, 8),
            ("ambush_saw", 12, 13, 3, 5, 340),
            ("ambush_saw", 20, 13, 3, 5, 340),
            ("spike_rain", 0.6, None, 0.8, 14),
        ],
    ),

    # 119 — penultimate
    _L(
        name="119 — almost",
        chapter=8,
        intro="one room after this.",
        outro="ready?",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("crushing_ceiling", 6, 8, 24, 0, 10, 6),
            ("ambush_row", 14, 12, 20, 14, "up"),
            ("narrate", "x", 20,
             "the next door is the last.", "top", 2.2),
        ],
    ),

    # 120 — farewell
    _L(
        name="120 — your room",
        chapter=8,
        intro="walk slow. it's done.",
        outro="thank you. now you decide.",
        tiles=[
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "................................",
            "..P........................E....",
            "================================",
            "################################",
            "################################",
        ],
        trolls=[
            ("bg_color", [222, 220, 215]),
            ("narrate", "x", 4,
             "i let you keep all of it.", "top", 2.2),
            ("narrate", "x", 10,
             "the strings. the room. the warden.", "top", 2.4),
            ("narrate", "x", 18,
             "go on. open it.", "top", 2.2),
        ],
    ),
]


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    g = Game()
    try:
        g.run()
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        pygame.quit()
        sys.exit(1)


if __name__ == "__main__":
    main()
