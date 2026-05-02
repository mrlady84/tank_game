"""
坦克AI系统模块
==============

组件:
1. PrioritizedReplayBuffer - 优先级经验回放缓冲区
   - 使用累积概率+二分查找实现O(n log n)采样
   - 支持动态优先级更新

2. PerformanceOptimizer - 性能优化缓存系统
   - 状态和奖励缓存(20帧TTL，惰性重建)
   - 每300帧清理过期缓存

3. QLearningAgent - Q学习算法实现
   - 状态空间: 相对位置(3x3) x 距离(3) x 方向(4) x 障碍(2) x 盟友(2) x 朝向(4) = 1728种
   - 动作空间: 4个移动方向
   - LRU淘汰机制(Q-table最大5000状态)

4. GeneticOptimizer - 遗传算法超参数优化
   - 优化目标: learning_rate, discount_factor, exploration_rate
   - 策略: 锦标赛选择 + 单点交叉 + 高斯变异
   - 种群大小: 10

5. HybridAgent - 混合AI代理
   - 组合Q-learning和遗传算法
   - 渐进式进化策略(3阶段: 数据积累→轻量进化→标准进化)

6. AutoAI - 自动路径finding系统
   - A*算法(限制200次迭代，曼哈顿距离启发式)
   - 砖墙检测与射击
   - 卡顿检测(3秒内移动<3单位则切换目标)

7. PerformanceMonitor - 性能监控系统
   - 实时跟踪FPS/CPU/内存/缓存命中率
   - 每1000帧自动分析性能趋势

性能优化:
- 缓存命中率目标: >80%
- 避免O(n²)复杂度（使用二分查找、距离平方比较）
- 禁用自动GC，手动控制内存清理

作者: Tank Battle AI Team
版本: 2.0
"""

import os
import random
import pickle
import math
from collections import deque, defaultdict
import copy
import time
import logging
import pygame
import bisect
from config.ai_config import *
from config.game_config import TILE_SIZE, SCREEN_COLS, SCREEN_ROWS
from utils.geometry import line_intersects_rect, is_between

# PLAYFIELD_RECT will be initialized at runtime
PLAYFIELD_RECT = None


class PrioritizedReplayBuffer:
    """
    优先级经验回放缓冲区
    
    使用累积概率+二分查找实现高效的优先级采样。
    相比均匀随机采样，优先学习TD误差大的经验，加速收敛。
    
    算法复杂度:
    - add: O(n) - 需要重建累积概率
    - sample: O(batch_size × log n) - 二分查找
    - update_priorities: O(n) - 重建累积概率
    
    优化策略:
    - 惰性重建: 只在sample时检查是否需要重建
    - 拒绝采样: 避免线性扫描已选索引
    """

    def __init__(self, capacity, alpha=0.6, beta=0.4, beta_increment=1e-6):
        """
        初始化优先级回放缓冲区
        
        Args:
            capacity: 缓冲区容量
            alpha: 优先级指数，控制采样概率分布(0=均匀, 1=纯优先级)
            beta: 重要性采样指数，用于校正偏差(0=无校正, 1=完全校正)
            beta_increment: 每采样一次beta的增量，逐渐趋向完全校正
        """
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.beta_max = 1.0

        self.buffer = []
        self.priorities = []
        self.cumulative_probs = []  # 累积概率，用于二分查找
        self.pos = 0
        self.max_priority = 1.0
        self.total_priority = 0.0  # 总优先级，用于快速计算
        self._dirty = False  # 标记是否需要重建累积概率
        self._sample_count = 0  # 采样计数器，减少重建频率

    def add(self, experience, priority=None):
        """添加经验到缓冲区 - O(1)"""
        if priority is None:
            priority = self.max_priority

        if len(self.buffer) < self.capacity:
            self.buffer.append(experience)
            self.priorities.append(priority)
            self.total_priority += priority
        else:
            # 覆盖旧数据
            old_priority = self.priorities[self.pos]
            self.buffer[self.pos] = experience
            self.priorities[self.pos] = priority
            self.total_priority = self.total_priority - old_priority + priority

        self.pos = (self.pos + 1) % self.capacity
        self._dirty = True  # 标记需要重建

    def _ensure_cumulative_probs(self):
        """惰性重建累积概率 - 优化版，减少重建频率"""
        # 只在dirty且采样次数超过阈值时重建
        if self._dirty:
            self._rebuild_cumulative_probs()
            self._dirty = False
            self._sample_count = 0
        else:
            # 每100次采样重建一次，避免频繁重建
            self._sample_count += 1
            if self._sample_count >= 100:
                self._rebuild_cumulative_probs()
                self._sample_count = 0

    def _rebuild_cumulative_probs(self):
        """重建累积概率列表 - O(n)但只在添加时调用"""
        self.cumulative_probs = []
        cumulative = 0.0
        for p in self.priorities:
            cumulative += p ** self.alpha
            self.cumulative_probs.append(cumulative)

    def sample(self, batch_size):
        """优先级采样 - O(batch_size × log n)，使用拒绝采样避免线性扫描"""
        if len(self.buffer) < batch_size:
            return [], [], []

        # 确保累积概率是最新的
        self._ensure_cumulative_probs()

        total_priority = self.cumulative_probs[-1] if self.cumulative_probs else 0
        if total_priority == 0:
            return [], [], []

        indices = []
        seen = set()
        max_attempts = batch_size * 10

        for _ in range(batch_size):
            if len(indices) >= batch_size:
                break

            for _ in range(max_attempts):
                r = random.random() * total_priority
                idx = bisect.bisect_left(self.cumulative_probs, r)

                if idx < len(self.buffer) and idx not in seen:
                    indices.append(idx)
                    seen.add(idx)
                    break

        if not indices:
            return [], [], []

        samples = [self.buffer[idx] for idx in indices]

        # 计算重要性采样权重
        weights = []
        for idx in indices:
            prob = (self.priorities[idx] ** self.alpha) / total_priority
            weight = (len(self.buffer) * prob) ** (-self.beta)
            weights.append(weight)

        if weights:
            max_weight = max(weights)
            weights = [w / max_weight for w in weights]

        self.beta = min(self.beta_max, self.beta + self.beta_increment)

        return samples, indices, weights

    def update_priorities(self, indices, priorities):
        """更新优先级 - O(n)重建累积概率"""
        for idx, priority in zip(indices, priorities):
            if idx < len(self.priorities):
                old_priority = self.priorities[idx]
                self.priorities[idx] = priority
                self.max_priority = max(self.max_priority, priority)
                self.total_priority += priority - old_priority

        # 标记需要重建（惰性）
        self._dirty = True

    def __len__(self):
        return len(self.buffer)



class PerformanceOptimizer:
    """性能优化缓存系统"""
    
    # 预计算距离奖励LUT (Lookup Table) - 避免运行时if-elif链
    # 距离分段: 每20像素一个桶，最大500像素
    _DISTANCE_BUCKETS = 25  # 500 / 20
    
    def _init_reward_lut(self):
        """初始化奖励查找表"""
        # aggressor: 近距离进攻型
        # flanker: 侧翼包抄型
        # suppressor: 远程压制型
        self._reward_lut = {
            'aggressor': [0.0] * self._DISTANCE_BUCKETS,
            'flanker': [0.0] * self._DISTANCE_BUCKETS,
            'suppressor': [0.0] * self._DISTANCE_BUCKETS
        }
        
        bucket_size = 20  # 每个桶20像素
        for i in range(self._DISTANCE_BUCKETS):
            dist = i * bucket_size
            
            # aggressor LUT
            if dist < 80:
                self._reward_lut['aggressor'][i] = 2.0
            elif dist < 150:
                self._reward_lut['aggressor'][i] = 1.0
            elif dist > 300:
                self._reward_lut['aggressor'][i] = -0.5
            else:
                self._reward_lut['aggressor'][i] = 0.0
            
            # flanker LUT
            if 120 < dist < 250:
                self._reward_lut['flanker'][i] = 1.5
            elif dist > 350:
                self._reward_lut['flanker'][i] = -0.3
            else:
                self._reward_lut['flanker'][i] = 0.0
            
            # suppressor LUT
            if 200 < dist < 350:
                self._reward_lut['suppressor'][i] = 1.0
            elif dist < 100:
                self._reward_lut['suppressor'][i] = -0.5
            else:
                self._reward_lut['suppressor'][i] = 0.0
    
    def _get_distance_reward(self, distance, role):
        """使用LUT快速获取距离奖励"""
        bucket = min(int(distance / 20), self._DISTANCE_BUCKETS - 1)
        return self._reward_lut.get(role, self._reward_lut['suppressor'])[bucket]
    
    def __init__(self):
        self.state_cache = {}  # 缓存状态计算结果
        self.reward_cache = {}  # 缓存奖励计算结果
        self.cache_timeout = 20  # 增加到20帧缓存（原来5帧）
        self.frame_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_cleanup = 0
        self.last_frame_count = 0  # 记录上次更新的实际帧数
        self._init_reward_lut()  # 初始化奖励LUT

    def _cleanup_cache(self):
        """定期清理过期缓存，防止内存泄漏 - 优化版，原地删除"""
        if self.frame_count - self.last_cleanup < 300:
            return

        self.last_cleanup = self.frame_count
        current_frame_group = self.frame_count // self.cache_timeout
        min_frame_group = current_frame_group - 3

        expired_state_keys = [k for k in self.state_cache if k[-1] < min_frame_group]
        for k in expired_state_keys:
            del self.state_cache[k]

        expired_reward_keys = [k for k in self.reward_cache if k[-2] < min_frame_group]
        for k in expired_reward_keys:
            del self.reward_cache[k]

    def get_cached_state(self, enemy, target, walls, all_enemies, force_update=False):
        """获取缓存的状态，如果不存在则计算 - 优化键设计"""
        self._cleanup_cache()
        current_frame_group = self.frame_count // self.cache_timeout

        # 改进的缓存键：使用网格位置替代id，提高命中率
        enemy_grid_x = enemy.rect.centerx // TILE_SIZE
        enemy_grid_y = enemy.rect.centery // TILE_SIZE
        target_grid_x = target.rect.centerx // TILE_SIZE
        target_grid_y = target.rect.centery // TILE_SIZE

        cache_key = (
            enemy_grid_x,
            enemy_grid_y,
            enemy.direction,
            target_grid_x,
            target_grid_y,
            current_frame_group
        )

        if not force_update and cache_key in self.state_cache:
            self.cache_hits += 1
            return self.state_cache[cache_key]
        else:
            self.cache_misses += 1
            state = self._compute_state(enemy, target, walls, all_enemies)
            self.state_cache[cache_key] = state
            return state

    def get_cached_reward(self, enemy, action, target, all_enemies, roles, walls,
                         killed_player=False, took_damage=False, force_update=False,
                         reward_weights=None):
        """获取缓存的奖励，如果不存在则计算 - 优化键设计"""
        current_frame_group = self.frame_count // self.cache_timeout

        enemy_grid_x = enemy.rect.centerx // TILE_SIZE
        enemy_grid_y = enemy.rect.centery // TILE_SIZE
        target_grid_x = target.rect.centerx // TILE_SIZE
        target_grid_y = target.rect.centery // TILE_SIZE

        # 权重哈希：不同权重个体不能共享缓存
        weights_key = tuple(sorted(reward_weights.items())) if reward_weights else ()

        role = roles.get(enemy, 'suppressor')

        cache_key = (
            enemy_grid_x,
            enemy_grid_y,
            action,
            killed_player,
            took_damage,
            target_grid_x,
            target_grid_y,
            role,
            current_frame_group,
            weights_key
        )

        if not force_update and cache_key in self.reward_cache:
            self.cache_hits += 1
            return self.reward_cache[cache_key]
        else:
            self.cache_misses += 1
            reward = self._compute_reward(enemy, action, target, all_enemies, roles, walls,
                                        killed_player, took_damage, reward_weights)
            self.reward_cache[cache_key] = reward
            return reward

    def _compute_state(self, enemy, target, walls, all_enemies):
        """实际计算状态（原有逻辑）"""
        enemy_x = enemy.rect.centerx
        enemy_y = enemy.rect.centery
        target_x = target.rect.centerx
        target_y = target.rect.centery

        # 简化相对位置 (3种)
        dx = target_x - enemy_x
        dy = target_y - enemy_y

        if abs(dx) < TILE_SIZE:
            rel_x = 1  # 同列
        elif dx > 0:
            rel_x = 2  # 玩家在右边
        else:
            rel_x = 0  # 玩家在左边

        if abs(dy) < TILE_SIZE:
            rel_y = 1  # 同行
        elif dy > 0:
            rel_y = 2  # 玩家在下边
        else:
            rel_y = 0  # 玩家在上边

        # 简化距离 (3种)
        distance = math.hypot(dx, dy)
        if distance < 100:
            distance_cat = 0  # 近距离
        elif distance < 250:
            distance_cat = 1  # 中距离
        else:
            distance_cat = 2  # 远距离

        # 目标方向 (4种)
        if abs(dx) > abs(dy):
            direction = 1 if dx > 0 else 3  # 右/左
        else:
            direction = 2 if dy > 0 else 0  # 下/上

        # 简化障碍物检测 (2种)
        has_obstacle = 0
        if walls:
            nearby_walls = sorted(walls, key=lambda w: (w.centerx - enemy_x)**2 + (w.centery - enemy_y)**2)[:5]
            for wall in nearby_walls:
                wall_center_x = wall.centerx
                wall_center_y = wall.centery
                if is_between(wall_center_x, enemy_x, target_x) and \
                   is_between(wall_center_y, enemy_y, target_y):
                    has_obstacle = 1
                    break

        # 简化的盟友检测 (2种)
        has_ally = 0
        if all_enemies:
            for other in all_enemies:
                if other != enemy:
                    dist = math.hypot(other.rect.centerx - enemy_x, other.rect.centery - enemy_y)
                    if dist < 150:
                        has_ally = 1
                        break

        # 自身朝向 (4种): 0=上, 1=右, 2=下, 3=左
        self_facing = enemy.direction

        # 对准检测 (2种): 自身朝向是否对准玩家，射击有效范围内
        align_tol = TILE_SIZE * 1.5
        if self_facing == 0:
            aligned = 1 if (dy < 0 and abs(dx) < align_tol) else 0
        elif self_facing == 1:
            aligned = 1 if (dx > 0 and abs(dy) < align_tol) else 0
        elif self_facing == 2:
            aligned = 1 if (dy > 0 and abs(dx) < align_tol) else 0
        else:
            aligned = 1 if (dx < 0 and abs(dy) < align_tol) else 0

        return (rel_x, rel_y, distance_cat, direction, has_obstacle, has_ally, self_facing, aligned)

    def _compute_reward(self, enemy, action, target, all_enemies, roles, walls,
                       killed_player=False, took_damage=False, reward_weights=None):
        """实际计算奖励，奖励权重由遗传算法优化"""
        if reward_weights is None:
            reward_weights = {}

        survival_bonus = reward_weights.get('survival_bonus', DEFAULT_SURVIVAL_BONUS)
        kill_reward    = reward_weights.get('kill_reward',    DEFAULT_KILL_REWARD)
        distance_scale = reward_weights.get('distance_scale', DEFAULT_DISTANCE_SCALE)
        team_bonus     = reward_weights.get('team_bonus',     DEFAULT_TEAM_BONUS)

        reward = survival_bonus

        enemy_x, enemy_y = enemy.rect.centerx, enemy.rect.centery
        target_x, target_y = target.rect.centerx, target.rect.centery
        distance_to_target = math.hypot(enemy_x - target_x, enemy_y - target_y)

        # 击杀/受伤奖励
        if killed_player:
            reward += kill_reward
        if took_damage:
            reward -= 3.0

        # 距离奖励 - 使用LUT查表，乘以遗传算法优化的缩放系数
        role = roles.get(enemy, 'suppressor')
        reward += self._get_distance_reward(distance_to_target, role) * distance_scale

        # flanker额外奖励：保持45度角
        if role == 'flanker':
            dx = abs(enemy_x - target_x)
            dy = abs(enemy_y - target_y)
            if abs(dx - dy) < 50:
                reward += 0.5 * distance_scale

        # 视野奖励
        has_line_of_sight = True
        if walls:
            nearby_walls = sorted(walls, key=lambda w: (w.centerx - enemy_x)**2 + (w.centery - enemy_y)**2)[:5]
            for wall in nearby_walls:
                if line_intersects_rect((enemy_x, enemy_y), (target_x, target_y), wall):
                    has_line_of_sight = False
                    break

        if has_line_of_sight and distance_to_target < 250:
            reward += 0.2

        # 团队协调 - 一次遍历，使用距离平方避免三角函数
        nearby_allies = 0
        too_close_allies = 0

        nearby_dist_sq_lower = 80 * 80
        nearby_dist_sq_upper = 200 * 200
        too_close_dist_sq = 60 * 60

        for other in all_enemies:
            if other != enemy:
                dx = other.rect.centerx - enemy_x
                dy = other.rect.centery - enemy_y
                dist_sq = dx * dx + dy * dy

                if nearby_dist_sq_lower < dist_sq < nearby_dist_sq_upper:
                    nearby_allies += 1

                if dist_sq < too_close_dist_sq:
                    too_close_allies += 1

        if nearby_allies > 0:
            reward += min(nearby_allies * 0.15, team_bonus)

        if too_close_allies > 0:
            reward -= too_close_allies * 0.3

        return reward

    def get_cache_stats(self):
        """获取缓存统计信息"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total_requests if total_requests > 0 else 0
        return {
            'hit_rate': hit_rate,
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'state_cache_size': len(self.state_cache),
            'reward_cache_size': len(self.reward_cache)
        }


# 全局性能优化器实例
performance_optimizer = PerformanceOptimizer()


def can_move_rect(rect, dx, dy, walls):
    """Check if a rectangle can move by dx, dy without colliding with walls"""
    global PLAYFIELD_RECT
    if PLAYFIELD_RECT is None:
        PLAYFIELD_RECT = pygame.Rect(0, 0, TILE_SIZE * SCREEN_COLS, TILE_SIZE * SCREEN_ROWS)
    
    new_rect = rect.move(dx, dy)
    # Check if new position is within game boundaries
    if not PLAYFIELD_RECT.contains(new_rect):
        return False
    path_rect = rect.union(new_rect)
    for wall in walls:
        if wall.colliderect(path_rect):
            return False
    return True


# 动作空间：0-3 移动方向（上/右/下/左），4 射击
NUM_ACTIONS = 5
ACTION_SHOOT = 4


class QLearningAgent:
    """
    Q学习算法实现
    
    算法:
        Q(s,a) ← Q(s,a) + α[r + γ·max_a'Q(s',a') - Q(s,a)]
    
    参数:
        α (learning_rate): 学习率，控制新信息覆盖旧信息的速度
        γ (discount_factor): 折扣因子，权衡即时和未来奖励
        ε (exploration_rate): 探索率，ε-贪心策略的随机探索概率
    
    状态表示:
        (rel_x, rel_y, distance_cat, direction, has_obstacle, has_ally, self_facing, aligned)
        - rel_x/rel_y: 目标相对位置(0=左/上, 1=同行/列, 2=右/下)
        - distance_cat: 距离分类(0<100px, 1<250px, 2>=250px)
        - direction: 目标方向(0上, 1右, 2下, 3左)
        - has_obstacle: 是否有障碍物阻挡
        - has_ally: 150px内是否有盟友
        - self_facing: 自身朝向(0上, 1右, 2下, 3左)
        - aligned: 自身朝向是否对准玩家射击范围(0/1)
    
    优化机制:
        - LRU淘汰: Q-table超过5000状态时淘汰最久未访问的
        - 优先级回放: TD误差大的经验优先学习
        - 协同奖励: 多角色(攻击者/侧翼/压制者)团队配合
    """

    def __init__(self):
        """初始化Q学习代理"""
        # 使用defaultdict自动初始化新状态为长度 NUM_ACTIONS 的零向量
        self.q_table = defaultdict(lambda: [0.0] * NUM_ACTIONS)
        self.q_table_access_order = deque()  # 记录访问顺序，用于LRU
        self.max_q_table_size = 5000  # 限制Q-table最大大小
        self._recorded_states = set()  # 辅助LRU去重

        self.exploration_rate = EXPLORATION_RATE
        self.learning_rate = LEARNING_RATE
        self.discount_factor = DISCOUNT_FACTOR
        self.replay_buffer = PrioritizedReplayBuffer(REPLAY_BUFFER_SIZE)
        self.load_q_table()

    def _record_access(self, state):
        """记录状态访问，用于LRU"""
        if state not in self._recorded_states:
            self.q_table_access_order.append(state)
            self._recorded_states.add(state)

            # 限制访问记录大小
            if len(self.q_table_access_order) > self.max_q_table_size * 2:
                # 清理一半
                half = len(self.q_table_access_order) // 2
                for i in range(half):
                    old_state = self.q_table_access_order.popleft()
                    self._recorded_states.discard(old_state)

    def _enforce_q_table_limit(self):
        """LRU淘汰机制：严格限制Q-table大小"""
        if len(self.q_table) <= self.max_q_table_size:
            return

        # 淘汰最久未访问的状态
        num_to_remove = len(self.q_table) - self.max_q_table_size
        removed = 0

        while removed < num_to_remove and self.q_table_access_order:
            oldest_state = self.q_table_access_order.popleft()
            if oldest_state in self.q_table:
                del self.q_table[oldest_state]
                if hasattr(self, '_recorded_states'):
                    self._recorded_states.discard(oldest_state)
                removed += 1

    def get_state(self, enemy, target, walls=None, all_enemies=None):
        """
        简化状态空间：从111,936种减少到约432种
        现在使用缓存优化性能
        """
        return performance_optimizer.get_cached_state(enemy, target, walls, all_enemies)

    def get_action(self, state):
        """ε-贪心策略选择动作"""
        if random.random() < self.exploration_rate:
            return random.randint(0, NUM_ACTIONS - 1)
        else:
            return self.get_best_action(state)

    def get_best_action(self, state):
        """获取当前状态下Q值最大的动作，随机打破平局"""
        values = self.q_table[state]
        self._record_access(state)

        max_val = values[0]
        for i in range(1, NUM_ACTIONS):
            if values[i] > max_val:
                max_val = values[i]

        # 随机打破平局：初期所有Q值为0时避免永远选action 0
        best = [i for i in range(NUM_ACTIONS) if values[i] == max_val]
        return random.choice(best)

    def update_q_value(self, state, action, reward, next_state):
        """
        Q-learning更新公式
        优化版：使用defaultdict自动初始化，无需显式检查
        """
        # defaultdict自动初始化新状态，无需显式检查
        old_value = self.q_table[state][action]
        next_values = self.q_table[next_state]

        # 使用优化后的max查找（手动展开比max()更快）
        next_max = next_values[0]
        for i in range(1, NUM_ACTIONS):
            if next_values[i] > next_max:
                next_max = next_values[i]

        new_value = old_value + self.learning_rate * (
            reward + self.discount_factor * next_max - old_value
        )
        self.q_table[state][action] = new_value

        self._record_access(state)
        self._record_access(next_state)
        self._enforce_q_table_limit()

    def add_experience(self, state, action, reward, next_state):
        """
        添加经验到优先级回放缓冲区
        优化版：使用defaultdict自动初始化
        """
        # defaultdict自动初始化新状态
        old_value = self.q_table[state][action]
        next_values = self.q_table[next_state]

        # 使用优化后的max查找
        next_max = next_values[0]
        for i in range(1, NUM_ACTIONS):
            if next_values[i] > next_max:
                next_max = next_values[i]

        td_error = abs(reward + self.discount_factor * next_max - old_value)

        # 使用TD误差作为优先级
        priority = td_error + 0.01  # 添加小常数避免优先级为0
        self.replay_buffer.add((state, action, reward, next_state), priority)

    def replay_experience(self):
        """
        从优先级回放缓冲区学习
        优化版：使用defaultdict自动初始化
        """
        if len(self.replay_buffer) < BATCH_SIZE:
            return

        # 采样批次
        batch, indices, weights = self.replay_buffer.sample(BATCH_SIZE)

        # 学习并更新优先级
        new_priorities = []
        for i, (state, action, reward, next_state) in enumerate(batch):
            # defaultdict自动初始化新状态
            old_value = self.q_table[state][action]
            next_values = self.q_table[next_state]

            # 使用优化后的max查找
            next_max = next_values[0]
            for j in range(1, NUM_ACTIONS):
                if next_values[j] > next_max:
                    next_max = next_values[j]

            # 使用重要性采样权重更新
            td_target = reward + self.discount_factor * next_max
            td_error = td_target - old_value
            new_value = old_value + self.learning_rate * weights[i] * td_error

            self.q_table[state][action] = new_value

            # 计算新的优先级
            new_priority = abs(td_error) + 0.01
            new_priorities.append(new_priority)

        # 更新优先级
        self.replay_buffer.update_priorities(indices, new_priorities)

        self._enforce_q_table_limit()

    def learn_from_death(self, enemy_history):
        """从死亡序列中学习，然后清空历史避免重复学习"""
        if not enemy_history:
            return

        for i in range(len(enemy_history) - 1):
            state, action, reward = enemy_history[i]
            next_state, _, _ = enemy_history[i + 1]
            self.add_experience(state, action, reward, next_state)

        last_state, last_action, _ = enemy_history[-1]
        # death_state: 距离近(0)、有障碍(1)、无盟友(0)、aligned保持原值
        # 维度与8D状态对齐: (rel_x, rel_y, 0, direction, 1, 0, self_facing, aligned)
        death_state = (last_state[0], last_state[1], 0, last_state[3], 1, 0, last_state[6], last_state[7])
        self.add_experience(last_state, last_action, -10, death_state)

        self.replay_experience()

    def load_q_table(self):
        """
        加载Q表
        优化版：将加载的dict转换为defaultdict
        兼容旧存档（4动作）：自动补零扩展到 NUM_ACTIONS
        """
        try:
            with open('q_table.pkl', 'rb') as f:
                loaded = pickle.load(f)
                # 转换为defaultdict，自动初始化新状态
                if isinstance(loaded, dict):
                    migrated = {}
                    for k, v in loaded.items():
                        if isinstance(v, list) and len(v) < NUM_ACTIONS:
                            v = list(v) + [0.0] * (NUM_ACTIONS - len(v))
                        migrated[k] = v
                    self.q_table = defaultdict(lambda: [0.0] * NUM_ACTIONS, migrated)
                else:
                    self.q_table = loaded
        except (IOError, OSError, pickle.UnpicklingError):
            # 保持已有的defaultdict
            pass

    def assign_roles(self, enemies, target):
        """
        动态角色分配：基于距离和战术位置（优化版 - 避免三角函数）
        每帧重新评估，允许角色动态切换
        """
        if not enemies:
            return {}

        roles = {}
        target_x, target_y = target.rect.centerx, target.rect.centery
        map_center_x = 10 * TILE_SIZE
        map_center_y = 7.5 * TILE_SIZE

        # 预计算距离平方
        map_center_dist_sq = (map_center_x - target_x)**2 + (map_center_y - target_y)**2

        # 计算每个敌人的战术分数
        enemy_scores = []
        for enemy in enemies:
            # 使用距离平方替代math.hypot
            dx = enemy.rect.centerx - target_x
            dy = enemy.rect.centery - target_y
            dist_sq_to_target = dx*dx + dy*dy

            dx_center = enemy.rect.centerx - map_center_x
            dy_center = enemy.rect.centery - map_center_y
            dist_sq_to_center = dx_center*dx_center + dy_center*dy_center

            # 攻击者分数：距离玩家近且视野清晰
            aggressor_score = -dist_sq_to_target

            # 侧翼者分数：与玩家呈45度角
            angle_diff = abs(abs(dx) - abs(dy))
            flanker_score = -angle_diff + 200

            # 压制者分数：控制关键位置
            suppressor_score = -dist_sq_to_center

            enemy_scores.append((enemy, aggressor_score, flanker_score, suppressor_score))

        # 为每个敌人分配最适合的角色
        used_roles = {'aggressor': False, 'flanker': False, 'suppressor': False}

        # 先分配明确的角色
        for enemy, agg_score, flk_score, sup_score in enemy_scores:
            scores = {'aggressor': agg_score, 'flanker': flk_score, 'suppressor': sup_score}
            best_role = max(scores, key=scores.get)

            if not used_roles[best_role]:
                roles[enemy] = best_role
                used_roles[best_role] = True

        # 剩余敌人分配未使用的角色
        remaining_roles = [role for role, used in used_roles.items() if not used]
        for enemy, _, _, _ in enemy_scores:
            if enemy not in roles:
                if remaining_roles:
                    roles[enemy] = remaining_roles.pop(0)
                else:
                    roles[enemy] = 'suppressor'

        return roles

    def get_cooperative_reward(self, enemy, action, target, all_enemies, roles, walls=None,
                              killed_player=False, took_damage=False, reward_weights=None):
        """协同奖励系统，奖励权重由遗传算法优化后注入"""
        return performance_optimizer.get_cached_reward(
            enemy, action, target, all_enemies, roles, walls,
            killed_player, took_damage, reward_weights=reward_weights
        )


# 旧版AI函数已删除：
# - choose_enemy_direction: 已被main.py中的内联逻辑替代
# - _get_random_valid_direction: 已被替代
# - _role_based_movement: 保留作为未来AI优化储备（见下方）


class GeneticOptimizer:
    """遗传算法优化奖励权重"""

    # 每个基因的合法范围，用于变异裁剪
    _GENE_RANGES = {
        'kill_reward':    (5.0,  50.0),
        'hit_reward':     (1.0,  20.0),
        'distance_scale': (0.1,   5.0),
        'team_bonus':     (0.0,   2.0),
        'survival_bonus': (0.0,   0.5),
    }

    def __init__(self):
        self.population = []
        self.generation = 0
        self.best_individual = None
        self.best_fitness = -float('inf')
        self.initialize_population()

    def initialize_population(self):
        """初始化种群，基因为奖励权重"""
        for _ in range(POPULATION_SIZE):
            self.population.append(self._random_individual())

    def _random_individual(self):
        """生成一个完全随机的个体（用于初始化和多样性注入）"""
        return {
            'kill_reward':    random.uniform(*self._GENE_RANGES['kill_reward']),
            'hit_reward':     random.uniform(*self._GENE_RANGES['hit_reward']),
            'distance_scale': random.uniform(*self._GENE_RANGES['distance_scale']),
            'team_bonus':     random.uniform(*self._GENE_RANGES['team_bonus']),
            'survival_bonus': random.uniform(*self._GENE_RANGES['survival_bonus']),
            'fitness': 0,
        }

    def evaluate_fitness(self, individual, game_stats):
        """
        连续适应度函数。

        主信号 damage_per_second（伤害密度）替代 damage_ratio：
            - damage_ratio 在短局（10-20s）下打 1-3 下也只有 0.05-0.15，几乎不区分好坏
            - dps 反映「单位时间打中能力」，是真实的策略质量指标

        权重（满分 ~100）：
            dps_norm × 60 + win × 25 + survival × 15
        """
        damage_inflicted = game_stats.get('damage_inflicted', 0)
        hybrid_wins      = game_stats.get('hybrid_wins', 0)
        survival_time    = game_stats.get('survival_time', 0)

        # 伤害密度：1.0 hits/sec 视为满分
        dps = damage_inflicted / max(survival_time, 1.0)
        dps_norm = min(dps, 1.0)

        # 存活时间：60s 视为满分（实测均值 ~14s，原来 120s 上界让此项几乎为 0）
        survival_ratio = min(survival_time / 60.0, 1.0)

        win_bonus = 1.0 if hybrid_wins else 0.0

        fitness = (
            dps_norm       * 60.0 +
            win_bonus      * 25.0 +
            survival_ratio * 15.0
        )

        individual['fitness'] = fitness
        return fitness

    def select_parent(self):
        """锦标赛选择"""
        tournament = random.sample(self.population, TOURNAMENT_SIZE)
        return max(tournament, key=lambda x: x['fitness'])

    def crossover(self, parent1, parent2):
        """单点交叉"""
        child = {}
        keys = [k for k in parent1.keys() if k != 'fitness']
        crossover_point = random.randint(1, len(keys) - 1)

        for i, key in enumerate(keys):
            if i < crossover_point:
                child[key] = parent1[key]
            else:
                child[key] = parent2[key]

        child['fitness'] = 0
        return child

    def mutate(self, individual):
        """高斯变异，按各基因范围裁剪"""
        for key, (lo, hi) in self._GENE_RANGES.items():
            if key in individual and random.random() < MUTATION_RATE:
                sigma = (hi - lo) * 0.2
                individual[key] = max(lo, min(hi, individual[key] + random.gauss(0, sigma)))
        return individual

    def evolve(self, avg_stats):
        """运行一代进化，所有个体用同一份平均统计评估，保证 fitness 可比"""
        for individual in self.population:
            self.evaluate_fitness(individual, avg_stats)

        # 排序
        self.population.sort(key=lambda x: x['fitness'], reverse=True)

        # 更新最优个体
        if self.population[0]['fitness'] > self.best_fitness:
            self.best_fitness = self.population[0]['fitness']
            self.best_individual = copy.deepcopy(self.population[0])

        # 精英保留
        new_population = []
        for i in range(ELITISM_COUNT):
            new_population.append(copy.deepcopy(self.population[i]))

        # 生成新种群
        while len(new_population) < POPULATION_SIZE:
            parent1 = self.select_parent()
            parent2 = self.select_parent()
            child = self.crossover(parent1, parent2)
            child = self.mutate(child)
            new_population.append(child)

        self.population = new_population

        # 多样性注入：种群崩溃时替换底部 30% 为随机个体
        # Why: 精英保留+小变异容易导致种群快速收敛，div=0 后 GA 等同停止优化
        if self.get_population_diversity() < 0.05:
            self.population.sort(key=lambda x: x['fitness'], reverse=True)
            inject_count = max(1, POPULATION_SIZE * 3 // 10)
            for i in range(POPULATION_SIZE - inject_count, POPULATION_SIZE):
                self.population[i] = self._random_individual()

        self.generation += 1

        return self.best_individual

    def get_best_parameters(self):
        return self.best_individual if self.best_individual else self.population[0]

    def get_population_diversity(self):
        """Return average normalized std across all genes as a diversity metric."""
        if len(self.population) < 2:
            return 0.0
        total_std = 0.0
        for key, (lo, hi) in self._GENE_RANGES.items():
            values = [ind[key] for ind in self.population]
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            gene_range = hi - lo
            if gene_range > 0:
                total_std += (variance ** 0.5) / gene_range
        return total_std / len(self._GENE_RANGES)


class HybridAgent:
    """
    混合智能代理：Q-learning + 遗传算法
    """

    def __init__(self, model_file='hybrid_model.pkl'):
        self.q_agent = QLearningAgent()
        self.genetic_optimizer = GeneticOptimizer()
        self.game_stats_buffer = []
        self.evolution_threshold = 10
        self.games_played = 0
        self.model_file = model_file
        # 奖励权重默认值，由遗传算法进化后更新
        self.reward_weights = {
            'kill_reward':    DEFAULT_KILL_REWARD,
            'hit_reward':     DEFAULT_HIT_REWARD,
            'distance_scale': DEFAULT_DISTANCE_SCALE,
            'team_bonus':     DEFAULT_TEAM_BONUS,
            'survival_bonus': DEFAULT_SURVIVAL_BONUS,
        }
        self.current_params = self.genetic_optimizer.get_best_parameters()

        # 应用初始参数
        self._apply_parameters(self.current_params)
        
        # ✅ 尝试加载已有的模型文件，实现断点续训
        self.load_checkpoint()

    def save_checkpoint(self):
        """保存当前模型状态（Q-table + 遗传算法参数）"""
        if not self.model_file:
            return
        try:
            # 将 defaultdict 转换为普通 dict 以便 pickle 序列化
            q_table_dict = dict(self.q_agent.q_table)
            data = {
                'q_table': q_table_dict,
                'best_individual': self.genetic_optimizer.best_individual,
                'best_fitness': self.genetic_optimizer.best_fitness,
                'generation': self.genetic_optimizer.generation,
                'games_played': self.games_played
            }
            with open(self.model_file, 'wb') as f:
                pickle.dump(data, f)
            logging.info(f"💾 模型已保存至 {self.model_file} (历史第 {self.games_played} 局)")
        except (IOError, OSError, pickle.PickleError) as e:
            logging.error(f"保存模型失败: {e}")

    def load_checkpoint(self):
        """从模型文件加载状态"""
        if not self.model_file or not os.path.exists(self.model_file):
            logging.info(f"📂 未找到模型文件 {self.model_file}，将从头开始训练")
            return

        try:
            with open(self.model_file, 'rb') as f:
                data = pickle.load(f)
            
            if 'q_table' in data:
                # 将普通 dict 转换回 defaultdict；兼容旧4动作存档
                raw = data['q_table']
                migrated = {}
                for k, v in raw.items():
                    if isinstance(v, list) and len(v) < NUM_ACTIONS:
                        v = list(v) + [0.0] * (NUM_ACTIONS - len(v))
                    migrated[k] = v
                self.q_agent.q_table = defaultdict(lambda: [0.0] * NUM_ACTIONS, migrated)
            if 'best_individual' in data:
                self.genetic_optimizer.best_individual = data['best_individual']
                self.genetic_optimizer.best_fitness = data.get('best_fitness', -float('inf'))
                self.genetic_optimizer.generation = data.get('generation', 0)
                self.current_params = self.genetic_optimizer.best_individual
                self._apply_parameters(self.current_params)
                
            self.games_played = data.get('games_played', 0)
            logging.info(f"✅ 模型加载成功！代数: {self.genetic_optimizer.generation}, 历史局数: {self.games_played}")
        except (IOError, OSError, pickle.UnpicklingError) as e:
            logging.error(f"加载模型失败: {e}")

    def _apply_parameters(self, params):
        """将遗传算法进化出的奖励权重存入实例，供奖励计算使用"""
        gene_keys = ('kill_reward', 'hit_reward', 'distance_scale', 'team_bonus', 'survival_bonus')
        for key in gene_keys:
            if key in params:
                self.reward_weights[key] = params[key]

    def _average_stats(self, stats_list):
        """将多局统计数据取平均，消除单局方差对 GA 评估的影响"""
        if not stats_list:
            return {}
        keys = stats_list[0].keys()
        return {k: sum(s.get(k, 0) for s in stats_list) / len(stats_list) for k in keys}

    def update_parameters(self):
        """从遗传优化器获取最新参数并应用"""
        params = self.genetic_optimizer.get_best_parameters()
        if params:
            self.current_params = params
            self._apply_parameters(params)

    def evolve_before_new_game(self, current_game_stats):
        """
        记录游戏统计并执行渐进式进化
        在新局开始前调用，包含探索率衰减和进化逻辑

        Args:
            current_game_stats: 当前局的统计数据
        """
        # 添加当前局统计到缓冲区
        self.game_stats_buffer.append(current_game_stats)
        self.games_played += 1  # ✅ 只在这里增加 games_played

        # 自适应探索率衰减：状态覆盖率低时保持较高探索
        # 3456 = 3×3×3×4×2×2×4×2 (8维状态空间上限)
        STATE_SPACE_SIZE = 3456
        coverage_ratio = len(self.q_agent.q_table) / STATE_SPACE_SIZE
        if coverage_ratio < 0.5:
            # 覆盖率不足50%时，衰减极慢（每局1%）
            decay = 0.99
        else:
            # 覆盖率充足后，正常衰减（每局2%）
            decay = 0.98
        self.q_agent.exploration_rate = max(
            MIN_EXPLORATION_RATE,
            self.q_agent.exploration_rate * decay
        )

        # 渐进式进化策略
        real_data_count = len(self.game_stats_buffer)

        if real_data_count <= 3:
            # 阶段1: 数据极少(1-3局)，只记录数据，不执行进化
            logging.info(f"📊 数据累积中: {real_data_count}/3局 (暂不进化)")
            return

        elif real_data_count < POPULATION_SIZE:
            # 阶段2: 数据不足(4-9局)，执行轻量级进化
            # 基于现有种群进行低强度变异，避免从零开始

            # 确保遗传优化器已初始化
            if not self.genetic_optimizer.population:
                self.genetic_optimizer.initialize_population()

            # 用 buffer 中所有已有数据的平均值评估，避免单局方差主导
            avg_stats = self._average_stats(self.game_stats_buffer)
            for individual in self.genetic_optimizer.population:
                self.genetic_optimizer.evaluate_fitness(individual, avg_stats)

            # 低强度进化: 只对最优个体进行小幅度变异
            self.genetic_optimizer.population.sort(
                key=lambda x: x['fitness'], reverse=True
            )

            # 保留精英(前50%)
            elite_count = POPULATION_SIZE // 2
            elite_individuals = self.genetic_optimizer.population[:elite_count]

            # 从精英生成新种群（低强度变异，幅度降至标准的25%）
            new_population = []
            for elite in elite_individuals:
                new_population.append(copy.deepcopy(elite))
                mutated = copy.deepcopy(elite)
                # 临时降低变异率到30%，通过随机门控实现
                for key, (lo, hi) in self.genetic_optimizer._GENE_RANGES.items():
                    if key in mutated and random.random() < MUTATION_RATE * 0.3:
                        sigma = (hi - lo) * 0.05  # 幅度也缩小到标准的50%
                        mutated[key] = max(lo, min(hi, mutated[key] + random.gauss(0, sigma)))
                new_population.append(mutated)

            # 填充剩余种群
            while len(new_population) < POPULATION_SIZE:
                parent1 = self.genetic_optimizer.select_parent()
                parent2 = self.genetic_optimizer.select_parent()
                child = self.genetic_optimizer.crossover(parent1, parent2)
                self.genetic_optimizer.mutate(child)
                new_population.append(child)

            self.genetic_optimizer.population = new_population

            # 多样性注入：与标准 evolve 一致
            if self.genetic_optimizer.get_population_diversity() < 0.05:
                self.genetic_optimizer.population.sort(key=lambda x: x['fitness'], reverse=True)
                inject_count = max(1, POPULATION_SIZE * 3 // 10)
                for i in range(POPULATION_SIZE - inject_count, POPULATION_SIZE):
                    self.genetic_optimizer.population[i] = self.genetic_optimizer._random_individual()

            # 更新最优个体
            self.genetic_optimizer.population.sort(
                key=lambda x: x['fitness'], reverse=True
            )
            if self.genetic_optimizer.population[0]['fitness'] > self.genetic_optimizer.best_fitness:
                self.genetic_optimizer.best_individual = copy.deepcopy(self.genetic_optimizer.population[0])
                self.genetic_optimizer.best_fitness = self.genetic_optimizer.population[0]['fitness']

            self.genetic_optimizer.generation += 1
            self.update_parameters()

            best = self.genetic_optimizer.best_individual
            logging.info(f"🌱 轻量进化 - 第{self.genetic_optimizer.generation}代 (历史第{self.games_played}局后, 真实数据{real_data_count}局)")
            logging.info(f"   最佳权重: kill={best.get('kill_reward', 0):.1f}, "
                        f"hit={best.get('hit_reward', 0):.1f}, "
                        f"dist_scale={best.get('distance_scale', 0):.2f}, "
                        f"team={best.get('team_bonus', 0):.2f}")
            logging.info(f"   最佳适应度: {self.genetic_optimizer.best_fitness:.2f}")

            # 保存模型
            self.save_checkpoint()

        else:
            # 阶段3: 数据充足(10局+)，执行标准遗传进化
            # 需要足够的数据来评估种群
            if len(self.game_stats_buffer) >= POPULATION_SIZE:
                stats_to_evaluate = self.game_stats_buffer[:POPULATION_SIZE]
                avg_stats = self._average_stats(stats_to_evaluate)
                self.genetic_optimizer.evolve(avg_stats)
                self.update_parameters()
                # 保留剩余统计
                self.game_stats_buffer = self.game_stats_buffer[POPULATION_SIZE:]

                # ✅ 进化完成后，自动保存模型到本地文件
                self.save_checkpoint()

                best = self.genetic_optimizer.best_individual
                logging.info(f"🧬 AI模型进化完成 - 第{self.genetic_optimizer.generation}代 (历史第{self.games_played}局后)")
                logging.info(f"   最佳权重: kill={best.get('kill_reward', 0):.1f}, "
                            f"hit={best.get('hit_reward', 0):.1f}, "
                            f"dist_scale={best.get('distance_scale', 0):.2f}, "
                            f"team={best.get('team_bonus', 0):.2f}, "
                            f"survival={best.get('survival_bonus', 0):.3f}")
                logging.info(f"   最佳适应度: {self.genetic_optimizer.best_fitness:.2f}")
                logging.info(f"   真实数据: {real_data_count}局")
            else:
                # 数据不足，累积更多
                logging.info(f"📊 数据积累中: {real_data_count}/{POPULATION_SIZE}局 (暂不进化)")

    def get_state(self, enemy, target, walls=None, all_enemies=None):
        return self.q_agent.get_state(enemy, target, walls, all_enemies)

    def get_action(self, state):
        return self.q_agent.get_action(state)

    def update_q_value(self, state, action, reward, next_state):
        self.q_agent.update_q_value(state, action, reward, next_state)

    def add_experience(self, state, action, reward, next_state):
        self.q_agent.add_experience(state, action, reward, next_state)

    def replay_experience(self):
        self.q_agent.replay_experience()

    def learn_from_death(self, enemy_history):
        self.q_agent.learn_from_death(enemy_history)

    def assign_roles(self, enemies, target):
        return self.q_agent.assign_roles(enemies, target)

    def get_cooperative_reward(self, enemy, action, target, all_enemies, roles, walls=None,
                              killed_player=False, took_damage=False):
        return self.q_agent.get_cooperative_reward(
            enemy, action, target, all_enemies, roles, walls,
            killed_player=killed_player, took_damage=took_damage,
            reward_weights=self.reward_weights
        )

    # save_q_table 已删除：已被save_checkpoint完全替代


class PerformanceMonitor:
    """实时性能监控和诊断系统 - 优化版，限制内存增长"""

    def __init__(self):
        self.metrics = {
            'fps': [],
            'memory_usage': [],
            'cpu_usage': [],
            'learning_efficiency': [],
            'decision_time': [],
            'q_table_size': [],
            'experience_buffer_size': [],
            'cache_hit_rate': [],
            'genetic_generation': [],
            'enemy_count': [],
            'bullet_count': [],
            'game_score': [],
            'ga_diversity': [],  # std of kill_reward across population
        }
        self.performance_log = []
        self.start_time = time.time()
        self.MAX_METRICS_SIZE = 1000  # 限制指标列表大小
        self.KEEP_SIZE = 500  # 清理时保留最近N个

    def _trim_metrics(self):
        """裁剪所有指标列表，防止无限增长"""
        for key in self.metrics:
            if len(self.metrics[key]) > self.MAX_METRICS_SIZE:
                self.metrics[key] = self.metrics[key][-self.KEEP_SIZE:]

    def log_frame_metrics(self, frame_data):
        """记录每帧性能指标 - 优化版，限制大小"""
        current_time = time.time()

        # 定期裁剪（每100帧）
        if len(self.metrics['fps']) % 100 == 0:
            self._trim_metrics()

        # 更新指标
        self.metrics['fps'].append(frame_data.get('fps', 60))
        self.metrics['memory_usage'].append(frame_data.get('memory_mb', 50))
        self.metrics['cpu_usage'].append(frame_data.get('cpu_percent', 10))
        self.metrics['decision_time'].append(frame_data.get('ai_decision_time', 5))
        self.metrics['q_table_size'].append(frame_data.get('q_table_states', 100))
        self.metrics['experience_buffer_size'].append(frame_data.get('experience_count', 1000))
        self.metrics['cache_hit_rate'].append(performance_optimizer.get_cache_stats()['hit_rate'])
        self.metrics['genetic_generation'].append(frame_data.get('genetic_gen', 0))
        self.metrics['enemy_count'].append(frame_data.get('enemy_count', 0))
        self.metrics['bullet_count'].append(frame_data.get('bullet_count', 0))
        self.metrics['game_score'].append(frame_data.get('score', 0))
        self.metrics['ga_diversity'].append(frame_data.get('ga_diversity', 0.0))

        # 定期分析趋势 (每1000帧/17秒，降低频率)
        if len(self.metrics['fps']) % 1000 == 0:
            self.analyze_performance_trends()

    def analyze_performance_trends(self):
        """分析性能趋势并提出优化建议"""
        suggestions = []

        # 分析FPS
        recent_fps = self.metrics['fps'][-100:]
        avg_fps = sum(recent_fps) / len(recent_fps) if recent_fps else 60

        if avg_fps < 50:
            suggestions.append("⚠️ FPS过低 (%.1f)，建议优化AI计算" % avg_fps)

        # 分析CPU使用率
        recent_cpu = self.metrics['cpu_usage'][-50:]
        avg_cpu = sum(recent_cpu) / len(recent_cpu) if recent_cpu else 10

        if avg_cpu > 80:
            suggestions.append("⚠️ CPU使用率过高 (%.1f%%)，考虑减少AI复杂度" % avg_cpu)

        # 分析内存使用
        recent_memory = self.metrics['memory_usage'][-50:]
        avg_memory = sum(recent_memory) / len(recent_memory) if recent_memory else 50

        if avg_memory > 200:  # MB
            suggestions.append("⚠️ 内存使用过高 (%.1fMB)，建议压缩Q-table" % avg_memory)

        # 分析决策时间
        recent_decision_time = self.metrics['decision_time'][-50:]
        avg_decision_time = sum(recent_decision_time) / len(recent_decision_time) if recent_decision_time else 5

        if avg_decision_time > 10:  # ms
            suggestions.append("⚠️ AI决策过慢 (%.1fms)，建议增加缓存" % avg_decision_time)

        # 分析缓存命中率
        recent_cache_hits = self.metrics['cache_hit_rate'][-50:]
        avg_cache_hit = sum(recent_cache_hits) / len(recent_cache_hits) if recent_cache_hits else 0

        if avg_cache_hit < 0.7:
            suggestions.append("⚠️ 缓存命中率低 (%.1f%%)，建议调整缓存策略" % (avg_cache_hit * 100))

        # 分析游戏对象数量
        recent_enemies = self.metrics['enemy_count'][-50:]
        avg_enemies = sum(recent_enemies) / len(recent_enemies) if recent_enemies else 0

        if avg_enemies > 8:
            suggestions.append("⚠️ 敌方坦克过多 (%d个)，可能影响性能" % int(avg_enemies))

        # 分析学习效率
        q_table_growth = len(self.metrics['q_table_size'])
        if q_table_growth > 1000:
            suggestions.append("✅ Q-table增长良好 (%d 状态)" % q_table_growth)

        # 分析得分趋势
        recent_scores = self.metrics['game_score'][-100:]
        if len(recent_scores) > 10:
            score_trend = recent_scores[-1] - recent_scores[0]
            if score_trend > 500:
                suggestions.append("✅ 游戏表现提升 (+%d 分)" % score_trend)

        # 输出建议
        if suggestions:
            print("\n" + "="*50)
            print("🔍 性能分析建议:")
            for suggestion in suggestions:
                print(f"  {suggestion}")
            print("="*50)

        return suggestions

    def get_performance_report(self):
        """生成详细性能报告"""
        report = {
            'avg_fps': sum(self.metrics['fps'][-100:]) / len(self.metrics['fps'][-100:]) if self.metrics['fps'] else 60,
            'avg_memory_mb': sum(self.metrics['memory_usage'][-50:]) / len(self.metrics['memory_usage'][-50:]) if self.metrics['memory_usage'] else 50,
            'avg_cpu_percent': sum(self.metrics['cpu_usage'][-50:]) / len(self.metrics['cpu_usage'][-50:]) if self.metrics['cpu_usage'] else 10,
            'avg_decision_time_ms': sum(self.metrics['decision_time'][-50:]) / len(self.metrics['decision_time'][-50:]) if self.metrics['decision_time'] else 5,
            'cache_hit_rate': sum(self.metrics['cache_hit_rate'][-50:]) / len(self.metrics['cache_hit_rate'][-50:]) if self.metrics['cache_hit_rate'] else 0,
            'q_table_states': self.metrics['q_table_size'][-1] if self.metrics['q_table_size'] else 0,
            'experience_buffer_size': self.metrics['experience_buffer_size'][-1] if self.metrics['experience_buffer_size'] else 0,
            'genetic_generations': self.metrics['genetic_generation'][-1] if self.metrics['genetic_generation'] else 0,
            'avg_enemy_count': sum(self.metrics['enemy_count'][-50:]) / len(self.metrics['enemy_count'][-50:]) if self.metrics['enemy_count'] else 0,
            'avg_bullet_count': sum(self.metrics['bullet_count'][-50:]) / len(self.metrics['bullet_count'][-50:]) if self.metrics['bullet_count'] else 0,
            'current_score': self.metrics['game_score'][-1] if self.metrics['game_score'] else 0,
            'ga_diversity': self.metrics['ga_diversity'][-1] if self.metrics['ga_diversity'] else 0.0,
        }

        return report


# 全局性能监控实例
performance_monitor = PerformanceMonitor()


def has_clear_line(source_rect, target_rect, walls):
    """检查两点之间是否有直线通路"""
    if source_rect.x != target_rect.x and source_rect.y != target_rect.y:
        return False
    if source_rect.x == target_rect.x:
        start = min(source_rect.centery, target_rect.centery)
        end = max(source_rect.centery, target_rect.centery)
        x = source_rect.centerx
        line = pygame.Rect(x - 2, start, 4, end - start)
    else:
        start = min(source_rect.centerx, target_rect.centerx)
        end = max(source_rect.centerx, target_rect.centerx)
        y = source_rect.centery
        line = pygame.Rect(start, y - 2, end - start, 4)
    for wall in walls:
        if line.colliderect(wall):
            return False
    return True


class AutoAI:
    """
    自动AI系统 - 简洁的目标锁定+自动寻路击杀算法
    
    功能:
    - 目标锁定: 优先选择最近的玩家，3秒内移动不足3单位则随机切换目标
    - A*路径finding: 曼哈顿距离启发式，限制200次迭代
    - 砖墙检测: 前方有砖墙时自动射击清除
    - 防卡住机制: 1秒内无法移动则随机选择方向
    
    移动策略:
    - 每帧重新规划路径，追踪移动目标
    - 砖墙视为"可行"方向（可射击清除）
    - 钢墙和其他坦克视为障碍，需要绕行
    
    射击策略:
    - 见人就打: 目标在射击直线上就发射
    - 放宽判定: 1.2格容差，无射程限制
    """

    def __init__(self, tank):
        """
        初始化自动AI
        
        Args:
            tank: 坦克实例
        """
        self.tank = tank
        self.current_target = None
        self.path_queue = []
        self.last_decision_time = 0
        self.decision_interval = 200
        self.shoot_cooldown = 0
        self.stuck_counter = 0
        self.last_position = (tank.rect.centerx, tank.rect.centery)
        self.last_move_time = 0

        # 移动历史追踪
        self.move_history = []
        # 每1秒检查，本体没有移动超过3个单位就认为卡住了，随机锁定下个目标
        self.min_move_distance = 3
        self.move_check_window = 1000

    def select_target(self, players, current_time=0):
        """
        选择并锁定目标 - 优先选择最近的玩家
        如果当前玩家已死亡，切换到新目标
        优化：如果3秒内移动距离少于3个单位，随机切换到其他目标
        """
        # 安全检查：确保自身坦克和目标列表有效
        if not self.tank or not self.tank.rect:
            self.current_target = None
            return None
            
        if not players:
            self.current_target = None
            return None

        # 过滤无效玩家（防止列表中包含None或已销毁对象）
        valid_players = [p for p in players if p and hasattr(p, 'rect') and p.rect]
        if not valid_players:
            self.current_target = None
            return None

        # 检查是否卡住（3秒内移动距离少于3个单位）
        if self._is_stuck(current_time) and len(valid_players) > 1:
            # 随机切换到其他目标
            return self._switch_to_random_target(valid_players)

        # 如果当前目标还活着且有效，继续跟踪
        if self.current_target and self.current_target in valid_players:
            return self.current_target

        # 选择最近的玩家作为新目标
        try:
            self.current_target = min(valid_players, key=lambda p: math.hypot(
                p.rect.centerx - self.tank.rect.centerx,
                p.rect.centery - self.tank.rect.centery
            ))
        except ValueError:
            self.current_target = None
            
        self.path_queue = []
        return self.current_target

    def _is_stuck(self, current_time):
        cutoff_time = current_time - self.move_check_window
        self.move_history = [(t, x, y) for t, x, y in self.move_history if t > cutoff_time]
        if len(self.move_history) < 2:
            return False
        total_distance = sum(math.hypot(self.move_history[i][1] - self.move_history[i-1][1],
                                        self.move_history[i][2] - self.move_history[i-1][2])
                             for i in range(1, len(self.move_history)))
        return total_distance < self.min_move_distance

    def _switch_to_random_target(self, players):
        if not players:
            return None
        other_targets = [p for p in players if p != self.current_target]
        if not other_targets:
            return self.current_target
        import random
        self.current_target = random.choice(other_targets)
        self.path_queue = []
        return self.current_target

    def plan_path(self, target, walls, all_tanks):
        if not target:
            return []
        start_grid = (self.tank.rect.centerx // TILE_SIZE, self.tank.rect.centery // TILE_SIZE)
        target_grid = (target.rect.centerx // TILE_SIZE, target.rect.centery // TILE_SIZE)
        distance = math.hypot(target.rect.centerx - self.tank.rect.centerx, target.rect.centery - self.tank.rect.centery)
        if distance < TILE_SIZE * 1.5:
            return self._direct_path_to_target(self.tank.rect.centerx, self.tank.rect.centery,
                                               target.rect.centerx, target.rect.centery, walls, all_tanks)
        path = self._astar_pathfinding(start_grid, target_grid, walls, all_tanks)
        self.path_queue = path
        return path

    def _astar_pathfinding(self, start, goal, walls, all_tanks):
        open_set = [start]
        came_from = {}
        g_score = {start: 0}
        h_score = self._heuristic(start, goal)
        f_score = {start: h_score}
        max_iterations = 200
        iterations = 0
        directions = [(0, -1, 0), (1, 0, 1), (0, 1, 2), (-1, 0, 3)]

        while open_set and iterations < max_iterations:
            iterations += 1
            current = min(open_set, key=lambda x: f_score.get(x, float('inf')))
            if current == goal:
                return self._reconstruct_path(came_from, current)
            open_set.remove(current)
            for dx, dy, direction in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                if not self._is_valid_grid_move(current[0], current[1], dx, dy, walls, all_tanks):
                    continue
                tentative_g_score = g_score[current] + 1
                if tentative_g_score < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = (current, direction)
                    g_score[neighbor] = tentative_g_score
                    h = self._heuristic(neighbor, goal)
                    f_score[neighbor] = tentative_g_score + h
                    if neighbor not in open_set:
                        open_set.append(neighbor)
        return self._get_direct_direction(start, goal)

    def _heuristic(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _reconstruct_path(self, came_from, current):
        path = []
        while current in came_from:
            prev, direction = came_from[current]
            path.append(direction)
            current = prev
        path.reverse()
        return path[:30]

    def _get_direct_direction(self, start, goal):
        dx = goal[0] - start[0]
        dy = goal[1] - start[1]
        if abs(dx) > abs(dy):
            return [1 if dx > 0 else 3]
        return [2 if dy > 0 else 0]

    def _is_valid_grid_move(self, grid_x, grid_y, dx, dy, walls, all_tanks):
        new_grid_x = grid_x + dx
        new_grid_y = grid_y + dy
        if not (0 <= new_grid_x < SCREEN_COLS and 0 <= new_grid_y < SCREEN_ROWS):
            return False
        new_rect = pygame.Rect(new_grid_x * TILE_SIZE, new_grid_y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        for wall in walls:
            if new_rect.colliderect(wall):
                return False
        self_grid_x = self.tank.rect.centerx // TILE_SIZE
        self_grid_y = self.tank.rect.centery // TILE_SIZE
        for tank in all_tanks:
            if tank.rect == self.tank.rect:
                continue
            tank_grid_x = tank.rect.centerx // TILE_SIZE
            tank_grid_y = tank.rect.centery // TILE_SIZE
            if abs(tank_grid_x - new_grid_x) <= 1 and abs(tank_grid_y - new_grid_y) <= 1:
                dist = math.hypot(tank.rect.centerx - new_grid_x * TILE_SIZE - TILE_SIZE // 2,
                                  tank.rect.centery - new_grid_y * TILE_SIZE - TILE_SIZE // 2)
                if dist < TILE_SIZE * 0.8:
                    return False
        return True

    def _direct_path_to_target(self, start_x, start_y, target_x, target_y, walls, all_tanks):
        directions = [(0, -1, 0), (1, 0, 1), (0, 1, 2), (-1, 0, 3)]
        best_direction = None
        best_distance = float('inf')
        for dx, dy, direction in directions:
            if self._is_valid_move(start_x, start_y, dx * self.tank.speed, dy * self.tank.speed, walls, all_tanks):
                new_x = start_x + dx * self.tank.speed
                new_y = start_y + dy * self.tank.speed
                distance = math.hypot(target_x - new_x, target_y - new_y)
                if distance < best_distance:
                    best_distance = distance
                    best_direction = direction
        return [best_direction] if best_direction is not None else []

    def _is_valid_move(self, current_x, current_y, dx, dy, walls, all_tanks):
        new_rect = pygame.Rect(int(current_x + dx - TILE_SIZE // 2), int(current_y + dy - TILE_SIZE // 2), TILE_SIZE, TILE_SIZE)
        if not PLAYFIELD_RECT.contains(new_rect):
            return False
        for wall in walls:
            if new_rect.colliderect(wall):
                return False
        for tank in all_tanks:
            if tank.rect != self.tank.rect and new_rect.colliderect(tank.rect):
                return False
        return True

    def get_next_move(self, players, walls, all_tanks, current_time, brick_tiles=None):
        target = self.select_target(players, current_time)
        if not target:
            return self.tank.direction, False

        current_pos = (self.tank.rect.centerx, self.tank.rect.centery)
        dist_moved = math.hypot(current_pos[0] - self.last_position[0], current_pos[1] - self.last_position[1])
        self.move_history.append((current_time, current_pos[0], current_pos[1]))

        if dist_moved < 1:
            self.stuck_counter += 1
        else:
            self.stuck_counter = 0
            self.last_position = current_pos

        should_shoot_brick = False
        if brick_tiles:
            should_shoot_brick = self._check_brick_ahead(walls, brick_tiles, current_time)

        if self.stuck_counter > 60:  # 60 帧 ≈ 1 秒
            self.stuck_counter = 0
            self.path_queue = []
            
            # 朝随机其他方向移动 3 个单位
            directions = [0, 1, 2, 3]
            random.shuffle(directions)
            for direction in directions:
                if self._can_move_in_direction(direction, walls, all_tanks):
                    # 将路径队列设置为连续 3 个相同的方向
                    self.path_queue = [direction, direction, direction]
                    return direction, False

        self.plan_path(target, walls, all_tanks)
        self.last_decision_time = current_time

        if self.path_queue:
            next_direction = self.path_queue.pop(0)
            if self._can_move_in_direction(next_direction, walls, all_tanks, brick_tiles):
                return next_direction, should_shoot_brick
            return self._find_alternative_direction(walls, all_tanks), False
        return self._get_direction_towards_target(target), should_shoot_brick

    def _check_brick_ahead(self, walls, brick_tiles, current_time):
        if not self.tank.can_shoot(current_time):
            return False
        directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        dx, dy = directions[self.tank.direction]
        check_x = self.tank.rect.centerx + dx * (TILE_SIZE + self.tank.speed)
        check_y = self.tank.rect.centery + dy * (TILE_SIZE + self.tank.speed)
        check_rect = pygame.Rect(int(check_x - TILE_SIZE // 2), int(check_y - TILE_SIZE // 2), TILE_SIZE, TILE_SIZE)
        for brick in brick_tiles:
            if brick.colliderect(check_rect):
                return True
        return False

    def shoot_brick(self, current_time):
        if self.tank.can_shoot(current_time):
            return self.tank.shoot(current_time)
        return None

    def _can_move_in_direction(self, direction, walls, all_tanks, brick_tiles=None):
        directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        if 0 <= direction < 4:
            dx, dy = directions[direction]
            if brick_tiles:
                check_x = self.tank.rect.centerx + dx * (TILE_SIZE * 0.8 + self.tank.speed)
                check_y = self.tank.rect.centery + dy * (TILE_SIZE * 0.8 + self.tank.speed)
                check_rect = pygame.Rect(int(check_x - TILE_SIZE // 2), int(check_y - TILE_SIZE // 2), TILE_SIZE, TILE_SIZE)
                for brick in brick_tiles:
                    if brick.colliderect(check_rect):
                        return True
            return self._is_valid_move(self.tank.rect.centerx, self.tank.rect.centery,
                                       dx * self.tank.speed, dy * self.tank.speed, walls, all_tanks)
        return False

    def _find_alternative_direction(self, walls, all_tanks):
        if self._can_move_in_direction(self.tank.direction, walls, all_tanks):
            return self.tank.direction
        directions = [0, 1, 2, 3]
        random.shuffle(directions)
        for direction in directions:
            if direction != self.tank.direction and self._can_move_in_direction(direction, walls, all_tanks):
                return direction
        return self.tank.direction

    def _get_direction_towards_target(self, target):
        dx = target.rect.centerx - self.tank.rect.centerx
        dy = target.rect.centery - self.tank.rect.centery
        if abs(dx) > abs(dy):
            return 1 if dx > 0 else 3
        return 2 if dy > 0 else 0

    def should_fire(self, target, walls, current_time):
        if not target or not self.tank.can_shoot(current_time):
            return False
        dx = target.rect.centerx - self.tank.rect.centerx
        dy = target.rect.centery - self.tank.rect.centery
        tank_dir = self.tank.direction
        if tank_dir == 0:
            in_line = dy < -TILE_SIZE * 0.3 and abs(dx) < TILE_SIZE * 1.2
        elif tank_dir == 1:
            in_line = dx > TILE_SIZE * 0.3 and abs(dy) < TILE_SIZE * 1.2
        elif tank_dir == 2:
            in_line = dy > TILE_SIZE * 0.3 and abs(dx) < TILE_SIZE * 1.2
        else:
            in_line = dx < -TILE_SIZE * 0.3 and abs(dy) < TILE_SIZE * 1.2
        return in_line
