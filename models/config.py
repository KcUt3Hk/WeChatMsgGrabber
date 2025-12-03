"""
Configuration data models for WeChat chat extractor.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List
import os


@dataclass
class OCRConfig:
    """OCR engine configuration."""
    language: str = "ch"
    confidence_threshold: float = 0.7
    use_gpu: bool = False
    # 是否启用角度分类（PaddleOCR 的 cls 分支）。
    # 说明：
    # - 在多数端到端聊天截图场景中，文本布局较为规整，关闭角度分类可显著降低处理开销；
    # - 若识别包含大量旋转文本或需要对倾斜文本做校正，可开启。
    use_angle_cls: bool = False

    # 预处理开关（作用于整图处理流程）。
    # 在性能敏感场景下，可关闭高开销步骤（例如双边滤波降噪）。
    preprocess_enhance_quality: bool = True
    preprocess_reduce_noise: bool = True
    preprocess_noise_method: str = "gaussian"  # gaussian/median/bilateral
    preprocess_convert_grayscale: bool = True
    # 整图预处理的最大边限制（像素）。当原图的宽或高超过该值时，按比例缩小到该最大边，降低后续推理与几何校正开销。
    # 说明：
    # - 对聊天截图等高分辨率图片，下采样到合理尺寸（如 1280）通常不影响可读性，能显著加速；
    # - 设置为 0 或 None 可禁用该缩放。
    preprocess_max_side: int = 1600

    # 预处理开关（作用于裁剪区域的识别流程）。
    # 裁剪区域通常较小，降噪收益有限且开销相对更高，建议默认关闭。
    preprocess_crop_reduce_noise: bool = False
    preprocess_crop_convert_grayscale: bool = True
    # 可选：裁剪区域的最大边限制（像素）。默认禁用（0）。
    # 对异常大的裁剪区域（例如整页截图中的大块文本）可开启以进一步加速；
    # 对常规小区域不建议启用，以免影响细小文字的识别率。
    preprocess_crop_max_side: int = 0

    # 可选：文本区域检测阶段（detect_text_regions）的最大边限制（像素）。默认禁用（0）。
    # 说明：
    # - 形态学操作与轮廓搜索的开销与分辨率近似线性相关；
    # - 在超大图像上先对检测阶段进行轻度下采样（如 960 或 1280）通常不影响区域定位的鲁棒性；
    # - 开启后仅作用于检测阶段，最终坐标会按比例缩放回原图尺寸，不影响后续裁剪与 OCR。
    preprocess_region_detect_max_side: int = 0

    # 可选：对较小图像跳过降噪以减少不必要开销（像素级阈值）。默认禁用（0）。
    # 说明：
    # - 当整图的最大边不超过该阈值时，自动关闭 reduce_noise_flag；
    # - 对常见小截图几乎不影响识别质量，却能避免双边/中值滤波的固定开销。
    preprocess_small_skip_noise_threshold: int = 0

    # 可选：OpenCV 线程数控制（>0 生效，0 表示不修改）。默认 0。
    # 说明：
    # - 在多核设备上合理设置可提升形态学与滤波等操作的并行效率；
    # - 若同时运行其他并行任务，可将其限制在较小值以避免竞争。
    preprocess_cv_threads: int = 0

    # 是否启用对 paddlex YAML/文件读取的内存缓存（猴子补丁）。
    # 说明：
    # - 在慢用例中，paddlex 的 load_config 会频繁读取同一 YAML 文件并解析，带来大量 YAML 扫描与 IO 开销；
    # - 开启后对 paddlex.inference.utils.io.readers.read/read_file 做轻量缓存，显著减少重复解析；
    # - 如需严格保持第三方函数的原始行为（例如调试第三方库），可关闭。
    enable_paddlex_yaml_cache: bool = False

    # 是否启用 paddlex 官方模型离线模式（猴子补丁）。
    # 说明：
    # - 跳过 official_models.is_available 的网络请求，避免慢用例中 requests.head 的阻塞；
    # - 对离线环境或 CI 场景尤为有益；如需真实网络探测可关闭。
    enable_paddlex_offline: bool = False

    # 是否启用整图 OCR 结果的内存 LRU 缓存。
    # 说明：
    # - 对于批处理或扫描策略下的重复整图识别请求，缓存可显著减少 PaddleOCR 的重复推理；
    # - 仅对非裁剪区域（is_cropped_region=False）的 process_image 调用生效；
    # - 缓存键包含原图哈希、预处理选项、语言与角度分类开关，保证不同配置下结果隔离。
    enable_full_image_cache: bool = True
    # 整图 OCR LRU 缓存的最大条目数（过大将增加内存占用）。
    full_image_cache_size: int = 16


@dataclass
class ScrollConfig:
    """Auto-scroll configuration."""
    speed: int = 2
    delay: float = 1.0
    max_retry_attempts: int = 3


@dataclass
class OutputConfig:
    """Output configuration."""
    format: str = "json"  # json, csv, txt, md
    directory: str = "./output"
    enable_deduplication: bool = True
    # 同时导出多种格式（若非空则优先生效），例如 ["json", "csv"]
    formats: List[str] = field(default_factory=list)
    # 需要从导出中排除的字段，例如 ["confidence_score", "raw_ocr_text"]
    exclude_fields: List[str] = field(default_factory=list)
    # 是否排除仅包含时间/日期的系统分隔消息
    exclude_time_only: bool = False
    # 更激进的内容级去重（基于 sender + content），减少同轮重复
    aggressive_dedup: bool = False
    # 用户自定义的“纯时间/日期分隔”识别正则列表（追加到内置规则之后）
    time_only_patterns: List[str] = field(default_factory=list)


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "./logs/extractor.log"
    max_size: str = "10MB"


@dataclass
class AppConfig:
    """Main application configuration."""
    scroll_speed: int = 2
    scroll_delay: float = 1.0
    # Default OCR language aligned with PaddleOCR's Chinese+English model code
    ocr_language: str = "ch"
    ocr_confidence_threshold: float = 0.7
    output_format: str = "json"
    output_directory: str = "./output"
    max_retry_attempts: int = 3
    enable_deduplication: bool = True
    
    # Nested configurations
    ocr: OCRConfig = field(default_factory=OCRConfig)
    scroll: ScrollConfig = field(default_factory=ScrollConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    def __post_init__(self):
        """Initialize nested configurations from flat attributes."""
        self.ocr = OCRConfig(
            language=self.ocr_language,
            confidence_threshold=self.ocr_confidence_threshold
        )
        self.scroll = ScrollConfig(
            speed=self.scroll_speed,
            delay=self.scroll_delay,
            max_retry_attempts=self.max_retry_attempts
        )
        self.output = OutputConfig(
            format=self.output_format,
            directory=self.output_directory,
            enable_deduplication=self.enable_deduplication,
            # 默认不设置多格式，CLI 可覆盖
            formats=[],
            exclude_fields=[],
            exclude_time_only=False,
            aggressive_dedup=False,
            time_only_patterns=[],
        )
    
    def validate(self) -> bool:
        """Validate configuration parameters."""
        errors = []
        
        # Validate scroll parameters
        if self.scroll_speed < 1 or self.scroll_speed > 10:
            errors.append("scroll_speed must be between 1 and 10")
        
        if self.scroll_delay < 0.1 or self.scroll_delay > 10.0:
            errors.append("scroll_delay must be between 0.1 and 10.0 seconds")
        
        # Validate OCR parameters
        if self.ocr_confidence_threshold < 0.0 or self.ocr_confidence_threshold > 1.0:
            errors.append("ocr_confidence_threshold must be between 0.0 and 1.0")
        
        # Validate output parameters（保持兼容单格式，同时支持多格式）
        allowed = {"json", "csv", "txt", "md"}
        if self.output_format not in allowed:
            errors.append("output_format must be one of: json, csv, txt, md")
        # 当配置中包含多格式时校验其有效性
        if hasattr(self, 'output') and isinstance(self.output, OutputConfig):
            if self.output.formats:
                invalid = [f for f in self.output.formats if f not in allowed]
                if invalid:
                    errors.append(f"output.formats contains unsupported: {','.join(invalid)}")
        
        # Validate retry attempts
        if self.max_retry_attempts < 1 or self.max_retry_attempts > 10:
            errors.append("max_retry_attempts must be between 1 and 10")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "app": {
                "scroll_speed": self.scroll_speed,
                "scroll_delay": self.scroll_delay,
                "max_retry_attempts": self.max_retry_attempts,
            },
            "ocr": {
                "language": self.ocr_language,
                "confidence_threshold": self.ocr_confidence_threshold,
                "use_gpu": self.ocr.use_gpu,
                # 新增字段：导出到字典以便 CLI/文档与持久化统一
                "use_angle_cls": getattr(self.ocr, "use_angle_cls", False),
                "preprocess_enhance_quality": getattr(self.ocr, "preprocess_enhance_quality", True),
                "preprocess_reduce_noise": getattr(self.ocr, "preprocess_reduce_noise", True),
                "preprocess_noise_method": getattr(self.ocr, "preprocess_noise_method", "gaussian"),
                "preprocess_convert_grayscale": getattr(self.ocr, "preprocess_convert_grayscale", True),
                "preprocess_crop_reduce_noise": getattr(self.ocr, "preprocess_crop_reduce_noise", False),
                "preprocess_crop_convert_grayscale": getattr(self.ocr, "preprocess_crop_convert_grayscale", True),
                "preprocess_max_side": getattr(self.ocr, "preprocess_max_side", 1280),
                "preprocess_crop_max_side": getattr(self.ocr, "preprocess_crop_max_side", 0),
                "preprocess_region_detect_max_side": getattr(self.ocr, "preprocess_region_detect_max_side", 0),
                "preprocess_small_skip_noise_threshold": getattr(self.ocr, "preprocess_small_skip_noise_threshold", 0),
                "preprocess_cv_threads": getattr(self.ocr, "preprocess_cv_threads", 0),
                "enable_paddlex_yaml_cache": getattr(self.ocr, "enable_paddlex_yaml_cache", True),
                "enable_full_image_cache": getattr(self.ocr, "enable_full_image_cache", True),
                "full_image_cache_size": getattr(self.ocr, "full_image_cache_size", 16),
                "enable_paddlex_offline": getattr(self.ocr, "enable_paddlex_offline", True),
            },
            "output": {
                "format": self.output_format,
                "directory": self.output_directory,
                "enable_deduplication": self.enable_deduplication,
                "formats": (self.output.formats if hasattr(self.output, 'formats') else []),
                "exclude_fields": (self.output.exclude_fields if hasattr(self.output, 'exclude_fields') else []),
                "exclude_time_only": (self.output.exclude_time_only if hasattr(self.output, 'exclude_time_only') else False),
                "aggressive_dedup": (self.output.aggressive_dedup if hasattr(self.output, 'aggressive_dedup') else False),
                "time_only_patterns": (self.output.time_only_patterns if hasattr(self.output, 'time_only_patterns') else []),
            },
            "logging": {
                "level": self.logging.level,
                "file": self.logging.file,
                "max_size": self.logging.max_size,
            }
        }
