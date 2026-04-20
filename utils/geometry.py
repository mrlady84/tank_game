"""
Geometry utility functions for collision detection and spatial calculations
"""

def _line_aabb_check(x1, y1, x2, y2, rect):
    """
    快速AABB包围盒检测
    如果线段的包围盒与矩形无交集，则线段不可能与矩形相交
    这是O(1)的快速排除测试
    """
    min_x = min(x1, x2)
    max_x = max(x1, x2)
    min_y = min(y1, y2)
    max_y = max(y1, y2)
    
    # 快速排除：线段包围盒在矩形外
    if max_x < rect.left or min_x > rect.right:
        return False
    if max_y < rect.top or min_y > rect.bottom:
        return False
    
    return True


def line_intersects_rect(start, end, rect):
    """
    检查线段是否与矩形相交
    优化版：先进行AABB快速检测，再进行精确检测
    """
    x1, y1 = start
    x2, y2 = end

    # 快速AABB预检测 - 排除明显不相交的情况
    if not _line_aabb_check(x1, y1, x2, y2, rect):
        return False

    left = rect.left
    right = rect.right
    top = rect.top
    bottom = rect.bottom

    # 内联的线段相交检测，减少函数调用开销
    # 左边
    if _line_intersects_line_fast(x1, y1, x2, y2, left, top, left, bottom):
        return True
    # 右边
    if _line_intersects_line_fast(x1, y1, x2, y2, right, top, right, bottom):
        return True
    # 上边
    if _line_intersects_line_fast(x1, y1, x2, y2, left, top, right, top):
        return True
    # 下边
    if _line_intersects_line_fast(x1, y1, x2, y2, left, bottom, right, bottom):
        return True

    return False


def _line_intersects_line_fast(x1, y1, x2, y2, x3, y3, x4, y4):
    """
    内联的线段相交检测 - 减少函数调用开销
    """
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return False

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    if t < 0 or t > 1:
        return False
        
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    return 0 <= u <= 1


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