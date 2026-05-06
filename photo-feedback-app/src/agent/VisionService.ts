import { RoomAnalysis, HazardZone, DetectedElement, ModificationSuggestion } from './ElderlyHomeAgent';

const API_BASE = 'http://localhost:3001/api';

export interface AnalyzeResult {
  analysis: RoomAnalysis;
  suggestions: ModificationSuggestion[];
  summary: string;
}

/**
 * 压缩图片到指定大小和质量
 */
async function compressImage(imageData: string, maxWidth = 1920, quality = 0.8): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      // 计算压缩后的尺寸
      let width = img.width;
      let height = img.height;
      
      if (width > maxWidth) {
        height = (height * maxWidth) / width;
        width = maxWidth;
      }
      
      // 创建 canvas 绘制压缩后的图片
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('无法创建 canvas context'));
        return;
      }
      
      ctx.drawImage(img, 0, 0, width, height);
      
      // 转换为 JPEG base64
      const compressed = canvas.toDataURL('image/jpeg', quality);
      resolve(compressed);
    };
    img.onerror = reject;
    img.src = imageData;
  });
}

export class VisionService {
  /**
   * 将图片数据转换为 base64
   */
  private async toBase64(imageData: string): Promise<string> {
    // 如果是 blob URL，转换为 base64
    if (imageData.startsWith('blob:')) {
      const response = await fetch(imageData);
      const blob = await response.blob();
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result as string);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    }
    
    return imageData;
  }

  /**
   * 分析房间图片
   */
  async analyzeRoom(imageData: string): Promise<AnalyzeResult> {
    try {
      // 转换为 base64
      let base64Data = await this.toBase64(imageData);
      
      // 压缩图片（确保小于5MB，符合智谱AI要求）
      base64Data = await compressImage(base64Data, 1920, 0.8);
      
      // 发送 base64 数据给后端
      const analysisResponse = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imageData: base64Data }),
      });

      if (!analysisResponse.ok) {
        const error = await analysisResponse.json();
        throw new Error(error.error || '分析失败');
      }

      const analysis = await analysisResponse.json();

      // 获取改造建议
      const suggestionsResponse = await fetch(`${API_BASE}/suggestions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analysis }),
      });

      if (!suggestionsResponse.ok) {
        const error = await suggestionsResponse.json();
        throw new Error(error.error || '生成建议失败');
      }

      const { suggestions, summary } = await suggestionsResponse.json();

      return {
        analysis: analysis as RoomAnalysis,
        suggestions: suggestions as ModificationSuggestion[],
        summary: summary || '',
      };
    } catch (error) {
      console.error('分析失败:', error);
      throw error;
    }
  }
}

export const visionService = new VisionService();
