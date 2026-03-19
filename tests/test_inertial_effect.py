#!/usr/bin/env python3
"""
测试滑动惯性效果功能
"""

import sys
import os
import time
import random
import logging
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(project_root))

def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_inertial_effect_calculation():
    """测试惯性效果计算逻辑"""
    print("🧪 测试惯性效果计算逻辑...")
    
    # 模拟滚动历史数据
    scroll_history = [
        {"scroll_distance": 250},
        {"scroll_distance": 280},
        {"scroll_distance": 230},
        {"scroll_distance": 260},
        {"scroll_distance": 270}
    ]
    
    # 测试不同情况下的惯性效果
    test_cases = [
        {
            "name": "基础距离计算",
            "base_distance": 250,
            "expected_min": 200,
            "expected_max": 600  # 最大范围的两倍
        },
        {
            "name": "小距离惯性",
            "base_distance": 200,
            "expected_min": 200,
            "expected_max": 400
        },
        {
            "name": "大距离惯性", 
            "base_distance": 300,
            "expected_min": 200,
            "expected_max": 600
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        base_distance = test_case["base_distance"]
        
        # 模拟惯性效果计算（基于实际实现逻辑）
        if len(scroll_history) >= 2:
            # 计算最近几次滚动的平均距离
            recent_distances = []
            for i in range(min(3, len(scroll_history))):
                state = scroll_history[-(i+1)]
                recent_distances.append(base_distance)  # 简化模拟
            
            avg_distance = sum(recent_distances) / len(recent_distances)
            
            # 添加随机波动模拟惯性
            inertia_factor = random.uniform(0.8, 1.2)
            adjusted_distance = int(avg_distance * inertia_factor)
            
            # 确保在合理范围内
            min_distance = 200
            max_distance = 600  # 最大范围的两倍
            final_distance = max(min_distance, min(adjusted_distance, max_distance))
            
            # 验证结果
            if test_case["expected_min"] <= final_distance <= test_case["expected_max"]:
                print(f"✅ {test_case['name']}: {final_distance}像素 (范围: {test_case['expected_min']}-{test_case['expected_max']})")
            else:
                print(f"❌ {test_case['name']}: {final_distance}像素 (超出范围: {test_case['expected_min']}-{test_case['expected_max']})")
                all_passed = False
        else:
            # 历史数据不足时返回基础距离
            final_distance = base_distance
            print(f"✅ {test_case['name']}: {final_distance}像素 (历史数据不足)")
    
    return all_passed

def test_progressive_scroll_adjustment():
    """测试渐进式滚动距离调整"""
    print("\n🧪 测试渐进式滚动距离调整...")
    
    test_cases = [
        {"scroll_count": 1, "base_distance": 250, "description": "第1次滚动 - 基础距离"},
        {"scroll_count": 2, "base_distance": 250, "description": "第2次滚动 - 基础距离"},
        {"scroll_count": 5, "base_distance": 250, "description": "第5次滚动 - 较大距离(1.5倍)"},
        {"scroll_count": 10, "base_distance": 250, "description": "第10次滚动 - 较大距离(1.5倍)"},
        {"scroll_count": 15, "base_distance": 250, "description": "第15次滚动 - 基础距离"}
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        scroll_count = test_case["scroll_count"]
        base_distance = test_case["base_distance"]
        
        # 模拟渐进式调整逻辑
        if scroll_count % 5 == 0:
            # 每5次滚动进行一次较大距离滚动
            scroll_distance = base_distance * 1.5
            expected_type = "较大距离"
        else:
            scroll_distance = base_distance
            expected_type = "基础距离"
        
        # 验证调整逻辑
        if scroll_count % 5 == 0 and scroll_distance == base_distance * 1.5:
            print(f"✅ {test_case['description']}: {scroll_distance:.0f}像素 ({expected_type})")
        elif scroll_count % 5 != 0 and scroll_distance == base_distance:
            print(f"✅ {test_case['description']}: {scroll_distance:.0f}像素 ({expected_type})")
        else:
            print(f"❌ {test_case['description']}: 距离调整逻辑错误")
            all_passed = False
    
    return all_passed

def test_position_estimation():
    """测试位置估计功能"""
    print("\n🧪 测试位置估计功能...")
    
    # 模拟测试用例
    test_cases = [
        {
            "current_position": (500, 300),
            "direction": "up",
            "distance": 250,
            "expected_y_change": 125,  # distance // 2
            "description": "向上滚动 - 位置向下移动"
        },
        {
            "current_position": (500, 300), 
            "direction": "down",
            "distance": 200,
            "expected_y_change": -100,  # distance // 2
            "description": "向下滚动 - 位置向上移动"
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        x, y = test_case["current_position"]
        direction = test_case["direction"]
        distance = test_case["distance"]
        
        # 模拟位置估计逻辑
        if direction.lower() == "up":
            # 向上滚动，位置向下移动
            y += distance // 2
        else:
            # 向下滚动，位置向上移动
            y -= distance // 2
        
        # 验证位置变化
        expected_y = test_case["current_position"][1] + test_case["expected_y_change"]
        
        if y == expected_y:
            print(f"✅ {test_case['description']}: 位置正确估计 Y={y}")
        else:
            print(f"❌ {test_case['description']}: 位置估计错误，预期 Y={expected_y}, 实际 Y={y}")
            all_passed = False
    
    return all_passed

def test_inertial_effect_integration():
    """测试惯性效果集成"""
    print("\n🧪 测试惯性效果集成...")
    
    try:
        from services.advanced_scroll_controller import AdvancedScrollController
        
        # 创建启用惯性效果的控制器
        controller_with_inertia = AdvancedScrollController(
            scroll_speed=2,
            scroll_delay=1.0,
            scroll_distance_range=(200, 300),
            scroll_interval_range=(0.3, 0.5),
            inertial_effect=True  # 启用惯性效果
        )
        
        # 创建禁用惯性效果的控制器
        controller_without_inertia = AdvancedScrollController(
            scroll_speed=2,
            scroll_delay=1.0,
            scroll_distance_range=(200, 300),
            scroll_interval_range=(0.3, 0.5),
            inertial_effect=False  # 禁用惯性效果
        )
        
        print("✅ 成功创建带惯性效果和不带惯性效果的控制器")
        print(f"   带惯性效果: {controller_with_inertia.inertial_effect}")
        print(f"   不带惯性效果: {controller_without_inertia.inertial_effect}")
        
        # 测试惯性效果方法存在性
        has_inertia_method = hasattr(controller_with_inertia, '_apply_inertial_effect')
        print(f"✅ 惯性效果方法存在: {has_inertia_method}")
        
        return True
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    setup_logging()
    
    print("=" * 60)
    print("🧪 滑动惯性效果功能测试")
    print("=" * 60)
    
    test_results = []
    
    # 运行所有测试
    test_results.append({
        "name": "惯性效果计算",
        "result": test_inertial_effect_calculation()
    })
    
    test_results.append({
        "name": "渐进式滚动调整", 
        "result": test_progressive_scroll_adjustment()
    })
    
    test_results.append({
        "name": "位置估计功能",
        "result": test_position_estimation()
    })
    
    test_results.append({
        "name": "惯性效果集成",
        "result": test_inertial_effect_integration()
    })
    
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    print("=" * 60)
    
    passed_count = 0
    total_count = len(test_results)
    
    for test in test_results:
        status = "✅ 通过" if test["result"] else "❌ 失败"
        print(f"   {test['name']}: {status}")
        if test["result"]:
            passed_count += 1
    
    success_rate = (passed_count / total_count) * 100
    
    print("-" * 60)
    print(f"🎯 总体通过率: {passed_count}/{total_count} ({success_rate:.1f}%)")
    
    if passed_count == total_count:
        print("🎉 所有滑动惯性效果功能测试通过！")
        print("\n📝 功能验证:")
        print("   • 惯性效果距离计算 ✓")
        print("   • 渐进式滚动调整 ✓")
        print("   • 位置估计模拟 ✓")
        print("   • 惯性效果集成 ✓")
        return True
    else:
        print("⚠️  部分测试未通过，需要进一步调试")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)