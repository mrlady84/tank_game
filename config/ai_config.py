"""
AI system configuration constants
"""

# Q-Learning constants
LEARNING_RATE = 0.2
DISCOUNT_FACTOR = 0.95
EXPLORATION_RATE = 0.3
EXPLORATION_DECAY = 0.999
MIN_EXPLORATION_RATE = 0.05

# Experience replay
REPLAY_BUFFER_SIZE = 5000
BATCH_SIZE = 16

# Genetic Algorithm constants
POPULATION_SIZE = 10
GENERATIONS = 50
MUTATION_RATE = 0.15
ELITISM_COUNT = 2
TOURNAMENT_SIZE = 3

# Performance optimization
CACHE_TIMEOUT = 10  # frames (increased from 5 for better cache hit rate)
PRIORITIZED_REPLAY_ALPHA = 0.6
PRIORITIZED_REPLAY_BETA = 0.4
PRIORITIZED_REPLAY_BETA_INCREMENT = 1e-6

# Game constants (will be passed from main)
TILE_SIZE = 32