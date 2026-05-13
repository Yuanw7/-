# 架构重构日志 (Architecture Changelog)

## 重构日期: 2026-05-13

---

## 一、重构背景

### 1.1 目标
将适老化多代理协同系统从**单体架构 (Legacy)** 重构为**多智能体协作架构 (Multi-Agent)**，满足以下核心约束：

| 约束 | 说明 |
|------|------|
| **禁止落盘缓存** | 废弃本地文件传递上下文，全面改用 LangGraph 内存级 TypedDict 流转 |
| **二次剪裁 (Pass 2)** | Agent 1 提取 BBox 后，必须在后端对原图执行 Crop 操作，并发传入 Agent 2 |
| **坐标系锁定** | 所有空间定位必须基于物件【几何中心点】(x, y)，单位强制毫米 (mm) |

### 1.2 原架构痛点

1. **职责过载**: `vision_engine.py` 包含旧版大杂烩提示词 + 新架构拆分提示词
2. **逻辑冲突**: 旧提示词禁止使用"x坐标"，但新架构核心恰恰是输出坐标
3. **并发性能**: `agent_2_batch_audit` 顺序执行，处理 5-10 件家具时可能长达数分钟
4. **规范注入断层**: 导入了 `CHINESE_REGULATION_SYSTEM_RULES` 但未有效整合

---

## 二、文件变更清单

### 2.1 新增文件

| 文件 | 用途 |
|------|------|
| `agents.py` | LangGraph StateGraph 多代理协同逻辑 |
| `image_processor.py` | 二次剪裁 (Pass 2) + 坐标转换工具 |
| `models.py` (更新) | 新增 TypedDict State 结构 + `FurnitureNode` |

### 2.2 重构文件

| 文件 | 变更内容 |
|------|----------|
| `vision_engine.py` | 从 1183 行精简至 ~600 行，删除所有 Legacy 代码 |

---

## 三、models.py 变更

### 3.1 新增 TypedDict 结构

```python
class FurnitureNode(TypedDict):
    """单个家具节点 — 几何中心点坐标系，单位毫米"""
    id: str
    label: str  # 中文名称，如"沙发"
    center: tuple[float, float]  # [x_mm, y_mm] 几何中心点
    elevation_mm: float  # 离地高度（毫米），地板物体填 0
    size: tuple[float, float, float]  # [width, depth, height] 单位 mm
    rotation: float  # 旋转角度（度）
    bbox: tuple[int, int, int, int]  # [left, top, right, bottom] 像素
    material: str  # 主要材质
    friction_level: Literal["high", "medium", "low"]  # 表面摩擦程度
    is_obstacle: bool  # 是否阻断主要通道 (Agent 2 判断)
    pass_2_audit: str  # Agent 2 填写: 合规审查结果

class GraphState(TypedDict):
    """LangGraph 全局记忆体 — 全程内存流转，禁止落盘"""
    session_id: str
    room_type: str
    furniture_list: list[FurnitureNode]
    boundary: RoomBoundaryInfo
    topology_matrix: dict
    final_report: str
    risk_level: Literal["high", "medium", "low", "unknown"]
    # ... 更多字段
```

### 3.2 保留的 Pydantic Models (向后兼容)

| 模型 | 说明 |
|------|------|
| `Dimensions` | 旧格式 (米)，保留用于 API 序列化 |
| `Position` | 旧格式 (米)，保留用于 API 序列化 |
| `FurnitureObject` | 旧格式，保留用于 API 序列化 |
| `RoomScene` | 旧格式，保留用于 API 序列化 |
| `RoomBlueprint` | 新格式 (毫米，几何中心点) |

### 3.3 新增工具函数

```python
def furniture_node_to_blueprint(node: FurnitureNode) -> BlueprintFurniture
def generate_furniture_id(label: str, index: int) -> str
def create_initial_state(session_id, room_type, image_paths) -> GraphState
```

---

## 四、vision_engine.py 重构详情

### 4.1 删除内容

| 删除项 | 原因 |
|--------|------|
| ~~`MODEL_VISION` (大写)~~ | 冗余，统一用小写 `glm-4v` |
| ~~`SYSTEM_PROMPT`~~ | 旧架构"老师傅说话"风格，干扰坐标输出 |
| ~~`SCENE_PROMPT`~~ | 同上 |
| ~~`SCENE_MULTI_PROMPT`~~ | 同上 |
| ~~`QUALITY_PROMPT`~~ | 已废弃 |
| ~~`QUALITY_MULTI_PROMPT`~~ | 已废弃 |
| ~~`analyze_room_image()`~~ | 旧架构入口函数 |
| ~~`analyze_room_images()`~~ | 旧架构入口函数 |
| ~~`_normalize_room_scene_payload()`~~ | 仅服务于旧架构 |
| ~~`_call_glm_vision()`~~ | 重命名为 `_call_vision()` |
| ~~`_call_glm_vision_multi()`~~ | 多图逻辑已移除 |

**删除代码量**: ~550 行

### 4.2 新增内容

#### 4.2.1 Agent 1: 空间拓扑提取器

**Prompt 核心约束**:
```
- 原点 (0,0) = 房间左下角
- X轴正向 = 向右, Y轴正向 = 向上
- 所有尺寸单位 = 毫米 (mm)
- 位置 = 物体【几何中心点】坐标
- 只提取精确几何数据，不判断障碍物
- 关注: 表面材质类型、预估摩擦系数 (friction_level)
```

**输出字段**:
```json
{
  "center": [x, y],
  "elevation_mm": 离地高度,
  "size": [width, depth, height],
  "bbox": [left, top, right, bottom],
  "material": "布艺/木质/金属",
  "friction_level": "high/medium/low"
}
```

#### 4.2.2 Agent 2: 合规审计员

**Prompt 核心增强**:

| 评估维度 | 说明 |
|----------|------|
| **几何边缘审计** | R角是否 ≥10mm，尖锐突出物 |
| **材质安全性** | 阻燃性、摩擦系数、易碎/锋利材料 |
| **起坐高度** | 座面高度 400-500mm (针对座椅类) |
| **结构稳固性** | 支撑基面、抗倾翻能力 |

**法规动态注入**:
```python
prompt = AGENT_2_PROMPT.format(
    regulation_rules=CHINESE_REGULATION_SYSTEM_RULES  # 直接注入法规库
)
```

#### 4.2.3 并发批处理

```python
def agent_2_audit_batch(
    crop_images_b64: list[str],
    furniture_nodes: list[FurnitureNode],
) -> list[dict[str, Any]]:
    """使用 ThreadPoolExecutor 实现真正的并发 API 调用"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(items), 8)) as executor:
        futures = {executor.submit(_worker, args): i for i, args in enumerate(...)}
        for future in concurrent.futures.as_completed(futures):
            results[idx] = future.result()
```

---

## 五、agents.py 新增内容

### 5.1 代理分工

| 代理 | 职责 |
|------|------|
| **Agent 1** (VisionExtractor) | 从图像提取 BBox、尺寸、位置 |
| **Agent 2** (ComplianceAuditor) | 对裁剪局部图进行材质/安全合规分析 |
| **Agent 3** (ReportGenerator) | 综合拓扑与合规结果生成报告 |

### 5.2 数据流

```
┌─────────┐    ┌─────────┐    ┌─────────┐
│  START  │───▶│ Agent 1 │───▶│  Crop   │
└─────────┘    └─────────┘    └────┬────┘
                                   │
                                   ▼
                              ┌─────────┐    ┌─────────┐
                              │ Agent 2 │───▶│Topology │
                              └────┬────┘    └────┬────┘
                                   │              │
                                   ▼              ▼
                              ┌─────────┐    ┌─────────┐
                              │ Agent 3 │◀───│ END     │
                              └────┬────┘    └─────────┘
                                   │
                                   ▼
                                报告输出
```

### 5.3 拓扑计算

```python
def calculate_topology(state: GraphState) -> GraphState:
    """基于几何中心点坐标计算边缘净距"""
    # dx = |cx_b - cx_a| - half_w_a - half_w_b
    # dy = |cy_b - cy_a| - half_d_a - half_d_b
    # clearance = max(0, min(dx, dy))
```

---

## 六、image_processor.py 新增内容

### 6.1 数据结构

```python
@dataclass
class CropRegion:
    furniture_id: str
    pixel_bbox: tuple[int, int, int, int]
    center_mm: tuple[float, float]
    size_mm: tuple[float, float, float]
    margin_px: int = 20  # 裁剪边距

@dataclass
class CropResult:
    furniture_id: str
    image_base64: str  # 裁剪图 Base64
    center_mm: tuple[float, float]
    size_mm: tuple[float, float, float]
```

### 6.2 核心函数

| 函数 | 说明 |
|------|------|
| `crop_image_by_bbox()` | 根据 BBox 裁剪图像 |
| `crop_to_base64()` | 裁剪并返回 Base64 |
| `crop_batch()` | 批量裁剪，为 Agent 2 并发分析准备 |
| `bbox_to_center_size_mm()` | 像素 BBox → 毫米坐标转换 |

---

## 七、坐标系规范

### 7.1 定义

```
        Y (mm)
         ↑
         │
    ┌────┼────┐
    │    │    │    ● ← 几何中心点 (center_x, center_y)
    │    │    │
    │    │    │
    └────┼────┼─────────→ X (mm)
         │
         └─ 原点 (0, 0) 左下角
```

### 7.2 单位统一

| 类型 | 单位 | 格式 |
|------|------|------|
| 位置坐标 | 毫米 (mm) | `center: tuple[float, float]` |
| 尺寸 | 毫米 (mm) | `size: tuple[float, float, float]` |
| 离地高度 | 毫米 (mm) | `elevation_mm: float` |
| 边缘净距 | 毫米 (mm) | `clearance_mm: float` |
| 像素边界 | 像素 (px) | `bbox: tuple[int, int, int, int]` |

---

## 八、待后续细节调整 (TODO)

| 模块 | TODO 项 | 优先级 |
|------|---------|--------|
| `agents.py` | Agent 1/2/3 内部 VLM 调用逻辑 | P0 |
| `agents.py` | Agent 2 真正的 asyncio 并发优化 | P1 |
| `image_processor.py` | 精确比例尺计算 (pixel_to_mm_ratio) | P1 |
| `image_processor.py` | 图像预处理 (EXIF/亮度均衡) | P2 |
| `vision_engine.py` | 完善 elevation_mm 传递 | P1 |

---

## 九、文件行数对比

| 文件 | 重构前 | 重构后 | 变更 |
|------|--------|--------|------|
| `vision_engine.py` | 1183 行 | ~600 行 | -583 行 |
| `models.py` | ~140 行 | ~280 行 | +140 行 |
| `agents.py` | 0 行 | ~330 行 | +330 行 |
| `image_processor.py` | 0 行 | ~280 行 | +280 行 |

**总计净变更**: +167 行（同时删除了 Legacy 代码并提升了功能）

---

## 十、使用示例 (重构后)

```python
# 方式 1: 使用 LangGraph (推荐)
from agents import run_compliance_analysis

result = run_compliance_analysis(
    image_paths=["/path/to/room.jpg"],
    room_type="客厅",
    calibration={"ref_object": "门", "ref_size_mm": 900},
)
print(result["final_report"])
print(result["risk_level"])

# 方式 2: 单独使用 Agent 1
from vision_engine import agent_1_extract

state = agent_1_extract(
    "/path/to/room.jpg",
    calibration_data={"ref_object": "门", "ref_size_mm": 900}
)
for node in state["furniture_list"]:
    print(f"{node['label']}: 中心点 {node['center']}mm")

# 方式 3: 图像裁剪
from image_processor import crop_batch, CropRegion

regions = [CropRegion(
    furniture_id="sofa_1",
    pixel_bbox=(100, 200, 400, 500),
    center_mm=(2500, 3500),
    size_mm=(1800, 850, 900),
)]
result = crop_batch("/path/to/room.jpg", regions)
```

---

## 十一、Agent 2 思维链模式增强 (2026-05-13 v1.1)

### 11.1 增强内容

**角色升级**: 适老化产品工业设计师与质检员

**执行逻辑 (Chain-of-Thought)**:

| 步骤 | 任务 | 关键指标 |
|------|------|----------|
| **步骤1: 材质预估** | 识别表面材质 | 摩擦系数、反光率、二次风险 |
| **步骤2: 几何测算** | 边缘特征分析 | R角半径、突出物检测 |
| **步骤3: 人机工学** | 座椅/床评估 | 座面高度、扶手支撑性 |

### 11.2 材质类型识别

| 材质 | 摩擦系数 | 反光率 | 二次风险 |
|------|----------|--------|----------|
| 高光瓷砖 | low | high | 湿滑风险高 |
| 哑光木皮 | medium | low | 低 |
| 皮革 | low | medium | 液体渗透后极滑 |
| 布艺/织物 | high | low | 可能积灰 |
| 玻璃 | low | high | 误导视弱老人深度判断 |

### 11.3 极其挑剔原则

1. 若无法确认是否倒角，默认判定为"存在锐角风险"
2. 玻璃/高光材质必须标注"反光误导风险"
3. 低于 400mm 的座椅高度直接判定为"高危"
4. 所有判断必须基于图像证据，无证据则标注"无法确认-存疑"

### 11.4 输出格式升级

```json
{
  "furniture_id": "sofa_1",
  "micro_features": {
    "material_analysis": {
      "primary_material": "皮革",
      "friction_coefficient": "low",
      "gloss_level": "medium",
      "secondary_risks": ["液体渗透后极滑"],
      "evidence_description": "表面光滑，有皮革纹理"
    },
    "geometry_analysis": {
      "corner_type": "安全倒角",
      "r_corner_radius_mm": 15,
      "sharp_protrusions": [],
      "edge_condition": "边缘圆润",
      "reference_calibration": "基于插座86mm估算"
    },
    "ergonomics_analysis": {
      "seat_height_mm": 450,
      "seat_height_compliant": true,
      "armrest_present": true,
      "armrest_height_mm": 680,
      "lumbar_support": "有",
      "sitting_stability": "稳定"
    }
  },
  "physical_risk_points": [...],
  "summary": "[sofa_1] - [皮革/低摩擦] - [安全倒角R15] - [液体滑倒风险]",
  "confidence": "high"
}
```

---

## 十二、变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-05-13 | v1.0 | 初始架构重构完成 |
| 2026-05-13 | v1.1 | Agent 2 思维链模式增强：微观特征提取 |

---

*本文件由 AI Agent 自动生成，记录架构重构详细信息*
