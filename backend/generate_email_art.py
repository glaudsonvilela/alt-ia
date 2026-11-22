"""Generate the email-only Alt-IA mascot art (requires Pillow when editing)."""

from pathlib import Path

from PIL import Image, ImageDraw


HERE = Path(__file__).parent
SCALE = 2


def mascot(draw, cx, cy, radius, color, shape="round", glasses=False, fire=False):
    x, y, r = cx * SCALE, cy * SCALE, radius * SCALE
    if shape == "octagon":
        points = [(x-r*.65,y-r),(x+r*.65,y-r),(x+r,y-r*.65),(x+r,y+r*.65),
                  (x+r*.65,y+r),(x-r*.65,y+r),(x-r,y+r*.65),(x-r,y-r*.65)]
        draw.polygon(points, fill=color)
    else:
        draw.rounded_rectangle((x-r,y-r,x+r,y+r), radius=r*.72, fill=color)
    for offset in (-.35, .35):
        ex = x + offset*r
        draw.ellipse((ex-r*.23,y-r*.35,ex+r*.23,y+r*.30), fill="#fffdfd")
        pupil = "#fb5722" if fire else "#24202c"
        draw.ellipse((ex-r*.02,y-r*.04,ex+r*.18,y+r*.25), fill=pupil)
        draw.ellipse((ex+r*.01,y-r*.12,ex+r*.07,y-r*.04), fill="white")
    if glasses:
        for offset in (-.35, .35):
            ex = x + offset*r
            draw.rounded_rectangle((ex-r*.29,y-r*.44,ex+r*.29,y+r*.39),
                                   radius=r*.12, outline="#26334f", width=5*SCALE)
        draw.line((x-r*.06,y-r*.08,x+r*.06,y-r*.08), fill="#26334f", width=5*SCALE)
        draw.rounded_rectangle((x-r*.13,y+r*.52,x+r*.13,y+r*.68), radius=3*SCALE, fill="white")
    elif not fire:
        draw.arc((x-r*.24,y+r*.25,x+r*.24,y+r*.65), 5, 175, fill="#5a274a", width=3*SCALE)


def make_banner():
    width, height = 880, 270
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    stops = ((255, 131, 31), (245, 143, 180), (139, 117, 226))
    for x in range(width):
        position = x / (width - 1) * 2
        index = min(int(position), 1)
        fraction = position - index
        color = tuple(round(stops[index][channel]*(1-fraction) + stops[index+1][channel]*fraction)
                      for channel in range(3))
        for y in range(height):
            pixels[x, y] = color
    draw = ImageDraw.Draw(image)
    draw.ellipse((34, 28, 78, 72), fill="#ffe071")
    draw.rounded_rectangle((755, 29, 797, 71), radius=10, fill="#6ee0b4")
    draw.polygon(((443, 23), (456, 37), (443, 51), (430, 37)), fill="#fff0b6")
    draw.ellipse((516, 216, 534, 234), fill="#ffe9f2")
    draw.polygon(((230, 215), (253, 232), (230, 249), (207, 232)), fill="#a9c6ff")
    mascot(draw, 65, 68, 42, "#fba7c4", shape="octagon")
    mascot(draw, 165, 65, 38, "#ab81e6")
    mascot(draw, 270, 68, 38, "#91b0f2", glasses=True)
    mascot(draw, 375, 65, 38, "#ed8c6e", fire=True)
    image.save(HERE / "email_mascots.png", optimize=True)


def make_icon():
    image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    mascot(draw, 24, 24, 20, "#fba7c4", shape="octagon")
    image.save(HERE / "email_mascot_icon.png", optimize=True)


if __name__ == "__main__":
    make_banner()
    make_icon()
