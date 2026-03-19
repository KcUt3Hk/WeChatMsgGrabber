from PIL import Image, ImageDraw, ImageFont
import os

def create_test_image(path):
    # Create a blank image (chat background color)
    width, height = 800, 600
    image = Image.new('RGB', (width, height), color='#F5F5F5')
    draw = ImageDraw.Draw(image)
    
    # Try to load a font, fallback to default
    try:
        # macOS standard font
        font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 20)
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
        except:
            font = ImageFont.load_default()

    # Draw a received message (white bubble on left)
    # Bubble
    draw.rectangle([20, 50, 220, 100], fill='white', outline='#E0E0E0')
    # Text
    draw.text((30, 60), "Hello, this is a test message", fill='black', font=font)
    
    # Draw a sent message (green bubble on right)
    # Bubble
    draw.rectangle([580, 150, 780, 200], fill='#95EC69', outline='#85D45C')
    # Text
    draw.text((590, 160), "Received, testing export function", fill='black', font=font)

    # Save
    image.save(path)
    print(f"Test image saved to {path}")

if __name__ == "__main__":
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    img_path = os.path.join(output_dir, "debug_full_screen.png")
    create_test_image(img_path)
