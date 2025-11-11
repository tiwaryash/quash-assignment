from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.api.websocket import websocket_endpoint

app = FastAPI(title="Quash Browser Agent API")

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Quash Browser Agent API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await websocket_endpoint(websocket)
