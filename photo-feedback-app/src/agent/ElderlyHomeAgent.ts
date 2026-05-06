import { Regulation } from '../types';
import { regulations } from '../data/regulations';
import { visionService } from './VisionService';

export interface ThreeJSRoomModel {
  scene: any;
  elements: any[];
  metadata: {
    roomType: string;
    dimensions: { width: number; length: number; height: number };
  };
}

export interface DetectedElement {
  id: string;
  type: 'door' | 'window' | 'furniture' | 'hazard' | 'barrier' | 'lighting' | 'floor' | 'wall' | 'toilet' | 'kitchen_counter' | 'bed';
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

export interface RoomAnalysis {
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

export interface HazardZone {
  id: string;
  type: 'trip_hazard' | 'slippery_floor' | 'poor_lighting' | 'narrow_path' | 'high_threshold' | 'no_grab_bar';
  position: { x: number; y: number };
  radius: number;
  severity: 'low' | 'medium' | 'high';
  description: string;
  relatedRegulation: string[];
}

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

export class ElderlyHomeAgent {
  private regulations: Regulation[];

  constructor() {
    this.regulations = regulations;
  }

  async analyzeRoom(imageData: string) {
    return await visionService.analyzeRoom(imageData);
  }

  getRegulationById(id: string): Regulation | undefined {
    return this.regulations.find((r) => r.id === id);
  }

  getAllRegulations(): Regulation[] {
    return this.regulations;
  }
}
