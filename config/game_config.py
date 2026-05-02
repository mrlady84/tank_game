"""
Game configuration constants
"""
# total games to simulate for training
MAX_GAME_TIMES = 10000

# Screen and tile settings
TILE_SIZE = 32
SCREEN_COLS = 20
SCREEN_ROWS = 15
PLAYFIELD_WIDTH = TILE_SIZE * SCREEN_COLS
SCREEN_WIDTH = PLAYFIELD_WIDTH + 96  # Add 96px for sidebar
SCREEN_HEIGHT = TILE_SIZE * SCREEN_ROWS

# Game area rectangle
PLAYFIELD_RECT = None  # Will be initialized after pygame.init()

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Game constants
SCORE_BRICK = 30
SCORE_ENEMY = 100
SCORE_BASE = 500

PLAYER_SHOT_DELAY = 200  # 我方射击冷却时间200ms
ENEMY_SHOT_DELAY = 300   # 敌方射击冷却时间300ms
START_LIVES = 10  # 玩家坦克可以抗住10次射击
EXPLOSION_DURATION = 8
MAX_ENEMIES = 5  # 敌方坦克数量
CANDIDATE_TANKS = 15  # 总候选坦克
PLAYER_TANK_COUNT = 2  # 玩家AI坦克数量

# Directions mapping
DIRECTIONS = [(0, -1), (0, 1), (1, 0), (-1, 0)]  # up, down, right, left
DIRECTION_NAMES = ['up', 'down', 'right', 'left']

# Map tile values
EMPTY = 0
BRICK_TILE = 1
STEEL_TILE = 2
GRASS_TILE = 3
BASE_TILE = 4

# Game level map
LEVEL_MAP = [
    [0, 0, 0, 0, 1, 1, 1, 0, 0, 2, 2, 0, 0, 1, 1, 1, 0, 0, 0, 0],
    [0, 3, 3, 0, 1, 0, 1, 0, 0, 2, 2, 0, 0, 1, 0, 1, 0, 3, 3, 0],
    [0, 3, 3, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 3, 3, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 0, 2, 2, 0, 0, 0, 0, 0, 0, 2, 2, 0, 1, 1, 1, 0],
    [0, 1, 0, 1, 0, 2, 2, 0, 0, 0, 0, 0, 0, 2, 2, 0, 1, 0, 1, 0],
    [0, 1, 1, 1, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 0, 1, 1, 1, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 3, 3, 0, 1, 1, 1, 0, 0, 2, 2, 0, 0, 1, 1, 1, 0, 3, 3, 0],
    [0, 3, 3, 0, 1, 0, 1, 0, 0, 2, 2, 0, 0, 1, 0, 1, 0, 3, 3, 0],
    [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0],
    [0, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0],
    [0, 2, 2, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 2, 2, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]