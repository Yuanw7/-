// 规范相关类型
export interface Regulation {
  id: string;
  category: '无障碍' | '安全防护' | '空间尺寸' | '设备安装' | '照明电气';
  code: string;
  title: string;
  description: string;
  requirement: string;
  minValue?: number;
  maxValue?: number;
  unit?: string;
  priority: '必须' | '建议' | '可选';
  relatedItems: string[];
}

// 上传的图片类型
export interface UploadedImage {
  file: File;
  preview: string;
  name: string;
}

// 房间分析结果类型
export interface AnalysisResult {
  roomType: 'living_room' | 'bedroom' | 'kitchen' | 'bathroom' | 'corridor' | 'balcony' | 'unknown';
  dimensions: {
    width: number;
    length: number;
    height: number;
  };
  elements: DetectedElement[];
  hazards: HazardZone[];
  lightingLevel: 'poor' | 'fair' | 'good';
  floorCondition: 'slippery' | 'good' | 'uneven';
  overallScore: number;
  additionalObservations?: string[];
}

// 检测到的元素
export interface DetectedElement {
  id: string;
  type: 'door' | 'window' | 'furniture' | 'hazard' | 'barrier' | 'toilet' | 'kitchen_counter' | 'bed' | 'lighting' | 'floor' | 'wall';
  boundingBox: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  confidence: number;
  properties: {
    width?: number;
    height?: number;
    position?: 'left' | 'center' | 'right' | 'corner';
    condition?: 'good' | 'fair' | 'poor';
    riskLevel?: 'low' | 'medium' | 'high';
    color?: string;
    material?: string;
    hasGrabBar?: boolean;
  };
}

// 安全隐患区域
export interface HazardZone {
  id: string;
  type: 'trip_hazard' | 'slippery_floor' | 'poor_lighting' | 'narrow_path' | 'high_threshold' | 'no_grab_bar';
  position: { x: number; y: number };
  radius: number;
  severity: 'low' | 'medium' | 'high';
  description: string;
  relatedRegulation: string[];
}

// 改造建议类型
export interface ModificationSuggestion {
  id: string;
  category: '无障碍改造' | '安全加固' | '空间优化' | '设备升级' | '照明改善';
  title: string;
  description: string;
  priority: '紧急' | '重要' | '一般';
  relatedRegulations: string[];
  estimatedCost: {
    min: number;
    max: number;
    currency: 'CNY';
  };
  difficulty: '简单' | '中等' | '复杂';
  steps: string[];
  materials?: string[];
  warnings?: string[];
  applicableRooms: string[];
}
