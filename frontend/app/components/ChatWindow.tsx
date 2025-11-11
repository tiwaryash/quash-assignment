'use client';

import { useState, useEffect, useRef } from 'react';

interface Message {
  type: string;
  message?: string;
  timestamp: number;
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

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
      wsRef.current.send(input);
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
        {messages.map((msg, idx) => (
          <div key={idx} className={`mb-2 ${msg.type === 'user' ? 'text-right' : ''}`}>
            <div className={`inline-block px-3 py-2 rounded-lg ${
              msg.type === 'user' 
                ? 'bg-blue-500 text-white' 
                : msg.type === 'system'
                ? 'bg-gray-200 text-gray-700'
                : 'bg-white border'
            }`}>
              {msg.message || JSON.stringify(msg)}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Type a message..."
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

