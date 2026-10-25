"""战术工坊 2.x 入口模块（分片组装，便于恢复大文件）。"""
from _app_part0 import PART_0
from _app_part1 import PART_1
from _app_part2 import PART_2

_code = PART_0 + PART_1 + PART_2
_ns = {"__name__": "app", "__file__": __file__}
exec(compile(_code, __file__, "exec"), _ns)
run = _ns["run"]
WorkshopWindow = _ns.get("WorkshopWindow")
globals().update({k: v for k, v in _ns.items() if not k.startswith("_")})
