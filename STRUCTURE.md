# Project Structure

## Root Directory
```
quash_assignment/
├── backend/              # Python FastAPI backend
├── frontend/             # Next.js frontend
├── docs/                 # Documentation files
├── Dockerfile.backend    # Backend Docker image
├── Dockerfile.frontend   # Frontend Docker image
├── docker-compose.yml    # Docker Compose configuration
├── .dockerignore         # Docker ignore patterns
└── README.md             # Main project documentation
```

## Backend Structure
```
backend/
├── app/                  # Main application package
│   ├── api/              # API routes/endpoints
│   │   ├── plan.py       # Planning endpoint
│   │   └── websocket.py  # WebSocket endpoint
│   ├── core/             # Core utilities
│   │   ├── config.py     # Configuration management
│   │   ├── llm_provider.py  # LLM provider abstraction
│   │   ├── logger.py     # Structured logging
│   │   └── retry.py      # Retry logic & circuit breaker
│   ├── services/         # Business logic services
│   │   ├── ai_planner.py      # AI-powered action planning
│   │   ├── browser_agent.py   # Browser automation
│   │   ├── comparison_handler.py  # Multi-site comparison
│   │   ├── conversation.py    # Conversation management
│   │   ├── edge_case_handlers.py  # Edge case handling
│   │   ├── executor.py        # Plan execution
│   │   ├── filter_results.py  # Result filtering
│   │   ├── intent_classifier.py  # Intent classification
│   │   └── site_selectors.py  # Site-specific selectors
│   ├── streaming/        # Streaming utilities (future)
│   └── main.py          # FastAPI application entry point
├── tests/               # Test suite
│   ├── conftest.py     # Pytest configuration
│   └── test_navigation.py  # Navigation tests
├── logs/                # Application logs
├── requirements.txt     # Python dependencies
├── pytest.ini          # Pytest configuration
└── .env.example        # Environment variables template
```

## Frontend Structure
```
frontend/
├── app/                 # Next.js App Router
│   ├── components/      # React components
│   │   ├── ActionCard.tsx    # Action display card
│   │   └── ChatWindow.tsx    # Main chat interface
│   ├── globals.css      # Global styles
│   ├── layout.tsx       # Root layout
│   └── page.tsx         # Home page
├── public/              # Static assets
│   └── *.svg           # Icon files
├── package.json         # Node.js dependencies
├── tsconfig.json       # TypeScript configuration
├── next.config.ts      # Next.js configuration
├── postcss.config.mjs  # PostCSS configuration
└── eslint.config.mjs   # ESLint configuration
```

## Documentation
```
docs/
├── Quash AI Assignment.txt  # Original assignment requirements
└── SETUP.md                  # Setup instructions
```

## Key Design Principles

### Backend Organization
- **api/**: HTTP endpoints and WebSocket handlers
- **core/**: Reusable utilities (config, logging, retry)
- **services/**: Business logic separated by concern
- **tests/**: Test files mirroring app structure

### Frontend Organization
- **app/**: Next.js 14 App Router structure
- **components/**: Reusable React components
- **public/**: Static assets

### Separation of Concerns
- Configuration: `core/config.py`
- Logging: `core/logger.py`
- Retry Logic: `core/retry.py`
- LLM Abstraction: `core/llm_provider.py`
- Browser Automation: `services/browser_agent.py`
- Planning: `services/ai_planner.py`
- Execution: `services/executor.py`
