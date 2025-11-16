'use client';

import { Globe } from 'lucide-react';

export default function AnimatedGlobe() {
  return (
    <div className="relative w-14 h-14 flex items-center justify-center bg-gradient-to-br from-yellow-400 to-yellow-600 rounded-full">
      {/* Outer pulsing ring */}
      <div className="absolute inset-0 rounded-full border-2 border-black/20 animate-pulse" />
      
      {/* Middle rotating ring with dots */}
      <div className="absolute inset-0 rounded-full border border-black/30 animate-spin-slow">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1.5 h-1.5 bg-black rounded-full shadow-lg shadow-black/50" />
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 w-1.5 h-1.5 bg-black rounded-full shadow-lg shadow-black/50" />
        <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 w-1.5 h-1.5 bg-black rounded-full shadow-lg shadow-black/50" />
        <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-1.5 h-1.5 bg-black rounded-full shadow-lg shadow-black/50" />
      </div>
      
      {/* Inner rotating ring (opposite direction) */}
      <div className="absolute inset-2 rounded-full border border-black/25 animate-spin-reverse">
        <div className="absolute top-1/2 left-0 -translate-y-1/2 -translate-x-1/2 w-1 h-1 bg-black/80 rounded-full" />
        <div className="absolute top-1/2 right-0 -translate-y-1/2 translate-x-1/2 w-1 h-1 bg-black/80 rounded-full" />
      </div>
      
      {/* Globe icon - main element */}
      <div className="relative z-10">
        <Globe 
          className="w-8 h-8 text-black drop-shadow-lg animate-float" 
          strokeWidth={2.5}
          fill="none"
          style={{ 
            filter: 'drop-shadow(0 0 4px rgba(0, 0, 0, 0.3))'
          }}
        />
      </div>
      
      {/* Network connection lines (subtle) */}
      <div className="absolute inset-0 opacity-15">
        <div className="absolute top-1/4 left-1/4 w-px h-1/2 bg-gradient-to-b from-black/60 to-transparent animate-pulse-line" />
        <div className="absolute bottom-1/4 right-1/4 w-px h-1/2 bg-gradient-to-t from-black/60 to-transparent animate-pulse-line" 
             style={{ animationDelay: '1s' }} />
      </div>
    </div>
  );
}

