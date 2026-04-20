"""
空间网格系统 - 用于快速碰撞检测

将游戏世界分割为固定大小的网格单元，
只在相邻单元格中查找潜在碰撞对象，
避免 O(n) 的全量遍历。

复杂度:
- 插入: O(1)
- 查询: O(1) - 只返回附近的对象
- 空间: O(n) - n为对象数量

作者: Tank Battle AI Team
版本: 1.0
"""

from collections import defaultdict


class SpatialGrid:
    """
    均匀网格空间分割系统
    
    使用哈希表存储网格单元，支持动态扩展。
    每个单元格存储落入该区域的物体引用。
    """
    
    def __init__(self, cell_size=64):
        """
        初始化空间网格
        
        Args:
            cell_size: 网格单元大小(像素)，默认64
                      值越小精度越高但内存消耗越大
                      值越大查询范围越大但效率降低
                      建议设为坦克大小的2-4倍(64-128)
        """
        self.cell_size = cell_size
        self.grid = defaultdict(list)
        self.object_to_cells = {}  # 记录每个对象占据的单元格，用于快速删除
    
    def _get_cell_coords(self, x, y):
        """获取坐标所属的网格单元坐标"""
        return int(x // self.cell_size), int(y // self.cell_size)
    
    def _get_rect_cells(self, rect):
        """获取矩形覆盖的所有网格单元"""
        min_cell_x = rect.left // self.cell_size
        max_cell_x = rect.right // self.cell_size
        min_cell_y = rect.top // self.cell_size
        max_cell_y = rect.bottom // self.cell_size
        
        cells = []
        for x in range(min_cell_x, max_cell_x + 1):
            for y in range(min_cell_y, max_cell_y + 1):
                cells.append((x, y))
        return cells
    
    def insert(self, obj, rect):
        """
        插入对象到网格
        
        Args:
            obj: 要存储的对象引用
            rect: 对象的矩形区域
        """
        cells = self._get_rect_cells(rect)
        self.object_to_cells[id(obj)] = cells
        
        for cell in cells:
            self.grid[cell].append(obj)
    
    def remove(self, obj):
        """
        从网格中移除对象
        
        Args:
            obj: 要移除的对象
        """
        obj_id = id(obj)
        if obj_id in self.object_to_cells:
            for cell in self.object_to_cells[obj_id]:
                if obj in self.grid[cell]:
                    self.grid[cell].remove(obj)
            del self.object_to_cells[obj_id]
    
    def update(self, obj, new_rect):
        """
        更新对象位置（先移除再插入）
        
        Args:
            obj: 要更新的对象
            new_rect: 新的矩形位置
        """
        self.remove(obj)
        self.insert(obj, new_rect)
    
    def query(self, rect):
        """
        查询与指定矩形可能碰撞的所有对象
        
        返回矩形所在及相邻单元格中的所有对象，
        需要进一步做精确碰撞检测。
        
        Args:
            rect: 查询区域
            
        Returns:
            list: 潜在碰撞对象的列表（无重复）
        """
        cells = self._get_rect_cells(rect)
        result = set()
        
        for cell in cells:
            result.update(self.grid[cell])
        
        return list(result)
    
    def query_nearby(self, x, y, radius=1):
        """
        查询某坐标周围指定半径内的所有对象
        
        Args:
            x, y: 中心坐标
            radius: 网格单元半径，默认为1（3x3区域）
            
        Returns:
            list: 附近对象的列表
        """
        center_cell = self._get_cell_coords(x, y)
        result = set()
        
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                cell = (center_cell[0] + dx, center_cell[1] + dy)
                result.update(self.grid[cell])
        
        return list(result)
    
    def clear(self):
        """清空整个网格"""
        self.grid.clear()
        self.object_to_cells.clear()
    
    def get_stats(self):
        """获取网格统计信息"""
        total_cells = len(self.grid)
        non_empty_cells = sum(1 for cell in self.grid.values() if cell)
        total_objects = sum(len(cell) for cell in self.grid.values())
        avg_per_cell = total_objects / non_empty_cells if non_empty_cells > 0 else 0
        
        return {
            'total_cells': total_cells,
            'non_empty_cells': non_empty_cells,
            'total_objects': total_objects,
            'avg_per_cell': avg_per_cell
        }
