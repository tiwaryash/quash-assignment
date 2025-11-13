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
      
      {result && result.status === 'success' && result.data && Array.isArray(result.data) && result.data.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-700/50">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold text-emerald-300">
              ✨ Extracted {result.count || result.data.length} item{result.data.length !== 1 ? 's' : ''}
            </div>
            {result.filtered && result.max_price && (
              <div className="text-xs text-amber-300 bg-amber-500/10 px-2 py-1 rounded">
                Filtered: Under ₹{result.max_price.toLocaleString('en-IN')}
              </div>
            )}
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3 max-h-96 overflow-y-auto">
            <div className="space-y-3">
              {result.data.map((item: any, idx: number) => (
                <div key={idx} className="bg-slate-800/50 p-3 rounded-lg border border-slate-700/50 hover:border-slate-600/50 transition-colors">
                  <div className="space-y-2">
                    {/* Item Number and Name */}
                    <div className="flex items-start gap-2">
                      <div className="text-xs font-semibold text-slate-500 min-w-[24px]">#{idx + 1}</div>
                      <div className="flex-1">
                        {item.name && (
                          <div className="font-semibold text-slate-200 text-sm leading-tight">{item.name}</div>
                        )}
                        {item.title && !item.name && (
                          <div className="font-semibold text-slate-200 text-sm leading-tight">{item.title}</div>
                        )}
                        {!item.name && !item.title && (
                          <div className="font-semibold text-slate-400 text-sm italic">Item {idx + 1}</div>
                        )}
                      </div>
                    </div>
                    
                    {/* Metrics Row */}
                    <div className="flex items-center gap-2 text-xs flex-wrap">
                      {item.rating && (
                        <div className="flex items-center gap-1 text-amber-400 bg-amber-500/10 px-2 py-1 rounded">
                          <span>⭐</span>
                          <span>{typeof item.rating === 'number' ? item.rating.toFixed(1) : item.rating}</span>
                          {item.reviews && (
                            <span className="text-slate-400 ml-1">
                              ({typeof item.reviews === 'number' ? item.reviews.toLocaleString('en-IN') : item.reviews})
                            </span>
                          )}
                        </div>
                      )}
                      {item.price && (
                        <div className="flex items-center gap-1 text-emerald-400 font-medium bg-emerald-500/10 px-2 py-1 rounded">
                          <span>💰</span>
                          <span>{typeof item.price === 'string' ? item.price : `₹${typeof item.price === 'number' ? item.price.toLocaleString('en-IN') : item.price}`}</span>
                        </div>
                      )}
                      {item.category && (
                        <div className="flex items-center gap-1 text-purple-400 bg-purple-500/10 px-2 py-1 rounded">
                          <span>🏷️</span>
                          <span>{item.category}</span>
                        </div>
                      )}
                    </div>
                    
                    {/* Location (for local discovery results) */}
                    {(item.location || item.address) && (
                      <div className="flex items-center gap-1 text-xs text-slate-400 bg-slate-700/30 px-2 py-1 rounded">
                        <span>📍</span>
                        <span>{item.location || item.address}</span>
                      </div>
                    )}
                    
                    {/* Additional metadata */}
                    {item.delivery_available && (
                      <div className="flex items-center gap-1 text-xs text-green-400 bg-green-500/10 px-2 py-1 rounded w-fit">
                        <span>🛵</span>
                        <span>Delivery Available</span>
                      </div>
                    )}
                    
                    {/* Link */}
                    {(item.link || item.url) && (
                      <div className="mt-2 pt-2 border-t border-slate-700/30">
                        <a 
                          href={item.link || item.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-xs text-blue-400 hover:text-blue-300 underline break-all inline-flex items-center gap-1"
                          title={item.link || item.url}
                        >
                          <span>🔗</span>
                          <span className="truncate max-w-[400px]">{item.link || item.url}</span>
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      
      {/* Show when extraction completed but no data */}
      {result && result.status === 'success' && (!result.data || !Array.isArray(result.data) || result.data.length === 0) && action === 'extract' && (
        <div className="mt-3 pt-3 border-t border-slate-700/50">
          <div className="text-sm text-amber-300 bg-amber-500/10 p-3 rounded-lg">
            ⚠️ Extraction completed but no data found. The selectors might not match the page structure.
          </div>
          {result.message && (
            <div className="text-xs text-slate-400 mt-2">{result.message}</div>
          )}
          {result.count === 0 && (
            <div className="text-xs text-slate-400 mt-2">
              Try checking the page structure or using different selectors.
            </div>
          )}
          {/* Always show debug info when empty */}
          <details className="mt-3 text-xs">
            <summary className="text-slate-400 cursor-pointer hover:text-slate-300">🔍 Show Debug Info</summary>
            <pre className="mt-2 bg-slate-900/50 p-2 rounded text-slate-300 overflow-auto max-h-40 text-[10px]">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
      
      {/* Show result info even if data is empty */}
      {result && status === 'completed' && action !== 'extract' && (
        <div className="mt-2 text-xs text-slate-400">
          {result.status && <span>Status: {result.status}</span>}
          {result.count !== undefined && <span className="ml-2">Count: {result.count}</span>}
        </div>
      )}
    </div>
  );
}
