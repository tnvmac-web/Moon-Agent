"""
Specialized agent implementations
"""

from typing import Any

from agents.base_agent import (
    AgentConfig,
    BaseAgent,
    PlanAndExecuteAgent,
    ReActAgent,
    Tool,
)
from models.local_llm import LocalLLM
from tools.code_tools import get_code_tools
from tools.file_tools import get_file_tools
from tools.web_tools import get_web_tools


def create_tool_from_def(definition: dict[str, Any]) -> Tool:
    """Create a Tool object from a tool definition dictionary"""
    return Tool(
        name=definition["name"],
        description=definition["description"],
        function=definition["function"],
        parameters=definition.get("parameters", {}),
    )


def get_all_tools() -> list[Tool]:
    """Get all available tools"""
    all_defs = get_file_tools() + get_web_tools() + get_code_tools()
    return [create_tool_from_def(d) for d in all_defs]


def create_researcher_agent(llm: LocalLLM) -> BaseAgent:
    """Create a research agent specialized in gathering information"""
    tools = [create_tool_from_def(d) for d in get_web_tools()] + [
        create_tool_from_def(d)
        for d in get_file_tools()
        if d["name"] in ("read_file", "write_file", "list_files")
    ]

    config = AgentConfig(
        name="Researcher",
        description="An agent specialized in researching topics, searching the web, and gathering information",
        system_prompt="""You are a Research Agent. Your job is to gather accurate, up-to-date information on any topic.

You have access to web search and file operations. Use web_search to find information, fetch_url to get details from specific pages, and file tools to save your findings.

Always cite your sources. When you search, look for multiple sources to verify information. Be thorough but concise in your summaries.""",
        tools=tools,
        model_config={"temperature": 0.3},
    )

    return ReActAgent(llm, config)


def create_coder_agent(llm: LocalLLM) -> BaseAgent:
    """Create a coding agent specialized in writing and debugging code"""
    tools = (
        [create_tool_from_def(d) for d in get_code_tools()]
        + [create_tool_from_def(d) for d in get_file_tools()]
        + [create_tool_from_def(d) for d in get_web_tools()]
    )

    config = AgentConfig(
        name="Coder",
        description="An agent specialized in writing, debugging, and explaining code",
        system_prompt="""You are a Coder Agent. Your job is to write, debug, and explain code.

You have access to:
- File operations (read, write, list, delete)
- Code execution (run_python, run_shell)
- Package installation
- Web search for documentation

Best practices:
1. Always read existing files before modifying them
2. Write clean, well-commented code
3. Test your code by running it
4. Handle errors gracefully
5. Follow the project's existing patterns and style

When asked to write code, first understand the requirements, then create a plan, then implement step by step.""",
        tools=tools,
        model_config={"temperature": 0.2},
    )

    return PlanAndExecuteAgent(llm, config)


def create_assistant_agent(llm: LocalLLM) -> BaseAgent:
    """Create a general-purpose assistant agent"""
    tools = get_all_tools()

    config = AgentConfig(
        name="Assistant",
        description="A general-purpose AI assistant that can help with a wide variety of tasks",
        system_prompt="""You are a helpful AI Assistant. You can help with a wide variety of tasks including:
- Answering questions
- Researching topics
- Writing and editing text
- Coding and debugging
- File operations
- Web searches
- Data analysis

You have access to many tools. Use them when they help you accomplish the task better.
Be conversational, helpful, and thorough. Ask clarifying questions when needed.""",
        tools=tools,
        model_config={"temperature": 0.7},
    )

    return ReActAgent(llm, config)


def create_agent(agent_type: str, llm: LocalLLM) -> BaseAgent:
    """Factory function to create agents by type"""
    agents = {
        "researcher": create_researcher_agent,
        "coder": create_coder_agent,
        "assistant": create_assistant_agent,
    }

    if agent_type not in agents:
        raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(agents.keys())}")

    return agents[agent_type](llm)
