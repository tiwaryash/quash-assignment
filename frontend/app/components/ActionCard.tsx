'use client';

interface ActionCardProps {
  action: string;
  status: string;
  step?: number;
  total?: number;
  details?: any;
  result?: any;
}

export default function ActionCard({ action, status, step, total, details, result }: ActionCardProps) {
  const getStatusConfig = () => {
    switch (status) {
      case 'executing':
        return {
          bg: 'bg-gradient-to-r from-amber-500/20 to-yellow-500/20',
          border: 'border-amber-500/50',
          text: 'text-amber-300',
          icon: '⏳',
          iconBg: 'bg-amber-500/20',
          pulse: true
        };
      case 'completed':
        return {
          bg: 'bg-gradient-to-r from-emerald-500/20 to-green-500/20',
          border: 'border-emerald-500/50',
          text: 'text-emerald-300',
          icon: '✅',
          iconBg: 'bg-emerald-500/20',
          pulse: false
        };
      case 'error':
        return {
          bg: 'bg-gradient-to-r from-red-500/20 to-rose-500/20',
          border: 'border-red-500/50',
          text: 'text-red-300',
          icon: '❌',
          iconBg: 'bg-red-500/20',
          pulse: false
        };
      default:
        return {
          bg: 'bg-slate-800/50',
          border: 'border-slate-600',
          text: 'text-slate-300',
          icon: '📋',
          iconBg: 'bg-slate-600/20',
          pulse: false
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div className={`animate-slide-in border rounded-xl p-4 mb-3 ${config.bg} ${config.border} ${config.pulse ? 'pulse-glow' : ''}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg ${config.iconBg} flex items-center justify-center text-xl`}>
            {config.icon}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className={`font-semibold capitalize ${config.text} text-base`}>
                {action.replace('_', ' ')}
              </span>
              {step && total && (
                <span className="text-xs text-slate-400 bg-slate-700/50 px-2 py-0.5 rounded-full">
                  {step}/{total}
                </span>
              )}
            </div>
            {details?.selector && (
              <div className="text-xs text-slate-400 mt-1 font-mono">
                {details.selector}
              </div>
            )}
          </div>
        </div>
        <span className={`text-xs font-medium px-3 py-1 rounded-full ${config.text} ${config.iconBg} capitalize`}>
          {status}
        </span>
      </div>
      
      {details && (
        <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-2 text-sm">
          {details.url && (
            <div className="flex items-center gap-2">
              <span className="text-slate-400">URL:</span>
              <code className="text-blue-300 bg-slate-800/50 px-2 py-1 rounded font-mono text-xs">
                {details.url}
              </code>
            </div>
          )}
          {details.text && (
            <div className="flex items-center gap-2">
              <span className="text-slate-400">Text:</span>
              <span className="text-slate-300">{details.text}</span>
            </div>
          )}
        </div>
      )}
      
      {result && result.error && (
        <div className="mt-3 pt-3 border-t border-red-500/30 space-y-2">
          <div className="text-sm text-red-300 bg-red-500/10 p-2 rounded-lg">
            <span className="font-semibold">Error: </span>
            {result.error}
          </div>
          {result.suggestions && result.suggestions.length > 0 && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
              <div className="text-xs font-semibold text-blue-300 mb-2">💡 Suggested selectors:</div>
              <div className="flex flex-wrap gap-2">
                {result.suggestions.map((suggestion: string, idx: number) => (
                  <code key={idx} className="text-xs bg-slate-800/50 text-blue-200 px-2 py-1 rounded border border-blue-500/30">
                    {suggestion}
                  </code>
                ))}
              </div>
            </div>
          )}
          {result.alternatives && result.alternatives.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
              <div className="text-xs font-semibold text-amber-300 mb-2">🔄 Common alternatives:</div>
              <div className="flex flex-wrap gap-2">
                {result.alternatives.map((alt: string, idx: number) => (
                  <code key={idx} className="text-xs bg-slate-800/50 text-amber-200 px-2 py-1 rounded border border-amber-500/30">
                    {alt}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      
      {result && result.data && Array.isArray(result.data) && result.data.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-700/50">
          <div className="text-sm font-semibold mb-2 text-emerald-300">
            ✨ Extracted {result.count || result.data.length} item{result.data.length !== 1 ? 's' : ''}
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3 max-h-64 overflow-y-auto">
            <div className="space-y-2">
              {result.data.slice(0, 5).map((item: any, idx: number) => (
                <div key={idx} className="bg-slate-800/50 p-2 rounded text-xs">
                  <pre className="text-slate-300 whitespace-pre-wrap">
                    {JSON.stringify(item, null, 2)}
                  </pre>
                </div>
              ))}
              {result.data.length > 5 && (
                <div className="text-xs text-slate-400 text-center pt-2">
                  ... and {result.data.length - 5} more
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
