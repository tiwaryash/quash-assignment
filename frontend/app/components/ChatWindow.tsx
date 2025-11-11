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
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
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
      setMessages(prev => [...prev, {
        ...data,
        timestamp: Date.now()
      }]);
    };

    ws.onerror = () => {
      setConnected(false);
    };

    ws.onclose = () => {
      setConnected(false);
      setMessages(prev => [...prev, {
        type: 'system',
        message: 'Disconnected from server',
        timestamp: Date.now()
      }]);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, []);

  const sendMessage = () => {
    if (input.trim() && wsRef.current && connected) {
      wsRef.current.send(JSON.stringify({ instruction: input }));
      setMessages(prev => [...prev, {
        type: 'user',
        message: input,
        timestamp: Date.now()
      }]);
      setInput('');
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto p-4">
      <div className="mb-4">
        <div className={`inline-block px-3 py-1 rounded text-sm ${connected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {connected ? 'Connected' : 'Disconnected'}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto border rounded-lg p-4 mb-4 bg-gray-50">
        {messages.map((msg, idx) => {
          if (msg.type === 'user') {
            return (
              <div key={idx} className="mb-2 text-right">
                <div className="inline-block px-3 py-2 rounded-lg bg-blue-500 text-white">
                  {msg.message}
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
              <div key={idx} className="mb-2">
                <div className="bg-purple-100 border border-purple-300 rounded-lg p-3">
                  <div className="font-semibold mb-2">📋 Action Plan ({msg.data?.length || 0} steps)</div>
                  <div className="text-sm space-y-1">
                    {msg.data?.map((action: any, i: number) => (
                      <div key={i} className="opacity-75">
                        {i + 1}. {action.action} {action.selector && `(${action.selector})`}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          }
          
          if (msg.type === 'error') {
            return (
              <div key={idx} className="mb-2">
                <div className="bg-red-100 border border-red-300 rounded-lg p-3 text-red-800">
                  <div className="font-semibold">❌ Error</div>
                  <div className="text-sm">{msg.message}</div>
                </div>
              </div>
            );
          }
          
          if (msg.type === 'status') {
            return (
              <div key={idx} className="mb-2">
                <div className="bg-blue-100 border border-blue-300 rounded-lg p-3 text-blue-800 text-sm">
                  {msg.message}
                </div>
              </div>
            );
          }
          
          return (
            <div key={idx} className="mb-2">
              <div className="inline-block px-3 py-2 rounded-lg bg-gray-200 text-gray-700">
                {msg.message || JSON.stringify(msg)}
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Type an instruction (e.g., 'Navigate to google.com')..."
          className="flex-1 px-4 py-2 border rounded-lg"
          disabled={!connected}
        />
        <button
          onClick={sendMessage}
          disabled={!connected || !input.trim()}
          className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </div>
    </div>
  );
}
