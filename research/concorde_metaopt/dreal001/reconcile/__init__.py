"""P2A-CAL 执行后独立对账包（A2）。

只读：不导入 A1 执行器、不启动 solver、不修改 run 目录；physical_call_count=0。
"""
from .cal_reconcile import (  # noqa: F401
    SCHEMA,
    TOOL_VERSION,
    reconcile,
    render_markdown,
    status_exit_code,
    write_outputs,
)

__all__ = ["SCHEMA", "TOOL_VERSION", "reconcile", "render_markdown",
           "status_exit_code", "write_outputs"]
