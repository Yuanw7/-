import { useState, useEffect, useRef } from 'react';
import { X, RefreshCw, Trash2, ChevronDown, ChevronUp, FileText, Download, Eye } from 'lucide-react';

interface Log {
  id: number;
  type: string;
  title: string;
  content?: string;
  status: string;
  timestamp: string;
}

interface AILog {
  requestId: string;
  type: string;
  model?: string;
  request?: any;
  response?: any;
  error?: string;
  savedAt: string;
}

interface LogPanelProps {
  onClose: () => void;
}

const typeColors = {
  info: 'bg-blue-100 text-blue-700',
  ai: 'bg-purple-100 text-purple-700',
  success: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
  system: 'bg-gray-100 text-gray-700',
};

const typeIcons = {
  info: '💡',
  ai: '🤖',
  success: '✅',
  error: '❌',
  system: '⚙️',
};

export default function LogPanel({ onClose }: LogPanelProps) {
  const [logs, setLogs] = useState<Log[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [expandedLogs, setExpandedLogs] = useState<Set<number>>(new Set());
  const [activeTab, setActiveTab] = useState<'realtime' | 'files'>('realtime');
  const [aiLogs, setAiLogs] = useState<AILog[]>([]);
  const [selectedLog, setSelectedLog] = useState<AILog | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const response = await fetch('http://localhost:3001/api/logs');
      const data = await response.json();
      setLogs(data);
    } catch (error) {
      console.error('获取日志失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchAILogs = async () => {
    try {
      const response = await fetch('http://localhost:3001/api/logs/content?lines=50');
      const data = await response.json();
      setAiLogs(data.logs || []);
    } catch (error) {
      console.error('获取AI日志失败:', error);
    }
  };

  const clearLogs = async () => {
    try {
      await fetch('http://localhost:3001/api/logs', { method: 'DELETE' });
      setLogs([]);
    } catch (error) {
      console.error('清空日志失败:', error);
    }
  };

  const toggleExpand = (id: number) => {
    const newExpanded = new Set(expandedLogs);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedLogs(newExpanded);
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeTab === 'files') {
      fetchAILogs();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'realtime') {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, activeTab]);

  const filteredLogs = filter === 'all' 
    ? logs 
    : logs.filter(log => log.type === filter);

  const downloadFile = (filename: string) => {
    window.open(`http://localhost:3001/api/logs/download?file=${filename}`, '_blank');
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[85vh] flex flex-col m-4">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-4">
            <h2 className="text-xl font-bold text-gray-800">🔍 运行日志</h2>
            <div className="flex bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => setActiveTab('realtime')}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'realtime' ? 'bg-white shadow text-blue-600' : 'text-gray-600'
                }`}
              >
                实时日志
              </button>
              <button
                onClick={() => setActiveTab('files')}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'files' ? 'bg-white shadow text-blue-600' : 'text-gray-600'
                }`}
              >
                <FileText className="w-4 h-4 inline mr-1" />
                本地日志
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {activeTab === 'realtime' && (
              <>
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="px-3 py-1.5 border rounded-lg text-sm"
                >
                  <option value="all">全部</option>
                  <option value="info">信息</option>
                  <option value="ai">AI调用</option>
                  <option value="success">成功</option>
                  <option value="error">错误</option>
                  <option value="system">系统</option>
                </select>
                <button
                  onClick={fetchLogs}
                  className="p-2 hover:bg-gray-100 rounded-lg"
                  title="刷新"
                >
                  <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={clearLogs}
                  className="p-2 hover:bg-red-100 text-red-600 rounded-lg"
                  title="清空日志"
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </>
            )}
            {activeTab === 'files' && (
              <button
                onClick={fetchAILogs}
                className="p-2 hover:bg-gray-100 rounded-lg"
                title="刷新"
              >
                <RefreshCw className="w-5 h-5" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-lg"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-hidden flex">
          {/* 实时日志 */}
          {activeTab === 'realtime' && (
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {filteredLogs.length === 0 ? (
                <div className="text-center text-gray-400 py-8">
                  暂无日志
                </div>
              ) : (
                filteredLogs.map((log) => (
                  <div
                    key={log.id}
                    className={`rounded-lg p-3 ${typeColors[log.type as keyof typeof typeColors] || typeColors.info}`}
                  >
                    <div 
                      className="flex items-center justify-between cursor-pointer"
                      onClick={() => log.content && toggleExpand(log.id)}
                    >
                      <div className="flex items-center gap-2">
                        <span>{typeIcons[log.type as keyof typeof typeIcons] || '📝'}</span>
                        <span className="font-medium">{log.title}</span>
                        <span className="text-xs opacity-70">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      {log.content && (
                        expandedLogs.has(log.id) 
                          ? <ChevronUp className="w-4 h-4" />
                          : <ChevronDown className="w-4 h-4" />
                      )}
                    </div>
                    {log.content && expandedLogs.has(log.id) && (
                      <pre className="mt-2 text-xs opacity-80 whitespace-pre-wrap break-all bg-white/50 p-2 rounded max-h-60 overflow-auto">
                        {log.content}
                      </pre>
                    )}
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          )}

          {/* 本地文件日志 */}
          {activeTab === 'files' && (
            <div className="flex-1 overflow-y-auto p-4">
              {aiLogs.length === 0 ? (
                <div className="text-center text-gray-400 py-8">
                  暂无AI日志文件
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="text-sm text-gray-500 mb-2">
                    共 {aiLogs.length} 条记录
                  </div>
                  {aiLogs.map((log, idx) => (
                    <div
                      key={idx}
                      className={`rounded-lg p-3 cursor-pointer hover:shadow-md transition-shadow ${
                        selectedLog?.requestId === log.requestId 
                          ? 'bg-blue-50 border-2 border-blue-300' 
                          : 'bg-gray-50'
                      }`}
                      onClick={() => setSelectedLog(log)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            log.type.includes('error') ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                          }`}>
                            {log.type}
                          </span>
                          <span className="font-medium">{log.model || 'Unknown'}</span>
                          <span className="text-xs text-gray-500">
                            {new Date(log.savedAt).toLocaleString()}
                          </span>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            downloadFile('ai_logs.jsonl');
                          }}
                          className="p-1 hover:bg-blue-100 rounded"
                          title="下载日志"
                        >
                          <Download className="w-4 h-4 text-blue-600" />
                        </button>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        RequestID: {log.requestId}
                        {log.response?.duration && ` | 耗时: ${log.response.duration}ms`}
                        {log.response?.usage && ` | Tokens: ${log.response.usage.total_tokens || 'N/A'}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* 详情面板 */}
              {selectedLog && (
                <div className="mt-4 border-t pt-4">
                  <div className="flex items-center gap-2 mb-3">
                    <h3 className="font-bold text-lg">日志详情</h3>
                    <span className="text-xs text-gray-500">RequestID: {selectedLog.requestId}</span>
                  </div>
                  
                  <div className="space-y-3 text-sm">
                    {/* 请求信息 */}
                    <div className="bg-blue-50 rounded-lg p-3">
                      <div className="font-medium text-blue-800 mb-2">📤 请求</div>
                      <pre className="text-xs overflow-auto max-h-40 whitespace-pre-wrap">
                        {JSON.stringify(selectedLog.request, null, 2)}
                      </pre>
                    </div>

                    {/* 响应信息 */}
                    <div className="bg-purple-50 rounded-lg p-3">
                      <div className="font-medium text-purple-800 mb-2">📥 响应</div>
                      <div className="text-xs mb-2">
                        状态: {selectedLog.response?.status} | 
                        耗时: {selectedLog.response?.duration}ms |
                        Tokens: {selectedLog.response?.usage?.total_tokens || 'N/A'}
                      </div>
                      <div className="text-xs mb-2">
                        Response ID: {selectedLog.response?.id || 'N/A'}
                      </div>
                      <details className="mt-2">
                        <summary className="cursor-pointer text-purple-600">查看原始响应</summary>
                        <pre className="mt-2 text-xs overflow-auto max-h-60 whitespace-pre-wrap bg-white p-2 rounded">
                          {JSON.stringify(selectedLog.response?.parsed || selectedLog.response?.rawResponse, null, 2)}
                        </pre>
                      </details>
                    </div>

                    {/* AI原始输出 */}
                    {selectedLog.response?.parsed?.choices?.[0]?.message?.content && (
                      <div className="bg-green-50 rounded-lg p-3">
                        <div className="font-medium text-green-800 mb-2">🤖 AI输出</div>
                        <pre className="text-xs overflow-auto max-h-60 whitespace-pre-wrap">
                          {selectedLog.response.parsed.choices[0].message.content}
                        </pre>
                      </div>
                    )}

                    {/* 错误信息 */}
                    {selectedLog.error && (
                      <div className="bg-red-50 rounded-lg p-3">
                        <div className="font-medium text-red-800 mb-2">❌ 错误</div>
                        <pre className="text-xs text-red-600 whitespace-pre-wrap">
                          {selectedLog.error}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
