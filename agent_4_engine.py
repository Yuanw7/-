"""Agent 4: 适老化改造项目经理与造价师 — 分级改造方案与成本核算。

Role: 适老化改造项目经理与造价师

Chain-of-Thought 执行逻辑:
1. 风险定级：按致死/致残概率对违规项进行 T0/T1/T2 风险评级
2. 最优方案 (Optimal)：彻底消除隐患，重资产投入
3. 备选方案 (Alternative)：极低成本+现有格局，轻资产改良

Constraint:
- 每一项风险必须同时具备 Optimal 与 Alternative 两套方案
- 空间位置调整必须输出明确的数学矢量偏移建议
- 强制输出 YAML 格式结构体
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from typing import Any, Literal

from agent_3_engine import ViolationRecord, CLEARANCE_STANDARDS


# ════════════════════════════════════════════════════════════════════════════════
# 风险定级标准
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class RiskLevel:
    """风险等级定义"""
    code: str  # T0/T1/T2
    name: str  # 严重/中等/一般
    probability_weight: float  # 致死/致残概率权重
    response_time: str  # 响应时限
    description: str


RISK_LEVELS = {
    "T0": RiskLevel(
        code="T0",
        name="严重风险",
        probability_weight=0.8,
        response_time="立即处理（24小时内）",
        description="存在直接生命安全威胁，必须立即整改",
    ),
    "T1": RiskLevel(
        code="T1",
        name="中等风险",
        probability_weight=0.4,
        response_time="限期处理（7天内）",
        description="存在较高受伤风险，需要尽快整改",
    ),
    "T2": RiskLevel(
        code="T2",
        name="一般风险",
        probability_weight=0.15,
        response_time="计划处理（30天内）",
        description="存在潜在安全隐患，建议优化改进",
    ),
}


# ════════════════════════════════════════════════════════════════════════════════
# 市场物料价格库 (参考价，单位：元)
# ════════════════════════════════════════════════════════════════════════════════

MATERIAL_PRICE_LIB = {
    # 地面材料
    "防滑地垫_平方米": 180,
    "防滑地胶_平方米": 280,
    "无障碍坡道_套": 1200,
    "门槛消除条_米": 85,

    # 墙面材料
    "L型防撞条_米": 45,
    "圆形防撞贴_个": 12,
    "墙面护角_套": 68,
    "夜光扶手_米": 320,

    # 家具调整
    "家具定位垫_个": 25,
    "防滑脚垫_套": 58,
    "家具移动服务_次": 380,

    # 适老家具
    "适老沙发_张": 8500,
    "适老餐椅_把": 1800,
    "升降茶几_张": 4200,
    "护理床_张": 12800,
    "折叠淋浴椅_把": 680,

    # 安全设施
    "一字型扶手_米": 280,
    "折臂式扶手_套": 680,
    "紧急呼叫器_套": 420,
    "感应夜灯_个": 128,
    "浴室防滑垫_套": 168,

    # 大型工程
    "非承重墙拆除_平方米": 380,
    "走廊拓宽_平方米": 680,
    "门宽扩大_套": 2200,
    "全屋定制适老家具_套": 58000,
    "无障碍卫生间改造_间": 35000,
}


@dataclass
class MaterialItem:
    """物料清单项"""
    name: str
    unit: str
    quantity: float
    unit_price: float
    total_price: float
    source: str  # 采购来源建议


@dataclass
class PositionAdjustment:
    """空间位置调整建议"""
    furniture_id: str
    current_center: tuple[float, float]
    target_center: tuple[float, float]
    offset_vector: tuple[float, float]  # [dx, dy] 单位mm
    offset_direction: str  # 如 "+X 方向"
    description: str


@dataclass
class RenovationPlan:
    """改造方案"""
    plan_id: str
    plan_type: Literal["optimal", "alternative"]
    risk_level: str
    violation_id: str
    title: str
    description: str

    # 空间调整
    position_adjustments: list[PositionAdjustment] = field(default_factory=list)

    # 物料清单
    materials: list[MaterialItem] = field(default_factory=list)

    # 工程措施
    engineering_measures: list[str] = field(default_factory=list)

    # 成本估算
    estimated_cost: float = 0.0
    cost_breakdown: dict[str, float] = field(default_factory=dict)

    # 实施信息
    implementation_days: int = 0
    difficulty_level: str = ""


# ════════════════════════════════════════════════════════════════════════════════
# 风险定级函数
# ════════════════════════════════════════════════════════════════════════════════

def classify_risk(violation: ViolationRecord) -> str:
    """根据违规类型和严重程度进行风险定级。

    T0: 致死/致残风险
    T1: 严重受伤风险
    T2: 轻微受伤风险

    Args:
        violation: 违规记录

    Returns:
        风险等级代码 (T0/T1/T2)
    """
    # 直接叠加 - 最高风险
    if violation.violation_type == "overlap":
        return "T0"

    # 轮椅通道严重不足 (低于50%)
    if violation.violation_type == "wheelchair_passage":
        if violation.actual_clearance_mm < 450:  # < 规范值50%
            return "T0"
        elif violation.actual_clearance_mm < 700:  # < 规范值78%
            return "T1"
        else:
            return "T2"

    # 门侧净距不足
    if violation.violation_type == "door_access_clearance":
        if violation.actual_clearance_mm < 400:
            return "T0"
        elif violation.actual_clearance_mm < 600:
            return "T1"
        else:
            return "T2"

    # 床侧净距不足
    if violation.violation_type == "bed_side_clearance":
        if violation.actual_clearance_mm < 400:
            return "T1"
        elif violation.actual_clearance_mm < 600:
            return "T2"
        else:
            return "T2"

    # 默认中等风险
    if violation.severity == "high":
        return "T1"
    elif violation.severity == "medium":
        return "T2"

    return "T2"


# ════════════════════════════════════════════════════════════════════════════════
# 最优方案生成函数 (Optimal Plan)
# ════════════════════════════════════════════════════════════════════════════════

def generate_optimal_plan(
    violation: ViolationRecord,
    furniture_labels: dict[str, str],
    clearance_required: float,
) -> RenovationPlan:
    """生成最优改造方案 — 以彻底消除隐患为唯一目标。

    特点：
    - 重资产投入
    - 可能涉及空间结构改造
    - 追求最佳适老化效果

    Args:
        violation: 违规记录
        furniture_labels: 家具ID到标签的映射
        clearance_required: 规范要求的净距

    Returns:
        最优改造方案
    """
    plan_id = f"OPT_{violation.violation_type}_{violation.source_id[:8]}"
    risk_level = classify_risk(violation)

    source_label = furniture_labels.get(violation.source_id, violation.source_id)
    target_label = furniture_labels.get(violation.target_id, violation.target_id)

    materials: list[MaterialItem] = []
    engineering: list[str] = []
    position_adjustments: list[PositionAdjustment] = []
    cost_breakdown: dict[str, float] = {}

    # 计算需要的位移量
    current_clearance = violation.actual_clearance_mm
    shortage = violation.shortage_mm

    # === 空间位置调整 ===
    if violation.violation_type in ("wheelchair_passage", "bed_side_clearance"):
        # 计算两件家具各自的位移量（平均分配）
        offset_per_furniture = shortage / 2 + 50  # 多移50mm确保安全

        # 确定移动方向（从两物体中心连线方向）
        # 简化处理：假设沿X轴方向移动
        dx = offset_per_furniture
        dy = 0.0

        # 源家具移动
        position_adjustments.append(PositionAdjustment(
            furniture_id=violation.source_id,
            current_center=(0, 0),  # 实际值从state获取
            target_center=(dx, dy),
            offset_vector=(dx, dy),
            offset_direction="+X 方向" if dx > 0 else "-X 方向",
            description=f"将 {source_label} 沿 X 轴正方向平移 {dx:.0f}mm",
        ))

        # 目标家具反方向移动
        position_adjustments.append(PositionAdjustment(
            furniture_id=violation.target_id,
            current_center=(0, 0),
            target_center=(-dx, -dy),
            offset_vector=(-dx, -dy),
            offset_direction="-X 方向",
            description=f"将 {target_label} 沿 X 轴负方向平移 {dx:.0f}mm",
        ))

        # 物料：防滑脚垫
        materials.append(MaterialItem(
            name="防滑脚垫_套",
            unit="套",
            quantity=4,
            unit_price=MATERIAL_PRICE_LIB["防滑脚垫_套"],
            total_price=4 * MATERIAL_PRICE_LIB["防滑脚垫_套"],
            source="建材市场/京东",
        ))
        cost_breakdown["物料"] = 4 * MATERIAL_PRICE_LIB["防滑脚垫_套"]

    # === 适老家具更换 ===
    if risk_level == "T0":
        # 高风险：建议更换适老家具
        if "沙发" in source_label or "沙发" in target_label:
            materials.append(MaterialItem(
                name="适老沙发_张",
                unit="张",
                quantity=1,
                unit_price=MATERIAL_PRICE_LIB["适老沙发_张"],
                total_price=MATERIAL_PRICE_LIB["适老沙发_张"],
                source="适老家具专卖店",
            ))
            cost_breakdown["适老家具"] = MATERIAL_PRICE_LIB["适老沙发_张"]

        if "床" in source_label or "床" in target_label:
            materials.append(MaterialItem(
                name="护理床_张",
                unit="张",
                quantity=1,
                unit_price=MATERIAL_PRICE_LIB["护理床_张"],
                total_price=MATERIAL_PRICE_LIB["护理床_张"],
                source="医疗器械专卖店",
            ))
            cost_breakdown["适老家具"] = MATERIAL_PRICE_LIB["护理床_张"]

        # 安全设施
        materials.append(MaterialItem(
            name="紧急呼叫器_套",
            unit="套",
            quantity=2,
            unit_price=MATERIAL_PRICE_LIB["紧急呼叫器_套"],
            total_price=2 * MATERIAL_PRICE_LIB["紧急呼叫器_套"],
            source="安防器材店",
        ))
        cost_breakdown["安全设施"] = 2 * MATERIAL_PRICE_LIB["紧急呼叫器_套"]

        # 工程措施
        engineering.append("拆除阻碍通行的固定家具")
        engineering.append("重新规划空间布局")

    # === 墙面防撞 ===
    materials.append(MaterialItem(
        name="墙面护角_套",
        unit="套",
        quantity=4,
        unit_price=MATERIAL_PRICE_LIB["墙面护角_套"],
        total_price=4 * MATERIAL_PRICE_LIB["墙面护角_套"],
        source="建材市场",
    ))
    cost_breakdown["防撞设施"] = cost_breakdown.get("防撞设施", 0) + 4 * MATERIAL_PRICE_LIB["墙面护角_套"]

    # === 工程量计算 ===
    if violation.actual_clearance_mm < 200:
        # 极端情况：需要较大工程
        engineering.append("局部墙体改造（需物业/开发商审批）")
        cost_breakdown["工程"] = cost_breakdown.get("工程", 0) + 5000
        days = 15
        difficulty = "高"
    elif violation.actual_clearance_mm < 500:
        # 中等情况
        engineering.append("家具重新布局调整")
        cost_breakdown["工程"] = cost_breakdown.get("工程", 0) + 800
        days = 5
        difficulty = "中"
    else:
        # 轻微调整
        engineering.append("小幅位置调整即可")
        cost_breakdown["工程"] = cost_breakdown.get("工程", 0) + 200
        days = 2
        difficulty = "低"

    # 计算总费用
    materials_cost = sum(m.total_price for m in materials)
    engineering_cost = cost_breakdown.get("工程", 0)
    total_cost = materials_cost + engineering_cost

    return RenovationPlan(
        plan_id=plan_id,
        plan_type="optimal",
        risk_level=risk_level,
        violation_id=f"{violation.source_id}↔{violation.target_id}",
        title=f"【最优方案】{source_label}与{target_label}通道优化",
        description=f"实测净距{current_clearance:.0f}mm，规范要求{clearance_required:.0f}mm，短缺{shortage:.0f}mm",
        position_adjustments=position_adjustments,
        materials=materials,
        engineering_measures=engineering,
        estimated_cost=total_cost,
        cost_breakdown=cost_breakdown,
        implementation_days=days,
        difficulty_level=difficulty,
    )


# ════════════════════════════════════════════════════════════════════════════════
# 备选方案生成函数 (Alternative Plan)
# ════════════════════════════════════════════════════════════════════════════════

def generate_alternative_plan(
    violation: ViolationRecord,
    furniture_labels: dict[str, str],
    clearance_required: float,
) -> RenovationPlan:
    """生成备选改造方案 — 以极低成本+现有格局为前提。

    特点：
    - 轻资产改良
    - 不改变空间结构
    - 快速实施

    Args:
        violation: 违规记录
        furniture_labels: 家具ID到标签的映射
        clearance_required: 规范要求的净距

    Returns:
        备选改造方案
    """
    plan_id = f"ALT_{violation.violation_type}_{violation.source_id[:8]}"
    risk_level = classify_risk(violation)

    source_label = furniture_labels.get(violation.source_id, violation.source_id)
    target_label = furniture_labels.get(violation.target_id, violation.target_id)

    materials: list[MaterialItem] = []
    engineering: list[str] = []
    position_adjustments: list[PositionAdjustment] = []
    cost_breakdown: dict[str, float] = {}

    current_clearance = violation.actual_clearance_mm
    shortage = violation.shortage_mm

    # === 最小化位置调整 ===
    if violation.violation_type in ("wheelchair_passage", "bed_side_clearance"):
        # 只移动较轻的家具，位移量最小化
        min_offset = min(shortage, 150)  # 最多移动150mm

        # 假设源家具是可移动的
        dx = min_offset
        dy = 0.0

        position_adjustments.append(PositionAdjustment(
            furniture_id=violation.source_id,
            current_center=(0, 0),
            target_center=(dx, dy),
            offset_vector=(dx, dy),
            offset_direction="+X 方向" if dx > 0 else "-X 方向",
            description=f"将 {source_label} 沿 X 轴正方向平移 {dx:.0f}mm（最小化调整）",
        ))

        # 物料：定位垫
        materials.append(MaterialItem(
            name="家具定位垫_个",
            unit="个",
            quantity=4,
            unit_price=MATERIAL_PRICE_LIB["家具定位垫_个"],
            total_price=4 * MATERIAL_PRICE_LIB["家具定位垫_个"],
            source="淘宝/拼多多",
        ))
        cost_breakdown["物料"] = 4 * MATERIAL_PRICE_LIB["家具定位垫_个"]

    # === 贴附式防护 ===
    # L型防撞条
    materials.append(MaterialItem(
        name="L型防撞条_米",
        unit="米",
        quantity=3,
        unit_price=MATERIAL_PRICE_LIB["L型防撞条_米"],
        total_price=3 * MATERIAL_PRICE_LIB["L型防撞条_米"],
        source="淘宝/京东",
    ))
    cost_breakdown["防撞设施"] = 3 * MATERIAL_PRICE_LIB["L型防撞条_米"]

    # 圆形防撞贴
    materials.append(MaterialItem(
        name="圆形防撞贴_个",
        unit="个",
        quantity=20,
        unit_price=MATERIAL_PRICE_LIB["圆形防撞贴_个"],
        total_price=20 * MATERIAL_PRICE_LIB["圆形防撞贴_个"],
        source="淘宝",
    ))
    cost_breakdown["防撞设施"] = cost_breakdown.get("防撞设施", 0) + 20 * MATERIAL_PRICE_LIB["圆形防撞贴_个"]

    # === 安全提示 ===
    if risk_level in ("T0", "T1"):
        materials.append(MaterialItem(
            name="感应夜灯_个",
            unit="个",
            quantity=2,
            unit_price=MATERIAL_PRICE_LIB["感应夜灯_个"],
            total_price=2 * MATERIAL_PRICE_LIB["感应夜灯_个"],
            source="小米/飞利浦",
        ))
        cost_breakdown["照明改造"] = 2 * MATERIAL_PRICE_LIB["感应夜灯_个"]

    # === T0/T1 增强措施 ===
    if risk_level == "T0":
        materials.append(MaterialItem(
            name="折叠淋浴椅_把",
            unit="把",
            quantity=1,
            unit_price=MATERIAL_PRICE_LIB["折叠淋浴椅_把"],
            total_price=MATERIAL_PRICE_LIB["折叠淋浴椅_把"],
            source="医疗器械店",
        ))
        cost_breakdown["安全设施"] = MATERIAL_PRICE_LIB["折叠淋浴椅_把"]

        materials.append(MaterialItem(
            name="浴室防滑垫_套",
            unit="套",
            quantity=1,
            unit_price=MATERIAL_PRICE_LIB["浴室防滑垫_套"],
            total_price=MATERIAL_PRICE_LIB["浴室防滑垫_套"],
            source="超市/淘宝",
        ))
        cost_breakdown["安全设施"] = cost_breakdown.get("安全设施", 0) + MATERIAL_PRICE_LIB["浴室防滑垫_套"]

        engineering.append("警示标识张贴（高风险区域）")
        engineering.append("定期巡检机制建立")

    # === 工程措施 ===
    engineering.append("粘贴防撞条（DIY可完成）")
    engineering.append("家具位置微调")
    cost_breakdown["人工"] = 300  # 简单人工费
    days = 1
    difficulty = "低"

    # 计算总费用
    materials_cost = sum(m.total_price for m in materials)
    labor_cost = cost_breakdown.get("人工", 0)
    total_cost = materials_cost + labor_cost

    return RenovationPlan(
        plan_id=plan_id,
        plan_type="alternative",
        risk_level=risk_level,
        violation_id=f"{violation.source_id}↔{violation.target_id}",
        title=f"【备选方案】{source_label}与{target_label}通道改良",
        description=f"实测净距{current_clearance:.0f}mm，规范要求{clearance_required:.0f}mm，短缺{shortage:.0f}mm",
        position_adjustments=position_adjustments,
        materials=materials,
        engineering_measures=engineering,
        estimated_cost=total_cost,
        cost_breakdown=cost_breakdown,
        implementation_days=days,
        difficulty_level=difficulty,
    )


# ════════════════════════════════════════════════════════════════════════════════
# YAML 输出格式化
# ════════════════════════════════════════════════════════════════════════════════

def plan_to_yaml(plan: RenovationPlan) -> str:
    """将改造方案转换为 YAML 格式。

    Args:
        plan: 改造方案

    Returns:
        YAML 格式字符串
    """
    data = {
        "plan_id": plan.plan_id,
        "plan_type": plan.plan_type,
        "risk_level": plan.risk_level,
        "violation_id": plan.violation_id,
        "title": plan.title,
        "description": plan.description,
        "position_adjustments": [
            {
                "furniture_id": adj.furniture_id,
                "current_center_mm": list(adj.current_center),
                "target_center_mm": list(adj.target_center),
                "offset_vector_mm": list(adj.offset_vector),
                "offset_direction": adj.offset_direction,
                "description": adj.description,
            }
            for adj in plan.position_adjustments
        ],
        "materials": [
            {
                "name": m.name,
                "unit": m.unit,
                "quantity": m.quantity,
                "unit_price_cny": m.unit_price,
                "total_price_cny": m.total_price,
                "source": m.source,
            }
            for m in plan.materials
        ],
        "engineering_measures": plan.engineering_measures,
        "estimated_cost_cny": plan.estimated_cost,
        "cost_breakdown": plan.cost_breakdown,
        "implementation": {
            "days": plan.implementation_days,
            "difficulty": plan.difficulty_level,
        },
    }

    return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def plans_to_yaml(
    optimal_plans: list[RenovationPlan],
    alternative_plans: list[RenovationPlan],
    summary: dict[str, Any],
) -> str:
    """将多套改造方案合并为完整 YAML 报告。

    Args:
        optimal_plans: 最优方案列表
        alternative_plans: 备选方案列表
        summary: 汇总信息

    Returns:
        完整 YAML 报告
    """
    data = {
        "report_metadata": {
            "generated_at": "ISO时间戳",
            "role": "适老化改造项目经理与造价师",
            "format_version": "1.0",
        },
        "executive_summary": summary,
        "optimal_plans": [
            yaml.safe_load(plan_to_yaml(p)) for p in optimal_plans
        ],
        "alternative_plans": [
            yaml.safe_load(plan_to_yaml(p)) for p in alternative_plans
        ],
        "total_optimal_cost_cny": sum(p.estimated_cost for p in optimal_plans),
        "total_alternative_cost_cny": sum(p.estimated_cost for p in alternative_plans),
        "recommendation": (
            "推荐最优方案以彻底消除安全隐患，"
            f"预算 {sum(p.estimated_cost for p in optimal_plans):.0f} 元；"
            "若预算有限，可先采用备选方案进行快速改良，"
            f"预算 {sum(p.estimated_cost for p in alternative_plans):.0f} 元。"
        ),
    }

    return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ════════════════════════════════════════════════════════════════════════════════
# Agent 4: 适老化改造项目经理与造价师
# ════════════════════════════════════════════════════════════════════════════════

AGENT_4_PROMPT = """【角色】适老化改造项目经理与造价师

【职责】接收合规审查报告，结合市场物料库，输出具有强可落地性的分级改造与成本核算方案。

【执行逻辑 — 思维链 (Chain-of-Thought)】

## 步骤1: 风险定级
按致死/致残概率对违规项进行分级：

| 等级 | 代码 | 响应时限 | 典型场景 |
|------|------|----------|----------|
| 严重 | T0 | 24小时 | 轮椅通道<450mm、物体重叠 |
| 中等 | T1 | 7天 | 轮椅通道450-700mm |
| 一般 | T2 | 30天 | 轻微净距不足 |

## 步骤2: 最优方案 (Optimal)
目标：彻底消除隐患

特点：
- 重资产投入
- 可能涉及空间结构改造
- 追求最佳适老化效果

典型措施：
- 更换适老家具（护理床、适老沙发）
- 大型工程（墙体改造、门宽扩大）
- 全屋定制适老家具

## 步骤3: 备选方案 (Alternative)
目标：极低成本+现有格局

特点：
- 轻资产改良
- 不改变空间结构
- 快速实施（1-2天）

典型措施：
- L型防撞条粘贴
- 家具位置微调（<150mm）
- 定位垫+感应夜灯

【约束】
1. 每一项风险必须同时具备 Optimal 与 Alternative 两套方案
2. 空间位置调整必须输出明确的数学矢量偏移建议
   - 格式: offset_vector: [dx_mm, dy_mm]
   - 方向: +X/-X/+Y/-Y
3. 强制输出 YAML 格式结构体

【市场物料价格库 (参考)】
- 防滑脚垫_套: 58元
- L型防撞条_米: 45元
- 圆形防撞贴_个: 12元
- 适老沙发_张: 8500元
- 护理床_张: 12800元
- 紧急呼叫器_套: 420元
- 感应夜灯_个: 128元
- 非承重墙拆除_平方米: 380元
- 全屋定制适老家具_套: 58000元

【输出格式 — YAML 结构体】
{yaml_template}

【规范依据】
{CHINESE_REGULATION_SYSTEM_RULES}"""


YAML_TEMPLATE = """report_metadata:
  generated_at: ISO时间戳
  role: 适老化改造项目经理与造价师

executive_summary:
  total_violations: 3
  t0_count: 1
  t1_count: 1
  t2_count: 1
  optimal_total_cost_cny: 14280
  alternative_total_cost_cny: 860

optimal_plans:
  - plan_id: OPT_wheelchair_passage_sofa_1
    plan_type: optimal
    risk_level: T1
    violation_id: sofa_1↔coffee_table_1
    title: 【最优方案】沙发与茶几通道优化
    description: 实测净距450mm，规范要求900mm，短缺450mm
    position_adjustments:
      - furniture_id: sofa_1
        current_center_mm: [2500, 3500]
        target_center_mm: [2700, 3500]
        offset_vector_mm: [200, 0]
        offset_direction: +X 方向
        description: 将沙发沿X轴正方向平移200mm
      - furniture_id: coffee_table_1
        current_center_mm: [2500, 2800]
        target_center_mm: [2300, 2800]
        offset_vector_mm: [-200, 0]
        offset_direction: -X 方向
        description: 将茶几沿X轴负方向平移200mm
    materials:
      - name: 防滑脚垫_套
        unit: 套
        quantity: 4
        unit_price_cny: 58
        total_price_cny: 232
        source: 建材市场/京东
      - name: 适老沙发_张
        unit: 张
        quantity: 1
        unit_price_cny: 8500
        total_price_cny: 8500
        source: 适老家具专卖店
    engineering_measures:
      - 拆除阻碍通行的固定家具
      - 重新规划空间布局
    estimated_cost_cny: 8732
    cost_breakdown:
      物料: 232
      适老家具: 8500
      工程: 1000
    implementation:
      days: 10
      difficulty: 中

alternative_plans:
  - plan_id: ALT_wheelchair_passage_sofa_1
    plan_type: alternative
    risk_level: T1
    violation_id: sofa_1↔coffee_table_1
    title: 【备选方案】沙发与茶几通道改良
    description: 实测净距450mm，规范要求900mm，短缺450mm
    position_adjustments:
      - furniture_id: sofa_1
        current_center_mm: [2500, 3500]
        target_center_mm: [2600, 3500]
        offset_vector_mm: [100, 0]
        offset_direction: +X 方向
        description: 将沙发沿X轴正方向平移100mm（最小化调整）
    materials:
      - name: 家具定位垫_个
        unit: 个
        quantity: 4
        unit_price_cny: 25
        total_price_cny: 100
        source: 淘宝/拼多多
      - name: L型防撞条_米
        unit: 米
        quantity: 3
        unit_price_cny: 45
        total_price_cny: 135
        source: 淘宝/京东
      - name: 圆形防撞贴_个
        unit: 个
        quantity: 20
        unit_price_cny: 12
        total_price_cny: 240
        source: 淘宝
    engineering_measures:
      - 粘贴防撞条（DIY可完成）
      - 家具位置微调
    estimated_cost_cny: 475
    cost_breakdown:
      物料: 475
      人工: 0
    implementation:
      days: 1
      difficulty: 低

total_optimal_cost_cny: 8732
total_alternative_cost_cny: 475

recommendation: |
  推荐最优方案彻底消除安全隐患，预算8732元；
  若预算有限，可先采用备选方案快速改良，预算475元。
"""


def generate_renovation_report(
    violations: list[ViolationRecord],
    furniture_labels: dict[str, str],
) -> dict[str, Any]:
    """生成完整的适老化改造报告。

    Args:
        violations: 违规记录列表
        furniture_labels: 家具ID到标签的映射

    Returns:
        包含 YAML 和摘要的报告
    """
    optimal_plans: list[RenovationPlan] = []
    alternative_plans: list[RenovationPlan] = []

    # 统计
    t0_count = 0
    t1_count = 0
    t2_count = 0

    for violation in violations:
        risk_level = classify_risk(violation)

        if risk_level == "T0":
            t0_count += 1
        elif risk_level == "T1":
            t1_count += 1
        else:
            t2_count += 1

        # 生成两套方案
        clearance_required = CLEARANCE_STANDARDS.get(
            violation.violation_type,
            CLEARANCE_STANDARDS["wheelchair_passage"]
        ).value_mm

        optimal_plan = generate_optimal_plan(
            violation, furniture_labels, clearance_required
        )
        alternative_plan = generate_alternative_plan(
            violation, furniture_labels, clearance_required
        )

        optimal_plans.append(optimal_plan)
        alternative_plans.append(alternative_plan)

    # 生成汇总
    summary = {
        "total_violations": len(violations),
        "t0_count": t0_count,
        "t1_count": t1_count,
        "t2_count": t2_count,
        "optimal_total_cost_cny": sum(p.estimated_cost for p in optimal_plans),
        "alternative_total_cost_cny": sum(p.estimated_cost for p in alternative_plans),
    }

    # 生成 YAML
    yaml_report = plans_to_yaml(optimal_plans, alternative_plans, summary)

    return {
        "summary": summary,
        "optimal_plans": optimal_plans,
        "alternative_plans": alternative_plans,
        "yaml_report": yaml_report,
    }
