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
            
            # Convert back to PIL
            denoised_rgb = cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB)
            result_image = Image.fromarray(denoised_rgb)
            
            self.logger.debug(f"Noise reduction applied using {method} method")
            return result_image
            
        except Exception as e:
            self.logger.error(f"Noise reduction failed: {e}")
            return image
    
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
    
    def detect_text_regions(self, image: Image.Image,
                            min_area: int = 80,
                            max_area_ratio: float = 0.5,
                            use_morphology: bool = True,
                            max_side: int = 0) -> List[Rectangle]:
        """
        基于自适应阈值与形态学操作的文本区域检测。

        设计目标：
        - 兼容浅色主题（深色文字）与深色主题（浅色文字）两种情况；
        - 自动选择使“文本为白、背景为黑”的二值化图像，以便轮廓提取；
        - 通过最小面积、最大面积比、长宽比约束过滤非文本区域；
        - 使用形态学开运算/闭运算降低噪声并连通字符。

        参数：
        - image: 输入的 PIL Image；
        - min_area: 文本区域的最小像素面积（默认为 80）；
        - max_area_ratio: 单个区域占整图面积的最大比例，避免整个背景被误判（默认为 0.5）；
        - use_morphology: 是否应用形态学操作（默认为 True）。
        - max_side: 检测阶段的最大边限制（像素，默认为 0 表示禁用）。当原图的宽或高超过该值时，
                    先对检测阶段做轻度下采样，再进行阈值与形态学处理；检测到的坐标将按比例缩放回原图尺寸。

        返回：
        - 文本区域的矩形列表。
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

            # 转为 OpenCV 格式与灰度图（基于可能下采样后的图像）
            cv_image = cv2.cvtColor(np.array(pil_for_detect), cv2.COLOR_RGB2BGR)
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
                # 形态学开运算去噪，再轻度闭运算连通字符
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
                closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=1)
                mask = closed

            # 查找外部轮廓
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            h_img, w_img = mask.shape[:2]
            img_area = float(h_img * w_img)
            text_regions: List[Rectangle] = []

            for contour in contours:
                area = cv2.contourArea(contour)
                # 若做了下采样，最小面积阈值需按比例缩放到当前分辨率（面积随缩放因子平方变化）
                effective_min_area = min_area
                if scale0 > 1.0:
                    try:
                        effective_min_area = max(1, int(round(min_area / (scale0 * scale0))))
                    except Exception:
                        effective_min_area = min_area
                if area < effective_min_area:
                    continue
                # 过滤过大的区域（通常是背景块）
                if (area / img_area) > max_area_ratio:
                    continue

                x, y, w, h = cv2.boundingRect(contour)
                # 合理长宽比过滤（文本行通常较扁，单词/字符也在此范围）
                aspect_ratio = (w / max(h, 1))
                if 0.1 <= aspect_ratio <= 30:
                    # 若做了下采样，需将坐标缩放回原图尺寸并进行边界裁剪
                    if scale0 > 1.0:
                        try:
                            ox = int(round(x * scale0))
                            oy = int(round(y * scale0))
                            ow = int(round(w * scale0))
                            oh = int(round(h * scale0))
                            # 边界裁剪，避免越界
                            right = min(ox + ow, w0)
                            bottom = min(oy + oh, h0)
                            ox = max(0, min(ox, w0 - 1))
                            oy = max(0, min(oy, h0 - 1))
                            ow = max(1, right - ox)
                            oh = max(1, bottom - oy)
                            text_regions.append(Rectangle(x=ox, y=oy, width=ow, height=oh))
                            continue
                        except Exception:
                            # 回退到下采样坐标（极少数异常情况下）
                            pass
                    text_regions.append(Rectangle(x=x, y=y, width=w, height=h))

            self.logger.debug(f"Detected {len(text_regions)} potential text regions")
            return text_regions

        except Exception as e:
            self.logger.error(f"Text region detection failed: {e}")
            return []
    
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
                          noise_method: str = "bilateral") -> Image.Image:
        """
        Apply complete preprocessing pipeline for OCR optimization.
        
        Args:
            image: Input PIL Image
            enhance_quality: Whether to enhance image quality
            reduce_noise_flag: Whether to apply noise reduction
            convert_grayscale: Whether to convert to grayscale
            noise_method: Noise reduction method to use ("gaussian", "median", "bilateral")
            
        Returns:
            PIL Image: Preprocessed image ready for OCR
        """
        try:
            processed_image = image.copy()
            
            # Step 1: Enhance image quality
            if enhance_quality:
                processed_image = self.enhance_image_quality(processed_image)
            
            # Step 2: Reduce noise
            if reduce_noise_flag:
                processed_image = self.reduce_noise(processed_image, method=noise_method)
            
            # Step 3: Convert to grayscale
            if convert_grayscale:
                processed_image = self.convert_to_grayscale(processed_image)
            
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