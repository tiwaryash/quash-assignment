# Quick Setup Guide

## 1. Set up OpenAI API Key

1. Get your API key from: https://platform.openai.com/account/api-keys
2. Open `backend/.env` file
3. Replace `your-api-key-here` with your actual API key:

```
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_MODEL=gpt-4o-mini
```

4. Save the file
5. Restart the backend server

## 2. Start the Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

## 3. Start the Frontend (in a new terminal)

```bash
cd frontend
npm run dev
```

## 4. Open in Browser

Go to: http://localhost:3000

## Troubleshooting

- If you see "API key not configured" error, make sure:
  - The `.env` file exists in the `backend/` directory
  - The API key starts with `sk-`
  - You've restarted the backend server after adding the key
  - No extra spaces around the `=` sign

