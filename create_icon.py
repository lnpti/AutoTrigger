"""
AutoTrigger V10 — Gerador de icone de automacao.
Cria assets/icon.ico com icone personalizado (multiplos tamanhos).

Uso:
    python create_icon.py
"""
import math
import os
from PIL import Image, ImageDraw


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

# Cores
BG_OUTER   = (8,  12, 28,  255)
BG_INNER   = (14, 22, 52,  255)
ARROW_1    = (0,  190, 255, 255)
ARROW_2    = (80, 100, 255, 255)
BOLT_COLOR = (255, 230, 60,  255)


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(4))


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx = cy = size / 2
    r = size * 0.44
    pad = size * 0.04

    # Fundo circular com gradiente simulado
    steps = 16
    for i in range(steps, 0, -1):
        t = i / steps
        col = lerp_color(BG_INNER, BG_OUTER, t)
        rr = r * t + pad
        box = [cx - rr, cy - rr, cx + rr, cy + rr]
        d.ellipse(box, fill=col)

    # Borda brilhante
    border_r = r + pad * 0.5
    d.ellipse(
        [cx - border_r, cy - border_r, cx + border_r, cy + border_r],
        outline=(0, 160, 255, 120),
        width=max(1, int(size * 0.025)),
    )

    # Setas circulares
    arrow_r   = size * 0.32
    arrow_w   = max(2, int(size * 0.085))
    head_size = size * 0.11

    def draw_arc_arrow(start_deg, end_deg, color, head_at_end=True):
        box = [cx - arrow_r, cy - arrow_r, cx + arrow_r, cy + arrow_r]
        d.arc(box, start=start_deg, end=end_deg, fill=color, width=arrow_w)
        angle_deg = end_deg if head_at_end else start_deg
        angle = math.radians(angle_deg)
        tip_x = cx + arrow_r * math.cos(angle)
        tip_y = cy + arrow_r * math.sin(angle)
        tang_angle = angle + (math.pi / 2 if head_at_end else -math.pi / 2)
        perp_angle = angle + math.pi / 2
        back = head_size * 0.9
        wide = head_size * 0.55
        b1x = tip_x - back * math.cos(tang_angle) + wide * math.cos(perp_angle)
        b1y = tip_y - back * math.sin(tang_angle) + wide * math.sin(perp_angle)
        b2x = tip_x - back * math.cos(tang_angle) - wide * math.cos(perp_angle)
        b2y = tip_y - back * math.sin(tang_angle) - wide * math.sin(perp_angle)
        d.polygon([(tip_x, tip_y), (b1x, b1y), (b2x, b2y)], fill=color)

    draw_arc_arrow(start_deg=-30, end_deg=130,  color=ARROW_1)
    draw_arc_arrow(start_deg=150, end_deg=310,  color=ARROW_2)

    # Raio central
    bolt_h = size * 0.38
    bolt_w = size * 0.18
    bx = cx - bolt_w * 0.5
    by = cy - bolt_h * 0.5
    bolt_pts = [
        (bx + bolt_w * 0.65, by),
        (bx + bolt_w * 0.15, by + bolt_h * 0.45),
        (bx + bolt_w * 0.55, by + bolt_h * 0.42),
        (bx + bolt_w * 0.35, by + bolt_h),
        (bx + bolt_w * 0.85, by + bolt_h * 0.55),
        (bx + bolt_w * 0.45, by + bolt_h * 0.58),
    ]
    # Glow
    glow = max(1, int(size * 0.045))
    for offset in range(glow, 0, -1):
        alpha = int(80 * (1 - offset / glow))
        glow_pts = [(x + offset * 0.5, y + offset * 0.5) for x, y in bolt_pts]
        d.polygon(glow_pts, fill=(255, 200, 0, alpha))
    d.polygon(bolt_pts, fill=BOLT_COLOR)

    return img


def _polygon(cx: float, cy: float, r: float, sides: int, start_deg: float = 0):
    pts = []
    for i in range(sides):
        angle = math.radians(start_deg + i * 360 / sides)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts


def _draw_ball(size: int) -> Image.Image:
    """Legado — mantido para compatibilidade."""
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx = cy = s / 2.0
    r = s / 2.0 * 0.88  # margem para sombra

    # ── Sombra oval sob a bola ────────────────────────────────────────────
    sx, sy = cx + s * 0.04, cy + r * 0.98
    sr, sh = r * 0.75, r * 0.18
    for i in range(8, 0, -1):
        a = int(8 * i)
        ex = sr + i * s * 0.005
        ey = sh + i * s * 0.003
        draw.ellipse([sx - ex, sy - ey, sx + ex, sy + ey], fill=(0, 0, 0, a))

    # ── Corpo da bola — gradiente radial branco → cinza ───────────────────
    steps = int(r)
    for i in range(steps, 0, -1):
        t = i / r  # 1 = borda, 0 = centro
        gray = int(255 - 90 * (t ** 1.8))
        draw.ellipse([cx - i, cy - i, cx + i, cy + i],
                     fill=(gray, gray, gray, 255))

    # ── Brilho (specular highlight) ───────────────────────────────────────
    hl_cx = cx - r * 0.28
    hl_cy = cy - r * 0.28
    hl_r = r * 0.33
    for i in range(int(hl_r), 0, -1):
        t = i / hl_r
        alpha = int(220 * (t ** 2.2))
        draw.ellipse(
            [hl_cx - i, hl_cy - i, hl_cx + i, hl_cy + i],
            fill=(255, 255, 255, alpha),
        )

    # ── Pentagons pretos — padrão clássico ────────────────────────────────
    if size >= 20:
        pr = r * 0.215  # raio de cada pentágono
        BLACK = (18, 18, 18, 255)
        lw = max(1, int(s * 0.004))

        # Pentágono central (topo da bola, ligeiramente acima do centro)
        top_x, top_y = cx, cy - r * 0.16
        pts = _polygon(top_x, top_y, pr, 5, -90)
        draw.polygon(pts, fill=BLACK)
        if size >= 32:
            draw.polygon(pts, outline=(0, 0, 0, 255), width=lw)

        if size >= 32:
            # 5 pentágonos na faixa intermediária
            ring_r = r * 0.57
            for i in range(5):
                angle_deg = -90.0 + 36.0 + i * 72.0
                angle = math.radians(angle_deg)
                px = cx + ring_r * math.cos(angle)
                # compressão vertical para dar perspectiva de esfera
                py = cy + ring_r * math.sin(angle) * 0.78
                pts2 = _polygon(px, py, pr * 0.82, 5, angle_deg - 72)
                draw.polygon(pts2, fill=BLACK)
                draw.polygon(pts2, outline=(0, 0, 0, 255), width=lw)

    # ── Borda circular da bola ────────────────────────────────────────────
    bw = max(2, int(s * 0.018))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=(15, 15, 15, 255), width=bw)

    # ── Downscale com LANCZOS ─────────────────────────────────────────────
    return img.resize((size, size), Image.LANCZOS)


def create_icon(output_path: str = "assets/icon.ico"):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [draw_icon(s) for s in sizes]

    frames[0].save(
        output_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"Icone gerado: {output_path}  ({len(frames)} tamanhos)")


if __name__ == "__main__":
    create_icon("assets/icon.ico")
    preview = draw_icon(256)
    preview.save("assets/icon_256.png")
    print("Preview: assets/icon_256.png")
