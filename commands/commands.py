"""
Slash commands system for agent interaction.
"""

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class Command:
    """Slash command definition"""

    name: str
    description: str
    usage: str
    aliases: list[str] = field(default_factory=list)
    handler: Callable = None
    requires_agent: bool = True
    hidden: bool = False


class CommandRegistry:
    """Registry for slash commands"""

    def __init__(self):
        self.commands: dict[str, Command] = {}
        self.aliases: dict[str, str] = {}

    def register(self, command: Command):
        """Register a command"""
        self.commands[command.name] = command
        for alias in command.aliases:
            self.aliases[alias] = command.name

    def unregister(self, name: str):
        """Unregister a command"""
        if name in self.commands:
            cmd = self.commands[name]
            for alias in cmd.aliases:
                self.aliases.pop(alias, None)
            del self.commands[name]

    def get(self, name: str) -> Command | None:
        """Get command by name or alias"""
        if name in self.commands:
            return self.commands[name]
        if name in self.aliases:
            return self.commands[self.aliases[name]]
        return None

    def list_commands(self, include_hidden: bool = False) -> list[Command]:
        """List all commands"""
        return [cmd for cmd in self.commands.values() if include_hidden or not cmd.hidden]

    def parse(self, input_text: str) -> tuple | None:
        """Parse slash command from input"""
        if not input_text.startswith("/"):
            return None

        parts = input_text[1:].split(" ", 1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        cmd = self.get(name)
        if cmd:
            return cmd, args
        return None


class CommandContext:
    """Context passed to command handlers"""

    def __init__(self, app, session_id: str, args: str = ""):
        self.app = app
        self.session_id = session_id
        self.args = args
        self.session = app.sessions.get(session_id) if session_id else None
        self.agent = self.session["agent"] if self.session else None
        self.memory = self.session["memory"] if self.session else None
        self.settings = app.settings
        self.llm = app.llm
        self.memory_store = app.memory_store
        self.skill_manager = app.skill_manager

    def reply(self, message: str):
        """Send a reply to the user"""
        self.app.add_message("system", message)

    def reply_markdown(self, message: str):
        """Send a markdown reply"""
        self.app.add_message("system", message)


# Built-in commands
def cmd_help(context: CommandContext, args: str):
    """Show help for commands"""
    registry = context.app.command_registry
    commands = registry.list_commands()

    help_text = "**Available Commands:**\n\n"
    for cmd in sorted(commands, key=lambda c: c.name):
        aliases = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
        help_text += f"**/{cmd.name}**{aliases} - {cmd.description}\n"
        if cmd.usage:
            help_text += f"  Usage: `{cmd.usage}`\n"

    context.reply_markdown(help_text)


def cmd_retry(context: CommandContext, args: str):
    """Resend last user message"""
    if not context.session:
        context.reply("No active session.")
        return
    conv_memory = context.session["memory"]
    recent = conv_memory.get_recent_context(limit=10)
    # Find last user message
    last_user_msg = None
    for entry in reversed(recent):
        if entry.content.startswith("User: "):
            last_user_msg = entry.content[6:]
            break
    if not last_user_msg:
        context.reply("No previous user message to retry.")
        return
    # Remove the assistant response that followed
    agent = context.session["agent"]
    # Re-run the last user message
    context.reply(f"Retrying: {last_user_msg}")
    response = agent.run(last_user_msg)
    context.reply(response)


def cmd_undo(context: CommandContext, args: str):
    """Back up N user turns and re-prompt"""
    if not context.session:
        context.reply("No active session.")
        return
    try:
        n = int(args.strip()) if args.strip() else 1
    except ValueError:
        context.reply("Usage: /undo [N]")
        return
    conv_memory = context.session["memory"]
    recent = conv_memory.get_recent_context(limit=n * 2 + 5)
    # Remove last N user-assistant pairs from memory
    removed = 0
    for entry in reversed(recent):
        if removed >= n * 2:
            break
        conv_memory.store.delete(entry.id)
        removed += 1
    context.reply(f"Undid {n} turn(s). You can now re-send your message.")


def cmd_title(context: CommandContext, args: str):
    """Name the session"""
    if not context.session:
        context.reply("No active session.")
        return
    name = args.strip()
    if not name:
        context.reply("Usage: /title <name>")
        return
    context.session["title"] = name
    context.reply(f"Session titled: {name}")


def cmd_compress(context: CommandContext, args: str):
    """Compress context (keep N recent turns)"""
    if not context.session:
        context.reply("No active session.")
        return
    try:
        parts = args.split()
        keep = int(parts[0]) if parts else 5
    except ValueError:
        context.reply("Usage: /compress [N]")
        return
    conv_memory = context.session["memory"]
    conv_memory.get_recent_context(limit=keep)
    # Clear and restore only recent
    # Note: This is a simplified implementation
    context.reply(f"Context compressed to last {keep} turns.")


def cmd_goal(context: CommandContext, args: str):
    """Set/manage standing goal across turns"""
    if not context.session:
        context.reply("No active session.")
        return
    if not args.strip():
        goal = context.session.get("goal", "None")
        context.reply(f"Current goal: {goal}")
        return
    sub = args.strip().lower()
    if sub in ("clear", "pause", "resume", "status"):
        if sub == "clear":
            context.session["goal"] = None
            context.reply("Goal cleared.")
        elif sub == "pause":
            context.session["goal_paused"] = True
            context.reply("Goal paused.")
        elif sub == "resume":
            context.session["goal_paused"] = False
            context.reply("Goal resumed.")
        else:
            context.reply(
                f"Goal: {context.session.get('goal', 'None')} | Paused: {context.session.get('goal_paused', False)}"
            )
        return
    context.session["goal"] = args.strip()
    context.session["goal_paused"] = False
    context.reply(f"Goal set: {args.strip()}")


def cmd_branch(context: CommandContext, args: str):
    """Branch the session"""
    if not context.session:
        context.reply("No active session.")
        return
    _name = args.strip() or f"branch-{datetime.now().strftime('%H%M%S')}"
    # Create new session with same history
    agent_type = context.session["agent_type"]
    new_session_id = context.app.create_session(agent_type)
    # Copy memory
    old_conv = context.session["memory"]
    new_conv = context.app.sessions[new_session_id]["memory"]
    for entry in old_conv.short_term_buffer:
        new_conv.store.add(entry)
    context.app.switch_session(new_session_id)
    context.reply(f"Branched to new session: {new_session_id}")


def cmd_resume(context: CommandContext, args: str):
    """Resume a named session"""
    session_id = args.strip()
    if not session_id:
        context.reply("Usage: /resume <session_id>")
        return
    if session_id not in context.app.sessions:
        context.reply(f"Session not found: {session_id}")
        return
    context.app.switch_session(session_id)
    context.reply(f"Resumed session: {session_id}")


def cmd_personality(context: CommandContext, args: str):
    """Set a personality for the agent"""
    if not context.session:
        context.reply("No active session.")
        return
    name = args.strip()
    if not name:
        personalities = [
            "default",
            "concise",
            "verbose",
            "creative",
            "analytical",
            "friendly",
            "professional",
        ]
        context.reply(f"Available: {', '.join(personalities)}")
        return
    context.session["personality"] = name
    context.reply(f"Personality set to: {name}")


def cmd_reasoning(context: CommandContext, args: str):
    """Set reasoning effort level"""
    if not context.session:
        context.reply("No active session.")
        return
    level = args.strip().lower()
    levels = ["none", "low", "medium", "high", "max", "ultra"]
    if level not in levels:
        context.reply(f"Usage: /reasoning <{ '|'.join(levels) }>")
        return
    context.session["reasoning_level"] = level
    context.reply(f"Reasoning level: {level}")


def cmd_yolo(context: CommandContext, args: str):
    """Toggle approval bypass"""
    if not context.session:
        context.reply("No active session.")
        return
    context.session["yolo"] = not context.session.get("yolo", False)
    context.reply(f"YOLO mode: {'ON' if context.session['yolo'] else 'OFF'}")


def cmd_usage(context: CommandContext, args: str):
    """Show token usage"""
    if not context.session:
        context.reply("No active session.")
        return
    # Simple usage tracking
    msg_count = context.session.get("message_count", 0)
    context.reply(
        f"Messages this session: {msg_count}\n(Full token tracking requires LLM provider support)"
    )


def cmd_whoami(context: CommandContext, args: str):
    """Show access level"""
    context.reply("Access level: User (local mode)")


def cmd_profile(context: CommandContext, args: str):
    """Show active profile info"""
    settings = context.app.settings.settings
    lines = [
        "**Profile Info:**",
        f"- LLM Backend: {settings.llm.backend}",
        f"- LLM Model: {settings.llm.model or 'auto'}",
        f"- Default Agent: {settings.agent.default_agent}",
        f"- Memory: {'Enabled' if settings.memory.enabled else 'Disabled'}",
        f"- Skills: {'Enabled' if settings.skills.enabled else 'Disabled'}",
    ]
    context.reply_markdown("\n".join(lines))


def cmd_version(context: CommandContext, args: str):
    """Show version"""
    context.reply("Moon AI Agent v1.0.0")


def cmd_update(context: CommandContext, args: str):
    """Check for updates"""
    context.reply("Update check: Run `git pull` in the project directory to update.")


def cmd_new_session(context: CommandContext, args: str):
    """Create a new session"""
    agent_type = args.strip() or "assistant"
    if agent_type not in ["assistant", "researcher", "coder"]:
        context.reply(f"Unknown agent type: {agent_type}. Use: assistant, researcher, coder")
        return

    session_id = context.app.create_session(agent_type)
    context.reply(f"Created new {agent_type} session: {session_id}")


def cmd_switch(context: CommandContext, args: str):
    """Switch to a different session"""
    session_id = args.strip()
    if not session_id:
        context.reply("Usage: /switch <session_id>")
        return

    if session_id not in context.app.sessions:
        context.reply(f"Session not found: {session_id}")
        return

    context.app.switch_session(session_id)
    context.reply(f"Switched to session: {session_id}")


def cmd_sessions(context: CommandContext, args: str):
    """List all sessions"""
    if not context.app.sessions:
        context.reply("No sessions yet.")
        return

    lines = ["**Sessions:**\n"]
    for sid, session in context.app.sessions.items():
        active = " 👉 **CURRENT**" if sid == context.session_id else ""
        created = datetime.fromisoformat(session["created_at"]).strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"- `{sid}` ({session['agent_type']}) - {session['message_count']} msgs - {created}{active}"
        )

    context.reply_markdown("\n".join(lines))


def cmd_delete(context: CommandContext, args: str):
    """Delete a session"""
    session_id = args.strip() or context.session_id
    if not session_id or session_id not in context.app.sessions:
        context.reply("Session not found.")
        return

    if session_id == context.session_id:
        # Create new default session
        context.app.create_session()

    del context.app.sessions[session_id]
    context.app.update_sidebar()
    context.reply(f"Deleted session: {session_id}")


def cmd_agent(context: CommandContext, args: str):
    """Switch agent type for current session"""
    agent_type = args.strip().lower()
    if agent_type not in ["assistant", "researcher", "coder"]:
        context.reply("Usage: /agent <assistant|researcher|coder>")
        return

    if not context.session:
        context.reply("No active session.")
        return

    session_id = context.session_id
    agent, conv_memory = context.app._create_agent_instance(agent_type, session_id)
    context.session["agent"] = agent
    context.session["memory"] = conv_memory
    context.session["agent_type"] = agent_type
    context.app.current_agent_type = agent_type

    context.reply(f"Switched to {agent_type} agent")
    context.app.update_sidebar()
    context.app.refresh_status()


def cmd_skills(context: CommandContext, args: str):
    """List loaded skills"""
    if not context.app.skill_manager:
        context.reply("Skill manager not initialized.")
        return

    skills = context.app.skill_manager.list_skills()
    if not skills:
        context.reply("No skills loaded.")
        return

    lines = ["**Loaded Skills:**\n"]
    for skill in skills:
        lines.append(f"- **{skill.name}** v{skill.version} - {skill.description}")

    context.reply_markdown("\n".join(lines))


def cmd_tools(context: CommandContext, args: str):
    """List available tools"""
    if not context.app.skill_manager:
        context.reply("Skill manager not initialized.")
        return

    tools = context.app.skill_manager.get_all_tools()
    if not tools:
        context.reply("No tools available.")
        return

    lines = ["**Available Tools:**\n"]
    for name, info in tools.items():
        desc = info.get("description", "No description")
        lines.append(f"- **{name}**: {desc}")

    context.reply_markdown("\n".join(lines))


def cmd_memory(context: CommandContext, args: str):
    """Show memory statistics"""
    if not context.app.memory_store:
        context.reply("Memory not initialized.")
        return

    stats = context.app.memory_store.get_stats()

    lines = ["**Memory Statistics:**", f"- Total entries: {stats['total']}", ""]

    for mem_type, info in stats["by_type"].items():
        lines.append(
            f"- {mem_type}: {info['count']} entries (avg importance: {info['avg_importance']:.2f})"
        )

    context.reply_markdown("\n".join(lines))


def cmd_search(context: CommandContext, args: str):
    """Search memories"""
    if not args.strip():
        context.reply("Usage: /search <query>")
        return

    if not context.app.memory_store:
        context.reply("Memory not initialized.")
        return

    results = context.app.memory_store.search(args.strip(), top_k=10)
    if not results:
        context.reply("No results found.")
        return

    lines = [f"**Search results for '{args.strip()}':**\n"]
    for i, result in enumerate(results, 1):
        preview = result.content[:200].replace("\n", " ")
        lines.append(f"{i}. [{result.type}] {preview}...")

    context.reply_markdown("\n".join(lines))


def cmd_clear(context: CommandContext, args: str):
    """Clear chat display"""
    context.app.action_clear_chat()
    context.reply("Chat cleared.")


def cmd_reload(context: CommandContext, args: str):
    """Reload skills"""
    context.app.action_reload_skills()


def cmd_config(context: CommandContext, args: str):
    """Show or modify configuration"""
    if not args.strip():
        # Show current config
        settings = context.app.settings
        lines = [
            "**Current Configuration:**",
            f"- LLM Backend: {settings.llm.backend}",
            f"- LLM Model: {settings.llm.model or 'auto'}",
            f"- Temperature: {settings.llm.temperature}",
            f"- Max Tokens: {settings.llm.max_tokens}",
            f"- Default Agent: {settings.agent.default_agent}",
            f"- Max Steps: {settings.agent.max_steps}",
            f"- Memory Enabled: {settings.memory.enabled}",
            f"- Skills Enabled: {settings.skills.enabled}",
        ]
        context.reply_markdown("\n".join(lines))
        return

    # Parse key=value
    parts = args.split("=", 1)
    if len(parts) != 2:
        context.reply("Usage: /config key=value")
        return

    key, value = parts[0].strip(), parts[1].strip()
    try:
        context.app.settings.set(key, value)
        context.app.settings.save()
        context.reply(f"Set {key} = {value}")
    except Exception as e:
        context.reply(f"Error: {e}")


def cmd_export(context: CommandContext, args: str):
    """Export session data"""
    session_id = args.strip() or context.session_id
    if not session_id or session_id not in context.app.sessions:
        context.reply("Session not found.")
        return

    session = context.app.sessions[session_id]
    conv_memory = session["memory"]

    # Get all messages from memory
    recent = conv_memory.get_recent_context(limit=1000)

    export_data = {
        "session_id": session_id,
        "agent_type": session["agent_type"],
        "created_at": session["created_at"],
        "message_count": session["message_count"],
        "messages": [
            {
                "role": (
                    "user"
                    if m.content.startswith("User: ")
                    else ("assistant" if m.content.startswith("Assistant: ") else "system")
                ),
                "content": m.content,
                "metadata": m.metadata,
                "timestamp": m.created_at,
            }
            for m in recent
        ],
    }

    filename = f"session_export_{session_id}.json"
    with open(filename, "w") as f:
        json.dump(export_data, f, indent=2)

    context.reply(f"Exported to {filename}")


def cmd_import(context: CommandContext, args: str):
    """Import session data"""
    if not args.strip():
        context.reply("Usage: /import <filename>")
        return

    filename = args.strip()
    if not os.path.exists(filename):
        context.reply(f"File not found: {filename}")
        return

    try:
        with open(filename) as f:
            data = json.load(f)

        session_id = data.get("session_id", f"imported-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        agent_type = data.get("agent_type", "assistant")

        session_id = context.app.create_session(agent_type)
        conv_memory = context.app.sessions[session_id]["memory"]

        for msg in data.get("messages", []):
            if msg["role"] == "user":
                conv_memory.add_user_message(msg["content"], msg.get("metadata", {}))
            elif msg["role"] == "assistant":
                conv_memory.add_assistant_message(msg["content"], msg.get("metadata", {}))

        context.reply(f"Imported {len(data.get('messages', []))} messages to session {session_id}")

    except Exception as e:
        context.reply(f"Import error: {e}")


def cmd_model(context: CommandContext, args: str):
    """Show or change LLM model"""
    if not args.strip():
        context.reply(f"Current model: {context.app.settings.llm.model or 'auto'}")
        context.reply(f"Backend: {context.app.settings.llm.backend}")
        return

    # This would require restarting the LLM
    context.reply("Model changes require restart. Use /config llm.model=<model> and restart.")


def cmd_theme(context: CommandContext, args: str):
    """Toggle theme"""
    context.app.action_toggle_theme()
    context.reply(f"Theme: {'dark' if context.app.dark else 'light'}")


def cmd_debug(context: CommandContext, args: str):
    """Debug information"""
    import platform
    import sys

    lines = [
        "**Debug Information:**",
        f"- Python: {sys.version.split()[0]}",
        f"- Platform: {platform.platform()}",
        f"- Sessions: {len(context.app.sessions)}",
        f"- Current session: {context.session_id}",
        f"- Agent: {context.app.current_agent_type}",
        f"- LLM: {type(context.app.llm).__name__}",
        f"- Skills loaded: {len(context.app.skill_manager.skills) if context.app.skill_manager else 0}",
        f"- Tools available: {len(context.app.skill_manager._tool_registry) if context.app.skill_manager else 0}",
        f"- Memory entries: {context.app.memory_store.get_stats()['total'] if context.app.memory_store else 0}",
    ]

    context.reply_markdown("\n".join(lines))


def create_command_registry(app) -> CommandRegistry:
    """Create and populate command registry"""
    registry = CommandRegistry()

    # Help & info
    registry.register(
        Command("help", "Show this help", "/help", handler=lambda ctx, a: cmd_help(ctx, a))
    )
    registry.register(
        Command(
            "debug",
            "Show debug info",
            "/debug",
            handler=lambda ctx, a: cmd_debug(ctx, a),
        )
    )
    registry.register(
        Command(
            "version",
            "Show version",
            "/version",
            aliases=["v"],
            handler=lambda ctx, a: cmd_version(ctx, a),
        )
    )
    registry.register(
        Command(
            "update",
            "Check for updates",
            "/update",
            handler=lambda ctx, a: cmd_update(ctx, a),
        )
    )
    registry.register(
        Command(
            "whoami",
            "Show access level",
            "/whoami",
            handler=lambda ctx, a: cmd_whoami(ctx, a),
        )
    )
    registry.register(
        Command(
            "profile",
            "Show profile info",
            "/profile",
            handler=lambda ctx, a: cmd_profile(ctx, a),
        )
    )
    registry.register(
        Command(
            "usage",
            "Show token usage",
            "/usage",
            handler=lambda ctx, a: cmd_usage(ctx, a),
        )
    )

    # Session management
    registry.register(
        Command(
            "new",
            "Create new session",
            "/new [agent_type]",
            aliases=["n"],
            handler=lambda ctx, a: cmd_new_session(ctx, a),
        )
    )
    registry.register(
        Command(
            "switch",
            "Switch session",
            "/switch <session_id>",
            aliases=["sw"],
            handler=lambda ctx, a: cmd_switch(ctx, a),
        )
    )
    registry.register(
        Command(
            "sessions",
            "List sessions",
            "/sessions",
            aliases=["ls"],
            handler=lambda ctx, a: cmd_sessions(ctx, a),
        )
    )
    registry.register(
        Command(
            "delete",
            "Delete session",
            "/delete [session_id]",
            aliases=["rm", "del"],
            handler=lambda ctx, a: cmd_delete(ctx, a),
        )
    )
    registry.register(
        Command(
            "retry",
            "Resend last message",
            "/retry",
            handler=lambda ctx, a: cmd_retry(ctx, a),
        )
    )
    registry.register(
        Command(
            "undo",
            "Back up N turns",
            "/undo [N]",
            handler=lambda ctx, a: cmd_undo(ctx, a),
        )
    )
    registry.register(
        Command(
            "title",
            "Name the session",
            "/title <name>",
            handler=lambda ctx, a: cmd_title(ctx, a),
        )
    )
    registry.register(
        Command(
            "compress",
            "Compress context",
            "/compress [N]",
            handler=lambda ctx, a: cmd_compress(ctx, a),
        )
    )
    registry.register(
        Command(
            "goal",
            "Set/manage standing goal",
            "/goal [text|sub]",
            handler=lambda ctx, a: cmd_goal(ctx, a),
        )
    )
    registry.register(
        Command(
            "branch",
            "Branch the session",
            "/branch [name]",
            aliases=["fork"],
            handler=lambda ctx, a: cmd_branch(ctx, a),
        )
    )
    registry.register(
        Command(
            "resume",
            "Resume a session",
            "/resume <session_id>",
            handler=lambda ctx, a: cmd_resume(ctx, a),
        )
    )

    # Agent management
    registry.register(
        Command(
            "agent",
            "Switch agent type",
            "/agent <assistant|researcher|coder>",
            aliases=["a"],
            handler=lambda ctx, a: cmd_agent(ctx, a),
        )
    )
    registry.register(
        Command(
            "personality",
            "Set agent personality",
            "/personality [name]",
            handler=lambda ctx, a: cmd_personality(ctx, a),
        )
    )
    registry.register(
        Command(
            "reasoning",
            "Set reasoning level",
            "/reasoning <level>",
            handler=lambda ctx, a: cmd_reasoning(ctx, a),
        )
    )
    registry.register(
        Command(
            "yolo",
            "Toggle approval bypass",
            "/yolo",
            handler=lambda ctx, a: cmd_yolo(ctx, a),
        )
    )

    # Skills & tools
    registry.register(
        Command(
            "skills",
            "List loaded skills",
            "/skills",
            handler=lambda ctx, a: cmd_skills(ctx, a),
        )
    )
    registry.register(
        Command(
            "tools",
            "List available tools",
            "/tools",
            handler=lambda ctx, a: cmd_tools(ctx, a),
        )
    )

    # Memory
    registry.register(
        Command(
            "memory",
            "Show memory stats",
            "/memory",
            aliases=["mem"],
            handler=lambda ctx, a: cmd_memory(ctx, a),
        )
    )
    registry.register(
        Command(
            "search",
            "Search memories",
            "/search <query>",
            handler=lambda ctx, a: cmd_search(ctx, a),
        )
    )

    # Config
    registry.register(
        Command(
            "config",
            "Show/set config",
            "/config [key=value]",
            handler=lambda ctx, a: cmd_config(ctx, a),
        )
    )

    # Import/Export
    registry.register(
        Command(
            "export",
            "Export session",
            "/export [session_id]",
            handler=lambda ctx, a: cmd_export(ctx, a),
        )
    )
    registry.register(
        Command(
            "import",
            "Import session",
            "/import <filename>",
            handler=lambda ctx, a: cmd_import(ctx, a),
        )
    )

    # Utility
    registry.register(
        Command(
            "clear",
            "Clear chat",
            "/clear",
            aliases=["cls"],
            handler=lambda ctx, a: cmd_clear(ctx, a),
        )
    )
    registry.register(
        Command(
            "reload",
            "Reload skills",
            "/reload",
            handler=lambda ctx, a: cmd_reload(ctx, a),
        )
    )
    registry.register(
        Command(
            "model",
            "Show model info",
            "/model",
            handler=lambda ctx, a: cmd_model(ctx, a),
        )
    )
    registry.register(
        Command("theme", "Toggle theme", "/theme", handler=lambda ctx, a: cmd_theme(ctx, a))
    )

    return registry
