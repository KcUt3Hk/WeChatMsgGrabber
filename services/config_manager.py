"""
Configuration manager for loading and validating application configuration.
"""
import os
import json
import yaml
from typing import Dict, Any, Optional
from models.config import AppConfig


class ConfigManager:
    """Manages application configuration loading and validation."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file. If None, uses default locations.
        """
        self.config_path = config_path or self._find_config_file()
        self._config: Optional[AppConfig] = None
    
    def _find_config_file(self) -> Optional[str]:
        """Find configuration file in standard locations."""
        possible_paths = [
            "config.yaml",
            "config.yml", 
            "config.json",
            "settings.yaml",
            "settings.yml",
            "settings.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def load_config(self) -> AppConfig:
        """
        Load configuration from file or create default configuration.
        
        Returns:
            AppConfig: Loaded or default configuration
            
        Raises:
            ValueError: If configuration validation fails
            FileNotFoundError: If specified config file doesn't exist
        """
        if self._config is not None:
            return self._config
        
        if self.config_path and os.path.exists(self.config_path):
            config_data = self._load_config_file(self.config_path)
            self._config = self._create_config_from_dict(config_data)
        else:
            # Create default configuration
            self._config = AppConfig()
        
        # Validate configuration
        self._config.validate()
        
        return self._config
    
    def _load_config_file(self, file_path: str) -> Dict[str, Any]:
        """
        Load configuration data from file.
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            Dict containing configuration data
            
        Raises:
            ValueError: If file format is not supported
            FileNotFoundError: If file doesn't exist
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_ext in ['.yaml', '.yml']:
                try:
                    import yaml
                    return yaml.safe_load(f) or {}
                except ImportError:
                    raise ValueError("PyYAML is required to load YAML configuration files")
            elif file_ext == '.json':
                return json.load(f)
            else:
                raise ValueError(f"Unsupported configuration file format: {file_ext}")
    
    def _create_config_from_dict(self, config_data: Dict[str, Any]) -> AppConfig:
        """
        从字典数据创建 AppConfig 实例，并处理 OutputConfig 的扩展字段。

        处理流程：
        1) 扁平化 app/ocr/output 三部分配置，传入 AppConfig 构造函数（含基础字段：
           - app: scroll_speed, scroll_delay, max_retry_attempts
           - ocr: ocr_language, ocr_confidence_threshold
           - output: output_format, output_directory, enable_deduplication
        2) 若存在 output 扩展字段，注入到 AppConfig.output：
           - formats: 多格式导出（list[str]）
           - exclude_fields: 导出时移除字段（list[str]）
           - exclude_time_only: 过滤纯时间/日期分隔消息（bool）
           - aggressive_dedup: 激进内容级去重（bool）
           - time_only_patterns: 用户自定义的时间分隔正则（list[str] 或 单字符串会被转为 list）

        容错策略：
        - 对不存在的键采用默认值；
        - 对 `time_only_patterns` 若为单字符串，自动转换为列表；若类型不合法则忽略；
        - 出现解析异常时不会抛出，保持默认配置并继续执行。

        Args:
            config_data: 原始配置字典

        Returns:
            AppConfig: 归一化后的应用配置对象
        """
        # Flatten nested configuration for AppConfig constructor
        flat_config = {}
        
        # Extract app-level settings
        if 'app' in config_data:
            app_settings = config_data['app']
            flat_config.update({
                'scroll_speed': app_settings.get('scroll_speed', 2),
                'scroll_delay': app_settings.get('scroll_delay', 1.0),
                'max_retry_attempts': app_settings.get('max_retry_attempts', 3),
            })
        
        # Extract OCR settings
        if 'ocr' in config_data:
            ocr_settings = config_data['ocr']
            flat_config.update({
                # Default to 'ch' (PaddleOCR Chinese+English) if not provided
                'ocr_language': ocr_settings.get('language', 'ch'),
                'ocr_confidence_threshold': ocr_settings.get('confidence_threshold', 0.7),
            })
        
        # Extract output settings
        if 'output' in config_data:
            output_settings = config_data['output']
            flat_config.update({
                'output_format': output_settings.get('format', 'json'),
                'output_directory': output_settings.get('directory', './output'),
                'enable_deduplication': output_settings.get('enable_deduplication', True),
            })

        app_cfg = AppConfig(**flat_config)
        # 将 OutputConfig 的扩展字段注入（若提供）
        try:
            if 'output' in config_data:
                o = config_data['output']
                if isinstance(o, dict):
                    app_cfg.output.formats = o.get('formats', app_cfg.output.formats) or []
                    app_cfg.output.exclude_fields = o.get('exclude_fields', app_cfg.output.exclude_fields) or []
                    app_cfg.output.exclude_system_messages = bool(o.get('exclude_system_messages', app_cfg.output.exclude_system_messages))
                    app_cfg.output.exclude_time_only = bool(o.get('exclude_time_only', app_cfg.output.exclude_time_only))
                    app_cfg.output.aggressive_dedup = bool(o.get('aggressive_dedup', app_cfg.output.aggressive_dedup))
                    # 用户自定义时间分隔正则列表
                    try:
                        patterns = o.get('time_only_patterns', app_cfg.output.time_only_patterns)
                        if patterns is None:
                            patterns = []
                        elif isinstance(patterns, (list, tuple)):
                            patterns = [str(p) for p in patterns if isinstance(p, (str, bytes))]
                        else:
                            # 单字符串也允许，转换为列表
                            patterns = [str(patterns)]
                        app_cfg.output.time_only_patterns = patterns
                    except Exception:
                        pass
        except Exception:
            pass
        return app_cfg
    
    def save_config(self, config: AppConfig, file_path: Optional[str] = None) -> None:
        """
        Save configuration to file.
        
        Args:
            config: Configuration to save
            file_path: Path to save file. If None, uses current config_path
        """
        save_path = file_path or self.config_path or "config.yaml"
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
        
        config_dict = config.to_dict()
        
        file_ext = os.path.splitext(save_path)[1].lower()
        
        with open(save_path, 'w', encoding='utf-8') as f:
            if file_ext in ['.yaml', '.yml']:
                try:
                    import yaml
                    yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
                except ImportError:
                    raise ValueError("PyYAML is required to save YAML configuration files")
            elif file_ext == '.json':
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Unsupported configuration file format: {file_ext}")
    
    def get_config(self) -> AppConfig:
        """
        Get current configuration, loading if necessary.
        
        Returns:
            Current AppConfig instance
        """
        if self._config is None:
            return self.load_config()
        return self._config
    
    def reload_config(self) -> AppConfig:
        """
        Reload configuration from file.
        
        Returns:
            Reloaded AppConfig instance
        """
        self._config = None
        return self.load_config()
    
    def create_default_config_file(self, file_path: str = "config.yaml") -> None:
        """
        Create a default configuration file.
        
        Args:
            file_path: Path where to create the config file
        """
        default_config = AppConfig()
        self.save_config(default_config, file_path)
