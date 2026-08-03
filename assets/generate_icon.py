"""Generate AirNode app icons (PNG + ICO).

Run from the project root:
    python assets/generate_icon.py

Creates:
    assets/airnode-icon.png   (512x512 RGBA PNG)
    assets/airnode-icon.ico   (multi-size ICO for the exe)

Uses Pillow — install with: pip install Pillow
"""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow is required. Install with: pip install Pillow")
    raise SystemExit(1)


ASSETS_DIR = Path(__file__).resolve().parent


def create_icon(size: int = 512) -> Image.Image:
    """Draw a rounded-square blue icon with a white 'A' letter."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background: rounded rectangle / circle
    margin = size // 16
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 8,
        fill=(59, 130, 246, 255),  # Tailwind blue-500
    )

    # Draw the letter 'A'
    font_size = int(size * 0.55)
    try:
        # Try common font paths; fall back to default on failure
        import sys
        candidates = []
        if sys.platform == "win32":
            candidates = [
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/arial.ttf",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
            ]
        font = None
        for path in candidates:
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()
        # Draw 'A' centered using textbbox for accurate positioning
        bbox = draw.textbbox((0, 0), "A", font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) // 2 - bbox[0]
        y = (size - text_height) // 2 - bbox[1]
        draw.text((x, y), "A", fill=(255, 255, 255, 255), font=font)
    except Exception:
        # Fallback: draw a simple triangle for 'A'
        draw.polygon(
            [
                (size * 0.35, size * 0.65),
                (size * 0.5, size * 0.25),
                (size * 0.65, size * 0.65),
            ],
            fill=(255, 255, 255, 255),
        )

    return img


def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    png_path = ASSETS_DIR / "airnode-icon.png"
    icon = create_icon(512)
    icon.save(png_path, "PNG")
    print(f"Saved {png_path}")

    # Create multi-size ICO
    ico_path = ASSETS_DIR / "airnode-icon.ico"
    icon.save(
        ico_path,
        "ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Saved {ico_path}")


if __name__ == "__main__":
    main()