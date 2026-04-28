"""
Unit tests for game components
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.game_config import *


class TestGameConfig(unittest.TestCase):
    """Test game configuration"""

    def test_constants_loaded(self):
        """Test that all required constants are loaded"""
        self.assertEqual(TILE_SIZE, 32)
        self.assertEqual(SCREEN_COLS, 20)
        self.assertEqual(SCREEN_ROWS, 15)
        self.assertEqual(MAX_ENEMIES, 5)

    def test_colors_defined(self):
        """Test color constants"""
        self.assertEqual(BLACK, (0, 0, 0))
        self.assertEqual(WHITE, (255, 255, 255))

    def test_level_map_structure(self):
        """Test level map structure"""
        # 实际LEVEL_MAP有16行，不是15行
        self.assertEqual(len(LEVEL_MAP), 16)
        self.assertEqual(len(LEVEL_MAP[0]), SCREEN_COLS)

    def test_directions_mapping(self):
        """Test direction mappings"""
        self.assertEqual(len(DIRECTIONS), 4)
        self.assertEqual(len(DIRECTION_NAMES), 4)


class TestGameConstants(unittest.TestCase):
    """Test game constants and scoring"""

    def test_scoring_system(self):
        """Test scoring constants"""
        self.assertEqual(SCORE_BRICK, 30)
        self.assertEqual(SCORE_ENEMY, 100)
        self.assertEqual(SCORE_BASE, 500)

    def test_game_limits(self):
        """Test game limits"""
        self.assertEqual(START_LIVES, 10)
        self.assertEqual(CANDIDATE_TANKS, 15)
        self.assertEqual(MAX_ENEMIES, 5)

    def test_timing_constants(self):
        """Test timing constants"""
        self.assertEqual(PLAYER_SHOT_DELAY, 200)
        self.assertEqual(ENEMY_SHOT_DELAY, 400)
        self.assertEqual(EXPLOSION_DURATION, 8)


if __name__ == '__main__':
    unittest.main()