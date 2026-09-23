"""现实交通参考（0.4.0）：已核验时刻表快照、交通枢纽参考、按服务日期落地的参考班次，以及从开船时间反推出门的一日行规划。

现实参考资料（班次、票价、枢纽）都带来源与适用范围；动物世界的承运编号只是世界里的身份，能追溯到参考班次；
星币旅费是世界内的经济，与现实票价分开展示。
"""

from .hubs import Hub, anchor, hub, load_hubs
from .timetable import Sailing, Timetable, load_timetable, timetables

__all__ = ["Hub", "Sailing", "Timetable", "anchor", "hub", "load_hubs", "load_timetable", "timetables"]
