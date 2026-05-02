"""
AI Metrics Visualization Window
Runs in a separate process, receives data via multiprocessing.Queue.
"""
import sys
import queue
from collections import deque

import pygame

COLORS = {
    'bg':          (26,  26,  46),
    'panel_bg':    (30,  30,  50),
    'border':      (70,  70, 120),
    'title':       (200, 200, 255),
    'epsilon':     (100, 149, 237),
    'coverage':    (255, 215,   0),
    'fitness':     ( 50, 205,  50),
    'diversity':   (255, 165,   0),
    'kill':        (220,  50,  47),
    'hit':         (255, 140,   0),
    'distance':    ( 42, 157, 143),
    'team':        (129, 178, 154),
    'survival_w':  (168, 218, 181),
    'player_win':  ( 50, 205,  50),
    'enemy_win':   (220,  50,  47),
    'surv_time':   (100, 149, 237),
    'text':        (180, 180, 200),
    'no_data':     ( 80,  80, 100),
    'white':       (255, 255, 255),
}

MAX_HISTORY = 200

PANEL_RECTS = {
    'qlearn':  pygame.Rect(10,  10,  380, 270),
    'ga':      pygame.Rect(410, 10,  380, 270),
    'weights': pygame.Rect(10,  290, 380, 300),
    'stats':   pygame.Rect(410, 290, 380, 300),
}

WEIGHT_RANGES = {
    'kill_reward':    (5.0,  50.0),
    'hit_reward':     (1.0,  20.0),
    'distance_scale': (0.1,   5.0),
    'team_bonus':     (0.0,   2.0),
    'survival_bonus': (0.0,   0.5),
}
WEIGHT_LABELS  = ['kill', 'hit', 'dist', 'team', 'surv']
WEIGHT_KEYS    = ['kill_reward', 'hit_reward', 'distance_scale', 'team_bonus', 'survival_bonus']
WEIGHT_COLORS  = [COLORS['kill'], COLORS['hit'], COLORS['distance'], COLORS['team'], COLORS['survival_w']]


class MetricsData:
    def __init__(self):
        self.games        = deque(maxlen=MAX_HISTORY)
        self.epsilon      = deque(maxlen=MAX_HISTORY)
        self.q_coverage   = deque(maxlen=MAX_HISTORY)
        self.ga_gen       = deque(maxlen=MAX_HISTORY)
        self.best_fitness = deque(maxlen=MAX_HISTORY)
        self.ga_diversity = deque(maxlen=MAX_HISTORY)
        self.surv_times   = deque(maxlen=MAX_HISTORY)
        self.damage_hits  = deque(maxlen=MAX_HISTORY)
        self.reward_weights = {}
        self.player_wins_total = 0
        self.hybrid_wins_total = 0

    def update(self, payload):
        g = payload.get('games_played', 0)
        self.games.append(g)
        self.epsilon.append(payload.get('exploration_rate', 0.0))
        self.q_coverage.append(payload.get('q_table_coverage', 0.0))
        self.ga_gen.append(payload.get('ga_generation', 0))
        raw_fit = payload.get('best_fitness', 0.0)
        self.best_fitness.append(max(raw_fit, 0.0) if raw_fit > -1e9 else 0.0)
        self.ga_diversity.append(payload.get('ga_diversity', 0.0) * 100.0)
        self.surv_times.append(payload.get('survival_time', 0.0))
        self.damage_hits.append(float(payload.get('damage_inflicted', 0)))
        if payload.get('reward_weights'):
            self.reward_weights = payload['reward_weights']
        self.player_wins_total += payload.get('player_wins', 0)
        self.hybrid_wins_total += payload.get('hybrid_wins', 0)


def _make_font(size):
    try:
        return pygame.font.SysFont('consolas', size)
    except Exception:
        return pygame.font.Font(None, size + 4)


def _draw_panel_base(surf, rect, title, font_title):
    pygame.draw.rect(surf, COLORS['panel_bg'], rect, border_radius=4)
    pygame.draw.rect(surf, COLORS['border'], rect, width=1, border_radius=4)
    label = font_title.render(title, True, COLORS['title'])
    surf.blit(label, (rect.x + 8, rect.y + 6))


def _no_data_text(surf, rect, font):
    msg = font.render("Waiting for game data...", True, COLORS['no_data'])
    cx = rect.x + (rect.w - msg.get_width()) // 2
    cy = rect.y + (rect.h - msg.get_height()) // 2
    surf.blit(msg, (cx, cy))


def _line_chart(surf, rect, series, colors, labels, title_h=24, padding=30):
    """Draw one or more line series inside rect. series = list of deques, colors/labels match."""
    chart_x = rect.x + padding
    chart_y = rect.y + title_h + 4
    chart_w = rect.w - padding - 8
    chart_h = rect.h - title_h - padding - 4

    if chart_w < 10 or chart_h < 10:
        return

    # Compute global Y range across all series
    all_vals = [v for s in series for v in s]
    if not all_vals:
        return
    y_min = min(all_vals)
    y_max = max(all_vals)
    if abs(y_max - y_min) < 1e-6:
        y_min -= 0.5
        y_max += 0.5
    y_range = y_max - y_min

    def to_px(val, idx, total):
        px = chart_x + int(idx / max(total - 1, 1) * chart_w)
        py = chart_y + chart_h - int((val - y_min) / y_range * chart_h)
        return (px, py)

    # Axes
    pygame.draw.line(surf, COLORS['border'],
                     (chart_x, chart_y), (chart_x, chart_y + chart_h), 1)
    pygame.draw.line(surf, COLORS['border'],
                     (chart_x, chart_y + chart_h), (chart_x + chart_w, chart_y + chart_h), 1)

    # Y tick labels (3 ticks)
    tick_font = _make_font(11)
    for i in range(3):
        val = y_min + y_range * i / 2
        py = chart_y + chart_h - int(i / 2 * chart_h)
        lbl = tick_font.render(f"{val:.2f}", True, COLORS['no_data'])
        surf.blit(lbl, (rect.x + 2, py - 6))
        pygame.draw.line(surf, COLORS['border'],
                         (chart_x - 2, py), (chart_x + 2, py), 1)

    # Series lines
    for s, color in zip(series, colors):
        if len(s) < 2:
            continue
        pts = [to_px(v, i, len(s)) for i, v in enumerate(s)]
        pygame.draw.lines(surf, color, False, pts, 2)

    # Legend (top-right of panel)
    leg_font = _make_font(11)
    lx = rect.x + rect.w - 90
    ly = rect.y + title_h + 4
    for color, lbl in zip(colors, labels):
        pygame.draw.rect(surf, color, pygame.Rect(lx, ly + 3, 10, 10))
        t = leg_font.render(lbl, True, COLORS['text'])
        surf.blit(t, (lx + 14, ly))
        ly += 16


def draw_panel_qlearn(surf, rect, data, font_title, font_body):
    _draw_panel_base(surf, rect, "Q-Learning Convergence", font_title)
    if not data.games:
        _no_data_text(surf, rect, font_body)
        return
    _line_chart(surf, rect,
                [data.epsilon, data.q_coverage],
                [COLORS['epsilon'], COLORS['coverage']],
                [f"ε={data.epsilon[-1]:.3f}", f"cov={data.q_coverage[-1]:.2f}"])


def draw_panel_ga(surf, rect, data, font_title, font_body):
    gen_label = f"GA Evolution  (gen={data.ga_gen[-1] if data.ga_gen else 0})"
    _draw_panel_base(surf, rect, gen_label, font_title)
    if not data.games:
        _no_data_text(surf, rect, font_body)
        return
    _line_chart(surf, rect,
                [data.best_fitness, data.ga_diversity],
                [COLORS['fitness'], COLORS['diversity']],
                [f"fit={data.best_fitness[-1]:.1f}", f"div×100={data.ga_diversity[-1]:.1f}"])


def draw_panel_weights(surf, rect, data, font_title, font_body):
    _draw_panel_base(surf, rect, "Reward Weights (best individual)", font_title)
    if not data.reward_weights:
        _no_data_text(surf, rect, font_body)
        return

    title_h = 24
    pad = 12
    bar_area_x = rect.x + pad
    bar_area_y = rect.y + title_h + 8
    bar_area_w = rect.w - pad * 2
    bar_area_h = rect.h - title_h - 40

    n = len(WEIGHT_KEYS)
    bar_w = (bar_area_w - (n - 1) * 6) // n
    val_font = _make_font(11)
    lbl_font = _make_font(12)

    for i, (key, color, lbl) in enumerate(zip(WEIGHT_KEYS, WEIGHT_COLORS, WEIGHT_LABELS)):
        lo, hi = WEIGHT_RANGES[key]
        val = data.reward_weights.get(key, lo)
        ratio = max(0.0, min(1.0, (val - lo) / (hi - lo)))
        bx = bar_area_x + i * (bar_w + 6)
        bh = max(4, int(ratio * bar_area_h))
        by = bar_area_y + bar_area_h - bh

        # Background bar
        pygame.draw.rect(surf, COLORS['border'],
                         pygame.Rect(bx, bar_area_y, bar_w, bar_area_h), border_radius=3)
        # Value bar
        pygame.draw.rect(surf, color,
                         pygame.Rect(bx, by, bar_w, bh), border_radius=3)

        # Value label above bar
        v_lbl = val_font.render(f"{val:.2f}", True, COLORS['white'])
        surf.blit(v_lbl, (bx + (bar_w - v_lbl.get_width()) // 2, max(bar_area_y, by - 14)))

        # Name label below
        n_lbl = lbl_font.render(lbl, True, COLORS['text'])
        surf.blit(n_lbl, (bx + (bar_w - n_lbl.get_width()) // 2,
                          bar_area_y + bar_area_h + 4))


def draw_panel_stats(surf, rect, data, font_title, font_body):
    _draw_panel_base(surf, rect, "Game Stats", font_title)
    if not data.games:
        _no_data_text(surf, rect, font_body)
        return

    title_h = 24
    total = data.player_wins_total + data.hybrid_wins_total
    p_ratio = data.player_wins_total / total if total else 0.0
    h_ratio = data.hybrid_wins_total / total if total else 0.0

    # Win rate bars
    bar_y = rect.y + title_h + 16
    bar_h = 22
    bar_x = rect.x + 10
    bar_w = rect.w - 20

    pygame.draw.rect(surf, COLORS['border'], pygame.Rect(bar_x, bar_y, bar_w, bar_h), border_radius=3)
    if p_ratio > 0:
        pygame.draw.rect(surf, COLORS['player_win'],
                         pygame.Rect(bar_x, bar_y, int(bar_w * p_ratio), bar_h), border_radius=3)
    p_lbl = font_body.render(f"Player {data.player_wins_total} ({p_ratio*100:.0f}%)", True, COLORS['white'])
    surf.blit(p_lbl, (bar_x + 4, bar_y + 3))

    bar_y2 = bar_y + bar_h + 6
    pygame.draw.rect(surf, COLORS['border'], pygame.Rect(bar_x, bar_y2, bar_w, bar_h), border_radius=3)
    if h_ratio > 0:
        pygame.draw.rect(surf, COLORS['enemy_win'],
                         pygame.Rect(bar_x, bar_y2, int(bar_w * h_ratio), bar_h), border_radius=3)
    h_lbl = font_body.render(f"Enemy  {data.hybrid_wins_total} ({h_ratio*100:.0f}%)", True, COLORS['white'])
    surf.blit(h_lbl, (bar_x + 4, bar_y2 + 3))

    total_lbl = font_body.render(f"Total games: {total}", True, COLORS['text'])
    surf.blit(total_lbl, (bar_x, bar_y2 + bar_h + 8))

    # Survival time + damage hits line chart
    surv_rect = pygame.Rect(rect.x, bar_y2 + bar_h + 30, rect.w, rect.h - (bar_y2 + bar_h + 30 - rect.y))
    series, colors_s, labels_s = [], [], []
    if len(data.surv_times) >= 2:
        series.append(data.surv_times)
        colors_s.append(COLORS['surv_time'])
        labels_s.append(f"dur={data.surv_times[-1]:.1f}s")
    if len(data.damage_hits) >= 2:
        series.append(data.damage_hits)
        colors_s.append(COLORS['kill'])
        labels_s.append(f"hits={int(data.damage_hits[-1])}")
    if series:
        _line_chart(surf, surv_rect, series, colors_s, labels_s, title_h=0, padding=28)


class MetricsWindow:
    def __init__(self, q):
        self.q = q
        self.data = MetricsData()
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("AI Training Metrics")
        self.clock = pygame.time.Clock()
        self.font_title = _make_font(14)
        self.font_body  = _make_font(13)
        self.running = True

    def drain_queue(self):
        while True:
            try:
                payload = self.q.get_nowait()
                if payload.get('__shutdown__'):
                    self.running = False
                    return
                self.data.update(payload)
            except queue.Empty:
                break

    def draw(self):
        self.screen.fill(COLORS['bg'])
        draw_panel_qlearn(self.screen, PANEL_RECTS['qlearn'], self.data, self.font_title, self.font_body)
        draw_panel_ga(self.screen, PANEL_RECTS['ga'],         self.data, self.font_title, self.font_body)
        draw_panel_weights(self.screen, PANEL_RECTS['weights'], self.data, self.font_title, self.font_body)
        draw_panel_stats(self.screen, PANEL_RECTS['stats'],   self.data, self.font_title, self.font_body)
        pygame.display.flip()

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

            self.drain_queue()
            self.draw()
            self.clock.tick(10)

        pygame.quit()


def run_metrics_window(q):
    win = MetricsWindow(q)
    win.run()


if __name__ == '__main__':
    import multiprocessing
    q = multiprocessing.Queue()
    run_metrics_window(q)
