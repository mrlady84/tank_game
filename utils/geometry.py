"""
Geometry utility functions for collision detection and spatial calculations
"""

def line_intersects_rect(start, end, rect):
    """检查线段是否与矩形相交"""
    x1, y1 = start
    x2, y2 = end

    left = rect.left
    right = rect.right
    top = rect.top
    bottom = rect.bottom

    if line_intersects_line(x1, y1, x2, y2, left, top, left, bottom):
        return True
    if line_intersects_line(x1, y1, x2, y2, right, top, right, bottom):
        return True
    if line_intersects_line(x1, y1, x2, y2, left, top, right, top):
        return True
    if line_intersects_line(x1, y1, x2, y2, left, bottom, right, bottom):
        return True

    return False


def line_intersects_line(x1, y1, x2, y2, x3, y3, x4, y4):
    """检查两条线段是否相交"""
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return False

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    return 0 <= t <= 1 and 0 <= u <= 1


def is_between(val, a, b):
    """检查值是否在两个边界之间"""
    return min(a, b) <= val <= max(a, b)