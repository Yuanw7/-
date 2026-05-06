# 老年人房屋改造智能分析系统 - 系统规范

## 1. 项目概述

### 1.1 项目名称
**ElderCare Home Transform** - 老年人房屋改造智能分析系统

### 1.2 核心功能
通过上传房间照片，AI 自动识别空间布局，生成符合老年人安全标准的2D/3D模型，并根据内置规范数据库提供针对性的改造建议。

### 1.3 目标用户
- 60岁以上老年人及其家属
- 养老护理人员
- 家庭装修设计师
- 社区养老服务工作者

---

## 2. 设计语言

### 2.1 视觉方向
采用 **温暖、专业、可信赖** 的设计风格：
- 柔和的暖色调为主，减少视觉刺激
- 大字体、高对比度，方便老年人阅读
- 清晰的图标和操作引导
- 卡片式布局，信息分区明确

### 2.2 色彩方案
```
主色调 (Primary):     #2D7D9A (深青色 - 专业、沉稳)
次要色 (Secondary):   #5BA88F (暖绿色 - 安全、健康)
强调色 (Accent):      #E8A849 (暖橙色 - 温暖、活力)
背景色 (Background):  #F8F6F3 (米白色 - 柔和、舒适)
卡片背景:             #FFFFFF (纯白)
文字主色:             #2C3E50 (深灰蓝)
文字次要:             #7F8C8D (中灰)
危险/警告:            #E74C3C (红色)
安全/通过:            #27AE60 (绿色)
提示/注意:            #F39C12 (黄色)
```

### 2.3 字体规范
```
标题字体: "Noto Sans SC", system-ui, sans-serif (700 weight)
正文字体: "Noto Sans SC", system-ui, sans-serif (400/500 weight)
数据字体: "JetBrains Mono", monospace
```

### 2.4 间距系统
```
基础单位: 8px
小间距:   8px / 16px
中间距:   24px / 32px
大间距:   48px / 64px
卡片圆角: 16px
按钮圆角: 12px
```

---

## 3. 核心功能模块

### 3.1 规范数据库模块

#### 3.1.1 国家标准规范
```typescript
interface Regulation {
  id: string;
  category: '无障碍' | '安全防护' | '空间尺寸' | '设备安装' | '照明电气';
  code: string;           // 规范编号
  title: string;          // 规范标题
  description: string;    // 规范描述
  requirement: string;   // 具体要求
  minValue?: number;      // 最小值要求
  maxValue?: number;      // 最大值要求
  unit?: string;          // 单位
  priority: '必须' | '建议' | '可选';
  relatedItems: string[]; // 相关改造项目
}
```

#### 3.1.2 规范列表
1. **无障碍通道**
   - 轮椅通道宽度 ≥ 900mm
   - 门口净宽度 ≥ 800mm
   - 走廊净空高度 ≥ 2000mm

2. **卫生间安全**
   - 马桶两侧扶手高度 650-750mm
   - 淋浴区防滑等级 R10 以上
   - 浴缸/淋浴凳高度 420-480mm

3. **厨房安全**
   - 操作台高度 800-850mm
   - 开关/插座高度 900-1200mm
   - 燃气灶需配熄火保护

4. **卧室安全**
   - 床高度 450-500mm
   - 床边通道宽度 ≥ 600mm
   - 紧急呼叫装置距离床 ≤ 300mm

5. **照明要求**
   - 走廊夜间照明照度 ≥ 50lx
   - 卧室照明照度 ≥ 100lx
   - 卫生间照明照度 ≥ 150lx

### 3.2 视觉识别系统

#### 3.2.1 房间元素识别
```typescript
interface DetectedElement {
  type: 'door' | 'window' | 'furniture' | 'hazard' | 'barrier' | 'lighting';
  boundingBox: BoundingBox;
  confidence: number;      // 0-1 置信度
  properties: {
    width?: number;        // 估算宽度 (mm)
    height?: number;       // 估算高度 (mm)
    position?: 'left' | 'center' | 'right' | 'corner';
    condition?: 'good' | 'fair' | 'poor';
    riskLevel?: 'low' | 'medium' | 'high';
  };
}

interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}
```

#### 3.2.2 识别的元素类型
- **门**: 单开门、双开门、推拉门、折叠门
- **窗**: 平开窗、推拉窗、飘窗
- **家具**: 床、沙发、餐桌、椅子、茶几、衣柜、橱柜
- **危险源**: 地毯边缘、电线裸露、湿滑地面、杂物堆放
- **障碍物**: 门槛、台阶、高差、狭窄通道
- **照明设备**: 吸顶灯、壁灯、落地灯、夜灯

### 3.3 建模系统

#### 3.3.1 2D 模型
- 俯视图网格显示
- 元素符号标注
- 尺寸标注（估算值）
- 危险区域高亮
- 改造建议可视化

#### 3.3.2 3D 模型
- WebGL 3D 可视化
- 热点标注
- 交互式查看
- 改造前后对比

#### 3.3.3 数据结构
```typescript
interface RoomModel {
  id: string;
  type: '2d' | '3d';
  dimensions: {
    width: number;   // mm
    length: number;  // mm
    height: number;  // mm
  };
  elements: RoomElement[];
  hazards: HazardZone[];
  analysis: AnalysisResult;
}

interface RoomElement {
  id: string;
  type: string;
  position: { x: number; y: number; z: number };
  dimensions: { width: number; depth: number; height: number };
  rotation: number;
  detectedFrom: string;  // 对应 DetectedElement.id
}
```

### 3.4 改造建议引擎

#### 3.4.1 建议类型
```typescript
interface ModificationSuggestion {
  id: string;
  category: '无障碍改造' | '安全加固' | '空间优化' | '设备升级' | '照明改善';
  title: string;
  description: string;
  priority: '紧急' | '重要' | '一般';
  relatedRegulation: string[];  // 关联的规范 ID
  estimatedCost: {
    min: number;
    max: number;
    currency: 'CNY';
  };
  difficulty: '简单' | '中等' | '复杂';
  steps: string[];
  materials?: string[];
  warnings?: string[];
  beforeAfter?: {
    before: string;   // 描述
    after: string;    // 描述
  };
}
```

#### 3.4.2 改造建议库
1. **紧急类**
   - 安装卫生间扶手
   - 移除地毯/地垫
   - 加装夜间照明
   - 消除门槛高差

2. **重要类**
   - 加宽通道门
   - 防滑地面处理
   - 安装紧急呼叫系统
   - 调整家具高度

3. **一般类**
   - 优化储物空间
   - 改善自然采光
   - 色彩对比优化
   - 简化家具布局

---

## 4. 页面结构

### 4.1 页面流程
```
首页 → 房间上传 → AI识别分析 → 2D/3D建模 → 改造建议报告
```

### 4.2 页面详情

#### 4.2.1 首页 (HomePage)
- 系统介绍
- 规范数据库入口
- 上传入口
- 项目案例展示

#### 4.2.2 房间上传页 (UploadPage)
- 拖拽上传区域
- 相机拍照入口
- 历史记录
- 房间类型选择（客厅/卧室/厨房/卫生间/走廊/阳台）

#### 4.2.3 分析页面 (AnalysisPage)
- 原始图片展示
- AI 识别进度
- 检测到的元素列表
- 识别置信度显示

#### 4.2.4 建模页面 (ModelingPage)
- 2D 俯视图
- 3D 可视化
- 尺寸标注
- 元素标注
- 危险区域标记

#### 4.2.5 报告页面 (ReportPage)
- 综合评分
- 问题清单
- 改造建议（分类展示）
- 规范依据
- 费用估算
- 导出功能（PDF）

---

## 5. 组件清单

### 5.1 导航组件
- **Navbar**: 顶部导航栏，品牌标识，菜单
- **StepIndicator**: 流程步骤指示器

### 5.2 上传组件
- **UploadZone**: 拖拽上传区
- **CameraCapture**: 相机拍照
- **RoomTypeSelector**: 房间类型选择器

### 5.3 分析组件
- **DetectionOverlay**: 检测结果叠加层
- **ConfidenceMeter**: 置信度仪表
- **ElementCard**: 检测元素卡片

### 5.4 建模组件
- **FloorPlan2D**: 2D 平面图
- **RoomViewer3D**: 3D 房间查看器
- **DimensionMarker**: 尺寸标注
- **HazardMarker**: 危险标记

### 5.5 报告组件
- **ScoreGauge**: 综合评分仪表
- **IssueList**: 问题列表
- **SuggestionCard**: 建议卡片
- **RegulationLink**: 规范引用链接
- **CostEstimate**: 费用估算

---

## 6. 技术架构

### 6.1 前端技术栈
```
框架:     React 18 + TypeScript
构建:     Vite
样式:     Tailwind CSS
3D渲染:   Three.js + React Three Fiber
图表:     Recharts
图标:     Lucide React
状态管理: Zustand
```

### 6.2 项目结构
```
elder-care-home/
├── public/
│   └── models/              # 3D 模型资源
├── src/
│   ├── assets/              # 静态资源
│   ├── components/
│   │   ├── layout/          # 布局组件
│   │   ├── upload/          # 上传相关
│   │   ├── analysis/        # 分析相关
│   │   ├── modeling/        # 建模相关
│   │   ├── report/          # 报告相关
│   │   └── ui/              # 通用 UI
│   ├── data/
│   │   ├── regulations.ts   # 规范数据库
│   │   ├── suggestions.ts   # 改造建议库
│   │   └── safety.ts        # 安全标准
│   ├── hooks/               # 自定义 hooks
│   ├── services/            # 服务层 (AI 识别接口)
│   ├── types/                # TypeScript 类型
│   ├── utils/                # 工具函数
│   └── pages/                # 页面组件
├── index.html
├── package.json
└── vite.config.ts
```

---

## 7. 响应式策略

### 7.1 断点
```
移动端: < 640px
平板:   640px - 1024px
桌面:   > 1024px
```

### 7.2 适配要求
- 移动端优先设计
- 触摸友好的交互
- 大字体选项（可访问性）
- 简化移动端 3D 视图

---

## 8. 可访问性 (A11Y)

- WCAG 2.1 AA 标准
- 色彩对比度 ≥ 4.5:1
- 支持键盘导航
- 屏幕阅读器友好
- 字体可缩放 150%
