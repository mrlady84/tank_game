"""
性能优化验证测试

测试内容:
1. 几何检测AABB预过滤性能
2. Q表defaultdict性能
3. 奖励计算LUT性能
4. 空间网格碰撞检测性能
"""
import unittest
import sys
import os
import time
import pygame
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.geometry import line_intersects_rect, line_intersects_line, _line_aabb_check
from utils.spatial_grid import SpatialGrid
from tank_ai import QLearningAgent, PerformanceOptimizer


class TestGeometryOptimization(unittest.TestCase):
    """测试几何检测优化"""
    
    def setUp(self):
        pygame.init()
        self.rect = pygame.Rect(100, 100, 32, 32)
    
    def test_aabb_fast_rejection(self):
        """测试AABB快速排除明显不相交的情况"""
        # 明显不相交的线段 - 应该在AABB阶段就返回False
        start = (0, 0)
        end = (10, 10)
        
        # 使用优化后的函数
        result = line_intersects_rect(start, end, self.rect)
        self.assertFalse(result)
    
    def test_aabb_performance(self):
        """测试AABB预过滤性能提升"""
        # 准备大量不相交的测试用例
        test_cases = [
            ((0, 0), (50, 50)),      # 左上外
            ((200, 200), (250, 250)), # 右下外
            ((0, 150), (50, 150)),    # 左侧
            ((150, 0), (150, 50)),    # 上侧
        ] * 1000  # 4000次测试
        
        start = time.perf_counter()
        for start_pos, end_pos in test_cases:
            line_intersects_rect(start_pos, end_pos, self.rect)
        elapsed = time.perf_counter() - start
        
        # 优化后应该在短时间内完成（AABB快速排除）
        print(f"\n几何检测4000次耗时: {elapsed:.4f}s")
        self.assertLess(elapsed, 1.0)  # 应该小于1秒


class TestQTableOptimization(unittest.TestCase):
    """测试Q表defaultdict优化"""
    
    def setUp(self):
        self.agent = QLearningAgent()
    
    def test_defaultdict_auto_init(self):
        """测试defaultdict自动初始化"""
        # 访问不存在的状态 - 应该自动初始化为[0.0, 0.0, 0.0, 0.0]
        state = (0, 1, 2, 3, 0, 1)
        values = self.agent.q_table[state]
        
        self.assertEqual(values, [0.0, 0.0, 0.0, 0.0])
    
    def test_get_best_action_performance(self):
        """测试get_best_action性能"""
        # 准备大量状态
        states = [(i % 3, i % 3, i % 3, i % 4, i % 2, i % 2) for i in range(1000)]
        
        # 预热
        for state in states[:100]:
            self.agent.get_best_action(state)
        
        start = time.perf_counter()
        for state in states:
            self.agent.get_best_action(state)
        elapsed = time.perf_counter() - start
        
        print(f"\nQ表get_best_action 1000次耗时: {elapsed:.4f}s")
        self.assertLess(elapsed, 0.5)
    
    def test_optimized_max_lookup(self):
        """测试优化后的max查找（单次遍历）"""
        state = (1, 1, 1, 1, 0, 0)
        self.agent.q_table[state] = [0.1, 0.5, 0.3, 0.2]
        
        action = self.agent.get_best_action(state)
        self.assertEqual(action, 1)  # 最大值0.5的索引是1


class TestRewardLUTOptimization(unittest.TestCase):
    """测试奖励计算LUT优化"""
    
    def setUp(self):
        self.optimizer = PerformanceOptimizer()
    
    def test_lut_initialization(self):
        """测试LUT已正确初始化"""
        self.assertIn('aggressor', self.optimizer._reward_lut)
        self.assertIn('flanker', self.optimizer._reward_lut)
        self.assertIn('suppressor', self.optimizer._reward_lut)
        
        # 检查LUT大小
        self.assertEqual(len(self.optimizer._reward_lut['aggressor']), 25)
    
    def test_lut_distance_reward(self):
        """测试LUT距离奖励计算"""
        # aggressor: <80应返回2.0
        reward = self.optimizer._get_distance_reward(50, 'aggressor')
        self.assertEqual(reward, 2.0)
        
        # aggressor: 80-150应返回1.0
        reward = self.optimizer._get_distance_reward(100, 'aggressor')
        self.assertEqual(reward, 1.0)
        
        # aggressor: >300应返回-0.5
        reward = self.optimizer._get_distance_reward(400, 'aggressor')
        self.assertEqual(reward, -0.5)
    
    def test_lut_performance(self):
        """测试LUT查表性能"""
        roles = ['aggressor', 'flanker', 'suppressor']
        distances = [50, 100, 150, 200, 250, 300, 350, 400]
        
        start = time.perf_counter()
        for _ in range(10000):
            for role in roles:
                for dist in distances:
                    self.optimizer._get_distance_reward(dist, role)
        elapsed = time.perf_counter() - start
        
        print(f"\nLUT查表 240000次耗时: {elapsed:.4f}s")
        self.assertLess(elapsed, 1.0)


class TestSpatialGrid(unittest.TestCase):
    """测试空间网格碰撞检测"""
    
    def setUp(self):
        self.grid = SpatialGrid(cell_size=64)
    
    def test_insert_and_query(self):
        """测试插入和查询"""
        rect1 = pygame.Rect(10, 10, 32, 32)
        rect2 = pygame.Rect(100, 100, 32, 32)
        
        self.grid.insert("tank1", rect1)
        self.grid.insert("tank2", rect2)
        
        # 查询rect1附近的对象
        nearby = self.grid.query(rect1)
        self.assertIn("tank1", nearby)
    
    def test_performance_vs_linear(self):
        """测试空间网格性能 vs 线性扫描"""
        # 创建大量对象
        objects = [(f"obj_{i}", pygame.Rect(
            (i * 37) % 600, 
            (i * 53) % 400, 
            32, 32
        )) for i in range(100)]
        
        # 插入到空间网格
        for name, rect in objects:
            self.grid.insert(name, rect)
        
        query_rect = pygame.Rect(100, 100, 32, 32)
        
        # 测试空间网格查询性能
        start = time.perf_counter()
        for _ in range(1000):
            self.grid.query(query_rect)
        grid_time = time.perf_counter() - start
        
        # 测试线性扫描性能
        start = time.perf_counter()
        for _ in range(1000):
            result = []
            for name, rect in objects:
                if rect.colliderect(query_rect):
                    result.append(name)
        linear_time = time.perf_counter() - start
        
        print(f"\n空间网格查询1000次: {grid_time:.4f}s")
        print(f"线性扫描查询1000次: {linear_time:.4f}s")
        print(f"加速比: {linear_time/grid_time:.2f}x")
        
        # 空间网格应该更快
        self.assertLess(grid_time, linear_time)
    
    def test_stats(self):
        """测试网格统计信息"""
        for i in range(10):
            rect = pygame.Rect(i * 50, i * 30, 32, 32)
            self.grid.insert(f"tank_{i}", rect)
        
        stats = self.grid.get_stats()
        self.assertIn('total_cells', stats)
        self.assertIn('non_empty_cells', stats)
        print(f"\n空间网格统计: {stats}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
