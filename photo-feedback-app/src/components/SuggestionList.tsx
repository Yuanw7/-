import { useState } from 'react';
import { ModificationSuggestion, Regulation } from '../types';

interface SuggestionListProps {
  suggestions: ModificationSuggestion[];
  regulations: Regulation[];
}

export default function SuggestionList({ suggestions, regulations }: SuggestionListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterPriority, setFilterPriority] = useState<string>('全部');

  const filteredSuggestions = filterPriority === '全部'
    ? suggestions
    : suggestions.filter(s => s.priority === filterPriority);

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case '紧急': return 'bg-red-100 text-red-700 border-red-200';
      case '重要': return 'bg-orange-100 text-orange-700 border-orange-200';
      case '一般': return 'bg-blue-100 text-blue-700 border-blue-200';
      default: return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case '无障碍改造': return '♿';
      case '安全加固': return '🛡️';
      case '空间优化': return '📐';
      case '设备升级': return '⚙️';
      case '照明改善': return '💡';
      default: return '📋';
    }
  };

  const getRegulationInfo = (regIds: string[]) => {
    return regIds.map(id => {
      const reg = regulations.find(r => r.id === id);
      return reg ? `${reg.code} - ${reg.title}` : id;
    });
  };

  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-800">改造建议</h2>
        <div className="flex gap-2">
          {['全部', '紧急', '重要', '一般'].map(p => (
            <button
              key={p}
              onClick={() => setFilterPriority(p)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                filterPriority === p
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        {filteredSuggestions.map((suggestion, index) => (
          <div
            key={suggestion.id}
            className="border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow"
          >
            <div
              className="p-4 cursor-pointer flex items-start gap-4"
              onClick={() => setExpandedId(expandedId === suggestion.id ? null : suggestion.id)}
            >
              <span className="text-2xl">{getCategoryIcon(suggestion.category)}</span>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getPriorityColor(suggestion.priority)}`}>
                    {suggestion.priority}
                  </span>
                  <span className="text-sm text-gray-500">{suggestion.category}</span>
                </div>
                <h3 className="font-semibold text-gray-800">{suggestion.title}</h3>
                <p className="text-sm text-gray-600 mt-1 line-clamp-2">{suggestion.description}</p>
                <div className="flex items-center gap-4 mt-2 text-sm">
                  <span className="text-gray-500">
                    预算: ¥{suggestion.estimatedCost.min.toLocaleString()} - ¥{suggestion.estimatedCost.max.toLocaleString()}
                  </span>
                  <span className="text-gray-500">难度: {suggestion.difficulty}</span>
                </div>
              </div>
              <span className="text-gray-400">
                {expandedId === suggestion.id ? '▲' : '▼'}
              </span>
            </div>

            {expandedId === suggestion.id && (
              <div className="px-4 pb-4 pt-0 border-t border-gray-100 bg-gray-50">
                <div className="mt-4 space-y-4">
                  <div>
                    <h4 className="font-medium text-gray-700 mb-2">改造步骤</h4>
                    <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600">
                      {suggestion.steps.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                  </div>

                  {suggestion.materials && (
                    <div>
                      <h4 className="font-medium text-gray-700 mb-2">所需材料</h4>
                      <div className="flex flex-wrap gap-2">
                        {suggestion.materials.map((material, i) => (
                          <span key={i} className="px-2 py-1 bg-white border border-gray-200 rounded text-sm text-gray-600">
                            {material}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {suggestion.relatedRegulations && (
                    <div>
                      <h4 className="font-medium text-gray-700 mb-2">相关规范</h4>
                      <div className="space-y-1">
                        {getRegulationInfo(suggestion.relatedRegulations).map((info, i) => (
                          <p key={i} className="text-sm text-gray-600 bg-blue-50 px-3 py-2 rounded">
                            {info}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {suggestion.warnings && (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                      <h4 className="font-medium text-yellow-800 mb-2">⚠️ 注意事项</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-yellow-700">
                        {suggestion.warnings.map((warning, i) => (
                          <li key={i}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {filteredSuggestions.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          暂无符合条件的改造建议
        </div>
      )}
    </div>
  );
}
