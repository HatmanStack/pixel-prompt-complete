"""
Unit tests for outpainting utilities.
"""

import pytest


class TestCalculateExpansion:
    """Tests for calculate_expansion() function."""

    def test_16_9_expands_horizontally(self):
        """16:9 preset should expand horizontally for portrait image."""
        from utils.outpaint import calculate_expansion

        # Start with 1:1 (1024x1024)
        result = calculate_expansion(1024, 1024, '16:9')

        # Should expand horizontally
        assert result['left'] > 0 or result['right'] > 0
        assert result['top'] == 0
        assert result['bottom'] == 0

        # Verify aspect ratio
        ratio = result['new_width'] / result['new_height']
        assert abs(ratio - (16/9)) < 0.05

    def test_9_16_expands_vertically(self):
        """9:16 preset should expand vertically for landscape image."""
        from utils.outpaint import calculate_expansion

        # Start with 1:1 (1024x1024)
        result = calculate_expansion(1024, 1024, '9:16')

        # Should expand vertically
        assert result['top'] > 0 or result['bottom'] > 0
        assert result['left'] == 0
        assert result['right'] == 0

        # Verify aspect ratio
        ratio = result['new_width'] / result['new_height']
        assert abs(ratio - (9/16)) < 0.05

    def test_1_1_no_expansion_for_square(self):
        """1:1 preset should not expand already square image."""
        from utils.outpaint import calculate_expansion

        result = calculate_expansion(1024, 1024, '1:1')

        assert result['left'] == 0
        assert result['right'] == 0
        assert result['top'] == 0
        assert result['bottom'] == 0
        assert result['new_width'] == 1024
        assert result['new_height'] == 1024

    def test_4_3_expansion(self):
        """4:3 preset should create correct ratio."""
        from utils.outpaint import calculate_expansion

        # Start with 16:9 (1920x1080)
        result = calculate_expansion(1920, 1080, '4:3')

        ratio = result['new_width'] / result['new_height']
        assert abs(ratio - (4/3)) < 0.05

    def test_expand_all_increases_both_dimensions(self):
        """expand_all preset should expand all sides by ~50%."""
        from utils.outpaint import calculate_expansion

        result = calculate_expansion(1024, 1024, 'expand_all')

        # Should expand all sides
        assert result['left'] > 0
        assert result['right'] > 0
        assert result['top'] > 0
        assert result['bottom'] > 0

        # Total expansion should be ~50%
        assert result['new_width'] > 1024
        assert result['new_height'] > 1024

    def test_invalid_preset_raises_error(self):
        """Invalid preset should raise ValueError."""
        from utils.outpaint import calculate_expansion

        with pytest.raises(ValueError) as excinfo:
            calculate_expansion(1024, 1024, 'invalid_preset')

        assert 'invalid preset' in str(excinfo.value).lower()

    def test_expansion_is_symmetric(self):
        """Expansion should be roughly symmetric on opposite sides."""
        from utils.outpaint import calculate_expansion

        result = calculate_expansion(1024, 1024, '16:9')

        # Left and right should be roughly equal (or differ by at most 1)
        assert abs(result['left'] - result['right']) <= 1


class TestGetDirectionDescription:
    """Tests for get_direction_description() function."""

    def test_returns_horizontal_for_16_9(self):
        """16:9 should return horizontal expansion description."""
        from utils.outpaint import get_direction_description

        desc = get_direction_description('16:9')

        assert 'horizontal' in desc.lower() or 'left' in desc.lower() or 'right' in desc.lower()

    def test_returns_vertical_for_9_16(self):
        """9:16 should return vertical expansion description."""
        from utils.outpaint import get_direction_description

        desc = get_direction_description('9:16')

        assert 'vertical' in desc.lower() or 'above' in desc.lower() or 'below' in desc.lower()

    def test_returns_all_directions_for_expand_all(self):
        """expand_all should return all-direction description."""
        from utils.outpaint import get_direction_description

        desc = get_direction_description('expand_all')

        assert 'all' in desc.lower()


class TestCreateExpansionMask:
    """Tests for create_expansion_mask() function."""

    @pytest.fixture
    def expansion_data(self):
        """Sample expansion data."""
        return {
            'left': 128,
            'right': 128,
            'top': 0,
            'bottom': 0,
            'new_width': 1280,  # 1024 + 256
            'new_height': 1024
        }

    def test_returns_bytes(self, expansion_data):
        """create_expansion_mask() should return bytes by default."""
        from utils.outpaint import create_expansion_mask

        result = create_expansion_mask(1024, 1024, expansion_data)

        assert isinstance(result, bytes)
        # Should be PNG format
        assert result[:8] == b'\x89PNG\r\n\x1a\n'

    def test_returns_base64_when_specified(self, expansion_data):
        """create_expansion_mask() should return base64 when specified."""
        from utils.outpaint import create_expansion_mask
        import base64

        result = create_expansion_mask(1024, 1024, expansion_data, mask_format='base64')

        assert isinstance(result, str)
        # Should be valid base64
        decoded = base64.b64decode(result)
        assert decoded[:8] == b'\x89PNG\r\n\x1a\n'


class TestPadImageWithTransparency:
    """Tests for pad_image_with_transparency() function."""

    @pytest.fixture
    def sample_image_bytes(self):
        """Create sample PNG image bytes."""
        from PIL import Image
        from io import BytesIO

        img = Image.new('RGB', (100, 100), color='red')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()

    @pytest.fixture
    def expansion_data(self):
        """Sample expansion data."""
        return {
            'left': 50,
            'right': 50,
            'top': 50,
            'bottom': 50,
            'new_width': 200,
            'new_height': 200
        }

    def test_returns_png_bytes(self, sample_image_bytes, expansion_data):
        """pad_image_with_transparency() should return PNG bytes."""
        from utils.outpaint import pad_image_with_transparency

        result = pad_image_with_transparency(sample_image_bytes, expansion_data)

        assert isinstance(result, bytes)
        assert result[:8] == b'\x89PNG\r\n\x1a\n'

    def test_output_has_correct_dimensions(self, sample_image_bytes, expansion_data):
        """Padded image should have correct dimensions."""
        from utils.outpaint import pad_image_with_transparency
        from PIL import Image
        from io import BytesIO

        result = pad_image_with_transparency(sample_image_bytes, expansion_data)

        # Load and check dimensions
        img = Image.open(BytesIO(result))
        assert img.size == (200, 200)


class TestGetImageDimensions:
    """Tests for get_image_dimensions() function."""

    def test_returns_width_height_tuple(self):
        """get_image_dimensions() should return (width, height) tuple."""
        from utils.outpaint import get_image_dimensions
        from PIL import Image
        from io import BytesIO

        # Create test image
        img = Image.new('RGB', (640, 480), color='blue')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        image_bytes = buffer.getvalue()

        width, height = get_image_dimensions(image_bytes)

        assert width == 640
        assert height == 480
