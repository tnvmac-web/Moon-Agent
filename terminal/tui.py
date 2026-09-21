"""
Rich Textual TUI for terminal interface.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from rich.markdown import Markdown
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.base_agent import AgentConfig, PlanAndExecuteAgent, ReActAgent, Tool
from commands.commands import CommandContext, create_command_registry
from config.settings import get_settings
from memory.memory import ConversationMemory, create_memory_store
from models.local_llm import create_llm
from skills.skills import SkillManager, create_builtin_skills


class ChatMessage(Message):
    """Message sent from agent to UI"""

    def __init__(self, role: str, content: str, tools_used: list[str] = None):
        self.role = role
        self.content = content
        self.tools_used = tools_used or []
        super().__init__()


class AgentSelected(Message):
    """Agent selection changed"""

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        super().__init__()


class TUIApp(App):
    """Main TUI Application"""

    CSS = """
    Screen {
        background: $surface;
    }
    #main-container {
        layout: horizontal;
        height: 1fr;
    }
    #sidebar {
        width: 35;
        background: $panel;
        border-right: solid $primary;
        padding: 1;
    }
    #chat-area {
        width: 1fr;
        layout: vertical;
    }
    #messages {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    #input-container {
        height: auto;
        padding: 1;
        border-top: solid $primary;
    }
    #message-input {
        height: 3;
    }
    .sidebar-section {
        margin-bottom: 1;
    }
    .sidebar-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .session-item {
        padding: 1;
        margin-bottom: 1;
        background: $surface;
        border: solid $panel;
    }
    .session-item.active {
        border: solid $accent;
        background: $primary 20%;
    }
    .session-name {
        text-style: bold;
    }
    .session-meta {
        color: $text-muted;
        text-style: dim;
    }
    .message {
        margin-bottom: 1;
        padding: 1;
    }
    .message-user {
        background: $primary 20%;
        border-left: solid $accent;
    }
    .message-assistant {
        background: $surface;
        border-left: solid $success;
    }
    .message-system {
        background: $warning 20%;
        border-left: solid $warning;
    }
    .message-role {
            text-style: bold;
            margin-bottom: 1;
        }
        .message-content {
            padding-left: 2;
        }
        #status-bar {
            height: 1;
            background: $panel;
            padding: 0 1;
        }
        DataTable {
            height: 1fr;
        }
        """
    BINDINGS = [
        Binding("ctrl+n", "new_session", "New Session"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "switch_agent", "Switch Agent"),
        Binding("ctrl+h", "toggle_sidebar", "Toggle Sidebar"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("ctrl+r", "reload_skills", "Reload Skills"),
        Binding("ctrl+d", "toggle_theme", "Toggle Theme"),
    ]
    current_session_id: reactive[str] = reactive("")
    current_agent_type: reactive[str] = reactive("assistant")
    sessions: reactive[dict] = reactive({})
    sidebar_visible: reactive[bool] = reactive(True)

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.settings.ensure_dirs()
        # Initialize LLM
        llm_config = self.settings.settings.llm
        self.llm = create_llm(llm_config.backend, model=llm_config.model)
        # Initialize memory
        self.memory_store = create_memory_store(self.settings.settings)
        # Initialize skills
        self.skill_manager = SkillManager(
            skills_dir=self.settings.settings.skills.skills_dir,
            config=(
                self.settings.settings.skills.model_dump()
                if hasattr(self.settings.settings.skills, "model_dump")
                else {}
            ),
        )
        # Load built-in skills
        for skill in create_builtin_skills():
            skill.initialize()
            for tool_name, tool_info in skill.get_tools().items():
                self.skill_manager._tool_registry[tool_name] = {
                    "skill_name": "builtin",
                    "tool_info": tool_info,
                }
        # Load custom skills
        if self.settings.settings.skills.enabled:
            self.skill_manager.load_all_skills()
        # Initialize command registry
        self.command_registry = create_command_registry(self)
        # Agent state
        self.agent = None
        self.conv_memory = None
        self.running = False
        # Don't create session here - do it in on_mount

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main-container"):
            # Sidebar
            with Vertical(id="sidebar") as sidebar:
                self.sidebar = sidebar
                # Sessions
                yield Static("📂 Sessions", classes="sidebar-title")
                with ScrollableContainer(id="sessions-container"):
                    yield Static("No sessions yet", id="sessions-list")
                # Skills
                yield Static("🔌 Skills", classes="sidebar-title")
                with ScrollableContainer(id="skills-container"):
                    yield Static("Loading...", id="skills-list")
                # Tools
                yield Static("🛠️ Tools", classes="sidebar-title")
                with ScrollableContainer(id="tools-container"):
                    yield Static("Loading...", id="tools-list")
            # Chat area
            with Vertical(id="chat-area"):
                with ScrollableContainer(id="messages"):
                    yield RichLog(id="chat-log", markup=True, highlight=True, wrap=True)
                with Container(id="input-container"):
                    yield Input(
                        placeholder="Type your message... (Ctrl+Enter to send, Ctrl+N new session)",
                        id="message-input",
                    )
        yield Footer()
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        """Initialize on mount"""
        self.create_session()
        self.update_sidebar()
        self.refresh_status()
        self.call_later(self.refresh_sidebar_data)
        # Focus input
        self.query_one("#message-input", Input).focus()

    def create_session(self, agent_type: str = None) -> str:
        """Create a new session"""
        import uuid

        session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"
        agent_type = agent_type or self.current_agent_type
        agent, conv_memory = self._create_agent_instance(agent_type, session_id)
        self.sessions[session_id] = {
            "agent": agent,
            "memory": conv_memory,
            "agent_type": agent_type,
            "created_at": datetime.now().isoformat(),
            "message_count": 0,
        }
        self.current_session_id = session_id
        self.current_agent_type = agent_type
        self.update_sidebar()
        self.refresh_status()
        return session_id

    def _create_agent_instance(self, agent_type: str, session_id: str) -> tuple:
        """Create agent instance with memory and tools"""
        conv_memory = ConversationMemory(self.memory_store)
        tools = []
        for tool_name, tool_info in self.skill_manager.get_all_tools().items():
            tools.append(
                Tool(
                    name=tool_name,
                    description=tool_info.get("description", ""),
                    function=tool_info["function"],
                    parameters=tool_info.get("parameters", {}),
                )
            )
        agent_config = AgentConfig(
            name=agent_type.capitalize(),
            description=f"{agent_type} agent",
            system_prompt=self.settings.settings.agent.system_prompt or "",
            tools=tools,
            model_config={
                "temperature": self.settings.settings.llm.temperature,
                "max_tokens": self.settings.settings.llm.max_tokens,
            },
        )
        if agent_type == "coder":
            agent = PlanAndExecuteAgent(self.llm, agent_config)
        else:
            agent = ReActAgent(self.llm, agent_config)
        agent.memory = conv_memory
        return agent, conv_memory

    def switch_session(self, session_id: str):
        """Switch to a different session"""
        if session_id in self.sessions:
            self.current_session_id = session_id
            self.current_agent_type = self.sessions[session_id]["agent_type"]
            self.update_sidebar()
            self.refresh_chat()
            self.refresh_status()

    def action_new_session(self) -> None:
        """Create new session"""
        self.create_session()
        self.refresh_chat()

    def action_switch_agent(self) -> None:
        """Cycle through agent types"""
        agents = ["assistant", "researcher", "coder"]
        current_idx = (
            agents.index(self.current_agent_type) if self.current_agent_type in agents else 0
        )
        next_agent = agents[(current_idx + 1) % len(agents)]
        if self.current_session_id in self.sessions:
            session_id = self.current_session_id
            agent, conv_memory = self._create_agent_instance(next_agent, session_id)
            self.sessions[session_id]["agent"] = agent
            self.sessions[session_id]["memory"] = conv_memory
            self.sessions[session_id]["agent_type"] = next_agent
            self.current_agent_type = next_agent
            self.add_message("system", f"Switched to {next_agent} agent")
            self.update_sidebar()
            self.refresh_status()

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility"""
        self.sidebar_visible = not self.sidebar_visible
        self.sidebar.display = self.sidebar_visible

    def action_clear_chat(self) -> None:
        """Clear chat history"""
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.clear()

    def action_reload_skills(self) -> None:
        """Reload skills"""
        if self.skill_manager:
            self.skill_manager.shutdown_all()
            self.skill_manager.load_all_skills()
            self.add_message("system", "Skills reloaded")
            self.refresh_sidebar_data()

    def action_toggle_theme(self) -> None:
        """Toggle theme"""
        self.dark = not self.dark

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message input"""
        message = event.value.strip()
        if not message:
            return
        event.input.value = ""
        # Check for slash command
        if message.startswith("/"):
            await self.handle_command(message)
        else:
            await self.send_message(message)

    async def send_message(self, message: str) -> None:
        """Send message to agent"""
        if not self.current_session_id or self.current_session_id not in self.sessions:
            return
        session = self.sessions[self.current_session_id]
        agent = session["agent"]
        conv_memory = session["memory"]
        # Add user message
        self.add_message("user", message)
        conv_memory.add_user_message(message)
        # Run agent in background
        self.running = True
        self.refresh_status()
        # Show typing indicator
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write("[dim]🤖 Assistant is thinking...[/dim]")
        # Run in thread
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, agent.run, message)
        # Remove typing indicator (last line)
        # Note: RichLog doesn't support removing last line easily, so we'll just add response
        # Add assistant response
        self.add_message("assistant", response)
        conv_memory.add_assistant_message(response)
        session["message_count"] += 1
        self.update_sidebar()
        self.running = False
        self.refresh_status()

    def add_message(self, role: str, content: str):
        """Add message to chat log"""
        chat_log = self.query_one("#chat-log", RichLog)
        timestamp = datetime.now().strftime("%H:%M:%S")
        if role == "user":
            chat_log.write(f"[bold cyan][{timestamp}] You:[/bold cyan]")
            chat_log.write(f"[cyan]{content}[/cyan]")
        elif role == "assistant":
            chat_log.write(f"[bold green][{timestamp}] Assistant:[/bold green]")
            # Try to render markdown
            try:
                chat_log.write(Markdown(content))
            except Exception:
                chat_log.write(content)
        elif role == "system":
            chat_log.write(f"[bold yellow][{timestamp}] System:[/bold yellow] [dim]{content}[/dim]")
        chat_log.write("")  # Empty line for spacing

    def refresh_chat(self):
        """Refresh chat display from current session"""
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.clear()
        if self.current_session_id and self.current_session_id in self.sessions:
            session = self.sessions[self.current_session_id]
            conv_memory = session["memory"]
            # Show recent messages from memory
            recent = conv_memory.get_recent_context(limit=20)
            for entry in recent:
                if entry.content.startswith("User: "):
                    self.add_message("user", entry.content[6:])
                elif entry.content.startswith("Assistant: "):
                    self.add_message("assistant", entry.content[11:])
                else:
                    self.add_message("system", entry.content)

    def update_sidebar(self):
        """Update sidebar with current session list"""
        sessions_list = self.query_one("#sessions-list", Static)
        if not self.sessions:
            sessions_list.update("No sessions yet")
            return
        # Build session list
        content = []
        for sid, session in self.sessions.items():
            active = " 👉" if sid == self.current_session_id else ""
            created = datetime.fromisoformat(session["created_at"]).strftime("%H:%M")
            content.append(
                f"[bold]{'►' if active else '  '} {session['agent_type']}{active}[/bold]\n"
                f"[dim]  {session['message_count']} msgs • {created}[/dim]"
            )
        sessions_list.update("\n\n".join(content))

    async def refresh_sidebar_data(self):
        """Load skills and tools data"""
        # Skills
        skills_list = self.query_one("#skills-list", Static)
        if self.skill_manager:
            skills = self.skill_manager.list_skills()
            if skills:
                content = []
                for skill in skills:
                    content.append(
                        f"[bold]{skill.name}[/bold] v{skill.version}\n[dim]{skill.description}[/dim]"
                    )
                skills_list.update("\n\n".join(content))
            else:
                skills_list.update("No skills loaded")
        # Tools
        tools_list = self.query_one("#tools-list", Static)
        if self.skill_manager:
            tools = self.skill_manager.get_all_tools()
            if tools:
                content = []
                for name, info in tools.items():
                    desc = info.get("description", "No description")
                    content.append(f"[bold]{name}[/bold]\n[dim]{desc}[/dim]")
                tools_list.update("\n\n".join(content))
            else:
                tools_list.update("No tools available")

    def refresh_status(self):
        """Update status bar"""
        status_bar = self.query_one("#status-bar", Static)
        status = [
            f"Agent: [bold]{self.current_agent_type}[/bold]",
            f"LLM: [bold]{type(self.llm).__name__}[/bold]",
            (
                f"Session: [bold]{self.current_session_id[:20]}...[/bold]"
                if self.current_session_id
                else "No session"
            ),
            f"Skills: [bold]{len(self.skill_manager.skills) if self.skill_manager else 0}[/bold]",
            f"Tools: [bold]{len(self.skill_manager._tool_registry) if self.skill_manager else 0}[/bold]",
            f"Memory: [bold]{self.memory_store.get_stats()['total'] if self.memory_store else 0}[/bold] entries",
        ]
        if self.running:
            status.append("[blink][bold red]● RUNNING[/bold red][/blink]")
        status_bar.update("  │  ".join(status))

    async def handle_command(self, message: str):
        """Handle slash command"""
        parsed = self.command_registry.parse(message)
        if not parsed:
            self.add_message("system", f"[red]Unknown command: {message}[/red]")
            self.add_message("system", "Type /help for available commands")
            return
        cmd, args = parsed
        context = CommandContext(self, self.current_session_id, args)
        try:
            if asyncio.iscoroutinefunction(cmd.handler):
                await cmd.handler(context, args)
            else:
                cmd.handler(context, args)
        except Exception as e:
            self.add_message("system", f"[red]Command error: {e}[/red]")


def run_tui():
    """Run the TUI application"""
    app = TUIApp()
    app.run()


if __name__ == "__main__":
    run_tui()
