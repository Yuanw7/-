import { useState, useCallback } from 'react';
import Header from './components/Header';
import UploadZone from './components/UploadZone';
import ImagePreview from './components/ImagePreview';
import SuggestionList from './components/SuggestionList';
import RoomModel2D from './components/RoomModel2D';
import LogPanel from './components/LogPanel';
import { ElderlyHomeAgent } from './agent/ElderlyHomeAgent';
import { UploadedImage, AnalysisResult, ModificationSuggestion } from './types';

export default function App() {
  const [uploadedImage, setUploadedImage] = useState<UploadedImage | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [suggestions, setSuggestions] = useState<ModificationSuggestion[]>([]);
  const [summary, setSummary] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showModel, setShowModel] = useState(false);
  const [showLogPanel, setShowLogPanel] = useState(false);

  const agent = new ElderlyHomeAgent();

  const handleImageUpload = useCallback(async (image: UploadedImage) => {
    setUploadedImage(image);
    setIsLoading(true);
    setError(null);
    setAnalysis(null);
    setSuggestions([]);
    setSummary('');

    try {
      const result = await agent.analyzeRoom(image.preview);
      setAnalysis(result.analysis);
      setSuggestions(result.suggestions);
      setSummary(result.summary || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败，请重试');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleRemove = useCallback(() => {
    if (uploadedImage?.preview) {
      URL.revokeObjectURL(uploadedImage.preview);
    }
    setUploadedImage(null);
    setAnalysis(null);
    setSuggestions([]);
    setSummary('');
    setError(null);
  }, [uploadedImage]);

  const handleReset = useCallback(() => {
    handleRemove();
  }, [handleRemove]);

  const handleViewModel = useCallback(() => {
    setShowModel(true);
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <Header />

        <UploadZone onImageUpload={handleImageUpload} isLoading={isLoading} />

        {uploadedImage && !isLoading && (
          <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <ImagePreview
                image={uploadedImage}
                onRemove={handleRemove}
                onReset={handleReset}
              />
              {analysis && (
                <div className="mt-4 p-4 bg-white rounded-lg shadow-md">
                  <h3 className="text-lg font-semibold mb-2">房间分析</h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-gray-500">房间类型：</span>
                      <span className="font-medium">{getRoomTypeLabel(analysis.roomType)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">安全评分：</span>
                      <span className={`font-medium ${analysis.overallScore >= 80 ? 'text-green-600' : analysis.overallScore >= 60 ? 'text-yellow-600' : 'text-red-600'}`}>
                        {analysis.overallScore}分
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">房间尺寸：</span>
                      <span className="font-medium">{Math.round(analysis.dimensions.width / 1000)}×{Math.round(analysis.dimensions.length / 1000)}×{Math.round(analysis.dimensions.height / 1000)}米</span>
                    </div>
                    <div>
                      <span className="text-gray-500">检测元素：</span>
                      <span className="font-medium">{analysis.elements.length}项</span>
                    </div>
                    <div>
                      <span className="text-gray-500">安全隐患：</span>
                      <span className="font-medium text-red-600">{analysis.hazards.length}处</span>
                    </div>
                    <div>
                      <span className="text-gray-500">光照条件：</span>
                      <span className="font-medium">{analysis.lightingLevel === 'good' ? '良好' : analysis.lightingLevel === 'fair' ? '一般' : '较差'}</span>
                    </div>
                  </div>
                  {summary && (
                    <div className="mt-4 p-3 bg-blue-50 rounded-lg">
                      <h4 className="text-sm font-medium text-blue-800 mb-1">总体评估</h4>
                      <p className="text-sm text-blue-700">{summary}</p>
                    </div>
                  )}
                  <button
                    onClick={handleViewModel}
                    className="mt-4 w-full py-2 px-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    查看2D/3D模型
                  </button>
                </div>
              )}
            </div>

            <div>
              {suggestions.length > 0 && (
                <SuggestionList suggestions={suggestions} regulations={agent.getAllRegulations()} />
              )}
            </div>
          </div>
        )}

        {error && (
          <div className="w-full max-w-4xl mx-auto mt-6 p-4 bg-red-50 border border-red-200 rounded-xl">
            <p className="text-red-600 text-center">{error}</p>
          </div>
        )}

        {showModel && analysis && (
          <RoomModel2D
            analysis={analysis}
            onClose={() => setShowModel(false)}
          />
        )}

        <footer className="text-center mt-12 text-sm text-gray-400">
          <p>上传房间照片，智能分析老年人居住安全风险并提供改造建议</p>
        </footer>

        {/* 日志查看按钮 */}
        <button
          onClick={() => setShowLogPanel(true)}
          className="fixed bottom-4 right-4 p-3 bg-gray-800 text-white rounded-full shadow-lg hover:bg-gray-700 transition-colors"
          title="查看运行日志"
        >
          <span className="text-xl">📋</span>
        </button>

        {/* 日志面板 */}
        {showLogPanel && <LogPanel onClose={() => setShowLogPanel(false)} />}
      </div>
    </div>
  );
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
