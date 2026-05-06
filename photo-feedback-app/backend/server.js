import express from 'express';
import cors from 'cors';
import fetch from 'node-fetch';
import multer from 'multer';
import path from 'path';
import fs from 'fs';

const app = express();
const PORT = 3001;

app.use(cors());
app.use(express.json({ limit: '50mb' }));

// 日志系统
const logs = [];
const MAX_LOGS = 100;

function addLog(type, title, content, status = 'info') {
  const log = {
    id: Date.now(),
    type,
    title,
    content,
    status,
    timestamp: new Date().toISOString()
  };
  logs.unshift(log);
  if (logs.length > MAX_LOGS) logs.pop();
  console.log(`[${type.toUpperCase()}] ${title}`);
  if (content) console.log(content);
  return log;
}

// 创建日志目录
const LOG_DIR = './logs';
const AI_LOG_FILE = path.join(LOG_DIR, 'ai_logs.jsonl');
if (!fs.existsSync(LOG_DIR)) {
  fs.mkdirSync(LOG_DIR, { recursive: true });
}

// 保存AI详细日志到本地文件
function saveAILog(requestId, data) {
  try {
    const logEntry = {
      requestId,
      ...data,
      savedAt: new Date().toISOString()
    };
    fs.appendFileSync(AI_LOG_FILE, JSON.stringify(logEntry) + '\n');
  } catch (error) {
    console.error('保存AI日志失败:', error);
  }
}

// 保存上传的图片
const uploadDir = './uploads';
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir);
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadDir),
  filename: (req, file, cb) => cb(null, Date.now() + path.extname(file.originalname))
});
const upload = multer({ storage, limits: { fileSize: 10 * 1024 * 1024 } });

// 智谱AI API Key
const ZHIPU_API_KEY = '8ecacbf2f86d4b43b9aa4ed61ea7646a.HETIgWBdMhgX1b98';

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
  "dimensions": {"width": 宽度mm, "length": 长度mm, "height": 高度mm},
  "elements": [{"id": "元素ID", "type": "类型", "boundingBox": {"x": 0, "y": 0, "width": 0, "height": 0}, "confidence": 0.0-1.0, "properties": {}}],
  "hazards": [{"id": "隐患ID", "type": "隐患类型", "position": {"x": 0, "y": 0}, "radius": 50, "severity": "low|medium|high", "description": "描述", "relatedRegulation": ["规范ID"]}],
  "lightingLevel": "poor|fair|good",
  "floorCondition": "slippery|good|uneven",
  "overallScore": 0-100,
  "additionalObservations": ["额外观察"]
}

请只输出JSON，不要输出其他内容。`;

// 获取日志列表
app.get('/api/logs', (req, res) => {
  const { type, limit = 50 } = req.query;
  let filteredLogs = logs;
  if (type) {
    filteredLogs = logs.filter(log => log.type === type);
  }
  res.json(filteredLogs.slice(0, parseInt(limit)));
});

// 获取AI日志文件列表
app.get('/api/logs/files', (req, res) => {
  try {
    const files = fs.readdirSync(LOG_DIR).map(file => {
      const filePath = path.join(LOG_DIR, file);
      const stats = fs.statSync(filePath);
      return {
        name: file,
        path: filePath,
        size: stats.size,
        modified: stats.mtime.toISOString()
      };
    });
    res.json(files);
  } catch (error) {
    res.json([]);
  }
});

// 下载AI日志文件
app.get('/api/logs/download', (req, res) => {
  const { file } = req.query;
  const filePath = path.join(LOG_DIR, file || 'ai_logs.jsonl');
  if (fs.existsSync(filePath)) {
    res.download(filePath);
  } else {
    res.status(404).json({ error: '文件不存在' });
  }
});

// 读取AI日志内容
app.get('/api/logs/content', (req, res) => {
  const { file, lines = 100 } = req.query;
  const filePath = path.join(LOG_DIR, file || 'ai_logs.jsonl');
  try {
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, 'utf-8');
      const allLines = content.trim().split('\n');
      const recentLines = allLines.slice(-parseInt(lines));
      const logs = recentLines.map(line => {
        try {
          return JSON.parse(line);
        } catch {
          return { raw: line };
        }
      });
      res.json({
        file,
        totalLines: allLines.length,
        returnedLines: logs.length,
        logs
      });
    } else {
      res.json({ file, logs: [], message: '文件不存在' });
    }
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// 清空日志
app.delete('/api/logs', (req, res) => {
  logs.length = 0;
  addLog('system', '日志已清空');
  res.json({ success: true });
});

// 分析接口 - 直接接收base64图片
app.post('/api/analyze', async (req, res) => {
  const requestId = `analyze_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  
  try {
    const { imageData } = req.body;
    
    if (!imageData) {
      addLog('error', '缺少图片数据', null, 'error');
      return res.status(400).json({ error: '缺少图片数据' });
    }

    // 记录图片信息
    const imageSizeKB = Math.round(imageData.length * 0.75 / 1024);
    addLog('info', '收到图片请求', `图片大小: ${imageSizeKB}KB, RequestID: ${requestId}`, 'info');

    // 直接使用前端的 data URL
    const imageUrl = imageData;

    // 构建请求
    const apiRequest = {
      model: 'glm-4.6v',
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'image_url',
              image_url: {
                url: imageUrl
              }
            },
            {
              type: 'text',
              text: SYSTEM_PROMPT + '\n\n请分析这张房间图片，输出JSON格式的房间分析结果。'
            }
          ]
        }
      ]
    };

    addLog('ai', '开始调用 GLM-4.6V', `RequestID: ${requestId}`, 'info');

    // 调用智谱AI
    const startTime = Date.now();
    const response = await fetch('https://open.bigmodel.cn/api/paas/v4/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${ZHIPU_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(apiRequest)
    });
    const duration = Date.now() - startTime;

    addLog('ai', 'API响应状态', `HTTP ${response.status}, 耗时: ${duration}ms`, response.ok ? 'info' : 'error');

    const responseText = await response.text();
    let responseData;
    try {
      responseData = JSON.parse(responseText);
    } catch {
      responseData = { raw: responseText };
    }

    // 保存完整日志
    saveAILog(requestId, {
      type: 'analyze',
      apiUrl: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
      model: 'glm-4.6v',
      imageSizeKB,
      request: {
        model: apiRequest.model,
        messageCount: apiRequest.messages.length,
        hasImage: true,
        promptLength: apiRequest.messages[0].content[1].text.length
      },
      response: {
        status: response.status,
        ok: response.ok,
        duration,
        rawResponse: responseText,
        parsed: responseData,
        usage: responseData.usage,
        id: responseData.id
      },
      requestId
    });

    if (!response.ok) {
      addLog('error', '智谱AI API错误', `状态: ${response.status}, 响应: ${responseText}`, 'error');
      throw new Error(`智谱AI API错误: ${response.status} - ${responseText}`);
    }

    const data = responseData;
    const text = data.choices?.[0]?.message?.content || '';
    
    addLog('ai', '收到AI响应', `响应长度: ${text.length}字符`, 'info');

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      addLog('error', '无法解析AI响应', `原始响应: ${text.substring(0, 500)}...`, 'error');
      throw new Error('无法解析分析结果');
    }

    addLog('ai', '解析JSON成功', `JSON长度: ${jsonMatch[0].length}字符`, 'success');

    const analysisResult = JSON.parse(jsonMatch[0]);
    const normalizedResult = normalizeResult(analysisResult);
    
    addLog('success', '房间分析完成', `房间类型: ${normalizedResult.roomType}, 评分: ${normalizedResult.overallScore}`, 'success');
    res.json(normalizedResult);
  } catch (error) {
    addLog('error', '分析失败', `${error.message}`, 'error');
    
    // 保存错误日志
    saveAILog(requestId, {
      type: 'analyze_error',
      error: error.message,
      stack: error.stack
    });
    
    res.status(500).json({ error: error.message || '分析失败' });
  }
});

// 建议接口
app.post('/api/suggestions', async (req, res) => {
  const requestId = `suggest_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  
  try {
    const { analysis } = req.body;
    
    if (!analysis) {
      return res.status(400).json({ error: '缺少分析数据' });
    }

    addLog('ai', '开始生成改造建议', `房间类型: ${analysis.roomType}, RequestID: ${requestId}`, 'info');

    const userPrompt = `基于以下房间分析结果，生成老年人友好改造建议。

房间分析结果：
- 房间类型: ${analysis.roomType}
- 尺寸: ${analysis.dimensions?.width || 0}mm x ${analysis.dimensions?.length || 0}mm x ${analysis.dimensions?.height || 0}mm
- 检测到的元素: ${JSON.stringify(analysis.elements)}
- 安全隐患: ${JSON.stringify(analysis.hazards)}
- 光照水平: ${analysis.lightingLevel}
- 地面状况: ${analysis.floorCondition}
- 安全评分: ${analysis.overallScore}/100

请以JSON格式输出改造建议列表：

{
  "suggestions": [
    {
      "id": "sug_序号",
      "category": "无障碍改造|安全加固|空间优化|设备升级|照明改善",
      "title": "建议标题",
      "description": "详细描述",
      "priority": "紧急|重要|一般",
      "relatedRegulations": ["REG001"],
      "estimatedCost": {"min": 最小金额, "max": 最大金额, "currency": "CNY"},
      "difficulty": "简单|中等|复杂",
      "steps": ["步骤1", "步骤2"],
      "materials": ["所需材料"],
      "warnings": ["注意事项"],
      "applicableRooms": ["适用房间"]
    }
  ],
  "summary": "总体评估（100字以内）"
}

只输出JSON。`;

    const apiRequest = {
      model: 'glm-4-flash',
      messages: [
        {
          role: 'user',
          content: userPrompt
        }
      ]
    };

    const startTime = Date.now();
    const response = await fetch('https://open.bigmodel.cn/api/paas/v4/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${ZHIPU_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(apiRequest)
    });
    const duration = Date.now() - startTime;

    const responseText = await response.text();
    let responseData;
    try {
      responseData = JSON.parse(responseText);
    } catch {
      responseData = { raw: responseText };
    }

    // 保存完整日志
    saveAILog(requestId, {
      type: 'suggestions',
      apiUrl: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
      model: 'glm-4-flash',
      request: {
        model: apiRequest.model,
        roomType: analysis.roomType,
        overallScore: analysis.overallScore
      },
      response: {
        status: response.status,
        ok: response.ok,
        duration,
        rawResponse: responseText,
        parsed: responseData,
        usage: responseData.usage,
        id: responseData.id
      },
      requestId
    });

    if (!response.ok) {
      addLog('error', '生成建议失败', `状态: ${response.status}, 响应: ${responseText}`, 'error');
      throw new Error(`智谱AI API错误: ${response.status} - ${responseText}`);
    }

    const data = responseData;
    const text = data.choices?.[0]?.message?.content || '';

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      addLog('error', '无法解析建议结果', `原始响应: ${text.substring(0, 500)}...`, 'error');
      throw new Error('无法解析建议结果');
    }

    const suggestionsResult = JSON.parse(jsonMatch[0]);
    addLog('success', '改造建议生成成功', `生成 ${suggestionsResult.suggestions?.length || 0} 条建议`, 'success');
    res.json(suggestionsResult);
  } catch (error) {
    addLog('error', '生成建议失败', error.message, 'error');
    
    saveAILog(requestId, {
      type: 'suggestions_error',
      error: error.message
    });
    
    res.status(500).json({ error: error.message || '生成建议失败' });
  }
});

function normalizeResult(result) {
  const validRoomTypes = ['living_room', 'bedroom', 'kitchen', 'bathroom', 'corridor', 'balcony', 'unknown'];
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
      type: el.type || 'furniture',
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

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
  console.log(`后端服务器运行在 http://localhost:${PORT}`);
  console.log(`AI日志文件: ${AI_LOG_FILE}`);
  addLog('system', '服务器启动', `端口: ${PORT}, 日志目录: ${LOG_DIR}`, 'success');
});
