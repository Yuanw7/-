"""Validator Node — 校验节点。

【职责】
在 Multi-Agent 数据流转过程中，对每个 Agent 的输出进行代码级校验，
确保数据符合约束条件，防止脏数据进入下游流程。

【校验规则】
1. Agent 1 输出的坐标必须在房间边界内
2. Agent 1 输出的尺寸必须为正数
3. Agent 2 输出的合规结果必须有 valid 标记
4. 拓扑矩阵中的净距计算结果必须非负
5. 所有 ID 必须唯一

【架构定位】
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Agent 1    │────▶│  Validator  │────▶│  Agent 2    │
│  extract    │     │  Node       │     │  audit      │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  校验失败   │
                   │  → 回退/重试 │
                   └─────────────┘
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models import GraphState, FurnitureNode, RoomBoundaryInfo


# ════════════════════════════════════════════════════════════════════════════════
# 校验结果
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    node_name: str  # 当前校验的节点名
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_details: list[str] = field(default_factory=list)

    def add_pass(self, check_name: str) -> None:
        self.checks_passed.append(check_name)

    def add_fail(self, check_name: str, detail: str = "") -> None:
        self.checks_failed.append(check_name)
        if detail:
            self.error_details.append(detail)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)


# ════════════════════════════════════════════════════════════════════════════════
# Agent 1 校验器
# ════════════════════════════════════════════════════════════════════════════════

def validate_agent_1_output(state: GraphState) -> ValidationResult:
    """校验 Agent 1 输出的空间拓扑数据。

    检查项：
    1. 房间边界尺寸为正数
    2. 家具中心坐标在房间范围内
    3. 家具尺寸为正数
    4. 家具 ID 唯一性
    5. BBox 坐标合理性 (left < right, top < bottom)

    Args:
        state: GraphState

    Returns:
        校验结果
    """
    result = ValidationResult(is_valid=True, node_name="Agent1_extract")

    furniture_list = state.get("furniture_list", [])
    boundary = state.get("boundary")

    # 检查 1: 房间边界
    if boundary:
        width = boundary.get("width_mm", 0)
        depth = boundary.get("depth_mm", 0)

        if width > 0 and depth > 0:
            result.add_pass("boundary_positive")
        else:
            result.add_fail("boundary_positive", f"房间尺寸异常: width={width}, depth={depth}")
    else:
        result.add_fail("boundary_exists", "缺少房间边界数据")

    # 检查 2: 家具列表非空
    if len(furniture_list) == 0:
        result.add_warning("furniture_list_empty")
    else:
        result.add_pass("furniture_list_not_empty")

    # 检查 3: 家具 ID 唯一性
    furniture_ids = [node.get("id") for node in furniture_list]
    if len(furniture_ids) != len(set(furniture_ids)):
        duplicate_ids = [fid for fid in furniture_ids if furniture_ids.count(fid) > 1]
        result.add_fail("furniture_id_unique", f"发现重复ID: {set(duplicate_ids)}")
    else:
        result.add_pass("furniture_id_unique")

    # 检查 4-7: 逐个检查家具属性
    for i, node in enumerate(furniture_list):
        node_id = node.get("id", f"item_{i}")

        # 尺寸检查
        size = node.get("size", [0, 0, 0])
        if len(size) != 3:
            result.add_fail(
                "furniture_size_dimensions",
                f"{node_id}: size 应为 3 维，实际 {len(size)} 维"
            )
        elif any(s <= 0 for s in size):
            result.add_fail(
                "furniture_size_positive",
                f"{node_id}: 尺寸必须为正数，实际 {size}"
            )
        else:
            result.add_pass(f"furniture_size_positive:{node_id}")

        # 坐标检查
        if boundary:
            cx, cy = node.get("center", [None, None])
            w, d, _ = size

            if cx is None or cy is None:
                result.add_fail("furniture_center_exists", f"{node_id}: 缺少中心坐标")
            else:
                # 边界检查：家具中心应在房间范围内
                half_w, half_d = w / 2, d / 2
                left = cx - half_w
                right = cx + half_w
                top = cy + half_d
                bottom = cy - half_d

                out_of_bounds = []
                if left < 0:
                    out_of_bounds.append(f"left={left}<0")
                if right > boundary.get("width_mm", float("inf")):
                    out_of_bounds.append(f"right={right}>width")
                if bottom < 0:
                    out_of_bounds.append(f"bottom={bottom}<0")
                if top > boundary.get("depth_mm", float("inf")):
                    out_of_bounds.append(f"top={top}>depth")

                if out_of_bounds:
                    result.add_fail(
                        "furniture_center_in_bounds",
                        f"{node_id}: 坐标越界 {out_of_bounds} (room: {boundary.get('width_mm')}x{boundary.get('depth_mm')})"
                    )
                else:
                    result.add_pass(f"furniture_center_in_bounds:{node_id}")

        # BBox 检查
        bbox = node.get("bbox", [0, 0, 0, 0])
        if len(bbox) != 4:
            result.add_fail("furniture_bbox_dimensions", f"{node_id}: bbox 应为 4 维")
        else:
            left, top, right, bottom = bbox
            if not (left < right and top < bottom):
                result.add_fail(
                    "furniture_bbox_valid",
                    f"{node_id}: bbox 坐标不合理 left={left}, top={top}, right={right}, bottom={bottom}"
                )
            else:
                result.add_pass(f"furniture_bbox_valid:{node_id}")

        # 材质检查
        material = node.get("material", "")
        if not material:
            result.add_warning(f"{node_id}: 材质未标注")

    return result


# ════════════════════════════════════════════════════════════════════════════════
# Agent 2 校验器
# ════════════════════════════════════════════════════════════════════════════════

def validate_agent_2_output(state: GraphState) -> ValidationResult:
    """校验 Agent 2 输出的合规审计结果。

    检查项：
    1. 所有家具都有 pass_2_audit 结果
    2. 微观特征报告结构完整
    3. physical_risk_points 格式正确

    Args:
        state: GraphState

    Returns:
        校验结果
    """
    result = ValidationResult(is_valid=True, node_name="Agent2_audit")

    furniture_list = state.get("furniture_list", [])

    for node in furniture_list:
        node_id = node.get("id", "unknown")
        audit_data = node.get("pass_2_audit", "")

        if not audit_data:
            result.add_warning(f"{node_id}: 缺少 Agent 2 审计结果")
            continue

        # 尝试解析 JSON
        import json
        try:
            if isinstance(audit_data, str):
                audit_dict = json.loads(audit_data)
            else:
                audit_dict = audit_data

            # 检查必要字段
            required_fields = ["furniture_id", "micro_features"]
            for field_name in required_fields:
                if field_name not in audit_dict:
                    result.add_fail(
                        "audit_field_exists",
                        f"{node_id}: 缺少字段 {field_name}"
                    )

            # 检查 micro_features 结构
            if "micro_features" in audit_dict:
                mf = audit_dict["micro_features"]

                # 材质分析
                if "material_analysis" in mf:
                    ma = mf["material_analysis"]
                    if "primary_material" not in ma:
                        result.add_warning(f"{node_id}: material_analysis 缺少 primary_material")

                # 几何分析
                if "geometry_analysis" in mf:
                    ga = mf["geometry_analysis"]
                    if "corner_type" not in ga:
                        result.add_warning(f"{node_id}: geometry_analysis 缺少 corner_type")

                # 人机工学分析
                if "ergonomics_analysis" in mf:
                    ea = mf["ergonomics_analysis"]
                    if "seat_height_compliant" not in ea:
                        result.add_warning(f"{node_id}: ergonomics_analysis 缺少 seat_height_compliant")

            # 检查 physical_risk_points
            if "physical_risk_points" in audit_dict:
                risk_points = audit_dict["physical_risk_points"]
                if not isinstance(risk_points, list):
                    result.add_fail(
                        "risk_points_type",
                        f"{node_id}: physical_risk_points 应为列表"
                    )

            result.add_pass(f"audit_structure_valid:{node_id}")

        except json.JSONDecodeError:
            result.add_fail("audit_json_valid", f"{node_id}: pass_2_audit JSON 解析失败")
        except Exception as e:
            result.add_fail("audit_structure_valid", f"{node_id}: 结构校验异常 {str(e)}")

    return result


# ════════════════════════════════════════════════════════════════════════════════
# 拓扑校验器
# ════════════════════════════════════════════════════════════════════════════════

def validate_topology_matrix(state: GraphState) -> ValidationResult:
    """校验拓扑矩阵的正确性。

    检查项：
    1. 拓扑矩阵非空
    2. 所有净距值非负
    3. 矩阵对称性 (A→B 和 B→A 净距相同)
    4. 与原始家具列表一致性

    Args:
        state: GraphState

    Returns:
        校验结果
    """
    result = ValidationResult(is_valid=True, node_name="topology_matrix")

    topology = state.get("topology_matrix", {})
    furniture_list = state.get("furniture_list", [])

    # 检查 1: 矩阵非空
    if not topology:
        result.add_fail("topology_not_empty")
    else:
        result.add_pass("topology_not_empty")

    # 检查 2: 净距非负
    negative_found = []
    for source_id, targets in topology.items():
        for target_id, edge in targets.items():
            clearance = edge.get("clearance_mm", -1)
            if clearance < 0:
                negative_found.append(f"{source_id}→{target_id}")

    if negative_found:
        result.add_fail("clearance_non_negative", f"发现负净距: {negative_found}")
    else:
        result.add_pass("clearance_non_negative")

    # 检查 3: 矩阵对称性
    asymmetry_found = []
    for source_id, targets in topology.items():
        for target_id, edge in targets.items():
            if target_id in topology and source_id in topology[target_id]:
                reverse_edge = topology[target_id][source_id]
                if abs(edge.get("clearance_mm", 0) - reverse_edge.get("clearance_mm", 0)) > 1:
                    asymmetry_found.append(f"{source_id}↔{target_id}")

    if asymmetry_found:
        result.add_warning(f"matrix_asymmetry: {asymmetry_found}")
    else:
        result.add_pass("matrix_symmetry")

    # 检查 4: 与家具列表一致性
    furniture_ids = {node.get("id") for node in furniture_list}
    matrix_ids = set(topology.keys())

    missing_from_matrix = furniture_ids - matrix_ids
    extra_in_matrix = matrix_ids - furniture_ids

    if missing_from_matrix:
        result.add_fail("matrix_furniture_consistency", f"矩阵缺少家具: {missing_from_matrix}")
    if extra_in_matrix:
        result.add_fail("matrix_furniture_consistency", f"矩阵有多余家具: {extra_in_matrix}")
    if not missing_from_matrix and not extra_in_matrix:
        result.add_pass("matrix_furniture_consistency")

    return result


# ════════════════════════════════════════════════════════════════════════════════
# 统一校验入口
# ════════════════════════════════════════════════════════════════════════════════

def validate_state(state: GraphState, after_node: str) -> ValidationResult:
    """根据当前节点统一调度校验。

    Args:
        state: GraphState
        after_node: 刚执行完成的节点名

    Returns:
        校验结果
    """
    validators = {
        "agent_1_extract": validate_agent_1_output,
        "agent_2_audit": validate_agent_2_output,
        "topology_calculate": validate_topology_matrix,
        "agent_3_report": lambda s: ValidationResult(is_valid=True, node_name="Agent3_report"),
    }

    validator = validators.get(after_node)
    if validator:
        return validator(state)

    return ValidationResult(is_valid=True, node_name="unknown")


# ════════════════════════════════════════════════════════════════════════════════
# 校验失败处理策略
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class ValidationError:
    """校验错误详情"""
    check_name: str
    detail: str
    severity: str  # fatal/warning


class ValidationStrategy:
    """校验失败处理策略"""

    FATAL_CHECKS = {
        "boundary_exists",
        "furniture_id_unique",
        "furniture_size_positive",
        "furniture_center_in_bounds",
        "furniture_bbox_valid",
        "topology_not_empty",
        "clearance_non_negative",
        "matrix_furniture_consistency",
        "audit_json_valid",
        "audit_structure_valid",
    }

    @classmethod
    def should_retry(cls, result: ValidationResult) -> bool:
        """判断是否需要重试"""
        if result.is_valid:
            return False

        for failed_check in result.checks_failed:
            check_base = failed_check.split(":")[0]
            if check_base in cls.FATAL_CHECKS:
                return True
        return False

    @classmethod
    def get_action(cls, result: ValidationResult) -> str:
        """获取后续动作建议"""
        if result.is_valid:
            return "continue"

        fatal_count = 0
        for failed_check in result.checks_failed:
            check_base = failed_check.split(":")[0]
            if check_base in cls.FATAL_CHECKS:
                fatal_count += 1

        if fatal_count > 0:
            return "retry_agent"
        return "continue_with_warning"


# ════════════════════════════════════════════════════════════════════════════════
# 格式化输出
# ════════════════════════════════════════════════════════════════════════════════

def format_validation_report(result: ValidationResult) -> str:
    """格式化校验报告为可读字符串。

    Args:
        result: 校验结果

    Returns:
        格式化的报告文本
    """
    lines = []
    lines.append("=" * 50)
    lines.append(f"校验报告: {result.node_name}")
    lines.append("=" * 50)

    if result.is_valid:
        lines.append("✅ 校验通过")
    else:
        lines.append("❌ 校验失败")

    if result.checks_passed:
        lines.append(f"\n✅ 通过 ({len(result.checks_passed)} 项):")
        for check in result.checks_passed[:5]:  # 最多显示5项
            lines.append(f"   - {check}")
        if len(result.checks_passed) > 5:
            lines.append(f"   ... 还有 {len(result.checks_passed) - 5} 项")

    if result.checks_failed:
        lines.append(f"\n❌ 失败 ({len(result.checks_failed)} 项):")
        for check, detail in zip(result.checks_failed, result.error_details):
            lines.append(f"   - {check}")
            if detail:
                lines.append(f"     {detail}")

    if result.warnings:
        lines.append(f"\n⚠️ 警告 ({len(result.warnings)} 项):")
        for warning in result.warnings[:5]:
            lines.append(f"   - {warning}")

    lines.append("=" * 50)

    return "\n".join(lines)
