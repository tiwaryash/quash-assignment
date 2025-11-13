# Quash Browser Control Agent

A conversational browser automation agent that controls a real browser through natural language. Built with FastAPI, Next.js, Playwright, and OpenAI.

## Features

### Core Capabilities
- 🤖 **AI-Powered Planning**: Converts natural language instructions into browser action plans
- 🌐 **Real Browser Control**: Uses Playwright for reliable browser automation  
- 💬 **Live Streaming UI**: WebSocket-based chat interface with real-time action updates
- 📊 **Data Extraction**: Extract structured data from web pages
- 🔄 **Multi-Site Comparison**: Compare products across Flipkart, Amazon, and other e-commerce sites
- 📝 **Form Automation**: Intelligent form filling with LLM-powered field detection

### Advanced Features
- 🔌 **LLM Provider Abstraction**: Support for OpenAI, Anthropic Claude, and local LLMs (Ollama)
- 📋 **Structured Logging**: JSON logging with automatic sensitive data redaction
- ⚡ **Retry Logic**: Exponential backoff for network failures and transient errors
- 🛡️ **Edge Case Handling**: Robust handling of element staleness, network timeouts, and blocking
- 💾 **Conversation Memory**: Remembers user preferences across sessions
- 🔍 **Intent Classification**: Automatic detection of task type and clarification requests
- 🐳 **Docker Support**: Fully containerized development environment

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

### Option 1: Docker (Recommended)

1. **Prerequisites:**
   - Docker and Docker Compose installed
   - OpenAI API key (get from https://platform.openai.com/account/api-keys)

2. **Setup:**
```bash
# Clone the repository
git clone <repository-url>
cd quash_assignment

# Set your OpenAI API key
export OPENAI_API_KEY=sk-your-actual-key-here

# Start all services
docker-compose up --build
```

3. **Access:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000

### Option 2: Local Development

#### Prerequisites

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

### Product Search & Comparison
- `Find MacBook Air under ₹1,00,000 on Flipkart`
- `Compare laptops under ₹60,000 on Flipkart and Amazon`
- `Search for wireless headphones with 4+ star ratings`

### Local Discovery
- `Find top 3 pizza places in Indiranagar with ratings`
- `Show best restaurants near HSR Layout on Google Maps`
- `Find coffee shops in Koramangala with delivery`

### Form Filling
- `Fill out the signup form on example.com/register`
- `Register with a temporary email on this page`

### General Browsing
- `Navigate to example.com and extract the page title`
- `Go to python.org and get the latest release version`

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

### Backend
- **Framework**: FastAPI with async/await support
- **Browser Automation**: Playwright (Chromium)
- **AI/LLM**: OpenAI GPT-4o-mini (with support for Claude & local models)
- **Communication**: WebSockets for real-time streaming
- **Testing**: Pytest with async support

### Frontend
- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS with custom animations
- **Icons**: Lucide React
- **Real-time**: WebSocket client

### DevOps
- **Containerization**: Docker & Docker Compose
- **Logging**: Structured JSON logging with redaction
- **Error Handling**: Retry logic with exponential backoff

## Testing

Run the test suite:

```bash
cd backend
pytest tests/ -v
```

Run specific test:
```bash
pytest tests/test_navigation.py::test_navigate_to_valid_url -v
```

## Advanced Configuration

### Using Alternative LLM Providers

#### Anthropic Claude
```bash
# In backend/.env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-anthropic-key
ANTHROPIC_MODEL=claude-3-sonnet-20240229
```

#### Local LLM (Ollama)
```bash
# In backend/.env
LLM_PROVIDER=local
LOCAL_LLM_URL=http://localhost:11434
LOCAL_LLM_MODEL=llama2
```

### Browser Configuration
```bash
# In backend/.env
HEADLESS=true  # Set to false to see browser
BROWSER_TIMEOUT=30000  # Navigation timeout in ms
```

### Logging Configuration
```bash
# In backend/.env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/app.log
```

## Architecture Highlights

### Clean Separation of Concerns
- **Conversation Layer**: Handles clarifications, context, and user preferences
- **Planning Layer**: Converts natural language to action plans
- **Execution Layer**: Orchestrates browser actions and data extraction
- **Browser Layer**: Low-level browser control with fallback strategies
- **AI Layer**: Abstracted LLM providers for flexibility

### Key Design Patterns
- **Provider Pattern**: Pluggable LLM providers (OpenAI, Anthropic, Local)
- **Strategy Pattern**: Site-specific selector strategies
- **Retry Pattern**: Exponential backoff for transient failures
- **Circuit Breaker**: Prevents cascading failures
- **Observer Pattern**: WebSocket streaming for real-time updates

### Error Handling
- Automatic retry with exponential backoff for network failures
- Graceful degradation when selectors don't match
- CAPTCHA and blocking detection with alternative suggestions
- Stale element recovery
- Network timeout handling

### Extensibility
- Easy to add new sites with custom selectors
- Pluggable LLM providers
- Modular workflow capabilities (search, compare, form-fill)
- Session-based preference learning

## Bonus Features Implemented

✅ WebSocket streaming with granular action events
✅ Memory of user preferences across tasks
✅ Multi-site comparison flows
✅ Provider abstraction for LLMs and pluggable planners
✅ Dockerized dev stack
✅ Deterministic e2e tests for navigation workflow

## License

MIT

