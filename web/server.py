"""
Web server with FastAPI + WebSocket for real-time chat interface.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from agents.base_agent import AgentConfig, PlanAndExecuteAgent, ReActAgent, Tool
from config.settings import Settings, get_settings
from memory.memory import ConversationMemory, create_memory_store
from models.local_llm import LocalLLM, create_llm
from skills.skills import SkillManager, create_builtin_skills


# Request/Response models
class ChatMessage(BaseModel):
    role: str  # user, assistant, system
    content: str
    metadata: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str
    agent_type: str = "assistant"
    session_id: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    agent_type: str
    tools_used: list[str] = []


class SessionInfo(BaseModel):
    session_id: str
    created_at: str
    agent_type: str
    message_count: int


# Global state
class ServerState:
    def __init__(self):
        self.settings: Settings | None = None
        self.llm: LocalLLM | None = None
        self.memory_store = None
        self.skill_manager: SkillManager | None = None
        self.active_sessions: dict[str, dict[str, Any]] = {}
        self.websocket_connections: dict[str, WebSocket] = {}


state = ServerState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    state.settings = get_settings()
    state.settings.ensure_dirs()

    # Initialize LLM
    llm_config = state.settings.settings.llm
    state.llm = create_llm(llm_config.backend, model=llm_config.model)

    # Initialize memory
    state.memory_store = create_memory_store(state.settings.settings)

    # Initialize skills
    state.skill_manager = SkillManager(
        skills_dir=state.settings.settings.skills.skills_dir,
        config=(
            state.settings.settings.skills.model_dump()
            if hasattr(state.settings.settings.skills, "model_dump")
            else {}
        ),
    )

    # Load built-in skills
    for skill in create_builtin_skills():
        skill.initialize()
        for tool_name, tool_info in skill.get_tools().items():
            state.skill_manager._tool_registry[tool_name] = {
                "skill_name": "builtin",
                "tool_info": tool_info,
            }

    # Load custom skills
    if state.settings.settings.skills.enabled:
        state.skill_manager.load_all_skills()

    print(
        f"Server started on http://{state.settings.settings.web.host}:{state.settings.settings.web.port}"
    )

    yield

    # Shutdown
    if state.skill_manager:
        state.skill_manager.shutdown_all()
    if state.memory_store:
        state.memory_store.persist()


app = FastAPI(
    title="Moon AI Agent",
    description="Web interface for Moon AI Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
if state.settings and state.settings.web.enable_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)

    async def send_message(self, session_id: str, message: dict[str, Any]):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)

    async def broadcast(self, message: dict[str, Any]):
        for ws in self.active_connections.values():
            await ws.send_json(message)


manager = ConnectionManager()


def create_agent_instance(agent_type: str, session_id: str) -> tuple:
    """Create agent instance with memory and tools"""
    # Get conversation memory
    conv_memory = ConversationMemory(state.memory_store)

    # Get tools from skill manager
    tools = []
    for tool_name, tool_info in state.skill_manager.get_all_tools().items():
        tools.append(
            Tool(
                name=tool_name,
                description=tool_info.get("description", ""),
                function=tool_info["function"],
                parameters=tool_info.get("parameters", {}),
            )
        )

    # Create agent config
    agent_config = AgentConfig(
        name=agent_type.capitalize(),
        description=f"{agent_type} agent",
        system_prompt=state.settings.settings.agent.system_prompt or "",
        tools=tools,
        model_config={
            "temperature": state.settings.settings.llm.temperature,
            "max_tokens": state.settings.settings.llm.max_tokens,
        },
    )

    # Create agent
    if agent_type == "coder":
        agent = PlanAndExecuteAgent(state.llm, agent_config)
    else:
        agent = ReActAgent(state.llm, agent_config)

    # Attach memory
    agent.memory = conv_memory

    return agent, conv_memory


@app.get("/")
async def root():
    """Serve the web UI"""
    static_dir = Path("web/static")
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("""
    <html><body style="font-family: sans-serif; max-width: 800px; margin: 50px auto; padding: 20px;">
    <h1>🌙 Moon AI Agent</h1>
    <p>Web UI not built yet. Use the WebSocket API at <code>/ws/{session_id}</code></p>
    <h2>API Endpoints:</h2>
    <ul>
        <li><code>POST /chat</code> - Send a message</li>
        <li><code>GET /sessions</code> - List sessions</li>
        <li><code>GET /sessions/{session_id}</code> - Get session info</li>
        <li><code>GET /agents</code> - List available agents</li>
        <li><code>GET /skills</code> - List loaded skills</li>
        <li><code>GET /tools</code> - List available tools</li>
        <li><code>GET /memory/stats</code> - Memory statistics</li>
        <li><code>WS /ws/{session_id}</code> - WebSocket for real-time chat</li>
    </ul>
    </body></html>
    """)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to an agent"""
    session_id = request.session_id or str(uuid.uuid4())

    # Get or create session
    if session_id not in state.active_sessions:
        agent, conv_memory = create_agent_instance(request.agent_type, session_id)
        state.active_sessions[session_id] = {
            "agent": agent,
            "memory": conv_memory,
            "agent_type": request.agent_type,
            "created_at": datetime.utcnow().isoformat(),
            "message_count": 0,
        }

    session = state.active_sessions[session_id]
    agent = session["agent"]
    conv_memory = session["memory"]

    # Add user message to memory
    conv_memory.add_user_message(request.message)

    # Run agent
    response = agent.run(request.message)

    # Add assistant response to memory
    conv_memory.add_assistant_message(response)

    session["message_count"] += 1

    # Notify websocket if connected
    await manager.send_message(
        session_id,
        {
            "type": "message",
            "role": "assistant",
            "content": response,
            "session_id": session_id,
        },
    )

    return ChatResponse(
        response=response,
        session_id=session_id,
        agent_type=request.agent_type,
        tools_used=[],
    )


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time chat"""
    await manager.connect(websocket, session_id)

    # Create session if not exists
    if session_id not in state.active_sessions:
        agent, conv_memory = create_agent_instance("assistant", session_id)
        state.active_sessions[session_id] = {
            "agent": agent,
            "memory": conv_memory,
            "agent_type": "assistant",
            "created_at": datetime.utcnow().isoformat(),
            "message_count": 0,
        }

    session = state.active_sessions[session_id]
    agent = session["agent"]
    conv_memory = session["memory"]

    # Send welcome
    await websocket.send_json(
        {
            "type": "welcome",
            "session_id": session_id,
            "agent_type": session["agent_type"],
        }
    )

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "message":
                message = data.get("content", "")
                if message:
                    # Add user message
                    conv_memory.add_user_message(message)

                    # Run agent (in thread to not block)
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, agent.run, message)

                    # Add to memory
                    conv_memory.add_assistant_message(response)
                    session["message_count"] += 1

                    # Send response
                    await websocket.send_json(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": response,
                            "session_id": session_id,
                        }
                    )

            elif data.get("type") == "switch_agent":
                new_agent_type = data.get("agent_type", "assistant")
                agent, conv_memory = create_agent_instance(new_agent_type, session_id)
                state.active_sessions[session_id]["agent"] = agent
                state.active_sessions[session_id]["memory"] = conv_memory
                state.active_sessions[session_id]["agent_type"] = new_agent_type

                await websocket.send_json({"type": "agent_switched", "agent_type": new_agent_type})

    except WebSocketDisconnect:
        manager.disconnect(session_id)


@app.get("/sessions", response_model=list[SessionInfo])
async def list_sessions():
    """List all active sessions"""
    return [
        SessionInfo(
            session_id=sid,
            created_at=info["created_at"],
            agent_type=info["agent_type"],
            message_count=info["message_count"],
        )
        for sid, info in state.active_sessions.items()
    ]


@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """Get session info"""
    if session_id not in state.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    info = state.active_sessions[session_id]
    return SessionInfo(
        session_id=session_id,
        created_at=info["created_at"],
        agent_type=info["agent_type"],
        message_count=info["message_count"],
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    if session_id in state.active_sessions:
        del state.active_sessions[session_id]
        manager.disconnect(session_id)
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/agents")
async def list_agents():
    """List available agent types"""
    return {
        "agents": [
            {
                "id": "assistant",
                "name": "Assistant",
                "description": "General-purpose assistant",
            },
            {
                "id": "researcher",
                "name": "Researcher",
                "description": "Web research and information gathering",
            },
            {
                "id": "coder",
                "name": "Coder",
                "description": "Code writing, debugging, and explanation",
            },
        ]
    }


@app.get("/skills")
async def list_skills():
    """List loaded skills"""
    if not state.skill_manager:
        return {"skills": []}
    return {
        "skills": [
            {
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "author": m.author,
                "tags": m.tags,
            }
            for m in state.skill_manager.list_skills()
        ]
    }


@app.get("/tools")
async def list_tools():
    """List available tools"""
    if not state.skill_manager:
        return {"tools": []}
    tools = state.skill_manager.get_all_tools()
    return {
        "tools": [
            {
                "name": name,
                "description": info.get("description", ""),
                "parameters": info.get("parameters", {}),
            }
            for name, info in tools.items()
        ]
    }


@app.get("/memory/stats")
async def memory_stats():
    """Get memory statistics"""
    if not state.memory_store:
        return {"error": "Memory not initialized"}
    return state.memory_store.get_stats()


@app.post("/memory/search")
async def search_memory(query: str, top_k: int = 10, memory_type: str | None = None):
    """Search memories"""
    if not state.memory_store:
        return {"error": "Memory not initialized"}
    results = state.memory_store.search(query, top_k=top_k, memory_type=memory_type)
    return {
        "results": [
            {
                "id": r.id,
                "type": r.type,
                "content": r.content[:500],
                "tags": r.tags,
                "importance": r.importance,
                "created_at": r.created_at,
            }
            for r in results
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "llm_backend": type(state.llm).__name__ if state.llm else "none",
        "skills_loaded": len(state.skill_manager.skills) if state.skill_manager else 0,
        "active_sessions": len(state.active_sessions),
    }


def run_server(host: str = None, port: int = None):
    """Run the web server"""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "web.server:app",
        host=host or settings.settings.web.host,
        port=port or settings.settings.web.port,
        reload=False,
    )


if __name__ == "__main__":
    run_server()
