from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 600
cols, rows = 4, 2
total = cols * rows

# Layout
padding = 70
grid_w = W - 2 * padding
grid_h = 260
cell_w = grid_w // cols
cell_h = grid_h // rows
radius = 55

bg = (235, 237, 240)          # light gray
empty = (220, 220, 220)       # empty stamp fill
empty_outline = (200, 200, 200)
full = (60, 60, 60)           # filled stamp
full_outline = (60, 60, 60)

def render(n_filled: int) -> Image.Image:
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)

    # Title band / area above grid (optional)
    # d.text((padding, 40), "SPA CLUB", fill=(30,30,30))

    top = 140
    for i in range(total):
        r = i // cols
        c = i % cols
        cx = padding + c * cell_w + cell_w // 2
        cy = top + r * cell_h + cell_h // 2

        if i < n_filled:
            fill, outline = full, full_outline
        else:
            fill, outline = empty, empty_outline

        d.rounded_rectangle(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            radius=18,
            fill=fill,
            outline=outline,
            width=6,
        )

    return im

for n in range(total + 1):
    img = render(n)
    img.save(f"stamps_{n}.png", optimize=True)
    print("wrote", f"stamps_{n}.png")

