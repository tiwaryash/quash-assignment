'use client';

import { useState, useEffect, useRef } from 'react';
import ActionCard from './ActionCard';

interface Message {
  type: string;
  message?: string;
  timestamp: number;
  action?: string;
  status?: string;
  step?: number;
  total?: number;
  details?: any;
  result?: any;
  data?: any;
  suggestions?: string[];
  selector?: string;
  question?: string;
  options?: Array<{value: string; label: string}>;
  field?: string;
  context?: string;
  clarification_type?: string;
  block_type?: string;
  alternatives?: string[];
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket('ws://localhost:8000/ws');
      
      ws.onopen = () => {
        setConnected(true);
        setMessages(prev => [...prev, {
          type: 'system',
          message: 'Connected to server',
          timestamp: Date.now()
        }]);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'status' && data.message?.includes('Planning')) {
          setIsLoading(true);
        }
        
        if (data.type === 'status' && data.message?.includes('completed')) {
          setIsLoading(false);
        }
        
        setMessages(prev => [...prev, {
          ...data,
          timestamp: Date.now()
        }]);
      };

      ws.onerror = (error) => {
        setConnected(false);
        setIsLoading(false);
      };

      ws.onclose = () => {
        setConnected(false);
        setIsLoading(false);
        setMessages(prev => [...prev, {
          type: 'system',
          message: 'Disconnected from server. Reconnecting...',
          timestamp: Date.now()
        }]);
        
        // Reconnect after 3 seconds
        setTimeout(connect, 3000);
      };

      wsRef.current = ws;
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const sendMessage = (clarificationValue?: string, clarificationType?: string) => {
    const messageToSend = clarificationValue || input.trim();
    if (messageToSend && wsRef.current && connected) {
      const payload: any = { instruction: messageToSend };
      if (clarificationValue) {
        payload.is_clarification = true;
        payload.value = clarificationValue;
        if (clarificationType) {
          payload.clarification_type = clarificationType;
        }
      }
      
      wsRef.current.send(JSON.stringify(payload));
      setMessages(prev => [...prev, {
        type: 'user',
        message: messageToSend,
        timestamp: Date.now()
      }]);
      setInput('');
      setIsLoading(true);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-200px)] min-h-[600px] bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700/50 bg-slate-800/30">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${connected ? 'bg-emerald-500 pulse-glow' : 'bg-red-500'}`}></div>
          <span className="text-sm font-medium text-slate-300">
            {connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-amber-400">
            <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
            <span>Processing...</span>
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-gradient-to-b from-slate-900/50 to-slate-800/30 min-h-[400px]">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🤖</div>
            <h3 className="text-xl font-semibold text-slate-300 mb-2">Welcome to Quash Browser Agent</h3>
            <p className="text-slate-400 mb-6">Start by sending a natural language instruction</p>
            <p className="text-xs text-slate-500 mb-4">Make sure the backend server is running on port 8000</p>
            <div className="flex flex-wrap gap-2 justify-center max-w-2xl mx-auto">
              {[
                "Find MacBook Air under ₹1,00,000",
                "Find top pizza places in Indiranagar",
                "Compare laptops on Flipkart and Amazon",
                "Search for best restaurants near me"
              ].map((example, idx) => (
                <button
                  key={idx}
                  onClick={() => setInput(example)}
                  className="px-4 py-2 bg-slate-800/50 hover:bg-slate-700/50 text-slate-300 rounded-lg text-sm transition-colors border border-slate-700/50 hover:border-slate-600/50"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
        
        {messages.map((msg, idx) => {
          if (msg.type === 'user') {
            return (
              <div key={idx} className="flex justify-end animate-slide-in">
                <div className="max-w-[80%] bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-2xl rounded-br-sm px-4 py-3 shadow-lg">
                  <p className="text-sm leading-relaxed">{msg.message}</p>
                </div>
              </div>
            );
          }
          
          if (msg.type === 'action_status') {
            return (
              <ActionCard
                key={idx}
                action={msg.action || 'unknown'}
                status={msg.status || 'pending'}
                step={msg.step}
                total={msg.total}
                details={msg.details}
                result={msg.result}
              />
            );
          }
          
          if (msg.type === 'plan') {
            return (
              <div key={idx} className="animate-slide-in">
                <div className="bg-gradient-to-r from-purple-600/20 to-indigo-600/20 border border-purple-500/50 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-2xl">📋</span>
                    <span className="font-semibold text-purple-300">Action Plan</span>
                    <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-1 rounded-full">
                      {msg.data?.length || 0} steps
                    </span>
                  </div>
                  <div className="space-y-2">
                    {msg.data?.map((action: any, i: number) => (
                      <div key={i} className="flex items-center gap-3 text-sm bg-slate-800/30 p-2 rounded-lg">
                        <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-semibold">
                          {i + 1}
                        </span>
                        <span className="text-slate-300 capitalize">{action.action}</span>
                        {action.selector && (
                          <code className="text-xs text-slate-400 ml-auto font-mono">
                            {action.selector}
                          </code>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          }
          
          if (msg.type === 'error') {
            return (
              <div key={idx} className="animate-slide-in">
                <div className="bg-gradient-to-r from-red-600/20 to-rose-600/20 border border-red-500/50 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">❌</span>
                    <span className="font-semibold text-red-300">Error</span>
                  </div>
                  <div className="text-sm text-red-200 whitespace-pre-line">
                    {msg.message}
                  </div>
                  {msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-red-500/30">
                      <div className="text-xs font-semibold text-blue-300 mb-2">
                        {msg.action === 'navigate' ? '💡 Suggestions:' : '💡 Suggested selectors:'}
                      </div>
                      {msg.action === 'navigate' ? (
                        <ul className="list-disc list-inside text-xs text-blue-200 space-y-1">
                          {msg.suggestions.map((suggestion: string, i: number) => (
                            <li key={i}>{suggestion}</li>
                          ))}
                        </ul>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {msg.suggestions.map((suggestion: string, i: number) => (
                            <code key={i} className="text-xs bg-slate-800/50 text-blue-200 px-2 py-1 rounded border border-blue-500/30">
                              {suggestion}
                            </code>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {msg.message?.includes('API key') && (
                    <div className="mt-3 pt-3 border-t border-red-500/30 text-xs text-red-300">
                      💡 Make sure to set your OPENAI_API_KEY in backend/.env file
                    </div>
                  )}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'status') {
            return (
              <div key={idx} className="flex justify-center animate-slide-in">
                <div className="bg-slate-800/50 border border-slate-700/50 rounded-full px-4 py-2 text-sm text-slate-400">
                  {msg.message}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'system') {
            return (
              <div key={idx} className="flex justify-center">
                <div className="bg-slate-800/30 border border-slate-700/30 rounded-full px-4 py-2 text-xs text-slate-500">
                  {msg.message}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'clarification') {
            return (
              <div key={idx} className="animate-slide-in">
                <div className="bg-gradient-to-r from-amber-600/20 to-yellow-600/20 border border-amber-500/50 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-2xl">❓</span>
                    <span className="font-semibold text-amber-300">Question</span>
                  </div>
                  <div className="text-sm text-amber-200 mb-4">
                    {msg.question}
                  </div>
                  {msg.options && msg.options.length > 0 && (
                    <div className="space-y-2">
                      {msg.options.map((option: {value: string; label: string}, optIdx: number) => (
                        <button
                          key={optIdx}
                          onClick={() => {
                            const clarificationType = msg.clarification_type || msg.context || (msg.field === 'site' ? 'site_selection' : null);
                            sendMessage(option.value, clarificationType);
                          }}
                          className="w-full text-left px-4 py-3 bg-slate-800/50 hover:bg-slate-700/50 border border-amber-500/30 rounded-lg text-sm text-amber-200 transition-colors"
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'blocked') {
            return (
              <div key={idx} className="animate-slide-in">
                <div className="bg-gradient-to-r from-orange-600/20 to-red-600/20 border border-orange-500/50 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">🚫</span>
                    <span className="font-semibold text-orange-300">Blocked</span>
                  </div>
                  <div className="text-sm text-orange-200 whitespace-pre-line mb-3">
                    {msg.message}
                  </div>
                  {msg.alternatives && msg.alternatives.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-orange-500/30">
                      <div className="text-xs font-semibold text-orange-300 mb-2">💡 Alternatives:</div>
                      <ul className="list-disc list-inside text-xs text-orange-200 space-y-1">
                        {msg.alternatives.map((alt: string, altIdx: number) => (
                          <li key={altIdx}>{alt}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            );
          }
          
          return null;
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-slate-700/50 bg-slate-800/30">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
              placeholder={connected ? "Type your instruction... (e.g., 'Find MacBook Air under ₹1,00,000')" : "Connecting to server..."}
              className="w-full px-4 py-3 bg-slate-800/50 border border-slate-700/50 rounded-xl text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!connected || isLoading}
            />
          </div>
          <button
            onClick={() => sendMessage()}
            disabled={!connected || !input.trim() || isLoading}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white font-medium rounded-xl shadow-lg hover:shadow-blue-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-lg flex items-center gap-2 min-w-[100px] justify-center"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Sending...</span>
              </>
            ) : (
              <>
                <span>Send</span>
                <span>→</span>
              </>
            )}
          </button>
        </div>
        {!connected && (
          <div className="mt-2 text-xs text-amber-400 text-center">
            ⚠️ Backend not connected. Make sure the server is running on port 8000
          </div>
        )}
        {connected && (
          <div className="mt-2 text-xs text-slate-500 text-center">
            Press Enter to send • Shift+Enter for new line
          </div>
        )}
      </div>
    </div>
  );
}
