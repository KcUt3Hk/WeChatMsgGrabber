#!/usr/bin/env python3
"""
测试内容识别和提取功能
验证OCR处理器和消息解析器是否能正确识别和提取聊天内容
"""

import os
import sys
import time
import logging
from pathlib import Path
import pytest

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image
from services.ocr_processor import OCRProcessor
from services.message_parser import MessageParser
from services.image_preprocessor import ImagePreprocessor

def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('test_content_extraction.log', encoding='utf-8')
        ]
    )

@pytest.mark.slow
def test_ocr_processor():
    """测试OCR处理器功能"""
    print("🧪 测试OCR处理器...")
    
    ocr = OCRProcessor()
    
    # 初始化OCR引擎
    print("  初始化OCR引擎...")
    if not ocr.initialize_engine():
        print("❌ OCR引擎初始化失败")
        return False
    
    print("✅ OCR引擎初始化成功")
    
    # 测试图像预处理
    print("  测试图像预处理...")
    preprocessor = ImagePreprocessor()
    
    # 加载测试图像
    test_image_path = project_root / "tests" / "test_images" / "wechat_chat_sample.png"
    if not test_image_path.exists():
        print(f"⚠️  测试图像不存在: {test_image_path}")
        print("  跳过UI截图以避免在自动化环境中产生段错误。")
        pytest.skip("测试图像缺失，跳过OCR处理器测试以避免真实屏幕截图")
    else:
        test_image = Image.open(test_image_path)
    
    print(f"✅ 加载测试图像: {test_image.size}")
    
    # 预处理图像
    preprocessed = preprocessor.preprocess_for_ocr(test_image)
    print(f"✅ 图像预处理完成: {preprocessed.size}")
    
    # 测试OCR处理
    print("  测试OCR处理...")
    try:
        result = ocr.process_image(preprocessed, preprocess=False)
        print(f"✅ OCR处理成功: {len(result.text)} 字符")
        print(f"   提取文本: {repr(result.text[:100])}...")
        print(f"   置信度: {result.confidence:.3f}")
        
        # 测试文本区域提取
        print("  测试文本区域提取...")
        text_regions = ocr.extract_text_regions(preprocessed)
        print(f"✅ 提取到 {len(text_regions)} 个文本区域")
        
        for i, region in enumerate(text_regions[:3]):  # 显示前3个区域
            text_preview = region.text[:50] + "..." if len(region.text) > 50 else region.text
            print(f"   区域 {i+1}: {repr(text_preview)} (置信度: {region.confidence:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ OCR处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_message_parsing():
    """测试消息解析功能"""
    print("\n🧪 测试消息解析器...")
    
    parser = MessageParser()
    ocr = OCRProcessor()
    
    # 确保OCR引擎就绪
    if not ocr.is_engine_ready():
        if not ocr.initialize_engine():
            print("❌ OCR引擎未就绪")
            return False
    
    # 创建模拟文本区域
    from models.data_models import TextRegion, Rectangle
    
    # 模拟微信聊天消息的文本区域
    test_regions = [
        TextRegion(
            text="张三 14:30",
            confidence=0.95,
            bounding_box=Rectangle(x=50, y=100, width=200, height=30)
        ),
        TextRegion(
            text="你好，今天天气不错",
            confidence=0.92,
            bounding_box=Rectangle(x=50, y=130, width=300, height=40)
        ),
        TextRegion(
            text="李四 14:31",
            confidence=0.94,
            bounding_box=Rectangle(x=400, y=180, width=200, height=30)
        ),
        TextRegion(
            text="是的，很适合出门",
            confidence=0.91,
            bounding_box=Rectangle(x=400, y=210, width=250, height=40)
        )
    ]
    
    print("  使用模拟数据进行测试...")
    
    try:
        messages = parser.parse(test_regions)
        print(f"✅ 解析出 {len(messages)} 条消息")
        
        for i, msg in enumerate(messages):
            print(f"   消息 {i+1}:")
            print(f"     发送者: {msg.sender}")
            print(f"     内容: {repr(msg.content)}")
            print(f"     时间: {msg.timestamp}")
            print(f"     类型: {msg.message_type}")
            print(f"     置信度: {msg.confidence_score:.3f}")
        
        return True
        
    except Exception as e:
        print(f"❌ 消息解析失败: {e}")
        import traceback
        traceback.print_exc()
        return False

@pytest.mark.integration
@pytest.mark.slow
def test_integration():
    """测试集成功能 - OCR + 消息解析"""
    print("\n🧪 测试集成功能...")
    
    ocr = OCRProcessor()
    parser = MessageParser()
    preprocessor = ImagePreprocessor()
    
    # 初始化OCR引擎
    if not ocr.initialize_engine():
        print("❌ OCR引擎初始化失败")
        return False
    
    # 尝试获取真实微信聊天截图
    # 默认在自动化测试环境中跳过真实UI截图
    if os.getenv("ENABLE_UI_TESTS") != "1":
        print("⚠️  未启用真实UI集成测试（设置 ENABLE_UI_TESTS=1 以开启），改为使用解析器单测。")
        pytest.skip("默认跳过真实UI截图的集成测试")
    
    try:
        import pyautogui
        import pygetwindow as gw
        
        print("  尝试捕获微信聊天区域...")
        
        # 查找微信窗口
        wechat_windows = [w for w in gw.getWindowsWithTitle('微信') if '微信' in w.title]
        
        if not wechat_windows:
            print("⚠️  未找到微信窗口，使用模拟数据测试")
            return test_message_parsing()
        
        # 激活第一个微信窗口
        wechat_window = wechat_windows[0]
        wechat_window.activate()
        time.sleep(2)  # 等待窗口激活
        
        # 捕获聊天区域
        chat_area = (
            wechat_window.left + 100,
            wechat_window.top + 150,
            wechat_window.width - 200,
            wechat_window.height - 250
        )
        
        screenshot = pyautogui.screenshot(region=chat_area)
        print(f"✅ 捕获聊天区域截图: {screenshot.size}")
        
        # 预处理图像
        preprocessed = preprocessor.preprocess_for_ocr(screenshot)
        
        # OCR处理
        text_regions = ocr.extract_text_regions(preprocessed)
        print(f"✅ 提取到 {len(text_regions)} 个文本区域")
        
        # 消息解析
        messages = parser.parse(text_regions)
        print(f"✅ 解析出 {len(messages)} 条消息")
        
        # 显示解析结果
        for i, msg in enumerate(messages[:5]):  # 显示前5条消息
            print(f"   消息 {i+1}: {repr(msg.content)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 内容识别和提取功能测试")
    print("=" * 60)
    
    setup_logging()
    
    # 运行测试
    tests = [
        ("OCR处理器", test_ocr_processor),
        ("消息解析器", test_message_parsing),
        ("集成功能", test_integration)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 开始测试: {test_name}")
        success = test_func()
        results.append((test_name, success))
        print(f"  结果: {'✅ 通过' if success else '❌ 失败'}")
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n🎯 总体通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 所有内容识别和提取功能测试通过！")
        return True
    else:
        print("⚠️  部分测试未通过，需要进一步调试")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)