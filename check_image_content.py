#!/usr/bin/env python3
"""
检查图像内容的简单脚本
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# 动态将项目根目录加入 Python 路径（脚本位于项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def analyze_image(image_path):
    """分析图像内容"""
    print(f"=== 分析图像: {image_path} ===")
    
    # 检查文件是否存在
    if not os.path.exists(image_path):
        print(f"❌ 文件不存在: {image_path}")
        return False
    
    # 加载图像
    try:
        image = Image.open(image_path)
        print(f"✅ 图像加载成功")
        print(f"   尺寸: {image.size}")
        print(f"   模式: {image.mode}")
        print(f"   格式: {image.format}")
    except Exception as e:
        print(f"❌ 图像加载失败: {e}")
        return False
    
    # 分析图像统计信息
    if image.mode == 'RGB':
        # 转换为numpy数组进行分析
        import numpy as np
        img_array = np.array(image)
        
        print(f"\n📊 图像统计信息:")
        print(f"   像素总数: {img_array.size // 3}")
        print(f"   平均亮度: {np.mean(img_array):.2f}")
        print(f"   亮度标准差: {np.std(img_array):.2f}")
        print(f"   最小亮度: {np.min(img_array)}")
        print(f"   最大亮度: {np.max(img_array)}")
        
        # 检查是否为纯色图像
        unique_colors = len(np.unique(img_array.reshape(-1, 3), axis=0))
        print(f"   唯一颜色数量: {unique_colors}")
        
        if unique_colors <= 10:
            print("⚠️  警告: 图像颜色数量很少，可能是纯色或简单背景")
        
        # 检查对比度
        contrast = np.max(img_array) - np.min(img_array)
        print(f"   对比度范围: {contrast}")
        
        if contrast < 50:
            print("⚠️  警告: 图像对比度较低，可能影响OCR识别")
    
    # 显示图像预览信息
    print(f"\n👀 图像预览:")
    print(f"   左上角区域像素: {list(image.getpixel((0, 0))[:3]) if image.mode == 'RGB' else image.getpixel((0, 0))}")
    print(f"   中心区域像素: {list(image.getpixel((image.width//2, image.height//2))[:3]) if image.mode == 'RGB' else image.getpixel((image.width//2, image.height//2))}")
    print(f"   右下角区域像素: {list(image.getpixel((image.width-1, image.height-1))[:3]) if image.mode == 'RGB' else image.getpixel((image.width-1, image.height-1))}")
    
    # 保存缩略图用于检查
    thumbnail_path = "/tmp/image_preview_thumbnail.png"
    image.thumbnail((200, 200))
    image.save(thumbnail_path)
    print(f"   缩略图已保存: {thumbnail_path}")
    
    return True

def main():
    image_path = "/tmp/debug_screenshot.png"
    
    if not analyze_image(image_path):
        print("\n❌ 图像分析失败")
        return
    
    print("\n✅ 图像分析完成")
    print("\n💡 建议:")
    print("1. 检查截图是否包含文本内容")
    print("2. 确保截图清晰且对比度足够")
    print("3. 尝试使用不同的截图区域")
    print("4. 检查图像是否过于简单或纯色")

if __name__ == "__main__":
    main()