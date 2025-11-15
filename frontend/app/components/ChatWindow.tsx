'use client';

import { useState, useEffect, useRef } from 'react';
import ActionCard from './ActionCard';
import { 
  Send, 
  Loader2, 
  Circle, 
  CheckCircle2, 
  XCircle, 
  AlertCircle,
  MessageSquare,
  ListChecks,
  HelpCircle,
  ShieldAlert,
  Wifi,
  WifiOff,
  Sparkles,
  Lightbulb,
  ArrowRight
} from 'lucide-react';

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
  filters?: Array<{field: string; label: string; options: string[]; type: string}>;
  filter_summary?: string[];
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedClarifications, setSelectedClarifications] = useState<Set<string>>(new Set());
  const [selectedFilters, setSelectedFilters] = useState<Record<string, Record<string, string>>>({});
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
        
        // Also clear loading when filter action completes (filter actions may not have step numbers)
        if (data.type === 'action_status' && data.action === 'filter' && data.status === 'completed') {
          setIsLoading(false);
        }
        
        // For action_status messages, replace existing card for the same step instead of adding new one
        if (data.type === 'action_status' && data.step !== undefined) {
          setMessages(prev => {
            // Find and remove existing card for this step and action
            // Use step + action to uniquely identify, so different plans don't interfere
            const filtered = prev.filter(msg => {
              // Remove if it's the same action_status with same step and action
              if (msg.type === 'action_status' && msg.step === data.step && msg.action === data.action) {
                return false; // Remove this message
              }
              return true; // Keep this message
            });
            // Add the new/updated card
            return [...filtered, {
              ...data,
              timestamp: Date.now()
            }];
          });
        } else if (data.type === 'action_status' && data.action === 'filter') {
          // Filter actions don't have step numbers, so handle them separately
          setMessages(prev => {
            // Remove any existing filter action_status messages
            const filtered = prev.filter(msg => {
              if (msg.type === 'action_status' && msg.action === 'filter') {
                return false; // Remove existing filter messages
              }
              return true;
            });
            // Add the new filter result
            return [...filtered, {
              ...data,
              timestamp: Date.now()
            }];
          });
        } else {
          // For other message types, just add them
          setMessages(prev => [...prev, {
            ...data,
            timestamp: Date.now()
          }]);
        }
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

  const exampleQueries = [
    "Find MacBook Air under ₹1,00,000",
    "Find top pizza places in Indiranagar",
    "Compare laptops on Flipkart and Amazon",
    "Search for best restaurants near me"
  ];

  return (
    <div className="flex flex-col h-full bg-black/40 backdrop-blur-xl rounded-3xl border-2 border-yellow-500/30 shadow-2xl overflow-hidden relative">
      {/* Glow Effect */}
      <div className="absolute inset-0 bg-gradient-to-br from-yellow-500/5 via-transparent to-yellow-500/5 pointer-events-none"></div>
      
      {/* Header */}
      <div className="relative flex items-center justify-between p-3 border-b-2 border-yellow-500/30 bg-black/50 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className={`relative flex items-center gap-1.5 px-3 py-1.5 rounded-full border transition-all ${
            connected 
              ? 'bg-yellow-500/10 border-yellow-500/50' 
              : 'bg-red-500/10 border-red-500/50'
          }`}>
            {connected ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-yellow-500" />
                <span className="text-xs font-bold text-yellow-500">Connected</span>
                <div className="w-1.5 h-1.5 bg-yellow-500 rounded-full glow-pulse"></div>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-red-400" />
                <span className="text-xs font-bold text-red-400">Disconnected</span>
              </>
            )}
          </div>
        </div>
        {isLoading && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-500/10 border border-yellow-500/50 rounded-full">
            <Loader2 className="w-3.5 h-3.5 text-yellow-500 animate-spin" />
            <span className="text-xs font-bold text-yellow-500">Processing...</span>
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 relative min-h-0">
        {messages.length === 0 && (
          <div className="text-center py-6 animate-slide-in">
            <div className="relative inline-block mb-4">
              <div className="absolute inset-0 bg-yellow-500/20 rounded-2xl blur-xl"></div>
              <div className="relative bg-gradient-to-br from-yellow-400 to-yellow-600 p-4 rounded-2xl">
                <MessageSquare className="w-10 h-10 text-black" strokeWidth={2} />
              </div>
            </div>
            
            <h3 className="text-xl font-black text-yellow-500 mb-2">Welcome to Quash Browser Agent</h3>
            <p className="text-yellow-500/60 mb-1 font-medium text-sm">Start by sending a natural language instruction</p>
            <p className="text-xs text-yellow-500/40 mb-4 font-medium">Backend server: port 8000</p>
            
            <div className="flex flex-wrap gap-2 justify-center max-w-2xl mx-auto">
              {exampleQueries.map((example, idx) => (
                <button
                  key={idx}
                  onClick={() => setInput(example)}
                  className="group px-3 py-2 bg-black/50 hover:bg-yellow-500/10 border border-yellow-500/30 hover:border-yellow-500/60 text-yellow-500/80 hover:text-yellow-500 rounded-lg text-xs font-semibold transition-all hover-lift"
                >
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="w-3 h-3 group-hover:rotate-12 transition-transform" />
                    {example}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
        
        {messages.map((msg, idx) => {
          if (msg.type === 'user') {
            return (
              <div key={idx} className="flex justify-end animate-slide-in-right">
                <div className="max-w-[80%] bg-gradient-to-r from-yellow-500 to-yellow-600 text-black rounded-2xl rounded-br-md px-5 py-3 shadow-lg border-2 border-yellow-400">
                  <p className="text-sm leading-relaxed font-semibold">{msg.message}</p>
                </div>
              </div>
            );
          }
          
          if (msg.type === 'action_status') {
            // Use a stable key based on step and action so React updates instead of remounting
            const actionKey = `action-${msg.step}-${msg.action || 'unknown'}`;
            return (
              <ActionCard
                key={actionKey}
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
              <div key={idx} className="animate-slide-in-left">
                <div className="bg-black/50 border-2 border-yellow-500/50 rounded-2xl p-5 yellow-glow">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="bg-yellow-500/20 p-2 rounded-xl">
                      <ListChecks className="w-6 h-6 text-yellow-500" />
                    </div>
                    <span className="font-black text-yellow-500 text-lg">Action Plan</span>
                    <span className="ml-auto text-xs bg-yellow-500/20 text-yellow-500 px-3 py-1.5 rounded-full font-bold border border-yellow-500/30">
                      {msg.data?.length || 0} steps
                    </span>
                  </div>
                  <div className="space-y-2">
                    {msg.data?.map((action: any, i: number) => (
                      <div key={i} className="flex items-center gap-3 text-sm bg-black/40 p-3 rounded-xl border border-yellow-500/20 hover:border-yellow-500/40 transition-colors">
                        <div className="w-7 h-7 rounded-full bg-yellow-500/20 text-yellow-500 flex items-center justify-center text-xs font-black border border-yellow-500/30">
                          {i + 1}
                        </div>
                        <span className="text-yellow-500/90 capitalize font-semibold">{action.action}</span>
                        {action.selector && (
                          <code className="text-xs text-yellow-500/60 ml-auto font-mono bg-black/50 px-2 py-1 rounded border border-yellow-500/20">
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
              <div key={idx} className="animate-slide-in-left">
                <div className="bg-black/50 border-2 border-red-500/50 rounded-2xl p-5">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="bg-red-500/20 p-2 rounded-xl">
                      <XCircle className="w-6 h-6 text-red-400" />
                    </div>
                    <span className="font-black text-red-400 text-lg">Error</span>
                  </div>
                  <div className="text-sm text-red-300 whitespace-pre-line font-medium">
                    {msg.message}
                  </div>
                  {msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-red-500/30">
                      <div className="flex items-center gap-2 text-xs font-black text-yellow-500 mb-3">
                        <Lightbulb className="w-4 h-4" />
                        {msg.action === 'navigate' ? 'Suggestions:' : 'Suggested selectors:'}
                      </div>
                      {msg.action === 'navigate' ? (
                        <ul className="list-disc list-inside text-xs text-yellow-400 space-y-1 font-medium">
                          {msg.suggestions.map((suggestion: string, i: number) => (
                            <li key={i}>{suggestion}</li>
                          ))}
                        </ul>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {msg.suggestions.map((suggestion: string, i: number) => (
                            <code key={i} className="text-xs bg-black/50 text-yellow-400 px-3 py-1.5 rounded-lg border border-yellow-500/30 font-mono">
                              {suggestion}
                            </code>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {msg.message?.includes('API key') && (
                    <div className="mt-4 pt-4 border-t border-red-500/30 flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 text-yellow-500 flex-shrink-0 mt-0.5" />
                      <span className="text-xs text-yellow-400 font-medium">
                        Make sure to set your OPENAI_API_KEY in backend/.env file
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'status') {
            return (
              <div key={idx} className="flex justify-center animate-slide-in">
                <div className="bg-black/40 border border-yellow-500/30 rounded-full px-5 py-2 text-sm text-yellow-500/70 font-medium inline-flex items-center gap-2">
                  <Circle className="w-3 h-3" />
                  {msg.message}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'system') {
            return (
              <div key={idx} className="flex justify-center">
                <div className="bg-black/30 border border-yellow-500/20 rounded-full px-4 py-1.5 text-xs text-yellow-500/50 font-medium inline-flex items-center gap-2">
                  <Circle className="w-2 h-2" />
                  {msg.message}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'clarification') {
            const clarificationId = `${msg.timestamp}-${msg.question}`;
            const isFrozen = selectedClarifications.has(clarificationId);
            
            return (
              <div key={idx} className="animate-slide-in-left">
                <div className={`bg-black/50 border-2 border-yellow-500/50 rounded-2xl p-5 ${isFrozen ? 'opacity-60' : 'yellow-glow'}`}>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="bg-yellow-500/20 p-2 rounded-xl">
                      <HelpCircle className="w-6 h-6 text-yellow-500" />
                    </div>
                    <span className="font-black text-yellow-500 text-lg">Question</span>
                    {isFrozen && (
                      <span className="ml-auto text-xs bg-yellow-500/20 text-yellow-500 px-3 py-1.5 rounded-full font-bold border border-yellow-500/30">
                        Answered
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-yellow-300 mb-4 font-medium">
                    {msg.question}
                  </div>
                  {msg.options && msg.options.length > 0 && (
                    <div className="space-y-2">
                      {msg.options.map((option: {value: string; label: string}, optIdx: number) => {
                        const optionId = `${clarificationId}-${optIdx}`;
                        const isSelected = selectedClarifications.has(optionId);
                        
                        return (
                          <button
                            key={optIdx}
                            onClick={() => {
                              if (isFrozen || isSelected) return; // Prevent multiple clicks
                              
                              const clarificationType = msg.clarification_type || msg.context || (msg.field === 'site' ? 'site_selection' : undefined);
                              setSelectedClarifications(prev => {
                                const newSet = new Set(prev);
                                newSet.add(clarificationId); // Mark clarification as answered
                                newSet.add(optionId); // Mark option as selected
                                return newSet;
                              });
                              sendMessage(option.value, clarificationType);
                            }}
                            disabled={isFrozen || isSelected}
                            className={`group w-full text-left px-5 py-3 border-2 rounded-xl text-sm font-semibold flex items-center justify-between transition-all ${
                              isFrozen || isSelected
                                ? 'bg-black/30 border-yellow-500/20 text-yellow-500/40 cursor-not-allowed'
                                : 'bg-black/50 hover:bg-yellow-500/10 border-yellow-500/30 hover:border-yellow-500/60 text-yellow-400 hover:text-yellow-500'
                            }`}
                          >
                            {option.label}
                            {isSelected ? (
                              <CheckCircle2 className="w-4 h-4 text-yellow-500" />
                            ) : (
                              <ArrowRight className={`w-4 h-4 transition-opacity ${isFrozen ? 'opacity-0' : 'opacity-0 group-hover:opacity-100'}`} />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            );
          }
          
          if (msg.type === 'blocked') {
            return (
              <div key={idx} className="animate-slide-in-left">
                <div className="bg-black/50 border-2 border-orange-500/50 rounded-2xl p-5">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="bg-orange-500/20 p-2 rounded-xl">
                      <ShieldAlert className="w-6 h-6 text-orange-400" />
                    </div>
                    <span className="font-black text-orange-400 text-lg">Blocked</span>
                  </div>
                  <div className="text-sm text-orange-300 whitespace-pre-line mb-3 font-medium">
                    {msg.message}
                  </div>
                  {msg.alternatives && msg.alternatives.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-orange-500/30">
                      <div className="flex items-center gap-2 text-xs font-black text-yellow-500 mb-3">
                        <Lightbulb className="w-4 h-4" />
                        Alternatives:
                      </div>
                      <ul className="list-disc list-inside text-xs text-orange-300 space-y-1 font-medium">
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
          
          if (msg.type === 'filter_options') {
            const filterId = `filter-${msg.timestamp}`;
            const currentFilters = selectedFilters[filterId] || {};
            const hasActiveFilters = Object.values(currentFilters).some(v => v);
            
            return (
              <div key={idx} className="animate-slide-in-left">
                <div className="bg-black/50 border-2 border-yellow-500/50 rounded-2xl p-5 yellow-glow">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="bg-yellow-500/20 p-2 rounded-xl">
                      <ListChecks className="w-6 h-6 text-yellow-500" />
                    </div>
                    <span className="font-black text-yellow-500 text-lg">Filter Options</span>
                    {hasActiveFilters && (
                      <span className="ml-auto text-xs bg-yellow-500/20 text-yellow-500 px-3 py-1.5 rounded-full font-bold border border-yellow-500/30">
                        {Object.values(currentFilters).filter(v => v).length} active
                      </span>
                    )}
                  </div>
                  
                  {msg.message && (
                    <div className="text-sm text-yellow-300 mb-4 font-medium">
                      {msg.message}
                    </div>
                  )}
                  
                  {msg.filter_summary && msg.filter_summary.length > 0 && (
                    <div className="mb-4 space-y-1">
                      {msg.filter_summary.map((summary: string, sumIdx: number) => (
                        <div key={sumIdx} className="text-xs text-yellow-400/80 font-medium bg-black/30 px-3 py-2 rounded-lg border border-yellow-500/20">
                          {summary}
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {msg.filters && msg.filters.length > 0 && (
                    <div className="space-y-4 mb-4">
                      {msg.filters.map((filter: {field: string; label: string; options: string[]; type: string}, filterIdx: number) => (
                          <div key={filterIdx} className="space-y-2">
                            <div className="text-xs font-black text-yellow-500 uppercase tracking-wide">
                              {filter.label}
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {filter.options.map((option: string, optIdx: number) => {
                                const isOptionSelected = currentFilters[filter.field] === option;
                                
                                return (
                                  <button
                                    key={optIdx}
                                    onClick={() => {
                                      setSelectedFilters(prev => ({
                                        ...prev,
                                        [filterId]: {
                                          ...prev[filterId],
                                          [filter.field]: isOptionSelected ? '' : option
                                        }
                                      }));
                                    }}
                                    className={`px-4 py-2 rounded-lg text-sm font-semibold border-2 transition-all ${
                                      isOptionSelected
                                        ? 'bg-yellow-500/20 border-yellow-500 text-yellow-500'
                                        : 'bg-black/50 hover:bg-yellow-500/10 border-yellow-500/30 hover:border-yellow-500/60 text-yellow-400 hover:text-yellow-500'
                                    }`}
                                  >
                                    {option}
                                    {isOptionSelected && (
                                      <CheckCircle2 className="w-3.5 h-3.5 inline-block ml-2" />
                                    )}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                      ))}
                    </div>
                  )}
                  
                  {msg.question && (
                    <div className="text-sm text-yellow-300 mb-4 font-medium">
                      {msg.question}
                    </div>
                  )}
                  
                  <div className="flex gap-2 pt-4 border-t border-yellow-500/30">
                    {hasActiveFilters && (
                      <button
                        onClick={() => {
                          // Clear all filters
                          setSelectedFilters(prev => ({
                            ...prev,
                            [filterId]: {}
                          }));
                        }}
                        className="px-5 py-3 rounded-xl text-sm font-black transition-all bg-black/50 hover:bg-red-500/10 border-2 border-red-500/30 hover:border-red-500/60 text-red-400 hover:text-red-500"
                      >
                        Clear All
                      </button>
                    )}
                    <button
                      onClick={() => {
                        // Build filter selection string
                        const filterParts: string[] = [];
                        Object.entries(currentFilters).forEach(([field, value]) => {
                          if (value) {
                            filterParts.push(value);
                          }
                        });
                        
                        const filterString = filterParts.length > 0 
                          ? filterParts.join(' ') 
                          : 'skip';
                        
                        // Don't freeze - allow re-filtering
                        sendMessage(filterString, 'product_filter_refinement');
                      }}
                      className="flex-1 px-5 py-3 rounded-xl text-sm font-black transition-all bg-gradient-to-r from-yellow-500 to-yellow-600 hover:from-yellow-400 hover:to-yellow-500 text-black border-2 border-yellow-400"
                    >
                      {Object.values(currentFilters).some(v => v) ? 'Apply Filters' : 'Skip (Show All)'}
                    </button>
                  </div>
                </div>
              </div>
            );
          }
          
          return null;
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="relative p-3 border-t-2 border-yellow-500/30 bg-black/50 flex-shrink-0">
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
              placeholder={connected ? "Type your instruction... (e.g., 'Find MacBook Air under ₹1,00,000')" : "Connecting to server..."}
              className="w-full px-4 py-3 bg-black/50 border-2 border-yellow-500/30 rounded-xl text-yellow-500 placeholder-yellow-500/40 focus:outline-none focus:ring-2 focus:ring-yellow-500/50 focus:border-yellow-500/60 transition-all disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
              disabled={!connected || isLoading}
            />
          </div>
          <button
            onClick={() => sendMessage()}
            disabled={!connected || !input.trim() || isLoading}
            className="group px-6 py-3 bg-gradient-to-r from-yellow-500 to-yellow-600 hover:from-yellow-400 hover:to-yellow-500 text-black font-black rounded-xl shadow-lg hover:shadow-yellow-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-lg flex items-center gap-2 min-w-[100px] justify-center border-2 border-yellow-400"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Send</span>
              </>
            ) : (
              <>
                <span className="text-sm">Send</span>
                <Send className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </>
            )}
          </button>
        </div>
        {!connected && (
          <div className="mt-2 flex items-center justify-center gap-1.5 text-xs text-orange-400 font-medium">
            <AlertCircle className="w-3 h-3" />
            Backend not connected. Server: port 8000
          </div>
        )}
        {connected && (
          <div className="mt-2 text-xs text-yellow-500/50 text-center font-medium">
            Press Enter to send
          </div>
        )}
      </div>
    </div>
  );
}
