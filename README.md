# Quash Browser Control Agent

A conversational browser automation agent that controls a real browser through natural language. Built with FastAPI, Next.js, Playwright, and OpenAI.

## Features

- 🤖 **AI-Powered Planning**: Converts natural language instructions into browser action plans
- 🌐 **Real Browser Control**: Uses Playwright for reliable browser automation
- 💬 **Live Streaming UI**: WebSocket-based chat interface with real-time action updates
- 📊 **Data Extraction**: Extract structured data from web pages
- 🛡️ **Error Handling**: Graceful error handling with user-friendly messages

## Architecture

```
┌─────────────┐
│   Frontend  │  Next.js + TypeScript + Tailwind
│  (Next.js)  │
└──────┬──────┘
       │ WebSocket
       │
┌──────▼──────┐
│   Backend   │  FastAPI + Python
│  (FastAPI)  │
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
┌──▼──┐ ┌──▼────┐
│ AI  │ │Browser│
│Planner│ │ Agent │
└─────┘ └───────┘
```

## Project Structure

```
quash-assignment/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers
│   │   ├── core/         # Config, settings
│   │   ├── services/     # Business logic
│   │   │   ├── browser_agent.py
│   │   │   ├── ai_planner.py
│   │   │   └── executor.py
│   │   └── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx
│   │   │   └── ActionCard.tsx
│   │   └── page.tsx
│   └── package.json
└── README.md
```

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- OpenAI API key

### Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers:
```bash
playwright install chromium
```

5. Create `.env` file:
```bash
cd backend
cp .env.example .env
```

6. **IMPORTANT:** Add your OpenAI API key to `backend/.env`:
   - Get your API key from: https://platform.openai.com/account/api-keys
   - Open `backend/.env` file
   - Replace `your-api-key-here` with your actual key:
   ```
   OPENAI_API_KEY=sk-your-actual-key-here
   OPENAI_MODEL=gpt-4o-mini
   ```
   - **Make sure the key starts with `sk-`**

7. Run the server:
```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

## Usage

1. Start both backend and frontend servers
2. Open the frontend in your browser
3. Type a natural language instruction, for example:
   - "Navigate to google.com"
   - "Search for laptops on flipkart"
   - "Find top 3 pizza places near me"

The agent will:
1. Plan the actions using AI
2. Execute them in a real browser
3. Stream live updates to the UI
4. Show results or errors

## Example Instructions

- `Navigate to https://example.com`
- `Go to google.com and search for "python tutorial"`
- `Find laptops under 60000 on Flipkart`
- `Extract the title and description from the current page`

## Development

### Backend

- Main entry: `backend/app/main.py`
- WebSocket endpoint: `/ws`
- Planning endpoint: `/api/plan`

### Frontend

- Main page: `frontend/app/page.tsx`
- Chat component: `frontend/app/components/ChatWindow.tsx`
- Action cards: `frontend/app/components/ActionCard.tsx`

## Tech Stack

- **Backend**: FastAPI, Python, Playwright, OpenAI
- **Frontend**: Next.js, TypeScript, Tailwind CSS
- **Communication**: WebSockets
- **AI**: OpenAI GPT-4o-mini

## License

MIT

