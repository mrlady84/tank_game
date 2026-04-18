"""
坦克大战游戏主模块
=================

功能:
- Pygame游戏循环和渲染
- 坦克物理和碰撞检测
- AI决策线程管理
- 游戏状态控制（玩家/老鹰/游戏结束）

架构:
- 固定时间步长物理更新(60 FPS)
- 异步AI决策(ThreadSafeAIDecider)
- 分离逻辑(update_physics)和渲染(render_game)

游戏规则:
- 玩家AI控制2辆坦克（黄色/蓝色），速度2.0
- 敌方AI控制最多5辆坦克，速度1.0，使用HybridAgent（Q-learning + 遗传算法）
- 基地为老鹰+3面砖墙保护，老鹰被击中立即重开
- 砖墙可被子弹摧毁，钢墙不可摧毁

作者: Tank Battle AI Team
版本: 2.0
"""

import os
import pygame
import random
import math
import time
import sys
import logging
import threading
import gc
from queue import Queue, Empty

# 优化GC：降低频次，减少卡顿
gc.disable()  # 禁用自动GC
gc.set_threshold(0, 0, 0)  # 设置为0，完全禁用自动GC

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Configure logging MUST be done before any imports that use logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('game.log', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True  # Python 3.8+: 强制重新配置，覆盖之前的配置
)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ModuleNotFoundError:
    psutil = None
    PSUTIL_AVAILABLE = False

from tank_ai import q_agent, choose_enemy_direction, can_move_rect, performance_monitor, HybridAgent, AutoAI, has_clear_line
from config.game_config import *

if not PSUTIL_AVAILABLE:
    logging.warning('psutil is not installed; performance monitoring will use fallback defaults.')

# Initialize Pygame with error handling
try:
    pygame.init()
    logging.info("Pygame initialized successfully")
except pygame.error as e:
    logging.error(f"Failed to initialize Pygame: {e}")
    sys.exit(1)

# Screen dimensions
TILE_SIZE = 32
SCREEN_COLS = 20
SCREEN_ROWS = 15
PLAYFIELD_WIDTH = TILE_SIZE * SCREEN_COLS
SCREEN_WIDTH = PLAYFIELD_WIDTH + 96  # Add 96px for sidebar
SCREEN_HEIGHT = TILE_SIZE * SCREEN_ROWS

try:
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    PLAYFIELD_RECT = pygame.Rect(0, 0, PLAYFIELD_WIDTH, SCREEN_HEIGHT)
    # Update config with initialized rect
    import config.game_config
    config.game_config.PLAYFIELD_RECT = PLAYFIELD_RECT
    
    # Update tank_ai module with initialized rect
    import tank_ai
    tank_ai.PLAYFIELD_RECT = PLAYFIELD_RECT
    
    pygame.display.set_caption("Tank Battle")
    logging.info("Game window created successfully")
except pygame.error as e:
    logging.error(f"Failed to create game window: {e}")
    sys.exit(1)

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

ASSET_DIR = os.path.join(os.path.dirname(__file__), 'assets')

# Load assets with error handling
try:
    TILE_IMAGES = {
        1: pygame.image.load(os.path.join(ASSET_DIR, 'brick.png')).convert(),
        2: pygame.image.load(os.path.join(ASSET_DIR, 'steel.png')).convert(),
        3: pygame.image.load(os.path.join(ASSET_DIR, 'grass.png')).convert(),
        4: pygame.image.load(os.path.join(ASSET_DIR, 'base.png')).convert(),
    }
    logging.info("Tile images loaded successfully")
    
    # 加载老鹰图像（用于基地内部）
    try:
        EAGLE_IMAGE = pygame.image.load(os.path.join(ASSET_DIR, 'eagle.png')).convert_alpha()
        logging.info("Eagle image loaded successfully")
    except pygame.error:
        EAGLE_IMAGE = None
        logging.warning("Eagle image not found, using base.png as fallback")

    PLAYER_TANK_IMAGE = pygame.image.load(os.path.join(ASSET_DIR, 'player_tank.png')).convert_alpha()
    ENEMY_TANK_IMAGE = pygame.image.load(os.path.join(ASSET_DIR, 'enemy_tank.png')).convert_alpha()
    BULLET_IMAGE = pygame.image.load(os.path.join(ASSET_DIR, 'bullet.png')).convert_alpha()
    logging.info("Tank and bullet images loaded successfully")

    # 创建黄色和蓝色的玩家坦克图像
    def tint_image(surface, target_color):
        """给图像着色 - 直接修改像素颜色"""
        tinted = surface.copy()
        width, height = tinted.get_size()
        
        for x in range(width):
            for y in range(height):
                pixel = tinted.get_at((x, y))
                # 只修改非透明且有颜色的像素
                if pixel.a > 50:  # 忽略透明或接近透明的像素
                    # 保持原始亮度，调整色相
                    brightness = max(pixel.r, pixel.g, pixel.b)
                    if brightness > 50:  # 只修改有颜色的部分
                        # 计算比例
                        scale = brightness / 255.0
                        new_r = int(target_color[0] * scale)
                        new_g = int(target_color[1] * scale)
                        new_b = int(target_color[2] * scale)
                        tinted.set_at((x, y), (new_r, new_g, new_b, pixel.a))
        
        return tinted

    # 黄色坦克
    PLAYER_TANK_YELLOW = tint_image(PLAYER_TANK_IMAGE, (255, 255, 0))
    # 蓝色坦克
    PLAYER_TANK_BLUE = tint_image(PLAYER_TANK_IMAGE, (50, 100, 255))

    logging.info("Created yellow and blue player tank images")

except pygame.error as e:
    logging.error(f"Failed to load game assets: {e}")
    logging.error(f"Please ensure all image files exist in {ASSET_DIR}")
    sys.exit(1)
except FileNotFoundError as e:
    logging.error(f"Asset file not found: {e}")
    logging.error(f"Please check that the assets directory exists and contains all required files")
    sys.exit(1)

PLAYER_SHOT_DELAY = 200  # 提高射击频率
ENEMY_SHOT_DELAY = 1200
START_LIVES = 10  # 玩家坦克可以抗住10次射击
EXPLOSION_DURATION = 8
MAX_ENEMIES = 5  # 敌方坦克数量
CANDIDATE_TANKS = 5  # 总候选坦克
PLAYER_TANK_COUNT = 2  # 玩家AI坦克数量

FONT = pygame.font.Font(None, 22)
LARGE_FONT = pygame.font.Font(None, 36)


class Tank:
    """
    坦克类 - 游戏中所有坦克的基础实现
    
    属性:
        x, y: 坦克位置（浮点数，支持平滑移动）
        image: 坦克图像
        team: 队伍标识 ('player' 或 'enemy')
        rect: Pygame矩形，用于碰撞检测
        direction: 当前朝向 (0=上, 1=右, 2=下, 3=左)
        speed: 移动速度（玩家=2.0, 敌方=1.0）
        hit_points: 生命值（玩家=10, 敌方=1）
        last_shot_time: 上次射击时间（用于冷却计算）
        shot_delay: 射击冷却时间（玩家=200ms, 敌方=1200ms）
    """
    
    def __init__(self, x, y, image, team='player'):
        """
        初始化坦克
        
        Args:
            x: 初始X坐标
            y: 初始Y坐标
            image: 坦克图像
            team: 队伍标识，默认为'player'
        """
        self.x = float(x)
        self.y = float(y)
        self.image = image
        self.team = team
        self.rect = pygame.Rect(int(x), int(y), TILE_SIZE, TILE_SIZE)
        self.direction = 0
        self.speed = 2
        self.last_shot_time = 0
        self.shot_delay = PLAYER_SHOT_DELAY if team == 'player' else ENEMY_SHOT_DELAY
        # Movement state tracking for enemy AI
        self.move_counter = 0
        self.max_consecutive_moves = 8  # Move in same direction for 8 steps before randomizing
        # Q-learning history for AI tanks
        self.learning_history = []
        self.last_state = None
        self.last_action = None  # 显式初始化，避免None错误
        # Hit points for player tanks
        self.hit_points = START_LIVES if team == 'player' else 1

    def update_rect(self):
        self.rect.topleft = (int(self.x), int(self.y))

    def draw(self):
        angle = {0: 0, 1: -90, 2: 180, 3: 90}[self.direction]
        rotated = pygame.transform.rotate(self.image, angle)
        rotated_rect = rotated.get_rect(center=self.rect.center)
        screen.blit(rotated, rotated_rect.topleft)

    def move(self, dx, dy, walls, other_tanks=None):
        steps = max(abs(dx), abs(dy))
        if steps == 0:
            return
        # 修复：将steps转换为整数，支持浮点数速度
        steps = int(steps)
        step_x = dx / steps if steps > 0 else 0
        step_y = dy / steps if steps > 0 else 0
        for _ in range(steps):
            new_x = self.x + step_x
            new_y = self.y + step_y
            new_rect = pygame.Rect(int(new_x), int(new_y), TILE_SIZE, TILE_SIZE)
            if not PLAYFIELD_RECT.contains(new_rect):
                return
            # 精确碰撞检测：检查新位置是否与任何墙壁重叠
            collision = False
            for wall in walls:
                if new_rect.colliderect(wall):
                    collision = True
                    break
            if collision:
                # 遇到墙壁时，尝试随机改变方向
                if self.team == 'enemy' and random.random() < 0.3:
                    self.direction = random.choice([0, 1, 2, 3])
                return
            # 检查与其他坦克的碰撞
            if other_tanks:
                for tank in other_tanks:
                    if tank != self and new_rect.colliderect(tank.rect):
                        collision = True
                        break
            if collision:
                # 遇到坦克时，尝试随机改变方向
                if self.team == 'enemy' and random.random() < 0.3:
                    self.direction = random.choice([0, 1, 2, 3])
                return
            self.x = new_x
            self.y = new_y
            self.update_rect()
        # Update movement counter for enemy AI
        if self.team == 'enemy':
            self.move_counter += 1

    def can_shoot(self, current_time):
        return current_time - self.last_shot_time >= self.shot_delay

    def shoot(self, current_time):
        self.last_shot_time = current_time
        if self.direction == 0:
            x = self.x + TILE_SIZE // 2 - 3
            y = self.y - 6
        elif self.direction == 1:
            x = self.x + TILE_SIZE
            y = self.y + TILE_SIZE // 2 - 3
        elif self.direction == 2:
            x = self.x + TILE_SIZE // 2 - 3
            y = self.y + TILE_SIZE
        else:
            x = self.x - 6
            y = self.y + TILE_SIZE // 2 - 3
        return Bullet(x, y, self.direction, self.team)

    def try_fire(self, target, current_time, walls):
        if not self.can_shoot(current_time):
            return None

        # Set direction based on target position
        if self.rect.x == target.rect.x:
            self.direction = 0 if self.rect.y > target.rect.y else 2
        elif self.rect.y == target.rect.y:
            self.direction = 3 if self.rect.x > target.rect.x else 1
        else:
            # Random direction change with small probability
            if random.random() < 0.08:
                self.direction = random.choice([0, 1, 2, 3])
                return self.shoot(current_time)

        # Check if we have a clear line of sight
        if has_clear_line(self.rect, target.rect, walls):
            return self.shoot(current_time)

        return None

class Bullet:
    def __init__(self, x, y, direction, owner):
        self.direction = direction
        self.speed = 8
        self.owner = owner
        self.rect = pygame.Rect(x, y, 6, 6)
        self.prev_rect = self.rect.copy()

    def move(self):
        self.prev_rect = self.rect.copy()
        if self.direction == 0:
            self.rect.y -= self.speed
        elif self.direction == 1:
            self.rect.x += self.speed
        elif self.direction == 2:
            self.rect.y += self.speed
        else:
            self.rect.x -= self.speed

    def get_path_rect(self):
        return self.rect.union(self.prev_rect)

    def draw(self):
        screen.blit(BULLET_IMAGE, self.rect.topleft)


class Explosion:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.frame = 0

    def update(self):
        self.frame += 1
        return self.frame < EXPLOSION_DURATION

    def draw(self):
        radius = 4 + (self.frame * 2)
        alpha = max(0, min(255, 255 - int((self.frame / EXPLOSION_DURATION) * 200)))
        explosion = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(explosion, (255, 220, 120, alpha), (radius, radius), radius)
        pygame.draw.circle(explosion, (255, 120, 40, alpha), (radius, radius), max(1, radius - 2))
        screen.blit(explosion, (self.x - radius, self.y - radius))


def get_tiles_rects():
    brick_tiles = []
    steel_tiles = []
    grass_tiles = []
    base_tiles = []
    for row_index, row in enumerate(LEVEL_MAP):
        for col_index, tile in enumerate(row):
            rect = pygame.Rect(col_index * TILE_SIZE, row_index * TILE_SIZE, TILE_SIZE, TILE_SIZE)
            if tile == BRICK_TILE:
                brick_tiles.append(rect)
            elif tile == STEEL_TILE:
                steel_tiles.append(rect)
            elif tile == GRASS_TILE:
                grass_tiles.append(rect)
            elif tile == BASE_TILE:
                base_tiles.append(rect)
    return brick_tiles, steel_tiles, grass_tiles, base_tiles


def draw_map():
    for row_index, row in enumerate(LEVEL_MAP):
        for col_index, tile in enumerate(row):
            x = col_index * TILE_SIZE
            y = row_index * TILE_SIZE
            if tile in TILE_IMAGES:
                screen.blit(TILE_IMAGES[tile], (x, y))


def can_move_rect(rect, dx, dy, walls):
    new_rect = rect.move(dx, dy)
    if not PLAYFIELD_RECT.contains(new_rect):
        return False
    path_rect = rect.union(new_rect)
    for wall in walls:
        if wall.colliderect(path_rect):
            return False
    return True


def handle_enemy_collision(bullet, bullet_rect, enemies, explosions, bullets, score, candidate_tanks, players=None, q_agent_instance=None, enemy_ais=None, global_hybrid_agents=None):
    """Handle bullet collision with enemies"""
    if players is None:
        players = []

    for enemy in enemies[:]:
        if enemy.rect.colliderect(bullet_rect):
            explosions.append(Explosion(enemy.rect.centerx, enemy.rect.centery))
            if bullet in bullets:
                bullets.remove(bullet)

            # 从敌人死亡前学习
            if enemy.learning_history is not None and q_agent_instance:
                q_agent_instance.learn_from_death(enemy.learning_history)

            enemies.remove(enemy)

            # 清理 enemy_ais 中对应的 AI 控制器（但不删除全局实例）
            if enemy_ais and enemy in enemy_ais:
                del enemy_ais[enemy]

            score += SCORE_ENEMY

            # 生成新敌人
            if candidate_tanks > 0 and len(enemies) < MAX_ENEMIES:
                available_positions = get_enemy_spawn_positions(LEVEL_MAP, 1, players + enemies)
                if available_positions:
                    x, y = available_positions[0]
                    new_enemy = Tank(x, y, ENEMY_TANK_IMAGE, 'enemy')
                    enemies.append(new_enemy)
                    # ✅ 从全局 AI 实例池中分配（不再创建新的 HybridAgent）
                    if enemy_ais is not None and global_hybrid_agents:
                        # 使用敌人数量作为索引，轮流分配全局 AI 实例
                        agent_index = len(enemies) % len(global_hybrid_agents)
                        enemy_ais[new_enemy] = global_hybrid_agents[agent_index]
                    candidate_tanks -= 1

            return True, score, candidate_tanks
    return False, score, candidate_tanks


def handle_brick_collision(bullet, bullet_rect, brick_tiles, wall_rects, explosions, bullets, score):
    """Handle bullet collision with bricks"""
    for brick in brick_tiles[:]:
        if brick.colliderect(bullet_rect):
            # 修复：使用bullet_rect而不是bullet.rect
            explosions.append(Explosion(bullet_rect.centerx, bullet_rect.centery))
            if bullet in bullets:
                bullets.remove(bullet)
            brick_tiles.remove(brick)
            if brick in wall_rects:
                wall_rects.remove(brick)
            score += SCORE_BRICK
            return True, wall_rects, score
    return False, wall_rects, score


def get_enemy_spawn_positions(map_data, max_count, existing_tanks=None):
    """Get random spawn positions for enemies from the top rows of the map, avoiding existing tanks and walls"""
    if existing_tanks is None:
        existing_tanks = []

    positions = []
    for row_index in range(0, 3):
        for col_index, tile in enumerate(map_data[row_index]):
            # 只生成在空白位置，避开所有墙壁
            if tile != EMPTY:
                continue
                
            candidate_pos = (col_index * TILE_SIZE, row_index * TILE_SIZE)
            # Check if this position conflicts with existing tanks
            conflict = False
            for tank in existing_tanks:
                distance = math.hypot(tank.x - candidate_pos[0], tank.y - candidate_pos[1])
                if distance < TILE_SIZE * 1.5:  # Keep at least 1.5 tile distance
                    conflict = True
                    break
            if not conflict:
                positions.append(candidate_pos)

    random.shuffle(positions)
    return positions[:max_count]


def draw_hud(score, total_hp, candidate_tanks, player_count):
    labels = [
        f'SCORE: {score:04d}',
        f'PLAYER HP: {total_hp}',
        f'PLAYERS: {player_count}',
        f'ENEMIES: {candidate_tanks}',
        'AI CONTROLLED'
    ]
    for idx, text in enumerate(labels):
        rendered = FONT.render(text, True, WHITE)
        screen.blit(rendered, (8, SCREEN_HEIGHT - 24 * (len(labels) - idx)))


def draw_sidebar(candidate_tanks):
    sidebar_x = TILE_SIZE * SCREEN_COLS  # 640
    for i in range(candidate_tanks):
        row = i // 10
        col = i % 10
        x = sidebar_x + 8 + col * 8
        y = 10 + row * 16
        pygame.draw.rect(screen, (190, 60, 60), (x, y, 6, 6))


def reset_game(global_hybrid_agents=None):
    """
    重置游戏状态（保留全局 AI 实例）
    
    Args:
        global_hybrid_agents: 全局 HybridAgent 列表，如果为 None 则创建新的
    """
    # 创建2个玩家AI坦克，分布在基地两边
    players = []
    # 黄色坦克在基地左边
    player_yellow = Tank(7 * TILE_SIZE, 13 * TILE_SIZE, PLAYER_TANK_YELLOW, 'player')
    player_yellow.speed = 2.0  # 玩家坦克速度是敌方的2倍
    players.append(player_yellow)
    # 蓝色坦克在基地右边
    player_blue = Tank(12 * TILE_SIZE, 13 * TILE_SIZE, PLAYER_TANK_BLUE, 'player')
    player_blue.speed = 2.0  # 玩家坦克速度是敌方的2倍
    players.append(player_blue)

    spawn_positions = get_enemy_spawn_positions(LEVEL_MAP, MAX_ENEMIES, players)
    enemies = [Tank(x, y, ENEMY_TANK_IMAGE, 'enemy') for x, y in spawn_positions]

    # 敌方坦克速度：玩家的一半
    for enemy in enemies:
        enemy.speed = 1.0  # 敌方速度为玩家的一半
    bullets = []
    explosions = []
    score = 0
    candidate_tanks = CANDIDATE_TANKS
    brick_tiles, steel_tiles, grass_tiles, base_tiles = get_tiles_rects()
    wall_rects = brick_tiles + steel_tiles + base_tiles
    enemy_timer = 0

    # 为玩家坦克创建AutoAI控制器（保持简洁）
    player_ais = {player: AutoAI(player) for player in players}
    
    # ✅ 只创建一个全局的 HybridAgent 实例（所有敌方坦克共享）
    # 这样可以避免多个实例数据冲突和重复计数问题
    if global_hybrid_agents is None:
        # 首次创建时加载 checkpoint
        global_hybrid_agents = [HybridAgent()]
    else:
        # 重置游戏时，不清空缓冲区
        # 让数据跨局累积，由 evolve_before_new_game() 在进化时自动清空
        pass  # 保持缓冲区，确保 games_played 准确累计
    
    # 为所有敌方坦克分配同一个全局 AI 实例
    enemy_ais = {}
    for enemy in enemies:
        enemy_ais[enemy] = global_hybrid_agents[0]

    # 初始化敌方坦克的学习状态
    for enemy in enemies:
        enemy.last_state = None
        enemy.last_action = None

    # 清理性能优化器的缓存
    from tank_ai import performance_optimizer
    performance_optimizer.state_cache.clear()
    performance_optimizer.reward_cache.clear()
    performance_optimizer.frame_count = 0
    performance_optimizer.cache_hits = 0
    performance_optimizer.cache_misses = 0

    return players, enemies, bullets, explosions, score, candidate_tanks, brick_tiles, steel_tiles, grass_tiles, base_tiles, wall_rects, enemy_timer, player_ais, enemy_ais, global_hybrid_agents


class ThreadSafeAIDecider:
    """线程安全的 AI 决策器"""
    def __init__(self):
        self.decision_queue = Queue()  # 待处理决策请求
        self.result_queue = Queue()    # 决策结果
        self.worker_thread = None
        self.running = False
        self.last_decisions = {}  # tank_id -> (direction, target_rect)
        self.decision_count = 0  # 用于定期清理

    def start(self):
        """启动 AI 决策线程"""
        self.running = True
        self.worker_thread = threading.Thread(target=self._ai_worker, daemon=True)
        self.worker_thread.start()

    def stop(self):
        """停止 AI 决策线程"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        
    def reset(self):
        """重置状态（游戏重启时调用）"""
        # 清空队列
        while not self.decision_queue.empty():
            try:
                self.decision_queue.get_nowait()
            except Empty:
                break
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except Empty:
                break
        # 清空缓存
        self.last_decisions.clear()
        self.decision_count = 0

    def submit_decision(self, tank_id, tank, target, walls, all_tanks, roles, q_agent_instance):
        """提交 AI 决策请求（非阻塞）"""
        # 更严格的队列限制
        if self.decision_queue.qsize() < 2:
            self.decision_count += 1
            # 更频繁地清理过期结果
            if self.decision_count % 30 == 0:
                self._cleanup_old_results()
            
            # 只传递必要的数据，避免内存泄漏
            self.decision_queue.put({
                'tank_id': tank_id,
                'tank_rect': tank.rect.copy(),
                'tank_direction': tank.direction,
                'tank_speed': tank.speed,
                'tank_move_counter': tank.move_counter,
                'tank_max_moves': tank.max_consecutive_moves,
                'target_rect': target.rect.copy() if target else None,
                'walls': [w.copy() for w in walls[:15]],  # 进一步减少墙壁数量
                'all_tanks_rects': [t.rect.copy() for t in all_tanks[:6]],  # 只传递前6个坦克的rect
            })

    def _cleanup_old_results(self):
        """清理过期的决策结果"""
        current_time = time.time()
        # 更激进的清理：只保留1秒内的结果
        expired = [tid for tid, data in self.last_decisions.items() 
                  if current_time - data.get('timestamp', 0) > 1.0]
        for tid in expired:
            del self.last_decisions[tid]
        
        # 限制字典大小
        if len(self.last_decisions) > 20:
            # 保留最近的20个
            sorted_items = sorted(self.last_decisions.items(), 
                                key=lambda x: x[1].get('timestamp', 0), 
                                reverse=True)
            self.last_decisions = dict(sorted_items[:20])

    def get_result(self, tank_id):
        """获取决策结果（非阻塞）"""
        try:
            while not self.result_queue.empty():
                result = self.result_queue.get_nowait()
                self.last_decisions[result['tank_id']] = result
        except Empty:
            pass
        return self.last_decisions.get(tank_id, None)

    def _ai_worker(self):
        """AI 决策工作线程"""
        while self.running:
            try:
                # 从队列获取决策请求（带超时）
                request = self.decision_queue.get(timeout=0.1)
                
                # 在后台线程中执行 AI 计算
                direction = self._compute_direction(request)
                
                # 将结果放回结果队列
                self.result_queue.put({
                    'tank_id': request['tank_id'],
                    'direction': direction,
                    'timestamp': time.time()
                })
                
                self.decision_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                logging.error(f"AI worker error: {e}")
                
    def _compute_direction(self, request):
        """计算 AI 决策方向"""
        try:
            # 创建临时的简化对象，避免传递整个 tank
            class TempTank:
                def __init__(self, rect, direction, move_counter, max_moves, speed):
                    self.rect = rect
                    self.direction = direction
                    self.move_counter = move_counter
                    self.max_consecutive_moves = max_moves
                    self.speed = speed
                    
            temp_tank = TempTank(
                request['tank_rect'],
                request['tank_direction'],
                request['tank_move_counter'],
                request['tank_max_moves'],
                request['tank_speed']
            )
            
            # 构建临时敌人列表
            temp_enemies = [t for t in request['all_tanks_rects']]
            
            # 调用简化的决策逻辑（不依赖完整的 AI 系统）
            return self._simple_decision(temp_tank, request['target_rect'], request['walls'], temp_enemies)
        except Exception as e:
            logging.error(f"Error computing AI direction: {e}")
            return request['tank_direction']

    def _simple_decision(self, tank, target_rect, walls, all_tanks_rects):
        """简化的决策逻辑（在后台线程中执行）"""
        # 简单的避障逻辑
        directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]  # 上右下左
        for i, (dx, dy) in enumerate(directions):
            new_rect = tank.rect.move(dx * tank.speed, dy * tank.speed)
            # 检查是否在边界内
            from config.game_config import TILE_SIZE, SCREEN_COLS, SCREEN_ROWS
            playfield_rect = pygame.Rect(0, 0, TILE_SIZE * SCREEN_COLS, TILE_SIZE * SCREEN_ROWS)
            if not playfield_rect.contains(new_rect):
                continue
            # 检查墙壁碰撞
            collision = False
            for wall in walls:
                if new_rect.colliderect(wall):
                    collision = True
                    break
            if collision:
                continue
            # 检查坦克碰撞
            for other_rect in all_tanks_rects:
                if other_rect != tank.rect and new_rect.colliderect(other_rect):
                    collision = True
                    break
            if not collision:
                return i
        
        # 如果所有方向都有碰撞，随机选择一个
        return random.randint(0, 3)


def update_physics(players, enemies, bullets, explosions, wall_rects,
                   brick_tiles, steel_tiles, base_tiles, score, candidate_tanks,
                   current_time, q_agent, enemy_timer, player_ai_timer, enemy_ai_timer, enemy_roles_cache, ai_learning_enabled, ai_decider, player_ais, enemy_ais, global_hybrid_agents):
    """
    执行固定时间步长的物理模拟更新
    
    处理流程:
    1. 玩家AI决策 (150ms间隔) - 使用AutoAI追踪敌方坦克
    2. 敌方AI决策 (200ms间隔) - 使用HybridAgent追踪玩家
    3. 所有坦克移动执行 - 逐格移动，碰撞检测
    4. 子弹移动和碰撞检测:
       - 出界: 子弹销毁 + 爆炸效果
       - 钢墙: 子弹销毁 + 爆炸效果（墙体保留）
       - 砖墙: 子弹销毁 + 墙体摧毁 + 爆炸效果
       - 敌方坦克: 触发重生逻辑，记录AI经验
       - 玩家坦克: HP-1，HP=0时移除
       - 基地: 游戏立即重启（eagle_destroyed状态）
    
    碰撞检测策略:
    - 使用子弹路径矩形(prev_rect union current_rect)而非点检测
    - 防止高速子弹穿透薄墙体
    
    Args:
        players: 玩家坦克列表
        enemies: 敌方坦克列表
        bullets: 子弹列表
        explosions: 爆炸效果列表
        wall_rects: 所有不可穿透的墙体（砖墙+钢墙+基地）
        brick_tiles: 可摧毁的砖墙列表
        steel_tiles: 不可摧毁的钢墙列表
        base_tiles: 基地瓷砖列表
        score: 当前分数
        candidate_tanks: 剩余可重生坦克数
        current_time: 当前游戏时间(毫秒)
        q_agent: AI代理实例(HybridAgent)
        enemy_timer: 敌人生成计时器
        player_ai_timer: 玩家AI决策计时器
        enemy_ai_timer: 敌方AI决策计时器
        enemy_roles_cache: 敌方角色缓存
        ai_learning_enabled: 是否启用AI学习
        ai_decider: 线程安全AI决策器
        player_ais: 玩家AI控制器映射 {Tank: AutoAI}
        enemy_ais: 敌方AI控制器映射 {Tank: HybridAgent}
    
    Returns:
        tuple: (game_state, score, candidate_tanks, enemy_timer, 
                player_ai_timer, enemy_ai_timer, enemy_roles_cache)
        game_state: 'playing' | 'game_over' | 'eagle_destroyed'
    """
    reference_player = players[0] if players else None

    # 预先计算所有坦克列表（只创建一次）
    all_tanks = players + enemies

    # 玩家AI决策更新 - 使用EnemyAI智能系统
    if current_time - player_ai_timer > 150:
        player_ai_timer = current_time
        
        for player in players:
            player_ai = player_ais.get(player)
            if not player_ai:
                continue
                
            # 获取下一步移动方向（传入brick_tiles用于打掉砖墙）
            result = player_ai.get_next_move(enemies, wall_rects, all_tanks, current_time, brick_tiles)
            
            # 处理返回值（可能是元组或单个值）
            if isinstance(result, tuple):
                next_direction, should_shoot_brick = result
                # 如果需要射击砖墙
                if should_shoot_brick:
                    brick_bullet = player_ai.shoot_brick(current_time)
                    if brick_bullet:
                        bullets.append(brick_bullet)
            else:
                next_direction = result
            
            player.direction = next_direction
            
            # 智能射击决策（针对目标）
            target = player_ai.current_target
            if player_ai.should_fire(target, wall_rects, current_time):
                bullets.append(player.shoot(current_time))

    # 敌方AI决策更新 - 使用HybridAgent智能系统（Q-learning + 遗传算法）
    if current_time - enemy_ai_timer > 200:
        enemy_ai_timer = current_time
        
        # 为每个敌方坦克执行HybridAgent决策
        for enemy in enemies:
            enemy_hybrid = enemy_ais.get(enemy)
            if not enemy_hybrid or not reference_player:
                continue
            
            # 获取状态
            state = enemy_hybrid.get_state(enemy, reference_player, wall_rects, enemies)
            
            # 获取动作
            action = enemy_hybrid.get_action(state)
            
            # 如果有上一步的状态和动作，记录经验
            if enemy.last_state is not None and enemy.last_action is not None:
                # 计算奖励
                reward = 0.1  # 基础生存奖励
                
                # 检查是否接近玩家
                dist_to_player = math.hypot(
                    enemy.rect.centerx - reference_player.rect.centerx,
                    enemy.rect.centery - reference_player.rect.centery
                )
                
                if dist_to_player < 100:
                    reward += 1.0  # 接近玩家奖励
                elif dist_to_player > 300:
                    reward -= 0.1  # 远离玩家惩罚
                
                # 记录经验
                new_state = enemy_hybrid.get_state(enemy, reference_player, wall_rects, enemies)
                enemy_hybrid.add_experience(enemy.last_state, enemy.last_action, reward, new_state)
                enemy_hybrid.update_q_value(enemy.last_state, enemy.last_action, reward, new_state)
            
            # 更新状态
            enemy.last_state = state
            enemy.last_action = action
            
            # 转换为方向
            directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]  # 上、右、下、左
            dx, dy = directions[action]
            
            # 检查是否可行
            from tank_ai import can_move_rect
            if can_move_rect(enemy.rect, dx * enemy.speed, dy * enemy.speed, wall_rects):
                enemy.direction = action
            else:
                # 回退到随机可行方向
                import random
                random_directions = [0, 1, 2, 3]
                random.shuffle(random_directions)
                for dir_idx in random_directions:
                    ddx, ddy = directions[dir_idx]
                    if can_move_rect(enemy.rect, ddx * enemy.speed, ddy * enemy.speed, wall_rects):
                        enemy.direction = dir_idx
                        break

            # 智能射击决策
            if enemy.can_shoot(current_time):
                # 检查是否有清晰射界
                if has_clear_line(enemy.rect, reference_player.rect, wall_rects):
                    shot = enemy.shoot(current_time)
                    bullets.append(shot)

    # 所有坦克执行移动 - 优化：避免创建生成器
    for tank in all_tanks:
        # 优化：直接过滤，不创建生成器
        other_tanks = []
        for t in all_tanks:
            if t != tank:
                other_tanks.append(t)
        
        if tank.direction == 0:
            tank.move(0, -tank.speed, wall_rects, other_tanks)
        elif tank.direction == 1:
            tank.move(tank.speed, 0, wall_rects, other_tanks)
        elif tank.direction == 2:
            tank.move(0, tank.speed, wall_rects, other_tanks)
        else:
            tank.move(-tank.speed, 0, wall_rects, other_tanks)

    # 子弹移动和碰撞检测 - 优化：避免创建列表副本
    bullets_to_remove = []
    for bullet in bullets:
        bullet.move()
        path_rect = bullet.get_path_rect()

        if not PLAYFIELD_RECT.contains(bullet.rect):
            explosions.append(Explosion(bullet.rect.centerx, bullet.rect.centery))
            bullets_to_remove.append(bullet)
            continue

        # 优化：提前退出，避免any()的开销
        hit_steel = False
        for rect in steel_tiles:
            if rect.colliderect(path_rect):
                hit_steel = True
                break

        if hit_steel:
            explosions.append(Explosion(bullet.rect.centerx, bullet.rect.centery))
            bullets_to_remove.append(bullet)
            # 注意：钢墙不可摧毁，不从steel_tiles移除
            continue

        hit_brick, wall_rects, score = handle_brick_collision(bullet, path_rect, brick_tiles, wall_rects, explosions, bullets, score)
        if hit_brick:
            # 砖墙已从brick_tiles和wall_rects中移除（见handle_brick_collision）
            continue

        if bullet.owner == 'player':
            hit_enemy, score, candidate_tanks = handle_enemy_collision(
                bullet, path_rect, enemies, explosions, bullets, score, candidate_tanks, players, q_agent, enemy_ais, global_hybrid_agents
            )
            if hit_enemy:
                # 敌人已从enemies列表中移除（见handle_enemy_collision）
                continue
        else:
            hit_player = False
            for player in players[:]:
                if player.rect.colliderect(path_rect):
                    explosions.append(Explosion(player.rect.centerx, player.rect.centery))
                    bullets_to_remove.append(bullet)
                    player.hit_points -= 1

                    if player.hit_points <= 0:
                        players.remove(player)  # 玩家HP为0时从列表移除

                    if not players:
                        return 'game_over', score, candidate_tanks, enemy_timer, player_ai_timer, enemy_ai_timer, enemy_roles_cache

                    hit_player = True
                    break

            if hit_player:
                continue

            for rect in base_tiles[:]:  # 使用副本迭代
                if rect.colliderect(path_rect):
                    explosions.append(Explosion(rect.centerx, rect.centery))
                    bullets_to_remove.append(bullet)
                    base_tiles.remove(rect)  # 老鹰被摧毁，从列表移除
                    if rect in wall_rects:
                        wall_rects.remove(rect)  # 也从wall_rects移除
                    
                    # 老鹰被打掉，立即重开一局
                    logging.info("🦅 老鹰被摧毁！立即重开一局")
                    return 'eagle_destroyed', score, candidate_tanks, enemy_timer, player_ai_timer, enemy_ai_timer, enemy_roles_cache

    # 批量移除子弹 - 优化：使用集合加速查找
    bullets_to_remove_set = set(bullets_to_remove)
    bullets[:] = [b for b in bullets if b not in bullets_to_remove_set]

    # 更新爆炸效果 - 优化：原地更新而非创建新列表
    explosions_len = len(explosions)
    write_idx = 0
    for read_idx in range(explosions_len):
        if explosions[read_idx].update():
            if write_idx != read_idx:
                explosions[write_idx] = explosions[read_idx]
            write_idx += 1
    del explosions[write_idx:]
    
    return 'playing', score, candidate_tanks, enemy_timer, player_ai_timer, enemy_ai_timer, enemy_roles_cache


def render_game(screen, players, enemies, bullets, explosions, score, candidate_tanks, brick_tiles, steel_tiles, grass_tiles, base_tiles):
    """
    渲染函数 - 只负责绘制，不处理逻辑
    """
    screen.fill(BLACK)
    
    # 优化：直接绘制动态砖墙列表，而不是使用静态地图
    # 绘制砖墙
    for brick in brick_tiles:
        if 1 in TILE_IMAGES:
            screen.blit(TILE_IMAGES[1], brick.topleft)
    
    # 绘制钢墙
    for steel in steel_tiles:
        if 2 in TILE_IMAGES:
            screen.blit(TILE_IMAGES[2], steel.topleft)
    
    # 绘制草地
    for grass in grass_tiles:
        if 3 in TILE_IMAGES:
            screen.blit(TILE_IMAGES[3], grass.topleft)
    
    # 绘制基地（内部使用老鹰图案）
    for base in base_tiles:
        # 先绘制基地外壳
        if 4 in TILE_IMAGES:
            screen.blit(TILE_IMAGES[4], base.topleft)
        # 再在内部绘制老鹰
        if EAGLE_IMAGE:
            # 计算老鹰图像的中心位置
            eagle_rect = EAGLE_IMAGE.get_rect()
            eagle_rect.center = base.center
            screen.blit(EAGLE_IMAGE, eagle_rect.topleft)
    
    pygame.draw.line(screen, WHITE, (TILE_SIZE * SCREEN_COLS, 0), (TILE_SIZE * SCREEN_COLS, SCREEN_HEIGHT))
    
    for player in players:
        player.draw()
    for enemy in enemies:
        enemy.draw()
    for bullet in bullets:
        bullet.draw()
    for explosion in explosions:
        explosion.draw()
    
    total_hp = sum(p.hit_points for p in players) if players else 0
    draw_hud(score, total_hp, candidate_tanks, len(players))
    draw_sidebar(candidate_tanks)


def main():
    clock = pygame.time.Clock()
    players, enemies, bullets, explosions, score, candidate_tanks, brick_tiles, steel_tiles, grass_tiles, base_tiles, wall_rects, enemy_timer, player_ais, enemy_ais, global_hybrid_agents = reset_game()
    game_state = 'playing'

    # 固定时间步长配置
    PHYSICS_FPS = 60
    physics_step = 1000 / PHYSICS_FPS  # 每帧物理更新时间间隔（毫秒）
    accumulator = 0.0
    last_time = pygame.time.get_ticks()

    # AI 决策定时器
    player_ai_timer = 0
    enemy_ai_timer = 0
    enemy_roles_cache = {}  # 缓存角色分配结果
    ai_learning_enabled = False  # 默认关闭学习模式，提升性能

    # 初始化线程化 AI 决策器
    ai_decider = ThreadSafeAIDecider()
    ai_decider.start()
    
    # 游戏重启时也重置 AI 决策器
    ai_decider.reset()

    # Game statistics
    game_start_time = pygame.time.get_ticks()
    enemies_killed = 0
    player_damage_taken = 0
    team_coordination_score = 0

    # 追踪总游戏数，使用配置文件中的 MAX_GAME_TIMES
    total_games = 0
    max_games = MAX_GAME_TIMES

    # Game Over 自动重启定时器
    game_over_timer = 0

    running = True
    try:
        while running:
            current_time = pygame.time.get_ticks()
            frame_time = current_time - last_time
            last_time = current_time
            
            # 限制最大帧时间，防止螺旋死亡
            if frame_time > 250:
                frame_time = 250
            
            accumulator += frame_time
            
            # 处理事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # 固定时间步长物理更新（限制最大更新次数防止累积）
            max_updates = 5  # 每帧最多更新5次物理
            update_count = 0
            while accumulator >= physics_step and game_state == 'playing' and update_count < max_updates:
                game_state, score, candidate_tanks, enemy_timer, player_ai_timer, enemy_ai_timer, enemy_roles_cache = update_physics(
                    players, enemies, bullets, explosions, wall_rects,
                    brick_tiles, steel_tiles, base_tiles, score, candidate_tanks,
                    current_time, q_agent, enemy_timer, player_ai_timer, enemy_ai_timer, enemy_roles_cache, ai_learning_enabled, ai_decider, player_ais, enemy_ais, global_hybrid_agents
                )
                accumulator -= physics_step
                update_count += 1
            
            # 如果累加器过大，重置防止螺旋死亡
            if accumulator > physics_step * 10:
                accumulator = 0

            # 渲染
            if game_state == 'playing':
                render_game(screen, players, enemies, bullets, explosions, score, candidate_tanks, brick_tiles, steel_tiles, grass_tiles, base_tiles)

                # 检查是否所有坦克都被击杀
                if candidate_tanks <= 0 and len(enemies) == 0:
                    logging.info(f"所有坦克已击杀！准备重新开始第 {total_games + 1} 局")
                    game_end_time = pygame.time.get_ticks()
                    survival_time = (game_end_time - game_start_time) / 1000.0

                    game_stats = {
                        'survival_time': survival_time,
                        'enemies_killed': enemies_killed,
                        'player_damage': player_damage_taken,
                        'team_coordination': team_coordination_score
                    }

                    # ✅ 收集本局数据并传给 AI，激活遗传算法
                    # ⚠️ 现在使用全局 HybridAgent 实例，即使 enemy_ais 被清空也不会丢失数据
                    # ✅ 使用 evolve_before_new_game() 替代 record_game_stats()，包含探索率衰减和渐进式进化
                    for agent in global_hybrid_agents:
                        agent.evolve_before_new_game(game_stats)

                    # 重置 AI 决策器
                    ai_decider.reset()

                    # 手动触发GC，清理内存碎片
                    gc.collect()

                    players, enemies, bullets, explosions, score, candidate_tanks, brick_tiles, steel_tiles, grass_tiles, base_tiles, wall_rects, enemy_timer, player_ais, enemy_ais, global_hybrid_agents = reset_game(global_hybrid_agents)
                    game_state = 'playing'
                    game_start_time = pygame.time.get_ticks()
                    enemies_killed = 0
                    player_damage_taken = 0
                    team_coordination_score = 0
                    total_games += 1

                    if total_games >= max_games:
                        running = False

            elif game_state == 'eagle_destroyed':
                # 老鹰被打掉，立即重开一局（无延迟）
                logging.info(f"🦅 老鹰阵亡！立即重新开始第 {total_games + 1} 局")

                # ✅ 收集本局数据并传给 AI，激活遗传算法
                survival_time = (current_time - game_start_time) / 1000.0
                game_stats = {
                    'survival_time': survival_time,
                    'enemies_killed': 0,
                    'player_damage': player_damage_taken,
                    'team_coordination': 0
                }
                for agent in global_hybrid_agents:
                    agent.evolve_before_new_game(game_stats)

                # 重置 AI 决策器
                ai_decider.reset()

                # 手动触发GC，清理内存碎片
                gc.collect()

                players, enemies, bullets, explosions, score, candidate_tanks, brick_tiles, steel_tiles, grass_tiles, base_tiles, wall_rects, enemy_timer, player_ais, enemy_ais, global_hybrid_agents = reset_game(global_hybrid_agents)
                game_state = 'playing'
                game_start_time = pygame.time.get_ticks()
                enemies_killed = 0
                player_damage_taken = 0
                team_coordination_score = 0
                total_games += 1
                game_over_timer = 0

                if total_games >= max_games:
                    running = False

            elif game_state == 'game_over':
                # Draw game over overlay
                overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 128))
                screen.blit(overlay, (0, 0))
                game_over_text = LARGE_FONT.render("GAME OVER", True, WHITE)
                restart_text = LARGE_FONT.render(f"Restarting... ({total_games + 1}/{max_games})", True, WHITE)
                screen.blit(game_over_text, (SCREEN_WIDTH // 2 - game_over_text.get_width() // 2, SCREEN_HEIGHT // 2 - 30))
                screen.blit(restart_text, (SCREEN_WIDTH // 2 - restart_text.get_width() // 2, SCREEN_HEIGHT // 2 + 20))
                
                if game_over_timer == 0:
                    game_over_timer = current_time
                
                if current_time - game_over_timer > 2000:
                    game_end_time = pygame.time.get_ticks()
                    survival_time = (game_end_time - game_start_time) / 1000.0
                    
                    if players:
                        avg_distance = sum(
                            math.hypot(e.rect.centerx - players[0].rect.centerx, e.rect.centery - players[0].rect.centery)
                            for e in enemies
                        ) / max(1, len(enemies))
                        team_coordination_score = max(0, 300 - avg_distance)
                    
                    game_stats = {
                        'survival_time': survival_time,
                        'enemies_killed': enemies_killed,
                        'player_damage': player_damage_taken,
                        'team_coordination': team_coordination_score
                    }

                    # ✅ 收集本局数据并传给 AI，激活遗传算法
                    # ✅ 使用 evolve_before_new_game() 替代 record_game_stats()，包含探索率衰减和渐进式进化
                    for agent in global_hybrid_agents:
                        agent.evolve_before_new_game(game_stats)

                    # 重置 AI 决策器
                    ai_decider.reset()

                    # 手动触发GC，清理内存碎片
                    gc.collect()

                    players, enemies, bullets, explosions, score, candidate_tanks, brick_tiles, steel_tiles, grass_tiles, base_tiles, wall_rects, enemy_timer, player_ais, enemy_ais, global_hybrid_agents = reset_game(global_hybrid_agents)
                    game_state = 'playing'
                    game_start_time = pygame.time.get_ticks()
                    enemies_killed = 0
                    player_damage_taken = 0
                    team_coordination_score = 0
                    total_games += 1
                    game_over_timer = 0

                    if total_games >= max_games:
                        running = False

            pygame.display.flip()

            clock.tick(60)
    finally:
        # 停止 AI 线程
        ai_decider.stop()

        # 显示训练进度
        logging.info(f"\n=== 游戏完成 ===")
        logging.info(f"总游戏局数: {total_games + 1}")
        
        pygame.quit()

if __name__ == "__main__":
    main()
