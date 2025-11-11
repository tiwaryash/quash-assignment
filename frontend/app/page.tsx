import ChatWindow from './components/ChatWindow';

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-100">
      <div className="container mx-auto py-4">
        <h1 className="text-3xl font-bold mb-4 text-center">Quash Browser Agent</h1>
        <ChatWindow />
      </div>
    </div>
  );
}
