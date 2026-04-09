# Tank Battle Game - Complete Project Details

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Core Features](#core-features)
4. [Technology Stack](#technology-stack)
5. [Project Structure](#project-structure)
6. [AI System Deep Dive](#ai-system-deep-dive)
7. [Game Mechanics](#game-mechanics)
8. [Installation & Running](#installation--running)
9. [Controls Guide](#controls-guide)
10. [Performance Monitoring](#performance-monitoring)
11. [Testing Framework](#testing-framework)
12. [Configuration Details](#configuration-details)
13. [Development Guide](#development-guide)
14. [FAQ](#faq)

---

## Project Overview

### Basic Information
- **Project Name**: Tank Battle Game
- **Inspired by**: Classic NES game "Battle City" (Tank 1990)
- **Language**: Python 3.8+
- **Game Engine**: Pygame 2.6.0+
- **Project Type**: 2D Pixel-style Shooting Game + AI Intelligence System

### Project Highlights
This is a modern implementation of the classic tank battle game, integrating a hybrid AI system powered by **Reinforcement Learning (Q-Learning)** and **Genetic Algorithms**. The game not only recreates the pixel style and core gameplay of the classic NES version, but also adds intelligent enemy learning systems, real-time performance monitoring, and comprehensive test coverage.

### Core Features
- 🎮 **Classic Recreation**: Perfectly replicates the pixel style and game mechanics of NES Tank Battle
- 🤖 **Intelligent AI**: Q-Learning + Genetic Algorithm hybrid system, enemies can autonomously learn tactics
- 🎯 **AI Player Tanks**: 2 player tanks fully controlled by AI, each can withstand 10 hits
- 🧬 **Progressive Evolution**: Three-stage progressive AI evolution strategy, avoiding early data insufficiency issues
- 🔄 **Auto Restart**: Automatically restarts when all tanks are destroyed, AI continuously evolves
- 📊 **Real-time Monitoring**: FPS, memory, CPU, AI decision time and other performance metrics tracked in real-time
- 🧪 **Comprehensive Testing**: Full unit test coverage ensuring code quality
- 🏗️ **Modular Architecture**: Clear code organization, easy to maintain and extend
- 🔧 **Global AI Instance**: Single global HybridAgent instance shared by all enemy tanks, avoiding data conflicts
- 📝 **Complete Logging System**: Logging configuration placed before all imports, ensuring all module logs work properly

---

## System Architecture

### Overall Architecture Design

```
┌─────────────────────────────────────────────────────────────┐
│                        Game Main Loop                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Game Logic   │  │  AI Layer    │  │ Performance Mon  │  │
│  │  (main.py)   │  │ (tank_ai.py) │  │ (PerformanceMon) │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                     Configuration Layer                      │
│  ┌──────────────────────┐  ┌────────────────────────────┐  │
│  │ Game Config          │  │ AI Config                  │  │
│  │ (game_config)        │  │ (ai_config)                │  │
│  └──────────────────────┘  └────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                      Resource Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Image Assets │  │ Audio Assets │  │ Font Resources   │  │
│  │  (assets/)   │  │  (optional)  │  │  (built-in)      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                     Testing Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ AI Tests     │  │ Game Logic   │  │ Performance      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Core Component Relationships

```
main.py (Game Main Program)
  │
  ├─→ Tank Class (Player/Enemy Tanks)
  │    ├─ Movement Control
  │    ├─ Shooting System
  │    └─ Collision Detection
  │
  ├─→ Bullet Class (Bullets)
  │    ├─ Trajectory Calculation
  │    └─ Collision Handling
  │
  ├─→ Explosion Class (Explosion Effects)
  │
  └─→ AI System (tank_ai.py)
       │
       ├─→ QLearningAgent (Q-Learning Agent)
       │    ├─ State Space (6 dimensions, 432 states)
       │    ├─ Action Space (4 directions)
       │    ├─ Experience Replay (5000 buffer)
       │    └─ Q-value Update
       │
       ├─→ GeneticOptimizer (Genetic Optimizer)
       │    ├─ Population Management (10 individuals)
       │    ├─ Fitness Evaluation
       │    └─ Parameter Evolution
       │
       └─→ PerformanceOptimizer (Performance Optimizer)
            ├─ State Cache
            ├─ Reward Cache
            └─ Performance Statistics
```

---

## Core Features

### 1. Game System

#### Map System
- **Map Size**: 20 columns × 15 rows (640×480 pixels)
- **Tile Size**: 32×32 pixels
- **Terrain Types**:
  - `0` - Empty space
  - `1` - Brick wall (destructible)
  - `2` - Steel block (indestructible)
  - `3` - Grass (concealment)
  - `4` - Base (needs protection)

#### Tank System
- **Player Tanks**:
  - Quantity: 2 (AI-controlled)
  - Initial Position: (7×32, 13×32) and (8×32, 13×32)
  - Hit Points: 10 (can withstand 10 hits)
  - Shooting Cooldown: 350ms
  - Movement Speed: 2 pixels/frame
  - Control Method: AI autonomous decision (every 300ms)

- **Enemy Tanks**:
  - Max Quantity: 10
  - Total Candidates: 20
  - Hit Points: 1
  - Shooting Cooldown: 1200ms
  - Movement Speed: 2 pixels/frame
  - AI Decision Cycle: 300ms

#### Bullet System
- **Bullet Speed**: 8 pixels/frame
- **Bullet Size**: 6×6 pixels
- **Collision Types**:
  - Hit brick wall → Destroy brick + explosion effect
  - Hit steel block → Explosion effect (steel block intact)
  - Hit enemy → Enemy explodes + score +100
  - Hit player tank → Player tank HP-1 + explosion effect
  - Hit base → Game over
  - Player tank HP≤0 → Tank destroyed
  - All player tanks destroyed → Game over
  - All tanks (player + enemy) killed → Auto restart

### 2. AI Intelligence System

#### Q-Learning Core

**State Space Design** (6-dimensional discretized, total 432 states):
```
State Vector = (rel_x, rel_y, distance_cat, direction, has_obstacle, has_ally)

rel_x:          Player on left (0) / Same column (1) / Player on right (2)
rel_y:          Player above (0) / Same row (1) / Player below (2)
distance_cat:   Near<100 (0) / Medium 100-250 (1) / Far>250 (2)
direction:      Up (0) / Right (1) / Down (2) / Left (3)
has_obstacle:   None (0) / Has obstacle (1)
has_ally:       None (0) / Has ally (1)
```

**Action Space**: 4 movement directions (Up/Right/Down/Left)

**Q-value Update Formula**:
```
Q(s,a) ← Q(s,a) + α × [r + γ × max(Q(s',a')) - Q(s,a)]

Where:
  α (Learning Rate) = 0.2 (genetically optimizable)
  γ (Discount Factor) = 0.95 (genetically optimizable)
  r = Immediate reward
  s' = Next state
  a' = Next action
```

**Experience Replay Mechanism**:
- **Buffer Capacity**: 5000 experiences
- **Sampling Strategy**: Prioritized sampling (TD error driven)
- **Batch Size**: 16 experiences/time
- **Priority Calculation**: priority = |TD_error| + 0.01
- **Importance Sampling**: Weight correction to avoid bias

#### Reward System Design

**Event Rewards** (Highest Priority):
| Event | Reward Value | Trigger Condition |
|-------|--------------|-------------------|
| Kill Player | +15.0 | Enemy bullet kills player |
| Damage Player | +3.0 | Enemy bullet hits player |
| Enemy Death | -10.0 | Enemy killed by player |

**Role Distance Rewards**:
| Role | Condition | Reward Value | Tactical Intent |
|------|-----------|--------------|-----------------|
| Aggressor | Distance<80 | +2.0 | Close combat |
| Aggressor | Distance 80-150 | +1.0 | Approaching |
| Aggressor | Distance>300 | -0.5 | Too far penalty |
| Flanker | Distance 120-250 & 45° angle | +2.0 | Ideal flank |
| Flanker | Distance>350 | -0.3 | Out of battle |
| Suppressor | Distance 200-350 | +1.0 | Area control |
| Suppressor | Distance<100 | -0.5 | Too close exposed |

#### Dynamic Role Assignment

**Three Tactical Roles**:

1. **Aggressor**
   - Selection Criteria: Enemy closest to player
   - Tactical Objective: Direct pursuit, shortest path
   - Optimal Distance: <80 pixels

2. **Flanker**
   - Selection Criteria: Enemy at 45-degree angle to player
   - Tactical Objective: Flanking maneuver, calculates perpendicular offset point
   - Optimal Distance: 120-250 pixels
   - Flanking Algorithm: perp_x = -dy/distance×100, perp_y = dx/distance×100

3. **Suppressor**
   - Selection Criteria: Enemy controlling center map position
   - Tactical Objective: Block paths, control key routes
   - Optimal Distance: 200-350 pixels

#### Genetic Algorithm Optimization

**Optimized Parameters**:
| Parameter | Range | Default Value | Function |
|-----------|-------|---------------|----------|
| Learning Rate α | 0.1~0.3 | 0.2 | Q-value update speed |
| Discount Factor γ | 0.9~0.99 | 0.95 | Long-term reward weight |
| Exploration Rate ε | 0.1~0.4 | 0.3 | Exploration vs Exploitation |

**Fitness Function**:
```
Fitness = survival_time × 0.2
        + enemies_killed × 8
        - player_damage × 1.5
        + team_coordination × 3
```

---

## Technology Stack

### Core Dependencies
- pygame >= 2.6.0: Game engine, responsible for rendering, input, audio, etc.
- psutil >= 5.9.0: System monitoring, getting process performance data

### Python Standard Library
- random: Random number generation
- pickle: Serialization
- math: Mathematical operations
- collections.deque: Double-ended queue
- logging: Logging
- os, sys, time, copy: System tools

---

## Project Structure

```
tank_game/
│
├── main.py                    # Game main program entry (1263 lines)
├── tank_ai.py                 # AI system implementation (1725 lines)
├── config/                    # Configuration directory
│   ├── game_config.py         # Game configuration (118 lines)
│   └── ai_config.py           # AI configuration (27 lines)
├── utils/                     # Utility functions
│   └── geometry.py            # Geometric calculations (41 lines)
├── assets/                    # Game resources
│   ├── base.png               # Base image
│   ├── brick.png              # Brick wall tile
│   ├── steel.png              # Steel block tile
│   ├── grass.png              # Grass tile
│   ├── player_tank.png        # Player tank sprite
│   ├── enemy_tank.png         # Enemy tank sprite
│   ├── eagle.png              # Eagle sprite
│   └── bullet.png             # Bullet sprite
├── tests/                     # Test directory
│   ├── test_ai.py             # AI system tests
│   ├── test_game.py           # Game logic tests
│   └── test_performance.py    # Performance tests
├── doc/                       # Documentation directory
├── .gitignore                 # Git ignore rules
├── requirements.txt           # Dependency list
├── README.md                  # Project documentation (English)
├── README_cn.md               # Project documentation (Chinese)
├── hybrid_model.pkl           # AI model checkpoint (generated at runtime)
└── game.log                   # Game log (generated at runtime)
```

### Code Statistics

| File | Lines | Main Function |
|------|-------|---------------|
| main.py | 1263 | Game main program, tank/bullet/explosion classes, collision handling |
| tank_ai.py | 1725 | AI system, Q-learning, genetic algorithm, performance optimization |
| config/game_config.py | 118 | Game constants, map data |
| config/ai_config.py | 27 | AI parameter configuration |
| utils/geometry.py | 41 | Geometry utilities |
| tests/ | ~550 | Unit tests |
| **Total** | **~3724** | **Core code** |

---

## AI System Deep Dive

### Workflow

#### 1. Initialization Phase
```
Game Start → Configure Logging System (logging.basicConfig)
    ↓  // ✅ Key: Logging must be configured before all imports
Initialize Pygame → Load Resources → Create Game Instance
    ↓
Initialize AI System (QLearningAgent + GeneticOptimizer + PerformanceOptimizer)
    ↓
Create Global HybridAgent Instance (Singleton Pattern)
    ↓
Reset Game State → Enter Game Loop
```

**Critical Fix** (2026-04-10):
- ❌ Old Design: `logging.basicConfig()` called after importing `tank_ai` → Logs in tank_ai don't work
- ✅ New Design: `logging.basicConfig()` placed before all imports → All module logs work properly

#### 2. Game Loop (Per Frame)
```
1. Event Handling (Keyboard input, window events)
2. AI Decision (Every 300ms)
   - Record previous frame experience
   - Call AI evolution (evolve_before_new_game)  // ✅ Unified method, replaces record_game_stats
   - Role assignment
   - Q-learning decision
   - Execute movement
   - Attempt shooting
3. Physics Update (Bullet movement, collision detection, explosion effects)
4. Rendering (Map, tanks, bullets, effects, UI)
5. Performance Monitoring (FPS, memory, cache hit rate)
6. Frame Rate Control (clock.tick(60))
```

#### 3. Event-Triggered Learning
- **When Enemy Dies**: learn_from_death(history) → Learn from historical sequence → Experience replay
- **When Player Killed**: All surviving enemies get kill reward (+15)
- **When Player Damaged**: Nearest enemy gets damage reward (+3)

#### 4. Progressive AI Evolution Strategy (Three Stages)

```
┌─────────────────────────────────────────────────────┐
│ Stage 1: Data Accumulation (Games 1-3)              │
│ 📊 Strategy: No evolution, only collect data         │
│ Reason: Avoid wrong decisions based on limited data  │
│ Exploration Rate: Decays 5% per game                 │
├─────────────────────────────────────────────────────┤
│ Stage 2: Light Evolution (Games 4-9)                │
│ 🌱 Strategy: Low-intensity mutation based on population│
│ Method: Preserve 50% elites, mutation amplitude 30%  │
│ Experience Replay: 2 times                            │
├─────────────────────────────────────────────────────┤
│ Stage 3: Standard Evolution (Games 10+)             │
│ 🧬 Strategy: Full genetic algorithm                  │
│ Data: Latest 10 games real data                      │
│ Experience Replay: 3 times                            │
└─────────────────────────────────────────────────────┘
```

**Evolution Trigger Timing**:
- Automatically triggered after all tanks are killed
- Manually triggered when restarting from game over screen
- Immediately triggered when eagle is destroyed

**Evolution Method**: `evolve_before_new_game(game_stats)`
- ✅ Unified entry: All game end scenarios call this method
- ✅ Auto decay: Exploration rate decays 5% per game
- ✅ Progressive evolution: Automatically selects evolution intensity based on game count
- ✅ Auto save: Automatically saves checkpoint after evolution completes

**Evolution Flow**:
```
Game End → Collect Statistics
    ↓
Call evolve_before_new_game(game_stats)
    ↓
Exploration Rate Decay 5% (exploration_rate *= 0.95)
    ↓
Determine Stage:
  ├─ Games 1-3: Accumulate data, no evolution
  ├─ Games 4-9: Light evolution (preserve elites, low-intensity mutation)
  └─ Games 10+: Standard evolution (full genetic algorithm)
    ↓
Update Q-learning Parameters → Experience Replay → Auto Save → Log Output
```

**Advantages**:
- ✅ Avoids wrong decisions based on early fake data
- ✅ Gradually increases evolution intensity, smooth transition
- ✅ Only uses real data, no virtual sample generation
- ✅ More stable parameter changes, consistent AI behavior
- ✅ Checkpoint support: Auto save/load model, supports continuous learning across program runs

#### 5. Global AI Instance Design

**Design Concept**: All enemy tanks share the same `HybridAgent` instance

**Implementation**:
```python
# main.py - reset_game()
if global_hybrid_agents is None:
    # Load checkpoint on first creation
    global_hybrid_agents = [HybridAgent()]
else:
    # When resetting game, don't clear buffer
    # Let data accumulate across games, cleared by evolve_before_new_game() during evolution
    pass

# All enemy tanks assigned the same AI instance
for enemy in enemies:
    enemy_ais[enemy] = global_hybrid_agents[0]
```

**Advantages**:
- ✅ Avoids duplicate counting: `games_played` only increments in one place
- ✅ Data consistency: All tanks share the same Q-table and learning history
- ✅ Memory optimization: Only maintains one AI instance instead of multiple
- ✅ Continuous learning: Buffer accumulates across games, auto cleared after evolution
- ✅ Checkpoint support: Save/load checkpoint, supports continued learning after program restart

**Critical Fix** (2026-04-10):
- ❌ Old Design: Each tank has independent HybridAgent instance → Data conflict, double counting
- ✅ New Design: Single global HybridAgent instance → Data consistent, accurate counting

---

## Game Mechanics

### 1. Map Design
- **Map Size**: 20 columns × 15 rows
- **Terrain Types**: Empty (0), Brick Wall (1), Steel Block (2), Grass (3), Base (4)

### 2. Collision System
- Tank ↔ Wall/Boundary: Block movement
- Player Bullet ↔ Brick Wall: Destroy brick + score +30
- Player Bullet ↔ Enemy: Enemy explodes + score +100
- Enemy Bullet ↔ Player: Life -1
- Any Bullet ↔ Base: Game over

### 3. Scoring System
| Event | Score |
|-------|-------|
| Destroy Brick Wall | +30 |
| Kill Enemy | +100 |
| Protect Base | +500 |

### 4. Life System

#### Player Tank Life System
- **Initial HP**: 10 points per player tank (START_LIVES=10)
- **Total HP**: 2 tanks = 20 points
- **Damage Penalty**: HP-1 per hit
- **Tank Destruction**: Tank removed when HP≤0
- **Game Over**: All player tanks destroyed

#### Enemy Tank Life System
- **Initial HP**: 1 point per enemy tank
- **When Hit**: Immediately explodes and destroyed
- **Respawn Mechanism**: Automatically generate new enemy when candidate tanks > 0 (max 20)

### 5. Auto Restart Mechanism

**Trigger Conditions**:
- All candidate tanks killed (`candidate_tanks ≤ 0`)
- No enemies on field (`len(enemies) == 0`)

**Restart Flow**:
```
1. Record current game statistics (survival_time, enemies_killed, etc.)
2. Call AI evolution: agent.evolve_before_new_game(game_stats)  // ✅ Unified method
3. Reset AI decider (ai_decider.reset())
4. Manually trigger GC (gc.collect())
5. Reset game to initial state (reset_game(global_hybrid_agents))  // ✅ Preserve global instance
6. Reset statistics counters
7. Increment game count (total_games += 1)
8. Continue game (or exit when reaching max_games=50)
```

**Critical Fixes** (2026-04-10):
- ❌ Old Design: Using `record_game_stats()` → Method duplication, exploration rate doesn't decay
- ✅ New Design: Unified use of `evolve_before_new_game()` → Complete functionality, auto exploration rate decay
- ✅ Global Instance: `reset_game(global_hybrid_agents)` preserves AI instance, avoids recreation

**Max Games**: 50 games (configurable `max_games`)

### 6. HUD Display

**Display Content**:
- `SCORE`: Current score
- `PLAYER HP`: Total remaining HP of all player tanks
- `PLAYERS`: Number of surviving player tanks
- `ENEMIES`: Remaining enemy candidate count
- `AI CONTROLLED`: Indicates AI control

---

## Installation & Running

### Environment Requirements
- Python 3.8+
- 2GB RAM (minimum) / 4GB RAM (recommended)

### Installation Steps
```bash
# 1. Clone project
git clone <repository-url>
cd tank_game

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run game
python main.py
```

---

## Controls Guide

### Game Controls

| Key | Function | Description |
|-----|----------|-------------|
| ↑↓←→ | **Disabled** | Player tanks now controlled by AI |
| Space | **Disabled** | AI auto-shooting |
| F1 | Exit | Game over screen |
| F2/R | Restart | Game over screen (triggers AI evolution) |

**Note**: Player tanks are fully AI-controlled, no keyboard input required!

---

## Performance Monitoring

| Metric | Normal Range | Warning Threshold |
|--------|--------------|-------------------|
| FPS | 55-60 | <50 |
| Memory | 50-150MB | >300MB |
| CPU | 5-20% | >50% |
| AI Decision Time | 1-5ms | >15ms |
| Cache Hit Rate | >70% | <50% |

---

## Testing Framework

### Running Tests
```bash
# Run all tests
python -m unittest discover tests/ -v

# Run specific tests
python -m unittest tests.test_ai -v
python -m unittest tests.test_game -v
python -m unittest tests.test_performance -v
```

### Test Coverage
| Test File | Test Count | Coverage |
|-----------|------------|----------|
| test_ai.py | ~30 | 80%+ |
| test_game.py | ~25 | 75%+ |
| test_performance.py | ~15 | 70%+ |
| **Total** | **~70** | **75%+** |

---

## Configuration Details

### game_config.py
- TILE_SIZE = 32 (Tile size)
- SCREEN_COLS = 20, SCREEN_ROWS = 15 (Map size)
- MAX_ENEMIES = 10 (Max simultaneous enemies)
- CANDIDATE_TANKS = 20 (Total candidate enemies)
- PLAYER_TANK_COUNT = 2 (Player AI tank count) ⭐ **New**
- START_LIVES = 10 (Player tank HP) ⭐ **Changed from 3 to 10**

### ai_config.py
- LEARNING_RATE = 0.2 (Learning rate)
- DISCOUNT_FACTOR = 0.95 (Discount factor)
- EXPLORATION_RATE = 0.3 (Exploration rate)
- REPLAY_BUFFER_SIZE = 5000 (Experience buffer)
- POPULATION_SIZE = 10 (Genetic population size)

### Progressive Evolution Configuration
- **Stage 1** (Games 1-3): Data accumulation, no evolution
- **Stage 2** (Games 4-9): Light evolution (preserve 50% elites, 30% mutation)
- **Stage 3** (Games 10+): Standard evolution (full genetic algorithm)
- **Exploration Rate Decay**: Decays 5% per game (exploration_rate *= 0.95)
- **Global AI Instance**: Single HybridAgent instance, shared by all enemy tanks
- **Checkpoint Support**: Auto save/load checkpoint, supports continuous learning across program runs
- **Experience Replay**: Stage 2=2 times, Stage 3=3 times

---

## Development Guide

### Code Standards
- Constants: UPPER_SNAKE_CASE (TILE_SIZE)
- Class Names: PascalCase (QLearningAgent)
- Functions/Variables: lower_snake_case (get_state)

### Extension Development
- Add new terrain: Modify game_config.py + Add resources + Update collision logic
- Add new weapons: Create new Bullet subclass + Add shooting logic
- Add new AI strategy: Inherit QLearningAgent and extend get_state method

---

## FAQ

### Q1: Game won't start
1. Check Python version (requires 3.8+)
2. Check dependency installation (pygame, psutil)
3. Check if resource files exist
4. Check game.log for errors

### Q2: Game runs laggy
1. Increase CACHE_TIMEOUT to 10
2. Reduce MAX_ENEMIES to 5
3. Close other programs to free resources

### Q3: AI not learning
1. Check exploration_rate > 0.05
2. Check replay_buffer > 100
3. Increase training games to 100
4. Check console evolution logs

### Q4: Memory usage too high
1. Reduce REPLAY_BUFFER_SIZE to 3000
2. Clear cache periodically
3. Restart game (F2)

### Q5: Why don't player tanks respond to keyboard?
**This is normal behavior!** Player tanks are now fully AI-controlled.
- AI automatically finds nearest enemy
- AI automatically moves and shoots
- Decides every 300ms

### Q6: How does the game auto restart?
When **all tanks** (2 players + 20 enemies) are killed:
1. Auto record game statistics
2. Auto evolve AI model
3. Auto reset game
4. Continue to next game
5. Max 50 games

---

## Appendix

### Key Algorithms
- **Q-Learning**: Learns through trial and error, gradually optimizes decision strategy
- **Genetic Algorithm**: Finds optimal Q-learning hyperparameter combinations
- **Experience Replay**: Prioritized sampling, important experiences learned first

### Learning Resources
- [Pygame Official Documentation](https://www.pygame.org/docs/)
- [Q-Learning Tutorial](https://en.wikipedia.org/wiki/Q-learning)
- [Genetic Algorithm Guide](https://www.obitko.com/tutorials/genetic-algorithms/)

---

## Document Information

- **Document Version**: v3.0 ⭐ **Updated** (April 10, 2026)
- **Created**: April 9, 2026
- **Last Updated**: April 10, 2026

### Update History

#### v3.0 (2026-04-10) - Major Fixes
- ✅ Fixed logging configuration order: `logging.basicConfig()` placed before imports
- ✅ Created global AI instance: Single `HybridAgent` instance shared by all enemy tanks
- ✅ Unified evolution method: Deleted `record_game_stats()`, using `evolve_before_new_game()`
- ✅ Fixed games_played duplicate counting: Changed from 2 instances to 1 global instance
- ✅ Added checkpoint support: Auto save/load checkpoint, continuous learning across sessions
- ✅ Updated code review report: All P0/P1/P2/P3 issues fixed

#### v2.0 (2026-04-09) - Progressive Evolution Strategy
- ✅ Implemented progressive three-stage evolution strategy
- ✅ Fixed stage 2 population initialization bug
- ✅ Fixed exploration rate double decay issue
- ✅ Cleaned up temporary test files
- ✅ Updated project documentation

#### v1.0 (2026-04-09) - Initial Version
- ✅ Project overview and system architecture
- ✅ AI system details
- ✅ Game mechanics documentation
- ✅ Configuration and development guide

### Current Code Version
- **main.py**: 1263 lines - Game main program
- **tank_ai.py**: 1725 lines - AI system implementation
- **config/game_config.py**: 118 lines - Game configuration
- **config/ai_config.py**: 27 lines - AI configuration
- **utils/geometry.py**: 41 lines - Geometry utilities
- **Python Version**: 3.8+
- **Dependencies**: pygame>=2.6.0, psutil>=5.9.0

### Major Updates (v3.0 - 2026-04-10)

#### 🐛 Bug Fixes
1. **Logging Configuration Order** (P0-Critical)
   - Issue: `logging.basicConfig()` called after importing `tank_ai`
   - Fix: Placed before all imports (line 46)
   - Effect: All module logs work properly

2. **games_played Duplicate Counting** (P0-Critical)
   - Issue: Created 2 `HybridAgent` instances, counting method called twice per game
   - Fix: Changed to single global instance shared by all tanks
   - Effect: Accurate counting, corrected from 20 games to 10 games

3. **evolve_before_new_game() Not Called** (P1-High)
   - Issue: Method defined but never called, exploration rate doesn't decay
   - Fix: Replaced all `record_game_stats()` calls
   - Effect: Exploration rate decays normally, progressive evolution works

#### 🔧 Architecture Optimizations
1. **Global AI Instance Design**
   - Single `HybridAgent` instance shared by all enemy tanks
   - Avoids data conflicts and duplicate counting
   - Halves memory usage

2. **Unified Evolution Interface**
   - Deleted duplicate `record_game_stats()` method
   - Unified use of `evolve_before_new_game(game_stats)`
   - Includes exploration rate decay, progressive evolution, auto save

3. **Checkpoint Support**
   - Auto save checkpoint to `hybrid_model.pkl`
   - Auto load on program restart, continuous learning
   - `games_played` accumulates across program runs

---

**🎮 Enjoy the Game!**
