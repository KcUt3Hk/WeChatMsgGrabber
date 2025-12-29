import numpy as np
from PIL import Image
import cv2
import logging
from collections import Counter

logger = logging.getLogger(__name__)

class ImageValidator:
    """
    Validates whether a cropped image region is likely a genuine image message/sticker
    or a misidentified text bubble/garbage.
    
    Enhanced with:
    - Entropy analysis (Information density)
    - Color histogram analysis (Bi-modality check)
    - Edge density analysis (Texture complexity)
    """

    @staticmethod
    def is_valid_image_content(img: Image.Image) -> bool:
        """
        Analyzes image content to determine if it's a valid photo/sticker.
        
        Args:
            img: The PIL Image to analyze.
            
        Returns:
            True if it looks like a valid image, False if it looks like a text bubble/solid block.
        """
        if img is None or img.width == 0 or img.height == 0:
            return False

        try:
            if img.mode != 'RGB':
                img = img.convert('RGB')

            img_np = np.array(img)
            img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

            h, w = img_np.shape[:2]
            if h < 30 or w < 30:
                return False

            # [NEW] Large image heuristic: If it's very large, it's likely a photo or screenshot.
            # Standard text bubbles are usually constrained in width or height.
            # But long text bubbles can be tall. Increasing threshold to avoid false positives.
            if h > 1000 or w > 1000 or (h * w > 800000):
                logger.debug(f"Image accepted by size heuristic: {w}x{h}")
                return True

            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            std = float(np.std(gray))
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist = hist / max(hist.sum(), 1e-9)
            hist = hist[hist > 0]
            entropy = -np.sum(hist * np.log2(hist))

            small = cv2.resize(img_cv, (64, 64), interpolation=cv2.INTER_AREA)
            pixels = small.reshape(-1, 3)
            unique_ratio = float(len(np.unique(pixels, axis=0)) / max(len(pixels), 1))

            counts = Counter([tuple(p) for p in pixels])
            dominance = (counts.most_common(1)[0][1] / max(len(pixels), 1)) if counts else 0.0

            gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            med = float(np.median(gray_small))
            lower = int(max(0, 0.66 * med))
            upper = int(min(255, 1.33 * med))
            edges = cv2.Canny(gray_small, lower, upper)
            edge_density = float(np.count_nonzero(edges) / max(edges.size, 1))

            _, binary_inv = cv2.threshold(gray_small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            fg_ratio = float(cv2.countNonZero(binary_inv) / max(binary_inv.size, 1))

            aspect = float(w / max(h, 1))

            logger.debug(
                f"Image metrics: entropy={entropy:.2f}, std={std:.2f}, unique_ratio={unique_ratio:.2%}, dominance={dominance:.2%}, edge_density={edge_density:.2%}, fg_ratio={fg_ratio:.2%}, aspect={aspect:.2f}"
            )

            # [Fix] Use std dev to rescue low-contrast images (std > 3.5) or high-contrast icons (std > 20)
            # from being classified as empty/solid bubbles.
            is_likely_content = std > 3.5

            square_rescue = (
                0.75 <= aspect <= 1.35
                and min(h, w) >= 60
                and edge_density >= 0.05
                and (fg_ratio >= 0.06 or unique_ratio >= 0.02)
            )

            square_icon_rescue = (
                0.75 <= aspect <= 1.35
                and min(h, w) >= 60
                and edge_density >= 0.05
                and (fg_ratio >= 0.06 or unique_ratio >= 0.02)
            )

            if entropy < 2.4 and dominance > 0.80 and unique_ratio < 0.010:
                if not is_likely_content and not square_rescue:
                    return False

            if entropy < 2.8 and dominance > 0.75 and unique_ratio < 0.015 and edge_density < 0.05:
                if not is_likely_content and not square_rescue:
                    return False

            mask_dark_bg = cv2.inRange(small, np.array([20, 20, 20]), np.array([30, 30, 30]))
            mask_dark_grey = cv2.inRange(small, np.array([39, 39, 39]), np.array([49, 49, 49]))

            mask_light_bg = cv2.inRange(small, np.array([240, 240, 240]), np.array([250, 250, 250]))
            mask_white_bubble = cv2.inRange(small, np.array([250, 250, 250]), np.array([255, 255, 255]))

            mask_green = cv2.inRange(small, np.array([95, 226, 139]), np.array([115, 246, 159]))

            total_pixels = small.shape[0] * small.shape[1]
            ratio_dark_bg = cv2.countNonZero(mask_dark_bg) / total_pixels
            ratio_dark_grey = cv2.countNonZero(mask_dark_grey) / total_pixels
            ratio_light_bg = cv2.countNonZero(mask_light_bg) / total_pixels
            ratio_white = cv2.countNonZero(mask_white_bubble) / total_pixels
            ratio_green = cv2.countNonZero(mask_green) / total_pixels

            ratio_dark_ui = ratio_dark_bg + ratio_dark_grey + ratio_green
            ratio_light_ui = ratio_light_bg + ratio_white + ratio_green

            ui_like = (
                ((ratio_dark_ui > 0.70) and (ratio_green > 0.01) and (ratio_dark_bg > 0.20))
                or ((ratio_light_ui > 0.70) and (ratio_green > 0.01) and (ratio_light_bg > 0.20 or ratio_white > 0.40))
            )

            logger.debug(
                f"UI Analysis: DarkUI={ratio_dark_ui:.2%} (BG={ratio_dark_bg:.2%}), LightUI={ratio_light_ui:.2%} (BG={ratio_light_bg:.2%})"
            )

            if (
                dominance > 0.70
                and fg_ratio < 0.12
                and aspect > 1.25
                and (ratio_white > 0.70 or ratio_light_bg > 0.70 or ratio_dark_bg > 0.60 or ratio_dark_grey > 0.60)
            ):
                if ui_like or (not is_likely_content and not square_rescue):
                    return False

            if ui_like:
                return False

            if ratio_light_ui > 0.70 and (ratio_light_bg > 0.30 or ratio_white > 0.55) and edge_density < 0.08:
                if not is_likely_content and not square_rescue:
                    return False

            if (
                dominance > 0.85
                and unique_ratio < 0.06
                and 0.01 <= fg_ratio <= 0.25
                and edge_density <= 0.22
                and aspect >= 1.2
                and not square_rescue
            ):
                return False

            if entropy < 3.0:
                if is_likely_content:
                    return True
                return unique_ratio >= 0.02 or edge_density >= 0.10

            if entropy < 4.2 and dominance > 0.75 and unique_ratio < 0.02 and edge_density < 0.08:
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating image content: {e}")
            return True

    @staticmethod
    def get_quality_metrics(img: Image.Image) -> dict:
        """Returns metrics for monitoring/debugging."""
        try:
            img_np = np.array(img.convert('RGB'))
            img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist = hist / hist.sum()
            hist = hist[hist > 0]
            entropy = -np.sum(hist * np.log2(hist))
            
            return {"entropy": entropy, "resolution": img.size}
        except:
            return {}
