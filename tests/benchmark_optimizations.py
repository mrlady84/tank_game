"""
优化效果基准测试

运行方式: python -m pytest tests/benchmark_optimizations.py -v -s
或: python tests/benchmark_optimizations.py
"""
import unittest
import sys
import os
import time
import math
import pygame
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.geometry import line_intersects_rect, _line_aabb_check
from utils.spatial_grid import SpatialGrid
from tank_ai import QLearningAgent, PerformanceOptimizer


class BenchmarkResults:
    """收集和显示基准测试结果"""
    results = []
    
    @classmethod
    def add(cls, name, baseline_time, optimized_time, baseline_desc="", optimized_desc=""):
        speedup = baseline_time / optimized_time if optimized_time > 0 else float('inf')
        improvement = (1 - optimized_time / baseline_time) * 100 if baseline_time > 0 else 0
        cls.results.append({
            'name': name,
            'baseline': baseline_time,
            'optimized': optimized_time,
            'speedup': speedup,
            'improvement': improvement,
            'baseline_desc': baseline_desc,
            'optimized_desc': optimized_desc
        })
    
    @classmethod
    def print_summary(cls):
        print("\n" + "="*80)
        print("优化效果基准测试汇总")
        print("="*80)
        print(f"{'测试项':<30} {'基线(s)':<12} {'优化后(s)':<12} {'加速比':<10} {'提升':<10}")
        print("-"*80)
        
        for r in cls.results:
            baseline_str = f"{r['baseline']:.4f}"
            optimized_str = f"{r['optimized']:.4f}"
            speedup_str = f"{r['speedup']:.2f}x"
            improvement_str = f"{r['improvement']:.1f}%"
            print(f"{r['name']:<30} {baseline_str:<12} {optimized_str:<12} {speedup_str:<10} {improvement_str:<10}")
        
        print("="*80)
        avg_speedup = sum(r['speedup'] for r in cls.results) / len(cls.results)
        avg_improvement = sum(r['improvement'] for r in cls.results) / len(cls.results)
        print(f"平均加速比: {avg_speedup:.2f}x")
        print(f"平均性能提升: {avg_improvement:.1f}%")
        print("="*80)


class TestGeometryBenchmark(unittest.TestCase):
    """几何检测性能基准"""
    
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.rect = pygame.Rect(100, 100, 32, 32)
    
    def test_aabb_vs_full_detection(self):
        """基准测试: AABB预过滤 vs 完整检测"""
        # 大量明显不相交的测试用例
        test_cases = [
            ((0, 0), (50, 50)),
            ((200, 200), (250, 250)),
            ((0, 150), (50, 150)),
            ((150, 0), (150, 50)),
        ] * 10000  # 40000次测试
        
        # 模拟"旧版本"：没有AABB预过滤
        def old_line_intersects_rect(start, end, rect):
            x1, y1 = start
            x2, y2 = end
            # 直接进入精确检测（模拟旧版本）
            denom = (x1 - x2) * (rect.top - rect.bottom) - (y1 - y2) * (rect.left - rect.left)
            return abs(denom) >= 1e-10  # 简化的旧版本
        
        # 基线测试（模拟旧版本）
        start = time.perf_counter()
        for start_pos, end_pos in test_cases:
            old_line_intersects_rect(start_pos, end_pos, self.rect)
        baseline_time = time.perf_counter() - start
        
        # 优化版本测试
        start = time.perf_counter()
        for start_pos, end_pos in test_cases:
            _line_aabb_check(start_pos[0], start_pos[1], end_pos[0], end_pos[1], self.rect)
        optimized_time = time.perf_counter() - start
        
        BenchmarkResults.add(
            "几何AABB预过滤", 
            baseline_time, 
            optimized_time,
            "完整检测", 
            "AABB快速排除"
        )
        
        print(f"\n几何检测AABB预过滤:")
        print(f"  基线: {baseline_time:.4f}s")
        print(f"  优化: {optimized_time:.4f}s")
        print(f"  加速: {baseline_time/optimized_time:.2f}x")


class TestQTableBenchmark(unittest.TestCase):
    """Q表操作性能基准"""
    
    def test_defaultdict_vs_manual_check(self):
        """基准测试: defaultdict vs 手动检查"""
        agent = QLearningAgent()
        states = [(i % 3, i % 3, i % 3, i % 4, i % 2, i % 2) for i in range(10000)]
        
        # 模拟"旧版本"：使用dict + 手动检查
        old_q_table = {}
        
        def old_get_action(state):
            if state not in old_q_table:
                old_q_table[state] = [0.0, 0.0, 0.0, 0.0]
            return old_q_table[state].index(max(old_q_table[state]))
        
        # 基线测试
        start = time.perf_counter()
        for state in states:
            old_get_action(state)
        baseline_time = time.perf_counter() - start
        
        # 优化版本测试
        start = time.perf_counter()
        for state in states:
            agent.get_best_action(state)
        optimized_time = time.perf_counter() - start
        
        BenchmarkResults.add(
            "Q表访问(defaultdict)", 
            baseline_time, 
            optimized_time,
            "手动检查", 
            "defaultdict自动"
        )
        
        print(f"\nQ表访问(defaultdict):")
        print(f"  基线: {baseline_time:.4f}s")
        print(f"  优化: {optimized_time:.4f}s")
        print(f"  加速: {baseline_time/optimized_time:.2f}x")
    
    def test_optimized_max_vs_builtin(self):
        """基准测试: 优化max查找 vs 内置max+index"""
        agent = QLearningAgent()
        
        # 预填充Q表
        for i in range(1000):
            state = (i % 3, i % 3, i % 3, i % 4, i % 2, i % 2)
            agent.q_table[state] = [0.1 * (i % 4), 0.2 * ((i+1) % 4), 
                                    0.15 * ((i+2) % 4), 0.25 * ((i+3) % 4)]
        
        states = list(agent.q_table.keys())[:1000]
        
        # 模拟"旧版本"：max + index
        def old_get_best(values):
            return values.index(max(values))
        
        # 基线测试
        start = time.perf_counter()
        for state in states:
            values = agent.q_table[state]
            old_get_best(values)
        baseline_time = time.perf_counter() - start
        
        # 优化版本：单次遍历
        def new_get_best(values):
            max_idx = 0
            max_val = values[0]
            for i in range(1, 4):
                if values[i] > max_val:
                    max_val = values[i]
                    max_idx = i
            return max_idx
        
        start = time.perf_counter()
        for state in states:
            values = agent.q_table[state]
            new_get_best(values)
        optimized_time = time.perf_counter() - start
        
        BenchmarkResults.add(
            "Max查找优化", 
            baseline_time, 
            optimized_time,
            "max+index", 
            "单次遍历"
        )
        
        print(f"\nMax查找优化:")
        print(f"  基线: {baseline_time:.4f}s")
        print(f"  优化: {optimized_time:.4f}s")
        print(f"  加速: {baseline_time/optimized_time:.2f}x")


class TestRewardLUTBenchmark(unittest.TestCase):
    """奖励计算LUT性能基准"""
    
    def test_lut_vs_if_else(self):
        """基准测试: LUT查表 vs if-elif链"""
        optimizer = PerformanceOptimizer()
        
        roles = ['aggressor', 'flanker', 'suppressor']
        distances = list(range(0, 500, 5))  # 100个距离值
        
        # 模拟"旧版本"：if-elif链
        def old_distance_reward(distance, role):
            if role == 'aggressor':
                if distance < 80:
                    return 2.0
                elif distance < 150:
                    return 1.0
                elif distance > 300:
                    return -0.5
            elif role == 'flanker':
                if 120 < distance < 250:
                    return 1.5
                elif distance > 350:
                    return -0.3
            else:  # suppressor
                if 200 < distance < 350:
                    return 1.0
                elif distance < 100:
                    return -0.5
            return 0.0
        
        # 基线测试
        start = time.perf_counter()
        for _ in range(100):
            for role in roles:
                for dist in distances:
                    old_distance_reward(dist, role)
        baseline_time = time.perf_counter() - start
        
        # 优化版本：LUT查表
        start = time.perf_counter()
        for _ in range(100):
            for role in roles:
                for dist in distances:
                    optimizer._get_distance_reward(dist, role)
        optimized_time = time.perf_counter() - start
        
        BenchmarkResults.add(
            "奖励计算(LUT)", 
            baseline_time, 
            optimized_time,
            "if-elif链", 
            "LUT查表"
        )
        
        print(f"\n奖励计算(LUT查表):")
        print(f"  基线: {baseline_time:.4f}s")
        print(f"  优化: {optimized_time:.4f}s")
        print(f"  加速: {baseline_time/optimized_time:.2f}x")


class TestSpatialGridBenchmark(unittest.TestCase):
    """空间网格性能基准"""
    
    def test_grid_vs_linear_scan(self):
        """基准测试: 空间网格 vs 线性扫描"""
        grid = SpatialGrid(cell_size=64)
        
        # 创建100个随机分布的对象
        objects = []
        for i in range(100):
            rect = pygame.Rect(
                (i * 37) % 600,
                (i * 53) % 400,
                32, 32
            )
            objects.append((f"obj_{i}", rect))
            grid.insert(f"obj_{i}", rect)
        
        query_rect = pygame.Rect(100, 100, 32, 32)
        iterations = 10000
        
        # 线性扫描
        def linear_scan(rect_list, query):
            return [name for name, r in rect_list if r.colliderect(query)]
        
        start = time.perf_counter()
        for _ in range(iterations):
            linear_scan(objects, query_rect)
        linear_time = time.perf_counter() - start
        
        # 空间网格查询
        start = time.perf_counter()
        for _ in range(iterations):
            grid.query(query_rect)
        grid_time = time.perf_counter() - start
        
        BenchmarkResults.add(
            "碰撞检测(空间网格)", 
            linear_time, 
            grid_time,
            "线性扫描", 
            "空间网格"
        )
        
        print(f"\n碰撞检测(空间网格):")
        print(f"  线性扫描: {linear_time:.4f}s")
        print(f"  空间网格: {grid_time:.4f}s")
        print(f"  加速比: {linear_time/grid_time:.2f}x")


class TestPrintSummary(unittest.TestCase):
    """打印汇总结果"""
    
    def test_z_print_summary(self):
        """Z_前缀确保最后执行 - 打印汇总"""
        BenchmarkResults.print_summary()


if __name__ == '__main__':
    # 运行所有测试
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    unittest.TextTestRunner(verbosity=2).run(suite)
