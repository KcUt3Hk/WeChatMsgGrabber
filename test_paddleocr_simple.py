#!/usr/bin/env python3
"""
简单测试PaddleOCR功能
"""
import os
import sys
# 动态将项目根目录加入 Python 路径（脚本位于项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from paddleocr import PaddleOCR
from PIL import Image
import numpy as np

def test_paddleocr():
    """测试PaddleOCR的基本功能"""
    print("=== 简单测试PaddleOCR ===")
    
    # 创建测试图像
    from create_test_image import create_test_image
    test_image_path = create_test_image()
    print(f"✅ 测试图像: {test_image_path}")
    
    # 加载图像
    image = Image.open(test_image_path)
    print(f"图像尺寸: {image.size}")
    
    # 转换为numpy数组
    image_array = np.array(image.convert('RGB'))
    print(f"数组形状: {image_array.shape}")
    
    # 初始化PaddleOCR
    print("初始化PaddleOCR...")
    ocr = PaddleOCR(lang='ch')
    print("✅ PaddleOCR初始化成功")
    
    # 测试OCR
    print("运行OCR...")
    result = ocr.ocr(image_array)
    
    print(f"结果类型: {type(result)}")
    
    if result is None:
        print("❌ OCR结果为None")
        return False
        
    if isinstance(result, list):
        print(f"结果长度: {len(result)}")
        
        for i, item in enumerate(result):
            print(f"第{i}项: {type(item)} - {item}")
            
            if isinstance(item, list):
                print(f"  该项长度: {len(item)}")
                for j, line in enumerate(item):
                    print(f"    第{j}行: {type(line)} - {line}")
                    
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        # 检查是否是标准的OCR结果格式
                        if isinstance(line[1], (list, tuple)) and len(line[1]) >= 2:
                            text = line[1][0]
                            confidence = line[1][1]
                            print(f"      文本: '{text}'")
                            print(f"      置信度: {confidence}")
                        elif isinstance(line[1], str):
                            text = line[1]
                            confidence = line[2] if len(line) >= 3 else 0.0
                            print(f"      文本: '{text}'")
                            print(f"      置信度: {confidence}")
    
    return True

def test_with_file_path():
    """使用文件路径测试OCR"""
    print("\n=== 使用文件路径测试OCR ===")
    
    from create_test_image import create_test_image
    test_image_path = create_test_image()
    
    ocr = PaddleOCR(lang='ch')
    
    print("使用文件路径运行OCR...")
    result = ocr.ocr(test_image_path)
    
    print(f"结果类型: {type(result)}")
    
    if result is None:
        print("❌ OCR结果为None")
        return False
        
    if isinstance(result, list) and len(result) > 0:
        if isinstance(result[0], list):
            print(f"检测到 {len(result[0])} 个文本区域")
            
            for i, line in enumerate(result[0]):
                if isinstance(line, (list, tuple)) and len(line) >= 2:
                    if isinstance(line[1], (list, tuple)) and len(line[1]) >= 2:
                        text = line[1][0]
                        confidence = line[1][1]
                        print(f"  区域 {i+1}: '{text}' (置信度: {confidence:.3f})")
                    elif isinstance(line[1], str):
                        text = line[1]
                        confidence = line[2] if len(line) >= 3 else 0.0
                        print(f"  区域 {i+1}: '{text}' (置信度: {confidence:.3f})")
            
            return len(result[0]) > 0
    
    print("❌ 没有检测到文本")
    return False

if __name__ == "__main__":
    print("开始PaddleOCR测试...")
    
    # 测试1: 使用numpy数组
    test_paddleocr()
    
    # 测试2: 使用文件路径
    success = test_with_file_path()
    
    if success:
        print("\n🎉 PaddleOCR测试成功!")
    else:
        print("\n❌ PaddleOCR测试失败")
        print("💡 可能需要检查PaddleOCR安装或模型文件")