"""
AI system configuration constants
"""

# Q-Learning constants
LEARNING_RATE = 0.3
DISCOUNT_FACTOR = 0.95
EXPLORATION_RATE = 0.3
EXPLORATION_DECAY = 0.999
MIN_EXPLORATION_RATE = 0.05

# Experience replay
REPLAY_BUFFER_SIZE = 5000
BATCH_SIZE = 16

# Genetic Algorithm constants
POPULATION_SIZE = 10
MUTATION_RATE = 0.15
ELITISM_COUNT = 2
TOURNAMENT_SIZE = 3

# Reward weight defaults (GA initialization center)
DEFAULT_KILL_REWARD    = 15.0
DEFAULT_HIT_REWARD     = 5.0
DEFAULT_DISTANCE_SCALE = 1.0
DEFAULT_TEAM_BONUS     = 0.5
DEFAULT_SURVIVAL_BONUS = 0.05

# Fitness normalization constants
PLAYER_MAX_HP       = 20    # 2 players × 10 HP each
FITNESS_MAX_GAME_S  = 120.0 # survival time ceiling for normalization (seconds)

# Performance optimization
CACHE_TIMEOUT = 10  # frames
PRIORITIZED_REPLAY_ALPHA = 0.6
PRIORITIZED_REPLAY_BETA = 0.4
PRIORITIZED_REPLAY_BETA_INCREMENT = 1e-6

# Game constants (will be passed from main)
TILE_SIZE = 32
