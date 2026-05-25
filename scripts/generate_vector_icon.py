#!/usr/bin/env python3
"""
Generate a pixel-perfect, vector-sharp macOS app icon using Pillow.
Creates a solid white circle with an orange dollar sign ($) on a transparent background.
Uses 4x supersampling to ensure perfect anti-aliasing.
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Define paths
PROJECT_DIR = Path("/Users/carson/Documents/R_Projects/budgeting_tool").resolve()
OUTPUT_PNG = PROJECT_DIR / "resources" / "app_icon_white_circle.png"

# Colors
ORANGE_RGB = (255, 103, 25, 255)  # #FF6719 (Substack orange)
WHITE_RGB = (255, 255, 255, 255)
TRANSPARENT_RGB = (0, 0, 0, 0)

def generate_icon():
    print("Generating transparent vector-style app icon...")
    
    # 1. We work at 4x supersampling (4096 x 4096) for crisp anti-aliased curves
    base_size = 1024
    scale = 4
    canvas_size = base_size * scale
    
    # Create transparent canvas
    img = Image.new("RGBA", (canvas_size, canvas_size), TRANSPARENT_RGB)
    draw = ImageDraw.Draw(img)
    
    # 2. Draw white circle
    # Circle diameter: leave a small padding (standard for macOS icons is ~7.5% - 10% padding)
    padding = 72 * scale
    circle_bbox = [
        padding, 
        padding, 
        canvas_size - padding, 
        canvas_size - padding
    ]
    draw.ellipse(circle_bbox, fill=WHITE_RGB)
    
    # 3. Load font and render the dollar sign
    # Find a beautiful serif font on macOS
    font_paths = [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/Library/Fonts/Georgia Bold.ttf",
        "/Library/Fonts/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    ]
    
    font_path = None
    for path in font_paths:
        if Path(path).exists():
            font_path = path
            break
            
    if not font_path:
        print("Warning: Could not find Georgia or Times New Roman, falling back to default font.")
        font = ImageFont.load_default()
        font_size = 300 * scale
    else:
        # Load font. Font size is ~55% of canvas height
        font_size = int(canvas_size * 0.55)
        font = ImageFont.truetype(font_path, font_size)
        print(f"Loaded font: {font_path} at size {font_size}")
        
    # Get text dimensions to center it perfectly
    text = "$"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    
    # Calculate position to center the glyph optically
    # Georgia's dollar sign is tall and has slightly offset bounds.
    # Align mathematically, but shift up slightly if needed for optical weight
    x = (canvas_size - text_w) / 2 - text_bbox[0]
    y = (canvas_size - text_h) / 2 - text_bbox[1]
    
    # Render text
    draw.text((x, y), text, font=font, fill=ORANGE_RGB)
    
    # 4. Downsample to 1024x1024 using Lanczos resampling for gorgeous anti-aliasing
    OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    resized_img = img.resize((base_size, base_size), Image.Resampling.LANCZOS)
    resized_img.save(OUTPUT_PNG, "PNG")
    
    print(f"✓ Successfully generated clean transparent PNG icon at: {OUTPUT_PNG}")


if __name__ == "__main__":
    generate_icon()
