"""几何网格身份与目标族固定（A1 / DREAL001，零物理）。

背景（E6-GAP-01）
-----------------
直接用 build_model -> VSPAEROComputeGeometry 一次成网格时，同一 x12 会随机落到
543/472 或 483/418 两个拓扑族；这是 OpenVSP 内部 tessellation 的非确定性，不是
设计变量响应，因此 E6 中除 W01(Sref) 外的变量敏感性都不能由该证据归因。

实验结论（runs/E6-SENSITIVITY-20261110/determinism/roundtrip/）
---------------------------------------------------------------
把几何先落盘为 .vsp3，再 ClearVSPModel -> ReadVSPFile(.vsp3) -> ComputeGeometry：
- 同进程 5/5、3 个独立进程 3/3 均为 543/472（9 次中 8 次记录在前，最后 1 次一致）；
- 字节 SHA 仍会变（对象 ID/顺序），且偶发 1 个节点的坐标抖动约 1e-2 m、面元连通
  随之改变，即"族稳定、字节与个别节点不保证完全一致"。

但"load 单文件 .vsp3 稳定"并不能消除随机性：新建 .vsp3 的族同样随机（同一 x12 写出的
不同 .vsp3 文件会导出不同族）。因此生产路径必须"每次尝试重新 build_model"做拒绝采样。
族频率（每设计 20 次 fresh build，determinism/frequency/determinism_probe3.json）：
  baseline  11x543/472, 9x483/418（p=0.55，12 次全失败 6.9e-05）
  W01-plus  11x543/472, 9x483/418（p=0.55，6.9e-05）
  V01-plus   5x543/472, 15x483/418（p=0.25，3.2e-02）
族概率与设计有关，V01-plus 在 12 次上限下最坏约 3.2% 概率 FAIL_CLOSED；该失败必须如实
记录并计入披露，不得静默放宽族目标或无限重试。

因此本模块定义 P2 的 canonical 规则：
1. 每个 design 从 x12 重新构建几何并落盘 .vsp3（禁止复制 P1 模板四件套）；
2. 以 round-trip 方式重建网格，最多 MAX_MESH_ATTEMPTS 次，取首个目标族样本；
3. 记录 mesh_attempts、mesh_family、nodes/elements、vspgeom 字节 SHA、规范化几何
   哈希（canonical_mesh_sha256）、.vsp3 SHA；
4. 达不到目标族 -> MeshFamilyUnavailable，FAIL_CLOSED，0 次真实启动。

规范化几何哈希定义：节点坐标以 %.9f 格式化后取多重集合，面元按"节点坐标序列"
表示后排序，对 NODES/ELEMS 文本取 sha256。它消除对象 ID/顺序的字节差异，但不
消除上述个别节点抖动；后者作为协变量披露，不做静默归一化。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MESH_IDENTITY_SCHEMA = "dreal001.mesh_identity.v1"
TARGET_MESH_FAMILY: Tuple[int, int] = (543, 472)
MAX_MESH_ATTEMPTS = 12
CANONICAL_COORD_FORMAT = "%.9f"


class MeshFamilyUnavailable(RuntimeError):
    """在允许的重建次数内没有得到目标网格族；调用方必须 FAIL_CLOSED。"""

    def __init__(self, target: Tuple[int, int], attempts: Sequence[Mapping[str, Any]]):
        self.target = tuple(target)
        self.attempts = [dict(item) for item in attempts]
        families = [item.get("mesh_family") for item in self.attempts]
        super().__init__(
            "target mesh family %s not obtained in %d attempt(s); observed families=%s"
            % (family_label(self.target), len(self.attempts), families))


def family_label(family: Optional[Sequence[int]]) -> Optional[str]:
    if not family:
        return None
    return "%dx%d" % (int(family[0]), int(family[1]))


def parse_vspgeom(path: str | Path) -> Dict[str, Any]:
    """解析 .vspgeom 的节点坐标与 3D 面元连通（仅前 nodes/elements 两段）。"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) < 3:
        raise ValueError("%s is not a vspgeom file (fewer than 3 lines)" % path)
    counts = [int(value) for value in lines[2].split()]
    n_nodes, n_elements = counts[0], counts[1]
    nodes: List[Tuple[float, float, float]] = []
    for raw in lines[3:3 + n_nodes]:
        values = [float(value) for value in raw.split()[:3]]
        if len(values) != 3:
            raise ValueError("malformed node line in %s: %r" % (path, raw))
        nodes.append((values[0], values[1], values[2]))
    elements: List[Tuple[int, ...]] = []
    for raw in lines[3 + n_nodes:3 + n_nodes + n_elements]:
        values = [int(value) for value in raw.split()]
        if not values:
            raise ValueError("malformed element line in %s: %r" % (path, raw))
        elements.append(tuple(values[1:1 + values[0]]))
    if len(nodes) != n_nodes or len(elements) != n_elements:
        raise ValueError("vspgeom of %s is truncated: %d/%d nodes, %d/%d elements"
                         % (path, len(nodes), n_nodes, len(elements), n_elements))
    return {"nodes": nodes, "elements": elements, "node_count": n_nodes,
            "element_count": n_elements, "header": lines[0].strip()}


def mesh_family(nodes_or_count: Any, element_count: Optional[int] = None) -> Tuple[int, int]:
    """接受解析结果、路径、或 (node_count, element_count)。"""
    if isinstance(nodes_or_count, Mapping):
        return (int(nodes_or_count["node_count"]), int(nodes_or_count["element_count"]))
    if isinstance(nodes_or_count, (str, Path)):
        parsed = parse_vspgeom(nodes_or_count)
        return (parsed["node_count"], parsed["element_count"])
    return (int(nodes_or_count), int(element_count))


def canonical_mesh_sha256(nodes: Sequence[Sequence[float]],
                          elements: Sequence[Sequence[int]]) -> str:
    node_keys = [",".join(CANONICAL_COORD_FORMAT % float(value) for value in node)
                 for node in nodes]
    element_keys = []
    for element in elements:
        element_keys.append("|".join(node_keys[int(index) - 1] for index in element))
    payload = "NODES\n" + "\n".join(sorted(node_keys)) + "\nELEMS\n" + "\n".join(
        sorted(element_keys))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def describe_mesh(path: str | Path) -> Dict[str, Any]:
    """返回一个网格文件的族、计数、字节 SHA 与规范化几何哈希（只读）。"""
    parsed = parse_vspgeom(path)
    data = Path(path).read_bytes()
    return {
        "schema": MESH_IDENTITY_SCHEMA,
        "mesh_family": family_label(mesh_family(parsed)),
        "nodes": parsed["node_count"],
        "elements": parsed["element_count"],
        "vspgeom_bytes": len(data),
        "vspgeom_sha256": hashlib.sha256(data).hexdigest(),
        "canonical_mesh_sha256": canonical_mesh_sha256(parsed["nodes"], parsed["elements"]),
        "canonical_coord_format": CANONICAL_COORD_FORMAT,
        "canonical_scope": "node multiset + sorted element coordinate-sequences; "
                           "removes object-ID/ordering bytes, NOT per-node jitter",
    }
