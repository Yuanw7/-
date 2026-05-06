import { Home, Shield } from 'lucide-react';

export default function Header() {
  return (
    <header className="text-center mb-10 animate-fade-in-up">
      <div className="inline-flex items-center gap-3 mb-4">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center shadow-lg">
          <Home className="w-6 h-6 text-white" />
        </div>
        <h1 className="font-display text-4xl font-bold bg-gradient-to-r from-blue-600 to-blue-800 bg-clip-text text-transparent">
          老年人房屋改造智能分析
        </h1>
      </div>
      <p className="text-slate-500 text-lg max-w-2xl mx-auto">
        基于国家无障碍设计规范，智能识别安全隐患，为老年人提供专业改造建议
      </p>
    </header>
  );
}
