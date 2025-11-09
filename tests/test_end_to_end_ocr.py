#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
端到端OCR处理流程测试
测试从图像输入到OCR结果输出的完整流程
"""

import os
import sys
import time
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ocr_processor import OCRProcessor, OCRConfig
from services.image_preprocessor import ImagePreprocessor


def create_test_image_with_text(text, width=400, height=200, font_size=24):
    """
    创建包含指定文本的测试图像
    
    Args:
        text: 要显示的文本
        width: 图像宽度
        height: 图像高度
        font_size: 字体大小
        
    Returns:
        PIL.Image对象
    """
    # 创建白色背景图像
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    
    try:
        # 尝试使用系统字体
        font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", font_size)
    except:
        try:
            # 备用字体
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
        except:
            # 使用默认字体
            font = ImageFont.load_default()
    
    # 计算文本位置（居中）
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    # 绘制黑色文本
    draw.text((x, y), text, fill='black', font=font)
    
    return image


@pytest.mark.slow
def test_end_to_end_ocr_processing():
    """测试完整的端到端OCR处理流程"""
    print("=== 测试端到端OCR处理流程 ===")
    
    # 创建OCR配置
    config = OCRConfig(
        language="ch",
        confidence_threshold=0.3,
        use_gpu=False
    )
    
    # 创建OCR处理器
    processor = OCRProcessor(config)
    
    # 初始化OCR引擎
    print("初始化OCR引擎...")
    start_time = time.time()
    assert processor.initialize_engine(), "OCR引擎初始化失败"
    init_time = time.time() - start_time
    print(f"OCR引擎初始化完成，耗时: {init_time:.2f}s")
    
    # 创建测试图像
    test_texts = [
        "Hello World 123",
        "你好世界测试",
        "OCR性能测试456",
        "多语言混合English中文"
    ]
    
    test_images = []
    for text in test_texts:
        test_images.append(create_test_image_with_text(text))
    
    # 测试每个图像
    all_results = []
    processing_times = []
    
    for i, (text, image) in enumerate(zip(test_texts, test_images)):
        print(f"\n处理图像 {i+1}/{len(test_texts)}: '{text}'")
        
        # 保存原始图像（用于调试）
        image_path = f"/tmp/test_image_{i}.png"
        image.save(image_path)
        
        # 处理图像
        start_time = time.time()
        result = processor.process_image(image)
        processing_time = time.time() - start_time
        processing_times.append(processing_time)
        
        # 记录结果
        all_results.append({
            'original_text': text,
            'ocr_text': result.text.strip(),
            'confidence': result.confidence,
            'processing_time': processing_time,
            'has_text': len(result.text.strip()) > 0
        })
        
        print(f"  OCR结果: '{result.text.strip()}'")
        print(f"  置信度: {result.confidence:.3f}")
        print(f"  处理时间: {processing_time:.3f}s")
        print(f"  检测到文本: {len(result.text.strip()) > 0}")
    
    # 分析结果
    print("\n=== 结果分析 ===")
    
    total_images = len(test_images)
    successful_ocr = sum(1 for r in all_results if r['has_text'])
    success_rate = successful_ocr / total_images
    
    avg_processing_time = np.mean(processing_times)
    min_processing_time = np.min(processing_times)
    max_processing_time = np.max(processing_times)
    
    print(f"总处理图像数: {total_images}")
    print(f"成功OCR图像数: {successful_ocr}")
    print(f"OCR成功率: {success_rate:.2%}")
    print(f"平均处理时间: {avg_processing_time:.3f}s")
    print(f"最短处理时间: {min_processing_time:.3f}s")
    print(f"最长处理时间: {max_processing_time:.3f}s")
    
    # 验证基本要求
    assert success_rate >= 0.5, f"OCR成功率过低: {success_rate:.2%} < 50%"
    assert avg_processing_time < 5.0, f"平均处理时间过长: {avg_processing_time:.3f}s >= 5s"
    
    # 显示详细结果
    print("\n=== 详细结果 ===")
    for i, result in enumerate(all_results):
        print(f"图像 {i+1}:")
        print(f"  原始文本: '{result['original_text']}'")
        print(f"  OCR文本: '{result['ocr_text']}'")
        print(f"  匹配度: {calculate_text_similarity(result['original_text'], result['ocr_text']):.2%}")
        print(f"  置信度: {result['confidence']:.3f}")
        print(f"  处理时间: {result['processing_time']:.3f}s")
    
    print("✅ 端到端OCR处理流程测试通过")
    return True


def calculate_text_similarity(text1, text2):
    """
    计算两个文本的相似度
    
    Args:
        text1: 第一个文本
        text2: 第二个文本
        
    Returns:
        相似度百分比 (0.0 - 1.0)
    """
    if not text1 or not text2:
        return 0.0
    
    # 简单的字符匹配相似度计算
    set1 = set(text1)
    set2 = set(text2)
    
    if not set1 or not set2:
        return 0.0
    
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    
    return len(intersection) / len(union) if union else 0.0


@pytest.mark.slow
def test_image_preprocessing_impact():
    """测试图像预处理对OCR效果的影响"""
    print("\n=== 测试图像预处理对OCR效果的影响 ===")
    
    config = OCRConfig(
        language="ch",
        confidence_threshold=0.3,
        use_gpu=False
    )
    
    processor = OCRProcessor(config)
    assert processor.initialize_engine(), "OCR引擎初始化失败"
    
    # 创建测试图像
    test_image = create_test_image_with_text("预处理测试文本")
    
    # 测试不同预处理配置
    preprocessing_configs = [
        {"name": "无预处理", "enhance_contrast": False, "reduce_noise": False},
        {"name": "仅对比度增强", "enhance_contrast": True, "reduce_noise": False},
        {"name": "仅降噪", "enhance_contrast": False, "reduce_noise": True},
        {"name": "完整预处理", "enhance_contrast": True, "reduce_noise": True}
    ]
    
    results = []
    
    for config in preprocessing_configs:
        print(f"\n测试配置: {config['name']}")
        
        # 应用预处理配置
        processor.config.enhance_contrast = config['enhance_contrast']
        processor.config.reduce_noise = config['reduce_noise']
        
        start_time = time.time()
        result = processor.process_image(test_image)
        processing_time = time.time() - start_time
        
        results.append({
            'config': config['name'],
            'text': result.text.strip(),
            'confidence': result.confidence,
            'processing_time': processing_time
        })
        
        print(f"  OCR结果: '{result.text.strip()}'")
        print(f"  置信度: {result.confidence:.3f}")
        print(f"  处理时间: {processing_time:.3f}s")
    
    # 分析预处理效果
    print("\n=== 预处理效果分析 ===")
    for result in results:
        print(f"{result['config']}: 置信度={result['confidence']:.3f}, 时间={result['processing_time']:.3f}s")
    
    print("✅ 图像预处理影响测试完成")
    return True


@pytest.mark.slow
def test_batch_processing_performance():
    """测试批量处理性能"""
    print("\n=== 测试批量处理性能 ===")
    
    config = OCRConfig(
        language="ch",
        confidence_threshold=0.3,
        use_gpu=False
    )
    
    processor = OCRProcessor(config)
    assert processor.initialize_engine(), "OCR引擎初始化失败"
    
    # 创建批量测试图像
    batch_size = 10
    test_images = [create_test_image_with_text(f"批量测试{i}") for i in range(batch_size)]
    
    # 批量处理
    print(f"处理 {batch_size} 张图像...")
    
    start_time = time.time()
    batch_results = []
    
    for i, image in enumerate(test_images):
        result = processor.process_image(image)
        batch_results.append(result)
        print(f"图像 {i+1}: '{result.text.strip()}' (置信度: {result.confidence:.3f})")
    
    total_time = time.time() - start_time
    avg_time = total_time / batch_size
    
    print(f"\n批量处理完成:")
    print(f"总时间: {total_time:.2f}s")
    print(f"平均每张: {avg_time:.2f}s")
    print(f"处理速度: {batch_size / total_time:.1f} 图像/秒")
    
    # 验证性能要求
    assert avg_time < 2.0, f"平均处理时间过长: {avg_time:.2f}s >= 2s"
    assert total_time < 30.0, f"总处理时间过长: {total_time:.2f}s >= 30s"
    
    print("✅ 批量处理性能测试通过")
    return True


if __name__ == "__main__":
    try:
        print("开始端到端OCR处理测试...")
        
        # 运行所有测试
        test_end_to_end_ocr_processing()
        test_image_preprocessing_impact()
        test_batch_processing_performance()
        
        print("\n🎉 所有端到端测试完成！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)