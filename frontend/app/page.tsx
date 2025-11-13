'use client';

import ChatWindow from './components/ChatWindow';
import { Bot, Sparkles, Zap } from 'lucide-react';

export default function Home() {
  return (
    <div className="min-h-screen bg-black relative overflow-hidden">
      {/* Animated Background */}
      <div className="absolute inset-0 bg-gradient-to-br from-black via-[#0a0a0a] to-black"></div>
      
      {/* Yellow Accent Patterns */}
      <div className="absolute top-0 left-0 w-96 h-96 bg-yellow-500/5 rounded-full blur-3xl"></div>
      <div className="absolute bottom-0 right-0 w-96 h-96 bg-yellow-500/5 rounded-full blur-3xl"></div>
      
      {/* Grid Pattern */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,215,0,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,215,0,0.03)_1px,transparent_1px)] bg-[size:50px_50px]"></div>
      
      <div className="container mx-auto px-4 py-3 max-w-6xl relative z-10 h-screen flex flex-col">
        {/* Compact Header */}
        <div className="text-center mb-3 animate-slide-in flex-shrink-0">
          <div className="flex items-center justify-center gap-3 mb-2">
            <div className="relative">
              <div className="absolute inset-0 bg-yellow-500/20 rounded-xl blur-lg"></div>
              <div className="relative bg-gradient-to-br from-yellow-400 to-yellow-600 p-2 rounded-xl">
                <Bot className="w-7 h-7 text-black" strokeWidth={2.5} />
              </div>
            </div>
            <h1 className="text-3xl font-black tracking-tight">
              <span className="bg-gradient-to-r from-yellow-400 via-yellow-500 to-yellow-400 bg-clip-text text-transparent">
                Quash Browser Agent
              </span>
            </h1>
          </div>
          
          <div className="flex items-center justify-center gap-2 text-yellow-500/80 text-sm font-medium">
            <Sparkles className="w-4 h-4" />
            <p>AI-Powered Browser Automation</p>
            <Zap className="w-4 h-4" />
          </div>
        </div>
        
        {/* Main Chat Window - Takes remaining height */}
        <div className="flex-1 min-h-0">
          <ChatWindow />
        </div>
      </div>
      
      {/* Bottom Accent Line */}
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-yellow-500 to-transparent"></div>
    </div>
  );
}
