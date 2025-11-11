import ChatWindow from './components/ChatWindow';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="container mx-auto px-4 py-6 max-w-6xl">
        <div className="text-center mb-6">
          <h1 className="text-5xl font-bold mb-2 bg-gradient-to-r from-blue-400 via-purple-400 to-blue-400 bg-clip-text text-transparent">
            Quash Browser Agent
          </h1>
          <p className="text-slate-400 text-lg">AI-Powered Conversational Browser Automation</p>
        </div>
        <div className="w-full">
          <ChatWindow />
        </div>
      </div>
    </div>
  );
}
