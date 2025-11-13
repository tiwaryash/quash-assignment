'use client';

import { 
  Loader2, 
  CheckCircle2, 
  XCircle, 
  FileText,
  Star,
  DollarSign,
  MapPin,
  Tag,
  Truck,
  Link as LinkIcon,
  ExternalLink,
  Lightbulb,
  RotateCw,
  AlertTriangle
} from 'lucide-react';

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
          bg: 'bg-black/50',
          border: 'border-yellow-500/50',
          text: 'text-yellow-500',
          icon: <Loader2 className="w-6 h-6 animate-spin" />,
          iconBg: 'bg-yellow-500/20',
          badgeBg: 'bg-yellow-500/20',
          pulse: true
        };
      case 'completed':
        return {
          bg: 'bg-black/50',
          border: 'border-green-500/50',
          text: 'text-green-400',
          icon: <CheckCircle2 className="w-6 h-6" />,
          iconBg: 'bg-green-500/20',
          badgeBg: 'bg-green-500/20',
          pulse: false
        };
      case 'error':
        return {
          bg: 'bg-black/50',
          border: 'border-red-500/50',
          text: 'text-red-400',
          icon: <XCircle className="w-6 h-6" />,
          iconBg: 'bg-red-500/20',
          badgeBg: 'bg-red-500/20',
          pulse: false
        };
      default:
        return {
          bg: 'bg-black/50',
          border: 'border-yellow-500/30',
          text: 'text-yellow-500/70',
          icon: <FileText className="w-6 h-6" />,
          iconBg: 'bg-yellow-500/10',
          badgeBg: 'bg-yellow-500/10',
          pulse: false
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div className={`animate-slide-in-left border-2 rounded-xl p-3 mb-2 ${config.bg} ${config.border} ${config.pulse ? 'pulse-glow' : ''} transition-all`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-8 h-8 rounded-lg ${config.iconBg} flex items-center justify-center ${config.text} border border-current/30`}>
            <div className="scale-75">
              {config.icon}
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className={`font-black capitalize ${config.text} text-sm`}>
                {action.replace('_', ' ')}
              </span>
              {step && total && (
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${config.text} ${config.badgeBg} border-current/30`}>
                  {step}/{total}
                </span>
              )}
            </div>
            {details?.selector && (
              <div className="text-xs text-yellow-500/60 mt-0.5 font-mono bg-black/50 px-2 py-0.5 rounded border border-yellow-500/20 inline-block">
                {details.selector}
              </div>
            )}
          </div>
        </div>
        <span className={`text-xs font-black px-3 py-1 rounded-full ${config.text} ${config.badgeBg} capitalize border border-current/30`}>
          {status}
        </span>
      </div>
      
      {details && (
        <div className="mt-2 pt-2 border-t border-yellow-500/20 space-y-1 text-xs">
          {details.url && (
            <div className="flex items-center gap-2">
              <span className="text-yellow-500/60 font-semibold">URL:</span>
              <code className="text-yellow-500 bg-black/50 px-2 py-1 rounded font-mono text-xs border border-yellow-500/20">
                {details.url}
              </code>
            </div>
          )}
          {details.text && (
            <div className="flex items-center gap-2">
              <span className="text-yellow-500/60 font-semibold">Text:</span>
              <span className="text-yellow-500 font-medium">{details.text}</span>
            </div>
          )}
        </div>
      )}
      
      {result && result.error && (
        <div className="mt-4 pt-4 border-t border-red-500/30 space-y-3">
          <div className="text-sm text-red-300 bg-red-500/10 p-3 rounded-xl border border-red-500/30 font-medium">
            <span className="font-black">Error: </span>
            {result.error}
          </div>
          {result.suggestions && result.suggestions.length > 0 && (
            <div className="bg-yellow-500/10 border-2 border-yellow-500/30 rounded-xl p-4">
              <div className="flex items-center gap-2 text-xs font-black text-yellow-500 mb-3">
                <Lightbulb className="w-4 h-4" />
                Suggested selectors:
              </div>
              <div className="flex flex-wrap gap-2">
                {result.suggestions.map((suggestion: string, idx: number) => (
                  <code key={idx} className="text-xs bg-black/50 text-yellow-400 px-3 py-1.5 rounded-lg border border-yellow-500/30 font-mono">
                    {suggestion}
                  </code>
                ))}
              </div>
            </div>
          )}
          {result.alternatives && result.alternatives.length > 0 && (
            <div className="bg-orange-500/10 border-2 border-orange-500/30 rounded-xl p-4">
              <div className="flex items-center gap-2 text-xs font-black text-orange-400 mb-3">
                <RotateCw className="w-4 h-4" />
                Common alternatives:
              </div>
              <div className="flex flex-wrap gap-2">
                {result.alternatives.map((alt: string, idx: number) => (
                  <code key={idx} className="text-xs bg-black/50 text-orange-300 px-3 py-1.5 rounded-lg border border-orange-500/30 font-mono">
                    {alt}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      
      {result && result.status === 'success' && result.data && Array.isArray(result.data) && result.data.length > 0 && (
        <div className="mt-2 pt-2 border-t border-yellow-500/20">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5 text-xs font-black text-green-400">
              <CheckCircle2 className="w-4 h-4" />
              Extracted {result.count || result.data.length} item{result.data.length !== 1 ? 's' : ''}
            </div>
            {result.filtered && result.max_price && (
              <div className="text-xs text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded-full font-bold border border-yellow-500/30">
                Under ₹{result.max_price.toLocaleString('en-IN')}
              </div>
            )}
          </div>
          <div className="bg-black/60 rounded-xl p-2 max-h-64 overflow-y-auto border border-yellow-500/20">
            <div className="space-y-2">
              {result.data.map((item: any, idx: number) => (
                <div key={idx} className="bg-black/50 p-2 rounded-lg border border-yellow-500/30 hover:border-yellow-500/50 transition-all hover-lift">
                  <div className="space-y-1.5">
                    {/* Item Number and Name */}
                    <div className="flex items-start gap-2">
                      <div className="text-xs font-black text-yellow-500/60 min-w-[24px] bg-yellow-500/10 px-1.5 py-0.5 rounded border border-yellow-500/20">
                        #{idx + 1}
                      </div>
                      <div className="flex-1">
                        {item.name && (
                          <div className="font-black text-yellow-500 text-xs leading-tight">{item.name}</div>
                        )}
                        {item.title && !item.name && (
                          <div className="font-black text-yellow-500 text-xs leading-tight">{item.title}</div>
                        )}
                        {!item.name && !item.title && (
                          <div className="font-black text-yellow-500/40 text-xs italic">Item {idx + 1}</div>
                        )}
                      </div>
                    </div>
                    
                    {/* Metrics Row */}
                    <div className="flex items-center gap-1.5 text-xs flex-wrap">
                      {item.rating && (
                        <div className="flex items-center gap-1 text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded font-bold border border-yellow-500/30">
                          <Star className="w-3 h-3 fill-yellow-500" />
                          <span>{typeof item.rating === 'number' ? item.rating.toFixed(1) : item.rating}</span>
                          {item.reviews && (
                            <span className="text-yellow-500/60">
                              ({typeof item.reviews === 'number' ? item.reviews.toLocaleString('en-IN') : item.reviews})
                            </span>
                          )}
                        </div>
                      )}
                      {item.price && (
                        <div className="flex items-center gap-1 text-green-400 font-black bg-green-500/10 px-2 py-1 rounded border border-green-500/30">
                          <DollarSign className="w-3 h-3" />
                          <span>{typeof item.price === 'string' ? item.price : `₹${typeof item.price === 'number' ? item.price.toLocaleString('en-IN') : item.price}`}</span>
                        </div>
                      )}
                      {item.category && (
                        <div className="flex items-center gap-1 text-purple-400 bg-purple-500/10 px-2 py-1 rounded font-bold border border-purple-500/30">
                          <Tag className="w-3 h-3" />
                          <span>{item.category}</span>
                        </div>
                      )}
                    </div>
                    
                    {/* Location */}
                    {(item.location || item.address) && (
                      <div className="flex items-center gap-1 text-xs text-blue-400 bg-blue-500/10 px-2 py-1 rounded font-medium border border-blue-500/30 w-fit">
                        <MapPin className="w-3 h-3" />
                        <span>{item.location || item.address}</span>
                      </div>
                    )}
                    
                    {/* Additional metadata */}
                    {item.delivery_available && (
                      <div className="flex items-center gap-1 text-xs text-green-400 bg-green-500/10 px-2 py-1 rounded w-fit font-bold border border-green-500/30">
                        <Truck className="w-3 h-3" />
                        <span>Delivery</span>
                      </div>
                    )}
                    
                    {/* Link */}
                    {(item.link || item.url) && (
                      <div className="mt-1.5 pt-1.5 border-t border-yellow-500/20">
                        <a 
                          href={item.link || item.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="group text-xs text-yellow-500 hover:text-yellow-400 font-medium break-all inline-flex items-center gap-1.5 bg-yellow-500/5 px-2 py-1 rounded border border-yellow-500/30 hover:border-yellow-500/50 transition-all"
                          title={item.link || item.url}
                        >
                          <ExternalLink className="w-3 h-3 flex-shrink-0 group-hover:scale-110 transition-transform" />
                          <span className="truncate max-w-[300px]">{item.link || item.url}</span>
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
        <div className="mt-4 pt-4 border-t border-yellow-500/20">
          <div className="flex items-start gap-2 text-sm text-orange-400 bg-orange-500/10 p-4 rounded-xl border border-orange-500/30 font-medium">
            <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span>Extraction completed but no data found. The selectors might not match the page structure.</span>
          </div>
          {result.message && (
            <div className="text-xs text-yellow-500/60 mt-2 font-medium">{result.message}</div>
          )}
          {result.count === 0 && (
            <div className="text-xs text-yellow-500/60 mt-2 font-medium">
              Try checking the page structure or using different selectors.
            </div>
          )}
          {/* Always show debug info when empty */}
          <details className="mt-3 text-xs">
            <summary className="text-yellow-500/60 cursor-pointer hover:text-yellow-500 font-bold flex items-center gap-2">
              <FileText className="w-3.5 h-3.5" />
              Show Debug Info
            </summary>
            <pre className="mt-2 bg-black/60 p-3 rounded-lg text-yellow-500/80 overflow-auto max-h-40 text-[10px] border border-yellow-500/20 font-mono">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
      
      {/* Show result info even if data is empty */}
      {result && status === 'completed' && action !== 'extract' && (
        <div className="mt-2 text-xs text-yellow-500/60 font-medium">
          {result.status && <span>Status: {result.status}</span>}
          {result.count !== undefined && <span className="ml-2">Count: {result.count}</span>}
        </div>
      )}
    </div>
  );
}
