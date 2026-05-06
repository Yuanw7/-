import { useEffect, useRef } from 'react';
import { RoomAnalysis } from '../agent/ElderlyHomeAgent';

interface RoomModel2DProps {
  analysis: RoomAnalysis;
  onClose: () => void;
}

export default function RoomModel2D({ analysis, onClose }: RoomModel2DProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // 设置画布大小
    const width = 600;
    const height = 500;
    canvas.width = width;
    canvas.height = height;

    // 清空画布
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, width, height);

    // 计算缩放比例
    const roomWidth = analysis.dimensions.width / 1000; // 转换为米
    const roomLength = analysis.dimensions.length / 1000;
    const maxDimension = Math.max(roomWidth, roomLength, 5);
    const scale = Math.min((width - 80) / roomWidth, (height - 80) / roomLength) * 0.8;

    const offsetX = (width - roomWidth * scale) / 2;
    const offsetY = (height - roomLength * scale) / 2;

    // 绘制房间边框
    ctx.strokeStyle = '#1e40af';
    ctx.lineWidth = 3;
    ctx.strokeRect(offsetX, offsetY, roomWidth * scale, roomLength * scale);

    // 填充房间
    ctx.fillStyle = '#eff6ff';
    ctx.fillRect(offsetX, offsetY, roomWidth * scale, roomLength * scale);

    // 绘制元素
    analysis.elements.forEach(element => {
      drawElement(ctx, element, offsetX, offsetY, scale, analysis.hazards);
    });

    // 绘制安全隐患标记
    analysis.hazards.forEach(hazard => {
      drawHazard(ctx, hazard, offsetX, offsetY, scale);
    });

    // 添加尺寸标注
    ctx.fillStyle = '#64748b';
    ctx.font = '12px system-ui';
    ctx.textAlign = 'center';

    // 宽度标注
    ctx.fillText(`${roomWidth.toFixed(1)}m`, offsetX + (roomWidth * scale) / 2, offsetY + roomLength * scale + 25);

    // 长度标注
    ctx.save();
    ctx.translate(offsetX - 20, offsetY + (roomLength * scale) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(`${roomLength.toFixed(1)}m`, 0, 0);
    ctx.restore();

    // 绘制图例
    drawLegend(ctx, width, analysis.hazards);

  }, [analysis]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-auto">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-gray-800">房间分析模型</h2>
              <p className="text-gray-500 mt-1">
                {getRoomTypeLabel(analysis.roomType)} - {Math.round(analysis.dimensions.width / 1000)}×{Math.round(analysis.dimensions.length / 1000)}米
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">
          <div className="flex flex-col lg:flex-row gap-6">
            <div className="flex-1">
              <canvas
                ref={canvasRef}
                className="w-full border border-gray-200 rounded-lg"
                style={{ maxWidth: '600px', margin: '0 auto' }}
              />
            </div>

            <div className="lg:w-64 space-y-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-700 mb-3">房间信息</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">安全评分</span>
                    <span className={`font-medium ${
                      analysis.overallScore >= 80 ? 'text-green-600' :
                      analysis.overallScore >= 60 ? 'text-yellow-600' : 'text-red-600'
                    }`}>
                      {analysis.overallScore}分
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">光照条件</span>
                    <span className="font-medium">
                      {analysis.lightingLevel === 'good' ? '良好' :
                       analysis.lightingLevel === 'fair' ? '一般' : '较差'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">地面状况</span>
                    <span className="font-medium">
                      {analysis.floorCondition === 'good' ? '良好' :
                       analysis.floorCondition === 'slippery' ? '光滑' : '不平整'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-700 mb-3">检测元素</h3>
                <div className="space-y-2">
                  {analysis.elements.map((el, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: getElementColor(el.type) }} />
                      <span className="text-gray-600">{getElementLabel(el.type)}</span>
                      <span className="text-gray-400 ml-auto">{Math.round(el.confidence * 100)}%</span>
                    </div>
                  ))}
                </div>
              </div>

              {analysis.hazards.length > 0 && (
                <div className="bg-red-50 rounded-lg p-4">
                  <h3 className="font-semibold text-red-700 mb-3">安全隐患</h3>
                  <div className="space-y-2">
                    {analysis.hazards.map((hazard, i) => (
                      <div key={i} className="text-sm">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${
                            hazard.severity === 'high' ? 'bg-red-500' :
                            hazard.severity === 'medium' ? 'bg-orange-500' : 'bg-yellow-500'
                          }`} />
                          <span className="text-red-800 font-medium">
                            {hazard.severity === 'high' ? '高' :
                             hazard.severity === 'medium' ? '中' : '低'}
                          </span>
                        </div>
                        <p className="text-red-700 mt-1">{hazard.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function drawElement(
  ctx: CanvasRenderingContext2D,
  element: any,
  offsetX: number,
  offsetY: number,
  scale: number,
  hazards: any[]
) {
  const { type, boundingBox, properties } = element;
  const x = offsetX + (boundingBox.x / 1000) * scale;
  const y = offsetY + (boundingBox.y / 1000) * scale;
  const w = (boundingBox.width / 1000) * scale;
  const h = (boundingBox.height / 1000) * scale;

  ctx.fillStyle = getElementColor(type);
  ctx.strokeStyle = getElementColor(type);
  ctx.lineWidth = 2;

  switch (type) {
    case 'door':
      ctx.fillRect(x, y, w, h);
      ctx.fillStyle = '#1e40af';
      ctx.beginPath();
      ctx.arc(x + 10, y + h / 2, 5, 0, Math.PI * 2);
      ctx.fill();
      break;
    case 'toilet':
      ctx.beginPath();
      ctx.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
      ctx.fill();
      if (!properties.hasGrabBar) {
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 3;
        ctx.setLineDash([5, 5]);
        ctx.strokeRect(x - 5, y - 20, 20, h + 40);
        ctx.setLineDash([]);
      }
      break;
    case 'furniture':
      ctx.fillRect(x, y, w, h);
      break;
    case 'window':
      ctx.fillStyle = '#7dd3fc';
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
      break;
    default:
      ctx.fillStyle = '#94a3b8';
      ctx.fillRect(x, y, w, h);
  }
}

function drawHazard(ctx: CanvasRenderingContext2D, hazard: any, offsetX: number, offsetY: number, scale: number) {
  const x = offsetX + (hazard.position.x / 1000) * scale;
  const y = offsetY + (hazard.position.y / 1000) * scale;

  ctx.save();
  ctx.fillStyle = hazard.severity === 'high' ? '#ef4444' :
                  hazard.severity === 'medium' ? '#f97316' : '#eab308';
  ctx.globalAlpha = 0.7;

  ctx.beginPath();
  ctx.moveTo(x, y - 15);
  ctx.lineTo(x + 12, y + 10);
  ctx.lineTo(x - 12, y + 10);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = 'white';
  ctx.font = 'bold 14px system-ui';
  ctx.textAlign = 'center';
  ctx.fillText('!', x, y + 5);
  ctx.restore();
}

function drawLegend(ctx: CanvasRenderingContext2D, width: number, hazards: any[]) {
  const startX = 20;
  let startY = 20;

  const items = [
    { color: '#1e40af', label: '门' },
    { color: '#64748b', label: '家具' },
    { color: '#7dd3fc', label: '窗户' },
    { color: '#ef4444', label: '高风险隐患' },
    { color: '#f97316', label: '中风险隐患' },
  ];

  ctx.font = '11px system-ui';

  items.forEach((item, i) => {
    const x = startX + (i % 3) * 100;
    const y = startY + Math.floor(i / 3) * 20;

    ctx.fillStyle = item.color;
    ctx.fillRect(x, y - 8, 12, 12);

    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'left';
    ctx.fillText(item.label, x + 16, y + 2);
  });
}

function getElementColor(type: string): string {
  const colors: Record<string, string> = {
    door: '#1e40af',
    window: '#7dd3fc',
    furniture: '#64748b',
    toilet: '#8b5cf6',
    kitchen_counter: '#f59e0b',
    bed: '#ec4899',
    floor: '#d1d5db',
    wall: '#9ca3af',
    lighting: '#fbbf24',
  };
  return colors[type] || '#94a3b8';
}

function getElementLabel(type: string): string {
  const labels: Record<string, string> = {
    door: '门',
    window: '窗户',
    furniture: '家具',
    toilet: '马桶',
    kitchen_counter: '厨房台面',
    bed: '床',
    floor: '地面',
    wall: '墙面',
    lighting: '灯具',
  };
  return labels[type] || type;
}

function getRoomTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    living_room: '客厅',
    bedroom: '卧室',
    kitchen: '厨房',
    bathroom: '卫生间',
    corridor: '走廊',
    balcony: '阳台',
    unknown: '未知',
  };
  return labels[type] || type;
}
