import { GoogleGenerativeAI, HarmCategory, HarmBlockThreshold } from '@google/generative-ai';
import { DetectedElement, RoomAnalysis, HazardZone, ModificationSuggestion } from './ElderlyHomeAgent';

// 你的Gemini API Key
const API_KEY = 'AIzaSyAS4EwbulEUsMu6Aed5fHO6mDjO8ZrhMmA';

const genAI = new GoogleGenerativeAI(API_KEY);

// 老年人友好设计规范系统提示
const SYSTEM_PROMPT = `你是一位专业的老年人居住环境无障碍改造工程师。请分析房间图片，输出严格的JSON格式结果。

## 分析要求

1. **房间元素检测**：识别门、窗、家具、卫生间设备、厨房设备、灯具、地面、墙面等
2. **房间类型判断**：living_room(客厅)、bedroom(卧室)、kitchen(厨房)、bathroom(卫生间)、corridor(走廊)
3. **安全隐患识别**：
   - 通道宽度不足(轮椅需≥900mm)
   - 门口宽度不足(轮椅需≥800mm)
   - 门槛高度超标(应≤20mm)
   - 缺少安全扶手(卫生间马桶旁、淋浴区)
   - 地面光滑(老年人易滑倒)
   - 光照不足
4. **尺寸估算**：基于常见的门(约800-900mm高)、窗户、家具参考尺寸估算房间尺寸

## 必须遵守的中国国家标准

- GB 50763-2012 无障碍设计规范
- GB 50340-2016 老年人照料设施建筑设计标准
- GB 50034-2013 建筑照明设计标准
- GB/T 35796-2017 养老机构服务质量基本规范

## 输出JSON格式（严格遵循）

{
  "roomType": "房间类型",
  "dimensions": {
    "width": 宽度mm,
    "length": 长度mm,
    "height": 高度mm
  },
  "elements": [
    {
      "id": "元素ID",
      "type": "door|window|furniture|toilet|kitchen_counter|bed|lighting|floor|wall|sofa|table",
      "boundingBox": {"x": 0, "y": 0, "width": 0, "height": 0},
      "confidence": 0.0-1.0,
      "properties": {
        "width": 宽度mm(如有),
        "height": 高度mm(如有),
        "position": "left|center|right|corner",
        "condition": "good|fair|poor",
        "hasGrabBar": true|false,
        "material": "材料描述",
        "color": "颜色"
      }
    }
  ],
  "hazards": [
    {
      "id": "隐患ID",
      "type": "narrow_path|slippery_floor|poor_lighting|high_threshold|no_grab_bar|trip_hazard",
      "position": {"x": 0, "y": 0},
      "radius": 影响半径,
      "severity": "low|medium|high",
      "description": "隐患描述",
      "relatedRegulation": ["规范ID"]
    }
  ],
  "lightingLevel": "poor|fair|good",
  "floorCondition": "slippery|good|uneven",
  "overallScore": 0-100,
  "additionalObservations": ["额外观察备注"]
}

请只输出JSON，不要输出其他内容。`;

export interface GeminiAnalysisResult {
  roomType: string;
  dimensions: { width: number; length: number; height: number };
  elements: Array<{
    id: string;
    type: string;
    boundingBox: { x: number; y: number; width: number; height: number };
    confidence: number;
    properties: Record<string, any>;
  }>;
  hazards: Array<{
    id: string;
    type: string;
    position: { x: number; y: number };
    radius: number;
    severity: string;
    description: string;
    relatedRegulation: string[];
  }>;
  lightingLevel: string;
  floorCondition: string;
  overallScore: number;
  additionalObservations?: string[];
}

export class GeminiVisionEngine {
  private model: any;

  constructor() {
    this.model = genAI.getGenerativeModel({
      model: 'gemini-2.0-flash',
      systemInstruction: SYSTEM_PROMPT,
    });
  }

  /**
   * 分析房间图片
   */
  async analyzeRoomImage(imageData: string): Promise<GeminiAnalysisResult> {
    try {
      // 将base64转换为Gemini可用的格式
      const imageBase64 = imageData.includes(',') 
        ? imageData.split(',')[1] 
        : imageData;
      
      const imageParts = [
        {
          inlineData: {
            data: imageBase64,
            mimeType: imageData.includes('image/png') ? 'image/png' : 'image/jpeg',
          },
        },
      ];

      const result = await this.model.generateContent([
        '请分析这张房间图片，输出JSON格式的房间分析结果。',
        ...imageParts,
      ]);

      const response = result.response;
      const text = response.text();
      
      // 提取JSON
      const jsonMatch = text.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        throw new Error('无法解析Gemini返回的结果');
      }

      const parsedResult = JSON.parse(jsonMatch[0]) as GeminiAnalysisResult;
      
      // 验证并规范化结果
      return this.normalizeResult(parsedResult);
    } catch (error) {
      console.error('Gemini分析错误:', error);
      throw error;
    }
  }

  /**
   * 规范化Gemini返回的结果
   */
  private normalizeResult(result: GeminiAnalysisResult): GeminiAnalysisResult {
    const validRoomTypes = ['living_room', 'bedroom', 'kitchen', 'bathroom', 'corridor', 'balcony', 'unknown'];
    const validElementTypes = ['door', 'window', 'furniture', 'toilet', 'kitchen_counter', 'bed', 'lighting', 'floor', 'wall', 'sofa', 'table', 'cabinet', 'shower', 'bathtub', 'sink'];
    const validHazardTypes = ['narrow_path', 'slippery_floor', 'poor_lighting', 'high_threshold', 'no_grab_bar', 'trip_hazard'];
    const validSeverityLevels = ['low', 'medium', 'high'];

    return {
      roomType: validRoomTypes.includes(result.roomType) ? result.roomType : 'unknown',
      dimensions: {
        width: Math.max(1000, Math.min(10000, result.dimensions?.width || 3000)),
        length: Math.max(1000, Math.min(10000, result.dimensions?.length || 4000)),
        height: Math.max(2000, Math.min(4000, result.dimensions?.height || 2800)),
      },
      elements: (result.elements || []).map((el, idx) => ({
        id: el.id || `element_${idx}`,
        type: validElementTypes.includes(el.type) ? el.type : 'furniture',
        boundingBox: el.boundingBox || { x: 0, y: 0, width: 100, height: 100 },
        confidence: Math.max(0, Math.min(1, el.confidence || 0.5)),
        properties: el.properties || {},
      })),
      hazards: (result.hazards || []).map((hz, idx) => ({
        id: hz.id || `hazard_${idx}`,
        type: validHazardTypes.includes(hz.type) ? hz.type : 'trip_hazard',
        position: hz.position || { x: 0, y: 0 },
        radius: Math.max(10, hz.radius || 50),
        severity: validSeverityLevels.includes(hz.severity) ? hz.severity : 'medium',
        description: hz.description || '未描述的安全隐患',
        relatedRegulation: hz.relatedRegulation || [],
      })),
      lightingLevel: ['poor', 'fair', 'good'].includes(result.lightingLevel) ? result.lightingLevel : 'fair',
      floorCondition: ['slippery', 'good', 'uneven'].includes(result.floorCondition) ? result.floorCondition : 'good',
      overallScore: Math.max(0, Math.min(100, result.overallScore || 50)),
      additionalObservations: result.additionalObservations || [],
    };
  }

  /**
   * 生成详细的改造建议（基于分析结果）
   */
  async generateDetailedSuggestions(analysis: GeminiAnalysisResult): Promise<{
    suggestions: ModificationSuggestion[];
    summary: string;
  }> {
    try {
      const model = genAI.getGenerativeModel({
        model: 'gemini-2.0-flash',
      });

      const prompt = `基于以下房间分析结果，生成老年人友好改造建议。

房间分析结果：
- 房间类型: ${analysis.roomType}
- 尺寸: ${analysis.dimensions.width}mm x ${analysis.dimensions.length}mm x ${analysis.dimensions.height}mm
- 检测到的元素: ${JSON.stringify(analysis.elements)}
- 安全隐患: ${JSON.stringify(analysis.hazards)}
- 光照水平: ${analysis.lightingLevel}
- 地面状况: ${analysis.floorCondition}
- 安全评分: ${analysis.overallScore}/100
- 额外观察: ${analysis.additionalObservations?.join(', ') || '无'}

请以JSON格式输出改造建议列表：

{
  "suggestions": [
    {
      "id": "sug_序号",
      "category": "无障碍改造|安全加固|空间优化|设备升级|照明改善",
      "title": "建议标题",
      "description": "详细描述为什么要改，以及当前问题",
      "priority": "紧急|重要|一般",
      "relatedRegulations": ["REG001", "REG002"],
      "estimatedCost": {"min": 最小金额, "max": 最大金额, "currency": "CNY"},
      "difficulty": "简单|中等|复杂",
      "steps": ["步骤1", "步骤2", "步骤3"],
      "materials": ["所需材料"],
      "warnings": ["注意事项"],
      "applicableRooms": ["适用的房间类型"]
    }
  ],
  "summary": "总体评估和最重要的改进建议概述（100字以内）"
}

只输出JSON，不要其他内容。`;

      const result = await model.generateContent([prompt]);
      const response = result.response;
      const text = response.text();

      const jsonMatch = text.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        throw new Error('无法解析改造建议');
      }

      const parsedResult = JSON.parse(jsonMatch[0]);

      return {
        suggestions: parsedResult.suggestions || [],
        summary: parsedResult.summary || '已完成分析，请查看详细建议。',
      };
    } catch (error) {
      console.error('生成建议错误:', error);
      throw error;
    }
  }
}

// 导出单例
export const geminiVision = new GeminiVisionEngine();
