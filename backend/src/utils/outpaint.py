"""
Outpainting utilities for aspect preset calculations.

Provides functions to calculate expansion pixels for different aspect ratios
and create masks for outpainting operations.
"""

from typing import Dict, Tuple, Union
from io import BytesIO

# Pillow import with fallback
try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# Supported aspect presets
ASPECT_PRESETS = {
    '16:9': (16, 9),
    '9:16': (9, 16),
    '1:1': (1, 1),
    '4:3': (4, 3),
    'expand_all': None,  # Special case: expand all sides by 50%
}


def calculate_expansion(width: int, height: int, preset: str) -> Dict:
    """
    Calculate expansion pixels for aspect preset.

    Args:
        width: Current image width in pixels
        height: Current image height in pixels
        preset: Aspect preset ('16:9', '9:16', '1:1', '4:3', 'expand_all')

    Returns:
        Dict with:
            - left: pixels to add on left
            - right: pixels to add on right
            - top: pixels to add on top
            - bottom: pixels to add on bottom
            - new_width: final width
            - new_height: final height

    Raises:
        ValueError: If preset is invalid or dimensions are non-positive
    """
    # Validate dimensions
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid dimensions: width={width}, height={height}. Both must be positive.")

    if preset not in ASPECT_PRESETS:
        raise ValueError(f"Invalid preset: {preset}. Valid: {list(ASPECT_PRESETS.keys())}")

    if preset == 'expand_all':
        # Expand each side by 50%
        expand_h = width // 2
        expand_v = height // 2
        return {
            'left': expand_h // 2,
            'right': expand_h - (expand_h // 2),
            'top': expand_v // 2,
            'bottom': expand_v - (expand_v // 2),
            'new_width': width + expand_h,
            'new_height': height + expand_v,
        }

    target_ratio = ASPECT_PRESETS[preset]
    target_w, target_h = target_ratio
    target_ratio_value = target_w / target_h
    current_ratio = width / height

    left = right = top = bottom = 0

    if abs(current_ratio - target_ratio_value) < 0.01:
        # Already at target ratio
        return {
            'left': 0, 'right': 0, 'top': 0, 'bottom': 0,
            'new_width': width, 'new_height': height
        }

    if current_ratio < target_ratio_value:
        # Need to expand horizontally (make wider)
        new_width = int(height * target_ratio_value)
        total_expand = new_width - width
        left = total_expand // 2
        right = total_expand - left
        new_height = height
    else:
        # Need to expand vertically (make taller)
        new_height = int(width / target_ratio_value)
        total_expand = new_height - height
        top = total_expand // 2
        bottom = total_expand - top
        new_width = width

    return {
        'left': left,
        'right': right,
        'top': top,
        'bottom': bottom,
        'new_width': new_width,
        'new_height': new_height,
    }


def create_expansion_mask(
    width: int,
    height: int,
    expansion: Dict,
    mask_format: str = 'bytes'
) -> Union[bytes, str]:
    """
    Create a binary mask with transparent (white) edges for expansion.

    The mask has:
    - Black (0) where the original image is
    - White (255) where expansion should occur

    Args:
        width: Original image width
        height: Original image height
        expansion: Dict from calculate_expansion()
        mask_format: 'bytes' for PNG bytes, 'base64' for base64 string

    Returns:
        Mask image as bytes (when mask_format='bytes') or str (when mask_format='base64')
    """
    if not HAS_PIL:
        raise RuntimeError("PIL/Pillow required for mask creation")

    import base64

    new_width = expansion['new_width']
    new_height = expansion['new_height']

    # Create white image (areas to fill)
    mask = Image.new('L', (new_width, new_height), 255)

    # Draw black rectangle where original image is (using ImageDraw for performance)
    left = expansion['left']
    top = expansion['top']
    right = left + width - 1  # -1 because rectangle is inclusive
    bottom = top + height - 1

    draw = ImageDraw.Draw(mask)
    draw.rectangle([(left, top), (right, bottom)], fill=0)

    # Convert to bytes
    buffer = BytesIO()
    mask.save(buffer, format='PNG')
    mask_bytes = buffer.getvalue()

    if mask_format == 'base64':
        return base64.b64encode(mask_bytes).decode('utf-8')

    return mask_bytes


def pad_image_with_transparency(
    image_bytes: bytes,
    expansion: Dict
) -> bytes:
    """
    Pad an image with transparent pixels for outpainting.

    Creates a new image with the original centered and transparent
    pixels around the edges.

    Args:
        image_bytes: Original image bytes
        expansion: Dict from calculate_expansion()

    Returns:
        Padded image as PNG bytes
    """
    if not HAS_PIL:
        raise RuntimeError("PIL/Pillow required for image padding")

    # Load original image
    original = Image.open(BytesIO(image_bytes))

    # Convert to RGBA if needed
    if original.mode != 'RGBA':
        original = original.convert('RGBA')

    new_width = expansion['new_width']
    new_height = expansion['new_height']

    # Create new transparent image
    padded = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))

    # Paste original image at offset
    left = expansion['left']
    top = expansion['top']
    padded.paste(original, (left, top))

    # Convert to bytes
    buffer = BytesIO()
    padded.save(buffer, format='PNG')
    return buffer.getvalue()


def get_direction_description(preset: str) -> str:
    """
    Get human-readable direction description for prompt-based outpainting.

    Used for providers like Gemini that use prompt-based expansion.

    Args:
        preset: Aspect preset

    Returns:
        Direction description string
    """
    descriptions = {
        '16:9': 'horizontally to the left and right to create a wider landscape view',
        '9:16': 'vertically above and below to create a taller portrait view',
        '1:1': 'to make it square, extending the shorter dimension',
        '4:3': 'to reach a 4:3 aspect ratio',
        'expand_all': 'in all directions to show more of the surrounding scene',
    }
    return descriptions.get(preset, 'to expand the scene')


def get_image_dimensions(image_bytes: bytes) -> Tuple[int, int]:
    """
    Get dimensions of an image from bytes.

    Args:
        image_bytes: Image bytes

    Returns:
        Tuple of (width, height)
    """
    if not HAS_PIL:
        raise RuntimeError("PIL/Pillow required for image dimension detection")

    image = Image.open(BytesIO(image_bytes))
    return image.size


def get_openai_compatible_size(target_width: int, target_height: int) -> str:
    """
    Get the closest OpenAI-compatible size for gpt-image-1.

    OpenAI only supports: 1024x1024, 1024x1536 (portrait), 1536x1024 (landscape)

    Args:
        target_width: Desired width in pixels
        target_height: Desired height in pixels

    Returns:
        Size string in format "WIDTHxHEIGHT"
    """
    # OpenAI supported sizes for gpt-image-1
    OPENAI_SIZES = [
        (1024, 1024),   # Square
        (1536, 1024),   # Landscape
        (1024, 1536),   # Portrait
    ]

    target_ratio = target_width / target_height

    # Find closest aspect ratio match
    best_size = (1024, 1024)
    best_diff = float('inf')

    for w, h in OPENAI_SIZES:
        size_ratio = w / h
        diff = abs(size_ratio - target_ratio)
        if diff < best_diff:
            best_diff = diff
            best_size = (w, h)

    return f"{best_size[0]}x{best_size[1]}"
