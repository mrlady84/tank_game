"""
Unit tests for AI components
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tank_ai import QLearningAgent, PrioritizedReplayBuffer, PerformanceOptimizer


class TestQLearningAgent(unittest.TestCase):
    """Test Q-Learning Agent functionality"""

    def setUp(self):
        self.agent = QLearningAgent()

    def test_initialization(self):
        """Test agent initialization"""
        self.assertIsNotNone(self.agent.q_table)
        self.assertIsNotNone(self.agent.replay_buffer)
        self.assertEqual(self.agent.exploration_rate, 0.3)

    def test_get_action(self):
        """Test action selection"""
        state = (0, 1, 2, 3, 0, 1)
        action = self.agent.get_action(state)
        self.assertIn(action, [0, 1, 2, 3])

    def test_add_experience(self):
        """Test experience addition"""
        state = (0, 1, 2, 3, 0, 1)
        action = 0
        reward = 1.0
        next_state = (0, 1, 2, 3, 0, 1)

        initial_size = len(self.agent.replay_buffer)
        self.agent.add_experience(state, action, reward, next_state)
        self.assertEqual(len(self.agent.replay_buffer), initial_size + 1)


class TestPrioritizedReplayBuffer(unittest.TestCase):
    """Test Prioritized Replay Buffer functionality"""

    def setUp(self):
        self.buffer = PrioritizedReplayBuffer(100)

    def test_initialization(self):
        """Test buffer initialization"""
        self.assertEqual(len(self.buffer), 0)
        self.assertEqual(self.buffer.capacity, 100)

    def test_add_experience(self):
        """Test adding experience to buffer"""
        experience = ((0, 1, 2, 3, 0, 1), 0, 1.0, (0, 1, 2, 3, 0, 1))
        self.buffer.add(experience)

        self.assertEqual(len(self.buffer), 1)

    def test_sample(self):
        """Test sampling from buffer"""
        # Add some experiences
        for i in range(10):
            experience = ((0, 1, 2, 3, 0, 1), i % 4, 1.0, (0, 1, 2, 3, 0, 1))
            self.buffer.add(experience)

        samples, indices, weights = self.buffer.sample(5)
        self.assertEqual(len(samples), 5)
        self.assertEqual(len(indices), 5)
        self.assertEqual(len(weights), 5)


class TestPerformanceOptimizer(unittest.TestCase):
    """Test Performance Optimizer functionality"""

    def setUp(self):
        self.optimizer = PerformanceOptimizer()

    def test_initialization(self):
        """Test optimizer initialization"""
        self.assertIsNotNone(self.optimizer.state_cache)
        self.assertIsNotNone(self.optimizer.reward_cache)
        self.assertEqual(self.optimizer.cache_timeout, 5)

    def test_cache_stats(self):
        """Test cache statistics"""
        stats = self.optimizer.get_cache_stats()
        self.assertIn('hit_rate', stats)
        self.assertIn('hits', stats)
        self.assertIn('misses', stats)
        self.assertIn('state_cache_size', stats)
        self.assertIn('reward_cache_size', stats)


if __name__ == '__main__':
    unittest.main()