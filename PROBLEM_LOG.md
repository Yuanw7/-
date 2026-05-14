# 问题日志 (Problem Log)

## 问题 #0: 函数命名不一致 (2026-05-14) - 已解决

**日期**: 2026-05-14
**状态**: ✓ 已解决

### 问题描述
版本迭代中函数名称没有全局更新，`main.py` 导入的 `analyze_room_image` 和 `analyze_room_images` 在 `vision_engine.py` 中已重命名为 `agent_1_extract`。

### 根因分析
- Multi-Agent 架构重构时，将函数重命名为更具语义的名称
- 但 `main.py` 未同步更新导入语句
- `agents.py` 和 `api_server.py` 使用新名称，但 `main.py` 使用旧名称

### 涉及文件
- `vision_engine.py` - 添加兼容性别名
- `main.py` - 第55行导入语句（无需修改）
- `test_full_integration.py` - 更新文件列表

### 解决方案
在 `vision_engine.py` 末尾添加兼容性别名，保持向后兼容：

```python
def analyze_room_image(image_path: str, calibration_data: dict | None = None) -> GraphState:
    """【兼容性别名】Agent 1: 从图像提取 BBox"""
    return agent_1_extract(image_path, calibration_data)

def analyze_room_images(image_paths: list[str], calibration_data: dict | None = None) -> GraphState:
    """【兼容性别名】Agent 1: 多图提取（取第一张）"""
    if not image_paths:
        raise ValueError("image_paths 不能为空")
    return agent_1_extract(image_paths[0], calibration_data)
```

### 验证结果
- ✓ `test_main_api_endpoints`: GET /, GET /health, POST /analyze-room 全部通过
- ✓ 全局测试: 10/10 项通过

---

## 问题 #1: 导入 analyze_room_image 函数缺失

**日期**: 2026-05-14
**状态**: 待修复

### 问题描述
`main.py` 导入 `from vision_engine import analyze_room_image`，但 `vision_engine.py` 中不存在该函数。

### 根因分析
- `vision_engine.py` 中的函数名为 `agent_1_extract` 和 `agent_2_audit_single`
- `main.py` 期望使用旧的 `analyze_room_image` 接口

### 涉及文件
- `main.py` (第55行)
- `vision_engine.py`

### 解决方案
**方案A**: 在 `vision_engine.py` 添加别名函数
```python
def analyze_room_image(image_path: str, calibration_data: dict = None) -> dict:
    """兼容旧接口的别名函数"""
    return agent_1_extract(image_path, calibration_data)

def analyze_room_images(image_paths: list, calibration_data: dict = None) -> dict:
    """兼容旧接口的别名函数"""
    return agent_1_extract(image_paths[0], calibration_data)
```

**方案B**: 修改 `main.py` 使用新接口
```python
from vision_engine import agent_1_extract
```

---

## 问题 #2: Shapely 模块未安装

**日期**: 2026-05-14
**状态**: ✓ 已解决

### 问题描述
启动 `api_server.py` 时报错: `ModuleNotFoundError: No module named 'shapely'`

### 涉及文件
- `api_server.py`

### 解决方案
```bash
pip install shapely
```

### 验证
```bash
python -c "import shapely; print(shapely.__version__)"
# 输出: 2.1.2
```

---

## 问题 #3: main.py 导入缺少 sniffio 依赖

**日期**: 2026-05-14
**状态**: ✓ 已解决

### 问题描述
`test_main_api_endpoints` 报错: `cannot import name 'sniffio' from 'httpcore'`

### 涉及文件
- `main.py`

### 解决方案
```bash
pip install sniffio
```

---

## 问题 #4: ZhipuAI 模块未安装

**日期**: 2026-05-14
**状态**: ✓ 已解决

### 问题描述
模块导入测试失败: `ModuleNotFoundError: No module named 'zhipuai'`

### 涉及文件
- 多个需要智谱AI的文件

### 解决方案
```bash
pip install zhipuai
```

---

## 问题 #5: 碰撞阻力字段冗余

**日期**: 2026-05-14
**状态**: ✓ 已解决

### 问题描述
用户反馈交互界面不需要 `collision_resistance` 字段

### 涉及文件
- `renderer.py`

### 解决方案
移除 `collision_resistance` 字段:
1. 删除 `MATERIAL_COLLISION_RESISTANCE` 映射表
2. 从 `RenderObject` dataclass 中移除该属性
3. 从所有输出 JSON 中移除该字段

### 修改记录
```diff
# renderer.py
- collision_resistance: int  # 从 RenderObject 移除
- collision_resistance: 1,  # 从 furniture_output 移除
```

---

## 问题 #6: index.html 检查项不适用

**日期**: 2026-05-14
**状态**: ✓ 已解决

### 问题描述
`test_full_integration.py` 对 `index.html` 的检查项不适用（它不是 Fabric.js 页面）

### 涉及文件
- `test_full_integration.py`

### 解决方案
修改检查逻辑:
```python
# 之前
checks = {
    "DOCTYPE": "<!DOCTYPE html>" in content,
    "Fabric.js": "fabric.js" in content,
    "Canvas": '<canvas' in content,
}

# 之后
checks = {
    "HTML 有效": "<html" in content,
    "JavaScript": "<script" in content,
}
```

---

## 问题 #7: Fabric.js CDN 检查误报

**日期**: 2026-05-14
**状态**: ✓ 已解决

### 问题描述
Fabric.js 是前端 JS 库，不需要 `pip install`，但测试脚本错误地要求导入

### 涉及文件
- `test_full_integration.py`

### 解决方案
```python
# 移除 __import__("fabric") 检查
# 改为检查 CDN 链接
floorplan_html = Path("static/floorplan.html").read_text()
if "fabric" in floorplan_html and "cdnjs" in floorplan_html:
    ok("Fabric.js CDN 引用正确")
```

---

## 问题 #8: 原架构痛点 - 职责过载

**日期**: 2026-05-13
**状态**: ✓ 已解决

### 问题描述
`vision_engine.py` 包含旧版大杂烩提示词 + 新架构拆分提示词，逻辑冲突

### 涉及文件
- `vision_engine.py` (1183行)

### 解决方案
1. 删除 Legacy 代码 ~550行
2. 统一使用 `glm-4v` 模型
3. 精简至 ~600行

---

## 问题 #9: 原架构痛点 - 并发性能

**日期**: 2026-05-13
**状态**: ✓ 部分解决

### 问题描述
`agent_2_batch_audit` 顺序执行，处理 5-10 件家具时可能长达数分钟

### 涉及文件
- `vision_engine.py`

### 解决方案
使用 `ThreadPoolExecutor` 实现并发:
```python
with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(items), 8)) as executor:
    futures = {executor.submit(_worker, args): i for i, args in enumerate(...)}
```

---

## 问题 #10: 原架构痛点 - 规范注入断层

**日期**: 2026-05-13
**状态**: ✓ 已解决

### 问题描述
导入了 `CHINESE_REGULATION_SYSTEM_RULES` 但未有效整合

### 涉及文件
- `vision_engine.py`

### 解决方案
```python
prompt = AGENT_2_PROMPT.format(
    regulation_rules=CHINESE_REGULATION_SYSTEM_RULES
)
```
