import { Regulation } from '../types';

export const regulations: Regulation[] = [
  // 无障碍类
  {
    id: 'REG001',
    category: '无障碍',
    code: 'GB 50763-2012',
    title: '轮椅通道宽度',
    description: '轮椅使用者通行的通道宽度不应小于900mm',
    requirement: '通道宽度 ≥ 900mm',
    minValue: 900,
    unit: 'mm',
    priority: '必须',
    relatedItems: ['door_width', 'corridor_access', 'furniture_spacing'],
  },
  {
    id: 'REG002',
    category: '无障碍',
    code: 'GB 50763-2012',
    title: '门口净宽度',
    description: '轮椅使用者通行的门净宽度不应小于800mm',
    requirement: '门净宽度 ≥ 800mm',
    minValue: 800,
    unit: 'mm',
    priority: '必须',
    relatedItems: ['door_width', 'door_modification'],
  },
  {
    id: 'REG003',
    category: '无障碍',
    code: 'GB 50763-2012',
    title: '走廊净空高度',
    description: '轮椅使用者的通行空间净高不应低于2000mm',
    requirement: '净空高度 ≥ 2000mm',
    minValue: 2000,
    unit: 'mm',
    priority: '必须',
    relatedItems: ['ceiling_height', 'overhead_clearance'],
  },
  {
    id: 'REG004',
    category: '无障碍',
    code: 'GB 50763-2012',
    title: '门槛高度限制',
    description: '老年人居室门槛高度不应大于20mm，且应平滑过渡',
    requirement: '门槛高度 ≤ 20mm',
    maxValue: 20,
    unit: 'mm',
    priority: '必须',
    relatedItems: ['threshold_removal', 'floor_transition'],
  },

  // 安全防护类
  {
    id: 'REG005',
    category: '安全防护',
    code: 'JGJ 122-99',
    title: '卫生间扶手安装',
    description: '老年人卫生间应安装安全扶手，马桶两侧及淋浴区均需配置',
    requirement: '马桶两侧扶手高度 650-750mm',
    minValue: 650,
    maxValue: 750,
    unit: 'mm',
    priority: '必须',
    relatedItems: ['toilet_grab_bar', 'shower_grab_bar', 'bathroom_safety'],
  },
  {
    id: 'REG006',
    category: '安全防护',
    code: 'GB/T 35796-2017',
    title: '地面防滑性能',
    description: '老年人活动区域地面防滑等级应达到R10及以上',
    requirement: '防滑等级 ≥ R10',
    priority: '必须',
    relatedItems: ['non-slip_flooring', 'bathroom_flooring', 'kitchen_flooring'],
  },
  {
    id: 'REG007',
    category: '安全防护',
    code: 'GB 50340-2016',
    title: '浴缸/淋浴凳高度',
    description: '老年人洗浴设备高度应便于使用，浴缸或淋浴凳高度宜在420-480mm',
    requirement: '洗浴设备高度 420-480mm',
    minValue: 420,
    maxValue: 480,
    unit: 'mm',
    priority: '建议',
    relatedItems: ['shower_seat', 'bathtub_height', 'bathroom_equipment'],
  },
  {
    id: 'REG008',
    category: '安全防护',
    code: 'GB 50096-2011',
    title: '紧急呼叫装置',
    description: '老年人卧室应安装紧急呼叫装置，床侧安装高度距地面600-800mm',
    requirement: '呼叫装置距床 ≤ 300mm，高度 600-800mm',
    priority: '必须',
    relatedItems: ['emergency_call', 'bedroom_safety', 'bathroom_call'],
  },

  // 空间尺寸类
  {
    id: 'REG009',
    category: '空间尺寸',
    code: 'GB 50099-2011',
    title: '厨房操作台高度',
    description: '老年人厨房操作台高度宜为800-850mm，便于站立操作',
    requirement: '操作台高度 800-850mm',
    minValue: 800,
    maxValue: 850,
    unit: 'mm',
    priority: '建议',
    relatedItems: ['kitchen_counter', 'sink_height', 'cooking_area'],
  },
  {
    id: 'REG010',
    category: '空间尺寸',
    code: 'GB 50763-2012',
    title: '开关插座高度',
    description: '老年人使用场所的开关、插座高度宜设置在900-1200mm范围',
    requirement: '开关/插座高度 900-1200mm',
    minValue: 900,
    maxValue: 1200,
    unit: 'mm',
    priority: '建议',
    relatedItems: ['light_switch', 'electrical_outlet', 'height_adjustment'],
  },
  {
    id: 'REG011',
    category: '空间尺寸',
    code: 'GB 50340-2016',
    title: '床铺高度',
    description: '老年人床铺高度宜为450-500mm，便于老年人上下床',
    requirement: '床高度 450-500mm',
    minValue: 450,
    maxValue: 500,
    unit: 'mm',
    priority: '建议',
    relatedItems: ['bed_height', 'bedside_clearance', 'bed_mattress'],
  },
  {
    id: 'REG012',
    category: '空间尺寸',
    code: 'GB 50763-2012',
    title: '床边通道宽度',
    description: '床侧通道净宽度不应小于600mm，便于轮椅通行',
    requirement: '床边通道宽度 ≥ 600mm',
    minValue: 600,
    unit: 'mm',
    priority: '必须',
    relatedItems: ['bedside_access', 'corridor_width', 'furniture_spacing'],
  },

  // 设备安装类
  {
    id: 'REG013',
    category: '设备安装',
    code: 'GB 50340-2016',
    title: '燃气灶安全装置',
    description: '老年人使用场所的燃气灶应配备熄火保护装置',
    requirement: '燃气灶需配熄火保护装置',
    priority: '必须',
    relatedItems: ['gas_stove', 'safety_valve', 'kitchen_safety'],
  },
  {
    id: 'REG014',
    category: '设备安装',
    code: 'GB 50340-2016',
    title: '扶手安装牢固度',
    description: '老年人使用的扶手应安装牢固，能承受不小于1000N的拉力',
    requirement: '扶手承受拉力 ≥ 1000N',
    minValue: 1000,
    unit: 'N',
    priority: '必须',
    relatedItems: ['grab_bar', 'handrail', 'installation_quality'],
  },
  {
    id: 'REG015',
    category: '设备安装',
    code: 'GB 50763-2012',
    title: '热水器温度限制',
    description: '老年人使用热水器应配置恒温装置，热水温度不超过50℃',
    requirement: '热水温度 ≤ 50℃',
    maxValue: 50,
    unit: '℃',
    priority: '必须',
    relatedItems: ['water_heater', 'thermostat', 'scald_prevention'],
  },

  // 照明电气类
  {
    id: 'REG016',
    category: '照明电气',
    code: 'GB 50034-2013',
    title: '走廊夜间照明',
    description: '老年人走廊夜间照明照度不应小于50lx，保障夜间行走安全',
    requirement: '走廊夜间照度 ≥ 50lx',
    minValue: 50,
    unit: 'lx',
    priority: '必须',
    relatedItems: ['corridor_lighting', 'night_lamp', 'motion_sensor'],
  },
  {
    id: 'REG017',
    category: '照明电气',
    code: 'GB 50034-2013',
    title: '卧室照明照度',
    description: '老年人卧室照明照度不应小于100lx，方便阅读和日常活动',
    requirement: '卧室照度 ≥ 100lx',
    minValue: 100,
    unit: 'lx',
    priority: '必须',
    relatedItems: ['bedroom_lighting', 'reading_lamp', 'ceiling_light'],
  },
  {
    id: 'REG018',
    category: '照明电气',
    code: 'GB 50034-2013',
    title: '卫生间照明照度',
    description: '老年人卫生间照明照度不应小于150lx，便于洗漱和如厕',
    requirement: '卫生间照度 ≥ 150lx',
    minValue: 150,
    unit: 'lx',
    priority: '必须',
    relatedItems: ['bathroom_lighting', 'vanity_light', 'mirror_lighting'],
  },
  {
    id: 'REG019',
    category: '照明电气',
    code: 'GB 50034-2013',
    title: '厨房照明照度',
    description: '老年人厨房操作区域照明照度不应小于200lx，保障烹饪安全',
    requirement: '厨房操作区照度 ≥ 200lx',
    minValue: 200,
    unit: 'lx',
    priority: '必须',
    relatedItems: ['kitchen_lighting', 'counter_lighting', 'hood_light'],
  },
  {
    id: 'REG020',
    category: '照明电气',
    code: 'GB 50340-2016',
    title: '起夜照明装置',
    description: '老年人卧室应设置起夜照明，从床边到卫生间的路径应有连续照明',
    requirement: '起夜路径连续照明',
    priority: '必须',
    relatedItems: ['night_light', 'pathway_lighting', 'motion_lamp'],
  },
];

// 按类别分组规范
export const regulationsByCategory = regulations.reduce((acc, reg) => {
  if (!acc[reg.category]) {
    acc[reg.category] = [];
  }
  acc[reg.category].push(reg);
  return acc;
}, {} as Record<string, Regulation[]>);

// 获取规范的辅助函数
export function getRegulationById(id: string): Regulation | undefined {
  return regulations.find(reg => reg.id === id);
}

export function getRegulationsByCategory(category: string): Regulation[] {
  return regulationsByCategory[category] || [];
}

export function getPriorityRegulations(priority: '必须' | '建议' | '可选'): Regulation[] {
  return regulations.filter(reg => reg.priority === priority);
}