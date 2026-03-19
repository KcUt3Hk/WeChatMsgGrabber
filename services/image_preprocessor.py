"""
Image preprocessing module for OCR optimization.
Handles image quality enhancement, noise reduction, and text region detection.
"""
import logging
from typing import List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from models.data_models import Rectangle, TextRegion


class ImagePreprocessor:
    """
    Image preprocessing utilities for OCR optimization.
    """
    
    def __init__(self):
        """Initialize image preprocessor.
        函数级注释：
        - 启用 OpenCV 的优化路径（如 SSE/NEON），减少滤波等操作的耗时；
        - 在部分平台（如 macOS/Apple Silicon）上，该设置可带来稳定的性能提升。
        """
        self.logger = logging.getLogger(__name__)
        try:
            # 开启 OpenCV 内部优化（如向量化/并行优化），提升降噪与阈值处理性能
            cv2.setUseOptimized(True)
        except Exception:
            # 非致命：若 OpenCV 不支持该调用，忽略即可
            pass
    
    def enhance_image_quality(self, image: Image.Image, 
                            contrast_factor: float = 1.2,
                            brightness_factor: float = 1.1,
                            sharpness_factor: float = 1.1) -> Image.Image:
        """
        Enhance image quality for better OCR recognition.
        
        Args:
            image: Input PIL Image
            contrast_factor: Contrast enhancement factor (1.0 = no change)
            brightness_factor: Brightness enhancement factor (1.0 = no change)
            sharpness_factor: Sharpness enhancement factor (1.0 = no change)
            
        Returns:
            PIL Image: Enhanced image
        """
        try:
            enhanced_image = image.copy()
            
            # Enhance contrast
            if contrast_factor != 1.0:
                enhancer = ImageEnhance.Contrast(enhanced_image)
                enhanced_image = enhancer.enhance(contrast_factor)
            
            # Enhance brightness
            if brightness_factor != 1.0:
                enhancer = ImageEnhance.Brightness(enhanced_image)
                enhanced_image = enhancer.enhance(brightness_factor)
            
            # Enhance sharpness
            if sharpness_factor != 1.0:
                enhancer = ImageEnhance.Sharpness(enhanced_image)
                enhanced_image = enhancer.enhance(sharpness_factor)
            
            self.logger.debug("Image quality enhanced successfully")
            return enhanced_image
            
        except Exception as e:
            self.logger.error(f"Image enhancement failed: {e}")
            return image
    
    def reduce_noise(self, image: Image.Image, method: str = "gaussian") -> Image.Image:
        """
        Reduce noise in image to improve OCR accuracy.
        
        Args:
            image: Input PIL Image
            method: Noise reduction method ("gaussian", "median", "bilateral")
            
        Returns:
            PIL Image: Denoised image
        """
        try:
            # Convert PIL to OpenCV format
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            if method == "gaussian":
                # Gaussian blur for noise reduction
                denoised = cv2.GaussianBlur(cv_image, (3, 3), 0)
            elif method == "median":
                # Median filter for salt-and-pepper noise
                denoised = cv2.medianBlur(cv_image, 3)
            elif method == "bilateral":
                # Bilateral filter preserves edges while reducing noise
                denoised = cv2.bilateralFilter(cv_image, 9, 75, 75)
            else:
                self.logger.warning(f"Unknown noise reduction method: {method}")
                return image
            
            return Image.fromarray(cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB))
            
        except Exception as e:
            self.logger.error(f"Noise reduction failed: {e}")
            return image

    def is_text_bubble(self, image: Image.Image) -> bool:
        """
        Check if the image is likely a text-only bubble (Solid Background + sparse text).
        Distinguishes from Chat Screenshots which have solid background but complex content.
        
        Logic:
        - Text Bubble: Very high dominant color (>60%) AND very low second color (<5%).
        - Chat Screenshot: High dominant color (50-60%) BUT high second color (>10%).
        """
        try:
            # 1. Resize for performance (small enough to be fast, large enough to be representative)
            w, h = image.size
            if w * h > 6400: # > 80x80
                scale = 80.0 / max(w, h)
                new_size = (int(w * scale), int(h * scale))
                img_small = image.resize(new_size, Image.Resampling.NEAREST)
            else:
                img_small = image

            # 2. Quantize to reduce color variations
            if img_small.mode != 'P':
                img_quantized = img_small.quantize(colors=32)
            else:
                img_quantized = img_small

            # 3. Analyze Histogram
            histogram = img_quantized.histogram()
            if not histogram:
                return False

            total_pixels = img_small.width * img_small.height
            if total_pixels == 0:
                return False

            # Get Top 3 ratios
            sorted_counts = sorted(histogram, reverse=True)
            top1_ratio = sorted_counts[0] / total_pixels
            top2_ratio = sorted_counts[1] / total_pixels if len(sorted_counts) > 1 else 0
            top3_ratio = sorted_counts[2] / total_pixels if len(sorted_counts) > 2 else 0
            
            # Debug info
            # self.logger.debug(f"Color Ratios: Top1={top1_ratio:.2f}, Top2={top2_ratio:.2f}, Top3={top3_ratio:.2f}")

            # Criteria for Text Bubble:
            # A text bubble typically has a dominant background color AND low color complexity (few unique colors).
            # An image (even on a background) will have high color complexity (many unique colors).
            
            # 获取前5种颜色的占比总和
            top5_count = sum(c for c in sorted_counts[:5])
            top5_ratio = top5_count / total_pixels
            
            # 1. Must have a dominant background (at least 60%)
            if top1_ratio > 0.60:
                # 2. Must be low complexity (Top 5 colors cover > 90% of image)
                # 3. Secondary color shouldn't be too large (< 15%)
                if top5_ratio > 0.90 and top2_ratio < 0.22:
                    # Final Structural Check: Text bubbles have regular text lines.
                    # Memes (even B&W) often have irregular shapes or large connected components.
                    if self.has_text_line_structure(image):
                        return True
            
            return False

        except Exception as e:
            self.logger.error(f"Text bubble check failed: {e}")
            return False

    def has_text_line_structure(self, image: Image.Image) -> bool:
        """
        Check if the image exhibits the structural characteristics of a text bubble.
        Text bubbles typically contain multiple small, regularly spaced connected components (letters).
        Memes/Images typically contain few large components or irregular shapes.
        """
        try:
            # Convert to grayscale and binary (inverse: text/content is white, bg is black)
            # Resize for speed if too large
            w, h = image.size
            if w * h > 40000: # 200x200
                scale = 200.0 / max(w, h)
                img_small = image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            else:
                img_small = image

            # Convert to grayscale
            if img_small.mode != 'L':
                gray = img_small.convert('L')
            else:
                gray = img_small
            
            arr = np.array(gray)

            block_size = 11
            cand = []
            try:
                cand.append(
                    cv2.adaptiveThreshold(
                        arr,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        block_size,
                        2,
                    )
                )
                cand.append(
                    cv2.adaptiveThreshold(
                        arr,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY_INV,
                        block_size,
                        2,
                    )
                )
            except Exception:
                pass
            try:
                _, otsu = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                cand.append(otsu)
                cand.append(cv2.bitwise_not(otsu))
            except Exception:
                pass

            if not cand:
                return False

            total = float(arr.shape[0] * arr.shape[1])
            scored = []
            for b in cand:
                if b is None or b.size == 0:
                    continue
                fg_ratio = float(np.count_nonzero(b)) / max(total, 1.0)
                scored.append((abs(fg_ratio - 0.06), fg_ratio, b))

            if not scored:
                return False

            scored.sort(key=lambda x: (x[0], x[1]))
            chosen = None
            for _, fg_ratio, b in scored:
                if 0.005 <= fg_ratio <= 0.25:
                    chosen = b
                    break
            if chosen is None:
                chosen = scored[0][2]
            binary = chosen
            
            # Connected Components Analysis
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
            
            # stats: [x, y, w, h, area]
            # Label 0 is background
            if num_labels <= 1:
                return False # Empty image
            
            # Filter out tiny noise (e.g. < 5 pixels)
            valid_components = []
            img_area = arr.shape[0] * arr.shape[1]
            
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area > 5 and area < int(img_area * 0.25):
                    valid_components.append(stats[i])
            
            if not valid_components:
                valid_components = []

            num_comps = len(valid_components)
            
            # Heuristic 1: Text bubbles usually have many components (letters) relative to their size
            # Memes might have 1 big component (face) or just a few.
            # But short text ("Hi") has few components too.
            
            # Heuristic 2: Component Height Variance
            # Text letters usually have similar heights.
            # Memes have varying component sizes.
            heights = [c[cv2.CC_STAT_HEIGHT] for c in valid_components]
            avg_height = np.mean(heights)
            std_height = np.std(heights)
            cv = std_height / avg_height if avg_height > 0 else 0
            
            # Heuristic 3: Max Component Area
            # In a text bubble, no single letter should dominate the area (e.g. > 20% of image).
            # In a meme, the main subject often covers a large portion.
            max_area = max([c[cv2.CC_STAT_AREA] for c in valid_components])
            max_area_ratio = max_area / img_area
            
            # Heuristic 4: Component Density (Fill Rate of bounding box)
            # Text is sparse. Drawings can be dense.
            
            # Decision Logic:
            
            # Case A: Very few components (e.g. < 5). Could be short text or simple icon.
            if num_comps < 5:
                if num_comps <= 2:
                    return False
                    
                # If components are small and similar height -> Short text
                # Tightened threshold from 0.5 to 0.35 to exclude simple charts/icons (which might have CV ~0.37)
                if cv < 0.55 and max_area_ratio < 0.10:
                    return True # Short text
                return False # Irregular icon
            
            # Case B: Many components.
            else:
                # If one component is huge -> Image (e.g. text with a big icon, or meme)
                if max_area_ratio > 0.12:
                    valid_components = []

                if valid_components:
                    if cv < 0.9:
                        return True
                    return False

            if not valid_components:
                edges = cv2.Canny(arr, 50, 150)
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                edges = cv2.dilate(edges, kernel, iterations=1)
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                    edges, connectivity=8
                )

                valid_edges = []
                h_img, w_img = edges.shape[:2]
                img_area = float(h_img * w_img)
                for i in range(1, num_labels):
                    x = int(stats[i, cv2.CC_STAT_LEFT])
                    y = int(stats[i, cv2.CC_STAT_TOP])
                    w = int(stats[i, cv2.CC_STAT_WIDTH])
                    h = int(stats[i, cv2.CC_STAT_HEIGHT])
                    area = int(stats[i, cv2.CC_STAT_AREA])
                    if area <= 5:
                        continue
                    if area >= int(img_area * 0.25):
                        continue
                    if x <= 1 or y <= 1 or (x + w) >= (w_img - 1) or (y + h) >= (h_img - 1):
                        continue
                    valid_edges.append(stats[i])

                if not valid_edges:
                    return False

                try:
                    pad = 6
                    if min(h_img, w_img) < 20:
                        pad = 2
                    if h_img > 2 * pad and w_img > 2 * pad:
                        core = edges[pad : (h_img - pad), pad : (w_img - pad)]
                    else:
                        core = edges
                    core_area = float(core.shape[0] * core.shape[1])
                    core_edge_density = float(np.count_nonzero(core)) / max(core_area, 1.0)
                except Exception:
                    core_edge_density = float(np.count_nonzero(edges)) / max(img_area, 1.0)

                try:
                    valid_edges = sorted(
                        valid_edges,
                        key=lambda s: int(s[cv2.CC_STAT_AREA]),
                        reverse=True,
                    )
                    if len(valid_edges) >= 2:
                        s0 = valid_edges[0]
                        bw = float(s0[cv2.CC_STAT_WIDTH])
                        bh = float(s0[cv2.CC_STAT_HEIGHT])
                        ba = float(s0[cv2.CC_STAT_AREA])
                        cover = (bw * bh) / max(img_area, 1.0)
                        if cover > 0.55 or (ba / max(img_area, 1.0)) > 0.08:
                            valid_edges = valid_edges[1:]
                except Exception:
                    pass

                if not valid_edges:
                    return False

                heights = [c[cv2.CC_STAT_HEIGHT] for c in valid_edges]
                avg_height = float(np.mean(heights))
                std_height = float(np.std(heights))
                cv = std_height / avg_height if avg_height > 0 else 0
                max_area = max([c[cv2.CC_STAT_AREA] for c in valid_edges])
                max_area_ratio = float(max_area) / max(img_area, 1.0)
                num_comps = len(valid_edges)

                if 0.002 <= core_edge_density <= 0.08 and 1 <= num_comps <= 80 and max_area_ratio < 0.10 and cv < 1.8:
                    return True

                return False
                
        except Exception as e:
            # self.logger.error(f"Structure check failed: {e}")
            return False # Fail safe: Assume image (don't filter)

    def is_solid_background(self, image: Image.Image, threshold: float = 0.35) -> bool:
        """
        Check if the image has a solid background color (indicative of a text bubble).
        Uses color quantization to find if a single color dominates the image.
        
        Args:
            image: PIL Image
            threshold: Minimum ratio of the dominant color (0.0 - 1.0). 
                       Text bubbles usually have > 40% background pixels.
            
        Returns:
            bool: True if likely a solid background
        """
        try:
            # 1. Resize for performance (small enough to be fast, large enough to be representative)
            w, h = image.size
            if w * h > 6400: # > 80x80
                scale = 80.0 / max(w, h)
                new_size = (int(w * scale), int(h * scale))
                img_small = image.resize(new_size, Image.Resampling.NEAREST)
            else:
                img_small = image

            # 2. Quantize to reduce color variations (e.g. compression artifacts)
            # 32 colors is enough to group similar shades of green/white
            if img_small.mode != 'P':
                img_quantized = img_small.quantize(colors=32)
            else:
                img_quantized = img_small

            # 3. Calculate dominant color ratio
            # getpalette() returns RGB sequences, but we just need the histogram of indices
            histogram = img_quantized.histogram()
            
            if not histogram:
                return False

            max_freq = max(histogram)
            total_pixels = img_small.width * img_small.height
            
            if total_pixels == 0:
                return False

            ratio = max_freq / total_pixels
            
            # self.logger.debug(f"Dominant color ratio: {ratio:.2f}")
            return ratio > threshold

        except Exception as e:
            self.logger.error(f"Solid background check failed: {e}")
            return False
    
    def convert_to_grayscale(self, image: Image.Image) -> Image.Image:
        """
        Convert image to grayscale for better OCR performance.
        
        Args:
            image: Input PIL Image
            
        Returns:
            PIL Image: Grayscale image
        """
        try:
            if image.mode != 'L':
                grayscale_image = image.convert('L')
                self.logger.debug("Image converted to grayscale")
                return grayscale_image
            return image
        except Exception as e:
            self.logger.error(f"Grayscale conversion failed: {e}")
            return image
    
    def apply_threshold(self, image: Image.Image, 
                       threshold_value: int = 127,
                       method: str = "binary") -> Image.Image:
        """
        Apply thresholding to create binary image for better text recognition.
        
        Args:
            image: Input PIL Image (should be grayscale)
            threshold_value: Threshold value (0-255)
            method: Thresholding method ("binary", "adaptive", "otsu")
            
        Returns:
            PIL Image: Thresholded binary image
        """
        try:
            # Convert to OpenCV format
            cv_image = np.array(image)
            
            if method == "binary":
                _, binary_image = cv2.threshold(cv_image, threshold_value, 255, cv2.THRESH_BINARY)
            elif method == "adaptive":
                binary_image = cv2.adaptiveThreshold(
                    cv_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
                )
            elif method == "otsu":
                _, binary_image = cv2.threshold(cv_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                self.logger.warning(f"Unknown threshold method: {method}")
                return image
            
            # Convert back to PIL
            result_image = Image.fromarray(binary_image)
            
            self.logger.debug(f"Thresholding applied using {method} method")
            return result_image
            
        except Exception as e:
            self.logger.error(f"Thresholding failed: {e}")
            return image

    def _compute_robust_edges(self, gray: np.ndarray) -> np.ndarray:
        """在不同亮度/对比度下生成更稳定的边缘图。"""
        try:
            if gray.ndim != 2:
                gray2 = gray.astype(np.uint8)
            else:
                gray2 = gray.astype(np.uint8)

            blur = cv2.GaussianBlur(gray2, (3, 3), 0)
            gx = cv2.Sobel(blur, cv2.CV_16S, 1, 0, ksize=3)
            gy = cv2.Sobel(blur, cv2.CV_16S, 0, 1, ksize=3)
            absx = cv2.convertScaleAbs(gx)
            absy = cv2.convertScaleAbs(gy)
            mag = cv2.addWeighted(absx, 0.5, absy, 0.5, 0)

            p90 = float(np.percentile(mag, 90))
            upper = int(max(60.0, min(220.0, p90)))
            lower = int(max(10.0, 0.45 * upper))

            edges = cv2.Canny(blur, lower, upper, apertureSize=3)
            return edges
        except Exception:
            try:
                return cv2.Canny(gray.astype(np.uint8), 50, 150)
            except Exception:
                return np.zeros_like(gray, dtype=np.uint8)
    
    def detect_content_roi(self, image: Image.Image, padding: int = 20) -> Rectangle:
        """
        Detect the main content region (ROI) to exclude static borders and empty backgrounds.
        Uses projection analysis to find the "active" area of the screenshot.
        
        Args:
            image: Input PIL Image
            padding: Padding pixels to add around the detected content
            
        Returns:
            Rectangle: The bounding box of the content area relative to the image
        """
        try:
            w_full, h_full = int(image.width), int(image.height)
            if w_full <= 0 or h_full <= 0:
                return Rectangle(0, 0, 0, 0)

            try:
                max_side = 1600
                scale_down = 1.0
                shot_for_detect = image
                if max(w_full, h_full) > max_side:
                    scale_down = float(max(w_full, h_full)) / float(max_side)
                    nw = max(1, int(round(w_full / scale_down)))
                    nh = max(1, int(round(h_full / scale_down)))
                    shot_for_detect = image.resize((nw, nh), Image.BILINEAR)

                chat_roi_small = self.detect_chat_area_smart(shot_for_detect)
                chat_roi = Rectangle(
                    x=int(round(chat_roi_small.x * scale_down)),
                    y=int(round(chat_roi_small.y * scale_down)),
                    width=int(round(chat_roi_small.width * scale_down)),
                    height=int(round(chat_roi_small.height * scale_down)),
                )

                if (
                    chat_roi.width >= int(0.40 * w_full)
                    and chat_roi.height >= int(0.40 * h_full)
                    and chat_roi.width <= int(0.97 * w_full)
                    and chat_roi.height <= int(0.97 * h_full)
                    and 0 <= chat_roi.x < w_full
                    and 0 <= chat_roi.y < h_full
                    and chat_roi.x + chat_roi.width <= w_full
                    and chat_roi.y + chat_roi.height <= h_full
                ):
                    pad = max(0, int(padding))
                    x1 = max(0, int(chat_roi.x) - pad)
                    y1 = max(0, int(chat_roi.y) - pad)
                    x2 = min(w_full, int(chat_roi.x + chat_roi.width) + pad)
                    y2 = min(h_full, int(chat_roi.y + chat_roi.height) + pad)
                    if x2 > x1 and y2 > y1:
                        return Rectangle(x1, y1, x2 - x1, y2 - y1)
            except Exception:
                pass

            # Convert to grayscale numpy array
            if image.mode != 'L':
                gray_img = image.convert('L')
            else:
                gray_img = image
            
            arr = np.array(gray_img)
            h, w = arr.shape
            
            # Use gradient/variance to detect activity
            # Simple approach: standard deviation in sliding windows or just raw pixel variance
            # For chat logs, the background is usually solid color (black/white/grey)
            # We can detect columns/rows that are "boring" (low variance)
            
            # Calculate variance along axes
            # Axis 0 = vertical projection (collapsing rows) -> shape (w,)
            # Axis 1 = horizontal projection (collapsing cols) -> shape (h,)
            
            edges = self._compute_robust_edges(arr)

            try:
                k = 3 if max(h, w) < 900 else 5
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
                edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
            except Exception:
                pass
            
            # Horizontal projection (project onto Y-axis) to find top/bottom bounds
            # Count non-zero edge pixels in each row
            h_counts = np.count_nonzero(edges, axis=1).astype(np.float32)
            v_counts = np.count_nonzero(edges, axis=0).astype(np.float32)

            def _active_indices(counts: np.ndarray, min_abs: int) -> np.ndarray:
                """根据计数序列的鲁棒阈值选出活跃索引。"""
                if counts.size == 0:
                    return np.array([], dtype=np.int64)
                med = float(np.median(counts))
                mad = float(np.median(np.abs(counts - med)))
                thr = med + 3.0 * mad
                thr = max(thr, float(min_abs))
                return np.where(counts >= thr)[0]

            min_row_abs = max(6, int(round(w * 0.004)))
            min_col_abs = max(6, int(round(h * 0.004)))
            active_rows = _active_indices(h_counts, min_row_abs)
            
            if len(active_rows) == 0:
                # No content found, return full image
                return Rectangle(0, 0, w, h)
                
            y_min = max(0, active_rows[0] - padding)
            y_max = min(h, active_rows[-1] + padding)
            
            # Vertical projection (project onto X-axis) to find left/right bounds
            # Count non-zero edge pixels in each col
            active_cols = _active_indices(v_counts, min_col_abs)
            
            if len(active_cols) == 0:
                x_min, x_max = 0, w
            else:
                x_min = max(0, active_cols[0] - padding)
                x_max = min(w, active_cols[-1] + padding)
                
            self.logger.debug(f"Detected ROI: x={x_min}, y={y_min}, w={x_max-x_min}, h={y_max-y_min} (from {w}x{h})")
            return Rectangle(x_min, y_min, x_max - x_min, y_max - y_min)
            
        except Exception as e:
            self.logger.error(f"ROI detection failed: {e}")
            return Rectangle(0, 0, image.width, image.height)

    def enhance_local_contrast(self, image: Image.Image, clip_limit: float = 2.0, tile_grid_size: tuple = (8, 8)) -> Image.Image:
        """
        Apply Contrast Limited Adaptive Histogram Equalization (CLAHE).
        Great for improving visibility in dark mode or low contrast images.
        """
        try:
            # Convert to OpenCV format (LAB color space usually better for contrast)
            img_np = np.array(image)
            
            is_rgb = True
            if len(img_np.shape) == 2:
                is_rgb = False
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
            elif img_np.shape[2] == 4:
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                
            # Convert to LAB
            lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L-channel
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
            cl = clahe.apply(l)
            
            # Merge and convert back
            limg = cv2.merge((cl, a, b))
            final_bgr = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
            
            if is_rgb:
                final_rgb = cv2.cvtColor(final_bgr, cv2.COLOR_BGR2RGB)
                return Image.fromarray(final_rgb)
            else:
                final_gray = cv2.cvtColor(final_bgr, cv2.COLOR_BGR2GRAY)
                return Image.fromarray(final_gray)
                
        except Exception as e:
            self.logger.error(f"CLAHE enhancement failed: {e}")
            return image

    def detect_chat_area_smart(self, image: Image.Image) -> Rectangle:
        """
        Smartly detect the chat content area by identifying structural lines 
        (sidebar separator, header separator, input box separator).
        
        Algorithm:
        1. Edge detection + Hough Lines to find long vertical/horizontal lines.
        2. Identify:
           - Left Sidebar: Vertical line in the left 1/3.
           - Header: Horizontal line in the top 1/5.
           - Input Box: Horizontal line in the bottom 1/3.
        3. Return the intersection of these boundaries.
        
        Args:
            image: PIL Image (screenshot of the window)
            
        Returns:
            Rectangle: The bounding box of the chat content area
        """
        try:
            # Convert to OpenCV format
            img_np = np.array(image)
            if len(img_np.shape) == 3:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_np
                
            h, w = gray.shape
            
            edges = self._compute_robust_edges(gray)

            try:
                k = 3 if max(h, w) < 900 else 5
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
                edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
            except Exception:
                pass
            
            # 2. Hough Lines (Probabilistic)
            # minLineLength: Line must be at least 20% of dimension to be a separator
            min_line_len = min(w, h) * 0.2
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=60, 
                                   minLineLength=min_line_len, maxLineGap=20)
            
            if lines is None:
                self.logger.debug("No structural lines found for smart detection.")
                return Rectangle(0, 0, w, h)
            
            # Initialize boundaries
            x_start, y_start = 0, 0
            x_end, y_end = w, h
            
            # Candidates
            v_lines = [] # x coordinates
            h_lines = [] # y coordinates
            
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if abs(x1 - x2) < 5: # Vertical line
                    x_pos = (x1 + x2) // 2
                    v_lines.append(x_pos)
                elif abs(y1 - y2) < 5: # Horizontal line
                    y_pos = (y1 + y2) // 2
                    h_lines.append(y_pos)
            
            # 3. Analyze Boundaries
            
            # Left Sidebar: Look for vertical line in left 10% - 40% range
            # WeChat sidebar is usually on the left.
            left_candidates = [x for x in v_lines if 0.1 * w < x < 0.4 * w]
            if left_candidates:
                # Take the right-most candidate in that region (closest to chat)
                # Usually there's just one, but if multiple, the one separating list from chat is desired.
                # Assuming the chat area is to the right of the sidebar.
                x_start = max(left_candidates)
                
            # Input Box: Look for horizontal line in bottom 15% - 40% range
            # WeChat input box is at the bottom. The line is the TOP of the input box.
            bottom_candidates = [y for y in h_lines if 0.6 * h < y < 0.9 * h]
            if bottom_candidates:
                # Take the top-most candidate in that region (the start of input box)
                # We want the content ABOVE the input box.
                y_end = min(bottom_candidates)
                
            # Header: Look for horizontal line in top 0% - 15% range
            top_candidates = [y for y in h_lines if 0 < y < 0.15 * h]
            if top_candidates:
                # Take the bottom-most candidate (end of header)
                y_start = max(top_candidates)
                
            # 4. Padding Correction
            # Separator lines are often 1px. We might want to step in slightly to avoid the line itself.
            padding = 2
            x_start = min(x_start + padding, w - 10)
            y_start = min(y_start + padding, h - 10)
            x_end = max(x_end - padding, x_start + 10)
            y_end = max(y_end - padding, y_start + 10)
            
            self.logger.debug(f"Smart ROI Detected: x={x_start}, y={y_start}, w={x_end-x_start}, h={y_end-y_start}")
            return Rectangle(int(x_start), int(y_start), int(x_end - x_start), int(y_end - y_start))
            
        except Exception as e:
            self.logger.error(f"Smart chat area detection failed: {e}")
            return Rectangle(0, 0, image.width, image.height)

    def detect_text_regions(self, image: Image.Image, min_area: int = 40, max_area_ratio: float = 0.90, use_morphology: bool = True, max_side: int = 0, filter_text_bubbles: bool = True) -> List[Rectangle]:
        """
        Detect regions containing text or images in the input image.
        Uses adaptive thresholding and morphological operations.
        
        Args:
            image: Input PIL Image
            min_area: Minimum area for a region to be considered valid
            max_area_ratio: Maximum ratio of region area to image area
            use_morphology: Whether to use morphological operations to merge text lines
            max_side: Maximum side length for downsampling (0 to disable)
            filter_text_bubbles: Whether to filter out solid background text bubbles (default: True)
            
        Returns:
            List[Rectangle]: List of detected regions
        """
        try:
            # 可选：检测阶段先做轻度下采样以加速形态学与轮廓查找
            w0, h0 = image.size
            cur_max0 = max(w0, h0)
            scale0 = 1.0
            pil_for_detect = image
            if isinstance(max_side, int) and max_side > 0 and cur_max0 > max_side:
                try:
                    scale0 = cur_max0 / float(max_side)
                    new_w0 = max(1, int(round(w0 / scale0)))
                    new_h0 = max(1, int(round(h0 / scale0)))
                    pil_for_detect = image.resize((new_w0, new_h0), resample=Image.LANCZOS)
                    self.logger.debug(
                        f"Region-detect downsample: {w0}x{h0} -> {new_w0}x{new_h0} (max_side={max_side}, scale={scale0:.3f})"
                    )
                except Exception as e:
                    self.logger.debug(f"Failed to pre-downsample for region detection: {e}")
                    pil_for_detect = image
                    scale0 = 1.0

            arr = np.array(pil_for_detect)
            if arr.ndim == 2:
                gray = arr.astype(np.uint8)
            else:
                if arr.shape[-1] == 4:
                    cv_image = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                else:
                    cv_image = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

            # 两种自适应阈值：普通与反相
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            binary_inv = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
            )

            # 选择“文本为白色”的版本：白色像素占比更小的一般更可能是文本
            white_ratio = (binary.sum() / 255.0) / (binary.shape[0] * binary.shape[1])
            white_ratio_inv = (binary_inv.sum() / 255.0) / (binary_inv.shape[0] * binary_inv.shape[1])
            mask = binary if white_ratio < white_ratio_inv else binary_inv

            if use_morphology:
                h_img, w_img = mask.shape[:2]
                max_side_cur = max(h_img, w_img)
                k = 3 if max_side_cur < 900 else 5
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
                its = 1 if k == 3 else 2
                opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=its)
                closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=its)
                mask = closed

            # 路径1：基于自适应阈值的轮廓（擅长文本）
            contours_adaptive, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # 路径2：基于Canny边缘的轮廓（擅长图片/表情包/复杂背景）
            # 图片区域通常边缘丰富，通过Canny+激进膨胀可以形成闭合块
            edges = cv2.Canny(gray, 50, 150)
            h_img, w_img = gray.shape[:2]
            max_side_cur = max(h_img, w_img)
            # 使用更大的核进行闭运算/膨胀，将纹理连成块
            # Increase kernel size to ensure gaps in images (dashed lines, light text) are bridged
            # Adjusted to be less aggressive to avoid merging independent bubbles
            k_edge = 5 if max_side_cur < 900 else 9
            kernel_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (k_edge, k_edge))
            # 闭运算连接断开的边缘
            edge_closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_edge, iterations=2)
            # 膨胀填充内部空洞 - 加强膨胀以连接断裂的图片纹理
            # 即使过度膨胀导致合并，后续的 check_and_split_region 也能将其分开
            edge_dilated = cv2.dilate(edge_closed, kernel_edge, iterations=2)
            contours_canny, _ = cv2.findContours(edge_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # 合并两组轮廓
            all_contours = list(contours_adaptive) + list(contours_canny)

            h_img, w_img = mask.shape[:2]
            img_area = float(h_img * w_img)
            # 临时列表存储未去重的矩形
            raw_regions: List[Rectangle] = []
            
            # Estimate background color from corners (for gap validation)
            corners = np.array([arr[0,0], arr[0,-1], arr[-1,0], arr[-1,-1]])
            bg_color = np.median(corners, axis=0)
            
            # Helper to check for splits
            def check_and_split_region(rect: Rectangle, source_map: np.ndarray, image_arr: np.ndarray = None, bg_color: np.ndarray = None) -> List[Rectangle]:
                """
                Check if a region contains vertically separated components and split if necessary.
                Uses horizontal projection on the source edge/binary map.
                Optionally verifies if the gap matches the background color.
                """
                x, y, w, h = rect.x, rect.y, rect.width, rect.height
                if h < 20: # Too small to split
                    return [rect]
                
                # Extract ROI from source map
                roi = source_map[y:y+h, x:x+w]
                
                # Horizontal projection
                # Ignore left/right margins (e.g. 5 pixels) to avoid vertical border lines affecting projection
                margin_x = min(5, w // 10)
                if w > 2 * margin_x:
                    roi_proj = roi[:, margin_x:-margin_x]
                else:
                    roi_proj = roi
                
                row_sums = np.sum(roi_proj, axis=1)
                
                # Threshold: a row is "empty" if it has very few edge pixels
                # Allow small noise (e.g. up to 5 pixels of edge)
                # 255 is the value of an edge pixel
                is_empty = row_sums < (5 * 255)
                
                # Find gaps
                # We look for continuous runs of empty rows
                # Minimum gap size to trigger split: 3 pixels (tight gap)
                min_gap = 3
                
                split_points = []
                current_gap_start = -1
                
                for r_idx in range(h):
                    if is_empty[r_idx]:
                        if current_gap_start == -1:
                            current_gap_start = r_idx
                    else:
                        if current_gap_start != -1:
                            gap_len = r_idx - current_gap_start
                            if gap_len >= min_gap:
                                # Check gap color if image is provided
                                is_valid_gap = True
                                if image_arr is not None and bg_color is not None:
                                    # Sample the gap area from the original image
                                    # Note: rect coords (x, y) must match image_arr coords
                                    gy1 = y + current_gap_start
                                    gy2 = y + r_idx
                                    # Limit width to center part to avoid border noise? 
                                    gx1 = x + w // 4
                                    gx2 = x + 3 * w // 4
                                    if gx2 > gx1:
                                        gap_roi = image_arr[gy1:gy2, gx1:gx2]
                                        if gap_roi.size > 0:
                                            # Calculate average color of the gap
                                            # Reshape to list of pixels
                                            pixels = gap_roi.reshape(-1, 3)
                                            avg_color = np.mean(pixels, axis=0)
                                            # Distance to global background
                                            dist = np.linalg.norm(avg_color - bg_color)
                                            # If distance is large (e.g. > 30), it's likely a Bubble Background, not Chat Background
                                            if dist > 30:
                                                is_valid_gap = False
                                
                                if is_valid_gap:
                                    # Found a valid gap. The split point is the middle of the gap
                                    split_y = current_gap_start + gap_len // 2
                                    # Don't split too close to edges (e.g. top/bottom margins)
                                    if 10 < split_y < h - 10:
                                        split_points.append(split_y)
                            
                            current_gap_start = -1
                
                if not split_points:
                    return [rect]
                    
                # Create sub-regions
                sub_regions = []
                last_y = 0
                for split_y in split_points:
                    # Add segment from last_y to split_y
                    seg_h = split_y - last_y
                    if seg_h > 5: # Filter tiny slivers
                        sub_regions.append(Rectangle(x, y + last_y, w, seg_h))
                    last_y = split_y
                
                # Add final segment
                remaining_h = h - last_y
                if remaining_h > 5:
                    sub_regions.append(Rectangle(x, y + last_y, w, remaining_h))
                    
                return sub_regions

            # Use the raw 'edges' (before morphological closing) for splitting analysis
            # This ensures we can detect small gaps that were bridged by closing/dilation
            split_ref_map = edges

            for contour in all_contours:
                area = cv2.contourArea(contour)
                # ... (rest of logic)
                # 若做了下采样，最小面积阈值需按比例缩放到当前分辨率（面积随缩放因子平方变化）
                effective_min_area = min_area
                if scale0 > 1.0:
                    try:
                        effective_min_area = max(1, int(round(min_area / (scale0 * scale0))))
                    except Exception:
                        effective_min_area = min_area
                
                # 对图片区域稍微放宽最小面积要求（Canny检测到的可能较碎，但如果聚合后应该不小）
                if area < effective_min_area:
                    continue
                # 过滤过大的区域（通常是背景块）
                if (area / img_area) > 0.85:
                    continue

                x, y, w, h = cv2.boundingRect(contour)
                # 合理长宽比过滤（文本行通常较扁，单词/字符也在此范围；图片通常较方）
                aspect_ratio = (w / max(h, 1))
                if 0.05 <= aspect_ratio <= 50:
                    # Perform split check on the base contour rect
                    base_rect = Rectangle(x=x, y=y, width=w, height=h)
                    sub_rects = check_and_split_region(base_rect, split_ref_map, arr, bg_color)
                    
                    for sr in sub_rects:
                        # 若做了下采样，需将坐标缩放回原图尺寸并进行边界裁剪
                        if scale0 > 1.0:
                            try:
                                ox = int(round(sr.x * scale0))
                                oy = int(round(sr.y * scale0))
                                ow = int(round(sr.width * scale0))
                                oh = int(round(sr.height * scale0))
                                # 边界裁剪，避免越界
                                right = min(ox + ow, w0)
                                bottom = min(oy + oh, h0)
                                ox = max(0, min(ox, w0 - 1))
                                oy = max(0, min(oy, h0 - 1))
                                ow = max(1, right - ox)
                                oh = max(1, bottom - oy)
                                raw_regions.append(Rectangle(x=ox, y=oy, width=ow, height=oh))
                            except Exception:
                                # Fallback (unlikely)
                                pass
                        else:
                            raw_regions.append(sr)

            # 简单去重：如果两个矩形重叠度高，保留较大的一个
            # 为提高效率，先按面积降序排列
            raw_regions.sort(key=lambda r: r.width * r.height, reverse=True)
            text_regions: List[Rectangle] = []
            
            for r in raw_regions:
                is_overlap = False
                r_area = r.width * r.height
                rx1, ry1, rx2, ry2 = r.x, r.y, r.x + r.width, r.y + r.height
                
                for kept in text_regions:
                    kx1, ky1, kx2, ky2 = kept.x, kept.y, kept.x + kept.width, kept.y + kept.height
                    
                    # 计算交集
                    ix1 = max(rx1, kx1)
                    iy1 = max(ry1, ky1)
                    ix2 = min(rx2, kx2)
                    iy2 = min(ry2, ky2)
                    
                    iw = max(0, ix2 - ix1)
                    ih = max(0, iy2 - iy1)
                    inter_area = iw * ih
                    
                    if inter_area > 0:
                        kept_area = kept.width * kept.height
                        # 如果交集占当前矩形面积的大部分（>70%），或者占已保留矩形的大部分，则视为重复
                        # 既然是按面积降序，kept_area >= r_area
                        if inter_area / r_area > 0.7:
                            is_overlap = True
                            break
                
                if not is_overlap:
                    text_regions.append(r)

            # Filter out solid background regions (likely text bubbles)
            # Users complained about text-only messages being detected as images.
            # Text bubbles typically have a high dominant color ratio (>60%).
            final_regions = []
            if filter_text_bubbles:
                for r in text_regions:
                    # Crop from the original image to check color
                    # Use a try-except block to be safe
                    try:
                        crop = image.crop((r.x, r.y, r.x + r.width, r.y + r.height))
                        # Check if it is a text bubble (solid background + sparse text)
                        if self.is_text_bubble(crop):
                            self.logger.debug(f"Filtered out text bubble region: {r}")
                            continue
                    except Exception as e:
                        self.logger.warning(f"Failed to check text bubble for region {r}: {e}")
                    
                    final_regions.append(r)
                self.logger.debug(f"Detected {len(final_regions)} potential regions (Adaptive+Canny) after filtering")
            else:
                final_regions = text_regions
                self.logger.debug(f"Detected {len(final_regions)} potential regions (Adaptive+Canny) - Bubble Filtering Disabled")
                
            return final_regions

        except Exception as e:
            self.logger.error(f"Text region detection failed: {e}")
            return []
    
    def refine_crop(self, image: Image.Image, tolerance: int = 15, padding: int = 15) -> Rectangle:
        """
        Refine the crop by removing uniform background borders and adding a buffer.
        
        Args:
            image: Input PIL Image
            tolerance: Color difference tolerance (0-255)
            padding: Buffer pixels to keep around content (default 15)
            
        Returns:
            Rectangle: The refined bounding box relative to the input image
        """
        try:
            arr = np.array(image)
            if arr.ndim == 2:
                # Grayscale
                pass
            elif arr.ndim == 3 and arr.shape[2] >= 3:
                # RGB/RGBA - use RGB channels only
                arr = arr[:, :, :3]
            
            h, w = arr.shape[:2]
            if h < 2 or w < 2:
                return Rectangle(0, 0, w, h)
                
            # Sample background color from 4 corners
            corners = [
                arr[0, 0], arr[0, w-1], 
                arr[h-1, 0], arr[h-1, w-1]
            ]
            
            # Use the most common color among corners as background reference
            # Or just use top-left if we trust the loose crop
            bg_ref = arr[0, 0].astype(int)
            
            # Calculate difference from background
            diff = np.abs(arr.astype(int) - bg_ref)
            if diff.ndim == 3:
                diff = np.sum(diff, axis=2)
            
            # Find foreground pixels
            rows, cols = np.where(diff > tolerance)
            
            if len(rows) == 0:
                # Image is solid color (same as background)
                return Rectangle(0, 0, w, h)
                
            y_min, y_max = int(rows.min()), int(rows.max())
            x_min, x_max = int(cols.min()), int(cols.max())
            
            # Add padding
            x_min = max(0, x_min - padding)
            y_min = max(0, y_min - padding)
            x_max = min(w, x_max + padding)
            y_max = min(h, y_max + padding)
            
            # Ensure we don't exceed original bounds
            width = x_max - x_min + 1
            height = y_max - y_min + 1
            
            # Clamp width/height just in case
            if x_min + width > w: width = w - x_min
            if y_min + height > h: height = h - y_min
            
            return Rectangle(x_min, y_min, width, height)
            
        except Exception as e:
            self.logger.error(f"Refine crop failed: {e}")
            return Rectangle(0, 0, image.width, image.height)

    def crop_text_region(self, image: Image.Image, region: Rectangle) -> Image.Image:
        """
        Crop specific text region from image.
        
        Args:
            image: Input PIL Image
            region: Rectangle defining the region to crop
            
        Returns:
            PIL Image: Cropped image region
        """
        try:
            # Define crop box (left, top, right, bottom)
            crop_box = (
                region.x,
                region.y,
                region.x + region.width,
                region.y + region.height
            )
            
            cropped_image = image.crop(crop_box)
            self.logger.debug(f"Cropped region: {region.width}x{region.height}")
            return cropped_image
            
        except Exception as e:
            self.logger.error(f"Image cropping failed: {e}")
            return image
    
    def preprocess_for_ocr(self, image: Image.Image, 
                          enhance_quality: bool = True,
                          reduce_noise_flag: bool = True,
                          convert_grayscale: bool = True,
                          noise_method: str = "bilateral",
                          padding: int = 0) -> Image.Image:
        """
        Apply complete preprocessing pipeline for OCR optimization.
        
        Args:
            image: Input PIL Image
            enhance_quality: Whether to enhance image quality
            reduce_noise_flag: Whether to apply noise reduction
            convert_grayscale: Whether to convert to grayscale
            noise_method: Noise reduction method to use ("gaussian", "median", "bilateral")
            padding: Padding pixels to add around the image (default: 0).
                     Adding padding (e.g. 10) can improve OCR for text touching edges.
            
        Returns:
            PIL Image: Preprocessed image ready for OCR
        """
        try:
            processed_image = image.copy()
            
            # Step 1: Smart enhancement based on quality score
            if enhance_quality:
                # Calculate quality score to decide if CLAHE is needed
                quality_score = self.calculate_image_quality_score(processed_image)
                
                # If quality is low (e.g. dark mode or low contrast), apply CLAHE first
                if quality_score < 0.6:
                    self.logger.debug(f"Low image quality ({quality_score:.3f}), applying CLAHE")
                    processed_image = self.enhance_local_contrast(processed_image)
                
                # Apply standard enhancements
                processed_image = self.enhance_image_quality(processed_image)
            
            # Step 2: Reduce noise
            if reduce_noise_flag:
                processed_image = self.reduce_noise(processed_image, method=noise_method)
            
            # Step 3: Convert to grayscale
            if convert_grayscale:
                processed_image = self.convert_to_grayscale(processed_image)
                
            # Step 4: Add padding if requested
            if padding > 0:
                w, h = processed_image.size
                new_w = w + 2 * padding
                new_h = h + 2 * padding
                
                # Determine background color based on mode
                bg_color = 255 # White for grayscale/L
                if processed_image.mode == 'RGB':
                    bg_color = (255, 255, 255)
                elif processed_image.mode == 'RGBA':
                    bg_color = (255, 255, 255, 255)
                    
                padded_image = Image.new(processed_image.mode, (new_w, new_h), bg_color)
                padded_image.paste(processed_image, (padding, padding))
                processed_image = padded_image
                self.logger.debug(f"Added padding: {padding}px")
            
            self.logger.debug("Complete OCR preprocessing pipeline applied")
            return processed_image
            
        except Exception as e:
            self.logger.error(f"OCR preprocessing failed: {e}")
            return image
    
    def calculate_image_quality_score(self, image: Image.Image) -> float:
        """
        Calculate image quality score based on various metrics.
        
        Args:
            image: Input PIL Image
            
        Returns:
            float: Quality score between 0.0 and 1.0
        """
        try:
            # Convert to OpenCV format
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            
            # Calculate Laplacian variance (sharpness measure)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            # Normalize sharpness score (typical range: 0-2000)
            sharpness_score = min(laplacian_var / 1000.0, 1.0)
            
            # Calculate contrast (standard deviation of pixel values)
            contrast_score = min(gray.std() / 128.0, 1.0)
            
            # Calculate brightness score (how close to optimal brightness)
            mean_brightness = gray.mean()
            optimal_brightness = 128
            brightness_score = 1.0 - abs(mean_brightness - optimal_brightness) / optimal_brightness
            
            # Combine scores with weights
            quality_score = (
                0.4 * sharpness_score +
                0.3 * contrast_score +
                0.3 * brightness_score
            )
            
            self.logger.debug(f"Image quality score: {quality_score:.3f}")
            return quality_score
            
        except Exception as e:
            self.logger.error(f"Quality score calculation failed: {e}")
            return 0.5  # Return neutral score on error

    def apply_privacy_protection(self, image: Image.Image) -> Image.Image:
        """
        Apply privacy protection to the image, specifically blurring green message bubbles.

        Features:
        1. Detects green bubble regions (R:180-220, G:230-255, B:180-220).
        2. Applies pixel-level Gaussian blur (radius >= 8px).
        3. Adds a semi-transparent overlay (30% opacity).

        Args:
            image: Input PIL Image

        Returns:
            PIL Image: Processed image with privacy protection
        """
        try:
            # Convert to numpy array (RGB)
            img_arr = np.array(image)
            is_rgba = False
            
            if img_arr.ndim == 2:
                # Convert grayscale to RGB
                img_arr_rgb = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2RGB)
            elif img_arr.shape[2] == 4:
                # Convert RGBA to RGB for processing
                is_rgba = True
                img_arr_rgb = cv2.cvtColor(img_arr, cv2.COLOR_RGBA2RGB)
            else:
                img_arr_rgb = img_arr

            # 1. Detect Green Bubbles
            # RGB Range: R:180-220, G:230-255, B:180-220
            lower_green = np.array([180, 230, 180])
            upper_green = np.array([220, 255, 220])
            
            # Create mask
            mask = cv2.inRange(img_arr_rgb, lower_green, upper_green)
            
            # Find contours to identify bubble regions
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                self.logger.debug("No green bubbles detected for privacy protection.")
                return image
            
            # Create a processing layer
            # Optimization: Avoid full image copy to save memory (target < 50MB)
            # img_arr is already a numpy copy of PIL image, so we can modify it in-place.
            processed_img = img_arr_rgb
            
            # 2. Blur and 3. Overlay
            for contour in contours:
                # Get bounding box
                x, y, w, h = cv2.boundingRect(contour)
                
                # Check area size to avoid noise
                if w * h < 100:
                    continue
                
                # Extract ROI
                roi = processed_img[y:y+h, x:x+w]
                
                # Dynamic Blur based on image resolution
                # Requirement: radius >= 8px
                # We scale radius based on image size to be effective on high-res screens
                img_h, img_w = img_arr_rgb.shape[:2]
                min_dim = min(img_h, img_w)
                blur_radius = max(8, int(min_dim * 0.02))
                
                # Sigma for Gaussian Blur. Kernel size will be automatically calculated.
                # To get a visual "radius" of X, sigma is usually X/2 or similar.
                # Let's use sigma = blur_radius.
                blurred_roi = cv2.GaussianBlur(roi, (0, 0), blur_radius)
                
                # Apply Overlay (Semi-transparent white)
                # 70% opacity (0.7) for enhanced protection (User requested 60-80%)
                white_overlay = np.ones_like(roi) * 255
                alpha = 0.7
                
                # Blend
                blended_roi = cv2.addWeighted(blurred_roi, 1 - alpha, white_overlay, alpha, 0)
                
                # Apply back strictly within the contour mask
                contour_mask = np.zeros_like(mask)
                cv2.drawContours(contour_mask, [contour], -1, 255, -1)
                roi_contour_mask = contour_mask[y:y+h, x:x+w]
                
                # Broadcast mask to 3 channels
                roi_contour_mask_3c = cv2.merge([roi_contour_mask, roi_contour_mask, roi_contour_mask])
                
                # Update pixels
                final_roi = np.where(roi_contour_mask_3c == 255, blended_roi, roi)
                processed_img[y:y+h, x:x+w] = final_roi

            # Convert back to PIL
            if is_rgba:
                # Restore alpha channel from original
                r, g, b = cv2.split(processed_img)
                _, _, _, a = cv2.split(img_arr)
                merged = cv2.merge([r, g, b, a])
                return Image.fromarray(merged)
            else:
                return Image.fromarray(processed_img)

        except Exception as e:
            self.logger.error(f"Privacy protection failed: {e}")
            return image
