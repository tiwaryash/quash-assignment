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
  const getStatusColor = () => {
    switch (status) {
      case 'executing':
        return 'bg-yellow-100 border-yellow-300 text-yellow-800';
      case 'completed':
        return 'bg-green-100 border-green-300 text-green-800';
      case 'error':
        return 'bg-red-100 border-red-300 text-red-800';
      default:
        return 'bg-gray-100 border-gray-300 text-gray-800';
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case 'executing':
        return '⏳';
      case 'completed':
        return '✅';
      case 'error':
        return '❌';
      default:
        return '📋';
    }
  };

  return (
    <div className={`border rounded-lg p-3 mb-2 ${getStatusColor()}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span>{getStatusIcon()}</span>
          <span className="font-semibold capitalize">{action}</span>
          {step && total && (
            <span className="text-sm opacity-75">({step}/{total})</span>
          )}
        </div>
        <span className="text-sm capitalize">{status}</span>
      </div>
      
      {details && (
        <div className="mt-2 text-sm opacity-75">
          {details.selector && <div>Selector: <code className="bg-white/50 px-1 rounded">{details.selector}</code></div>}
          {details.url && <div>URL: <code className="bg-white/50 px-1 rounded">{details.url}</code></div>}
          {details.text && <div>Text: {details.text}</div>}
        </div>
      )}
      
      {result && result.error && (
        <div className="mt-2 text-sm font-medium">
          Error: {result.error}
        </div>
      )}
      
      {result && result.data && (
        <div className="mt-2 text-sm">
          <div className="font-medium mb-1">Extracted data:</div>
          <pre className="bg-white/50 p-2 rounded text-xs overflow-auto">
            {JSON.stringify(result.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

