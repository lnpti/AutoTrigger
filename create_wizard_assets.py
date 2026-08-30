"""
Gera as imagens de banner e ícone pequeno para o wizard do Inno Setup.
  - wizard_banner.bmp : 497x55 px  (faixa lateral esquerda do instalador)
  - wizard_icon.bmp   : 55x55 px   (ícone no canto do wizard)
"""
import os
import math
from PIL import Image, ImageDraw, ImageFont


def _polygon(cx, cy, r, sides, start_deg=0):
    pts = []
    for i in range(sides):
        a = math.radians(start_deg + i * 360 / sides)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _mini_ball(img: Image.Image, cx: float, cy: float, r: float, alpha: int = 255):
    """Desenha uma bola de futebol simples dentro de uma imagem existente."""
    draw = ImageDraw.Draw(img)

    # Corpo
    for i in range(int(r), 0, -1):
        t = i / r
        gray = int(255 - 70 * (t ** 1.6))
        draw.ellipse([cx - i, cy - i, cx + i, cy + i],
                     fill=(gray, gray, gray, alpha))

    # Highlight
    hl_r = r * 0.32
    for i in range(int(hl_r), 0, -1):
        t = i / hl_r
        draw.ellipse([cx - r*0.28 - i, cy - r*0.28 - i,
                      cx - r*0.28 + i, cy - r*0.28 + i],
                     fill=(255, 255, 255, int(200 * t**2.2)))

    # Pentagons
    if r >= 10:
        pr = r * 0.22
        BLACK = (20, 20, 20, alpha)
        pts = _polygon(cx, cy - r*0.15, pr, 5, -90)
        draw.polygon(pts, fill=BLACK)
        if r >= 18:
            ring = r * 0.58
            for i in range(5):
                ang = math.radians(-54 + i * 72)
                px = cx + ring * math.cos(ang)
                py = cy + ring * math.sin(ang) * 0.78
                draw.polygon(_polygon(px, py, pr*0.82, 5, -54 + i*72 - 72), fill=BLACK)

    # Borda
    lw = max(1, int(r * 0.06))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=(15, 15, 15, alpha), width=lw)


def create_wizard_banner(output_path: str):
    """Banner lateral do Inno Setup: 497x55 px."""
    W, H = 497, 314  # tamanho padrão do wizard image (modern style)
    img = Image.new("RGB", (W, H), (10, 10, 26))  # fundo azul escuro
    draw = ImageDraw.Draw(img)

    # Gradiente vertical
    for y in range(H):
        t = y / H
        r = int(10 + 20 * t)
        g = int(10 + 15 * t)
        b = int(26 + 40 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Bolas decorativas em tamanhos variados
    balls = [
        (80, 160, 55),
        (220, 240, 40),
        (360, 180, 35),
        (430, 80, 28),
        (150, 290, 25),
        (320, 295, 22),
        (460, 260, 18),
    ]
    for bx, by, br in balls:
        ball_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        _mini_ball(ball_layer, bx, by, br, alpha=200)
        img.paste(ball_layer, mask=ball_layer.split()[3])

    # Linha decorativa
    draw.rectangle([0, H - 3, W, H], fill=(79, 195, 247))

    # Texto do produto
    try:
        font_big = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = font_big

    draw.text((20, 30), "AutoTrigger V10", font=font_big, fill=(79, 195, 247))
    draw.text((22, 70), "by RobsonDV", font=font_small, fill=(255, 255, 255))
    draw.text((22, 105), "Automação de disparos por gatilho", font=font_small, fill=(180, 180, 210))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "BMP")
    print(f"Banner gerado: {output_path}")


def create_wizard_icon(output_path: str):
    """Ícone pequeno do wizard: 55x55 px."""
    W = H = 55
    img = Image.new("RGB", (W, H), (10, 10, 26))
    draw = ImageDraw.Draw(img)

    # Fundo degradê
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(10 + 20*t), int(10 + 15*t), int(26 + 40*t)))

    # Bola central
    ball_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _mini_ball(ball_layer, W//2, H//2, H*0.40, alpha=255)
    img.paste(ball_layer, mask=ball_layer.split()[3])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "BMP")
    print(f"Ícone wizard gerado: {output_path}")


if __name__ == "__main__":
    create_wizard_banner("assets/wizard_banner.bmp")
    create_wizard_icon("assets/wizard_icon.bmp")
