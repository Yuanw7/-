interface ScoreBarProps {
  score: number;
  color: string;
  delay?: number;
}

export default function ScoreBar({ score, color, delay = 0 }: ScoreBarProps) {
  const getScoreColor = (score: number) => {
    if (score >= 8) return 'from-green-400 to-green-500';
    if (score >= 6) return 'from-amber-400 to-amber-500';
    return 'from-red-400 to-red-500';
  };

  return (
    <div className="flex items-center gap-3">
      <div className="relative w-32 h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`absolute inset-y-0 left-0 bg-gradient-to-r ${getScoreColor(score)} rounded-full transition-all duration-700 ease-out`}
          style={{
            width: `${score * 10}%`,
            animationDelay: `${delay}ms`,
          }}
        />
      </div>
      <span
        className="font-mono text-lg font-bold w-8"
        style={{ color }}
      >
        {score}
      </span>
      <span className="text-sm text-slate-400">/ 10</span>
    </div>
  );
}
