"""
Performance tests for AI and game systems
"""
import unittest
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tank_ai import QLearningAgent, PerformanceMonitor, performance_optimizer


class TestPerformance(unittest.TestCase):
    """Test performance characteristics"""

    def setUp(self):
        self.agent = QLearningAgent()
        self.monitor = PerformanceMonitor()

    def test_ai_decision_speed(self):
        """Test AI decision making speed"""
        state = (0, 1, 2, 3, 0, 1)

        start_time = time.time()
        for _ in range(100):
            action = self.agent.get_action(state)
        end_time = time.time()

        avg_time = (end_time - start_time) / 100 * 1000  # Convert to ms
        self.assertLess(avg_time, 10, f"AI decision too slow: {avg_time:.2f}ms")

    def test_cache_performance(self):
        """Test caching system performance"""
        # Create mock objects
        class MockTank:
            def __init__(self, x, y):
                self.rect = type('Rect', (), {'centerx': x, 'centery': y})()

        enemy = MockTank(100, 100)
        target = MockTank(200, 200)
        walls = []
        allies = []

        # Test cache hit
        start_time = time.time()
        for _ in range(100):
            state = performance_optimizer.get_cached_state(enemy, target, walls, allies)
        end_time = time.time()

        avg_time = (end_time - start_time) / 100 * 1000  # Convert to ms
        self.assertLess(avg_time, 1, f"Cache too slow: {avg_time:.2f}ms")

    def test_memory_usage(self):
        """Test memory usage monitoring"""
        # Log some metrics
        frame_data = {
            'fps': 60.0,
            'memory_mb': 150.0,
            'cpu_percent': 25.0,
            'ai_decision_time': 5.0,
            'q_table_states': 500,
            'experience_count': 2000,
            'genetic_gen': 5,
            'enemy_count': 5,
            'bullet_count': 10,
            'score': 1000
        }

        self.monitor.log_frame_metrics(frame_data)

        # Check report generation
        report = self.monitor.get_performance_report()
        self.assertIn('avg_fps', report)
        self.assertIn('avg_memory_mb', report)
        self.assertIn('avg_cpu_percent', report)
        self.assertIn('current_score', report)

    def test_q_table_growth(self):
        """Test Q-table growth under load"""
        initial_states = len(self.agent.q_table)

        # Simulate learning
        for episode in range(50):
            state = (episode % 3, (episode + 1) % 3, (episode + 2) % 3,
                    episode % 4, episode % 2, (episode + 1) % 2)

            for step in range(10):
                action = self.agent.get_action(state)
                reward = 1.0 if action == 0 else -0.1
                next_state = ((state[0] + 1) % 3, state[1], state[2],
                             state[3], state[4], state[5])

                self.agent.add_experience(state, action, reward, next_state)
                self.agent.replay_experience()
                state = next_state

        final_states = len(self.agent.q_table)
        growth = final_states - initial_states
        self.assertGreater(growth, 0, "Q-table should grow during learning")


class TestStressPerformance(unittest.TestCase):
    """Stress tests for performance limits"""

    def test_high_load_ai_decisions(self):
        """Test AI performance under high load"""
        agent = QLearningAgent()
        states = [(i % 3, (i + 1) % 3, (i + 2) % 3, i % 4, i % 2, (i + 1) % 2)
                 for i in range(100)]

        start_time = time.time()
        for state in states:
            for _ in range(10):  # 10 decisions per state
                action = agent.get_action(state)
        end_time = time.time()

        total_decisions = len(states) * 10
        avg_time_per_decision = (end_time - start_time) / total_decisions * 1000

        # Should be well under 1ms per decision
        self.assertLess(avg_time_per_decision, 1,
                       f"High load performance poor: {avg_time_per_decision:.2f}ms/decision")


if __name__ == '__main__':
    unittest.main()