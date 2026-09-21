"""Tests for Moon AI Agent"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_import():
    """Test that main modules can be imported"""
    from models.local_llm import create_llm, LocalLLM, OllamaLLM, OpenAICompatibleLLM, NVIDIANIM_LLM, MockLLM
    from agents.base_agent import BaseAgent, ReActAgent, PlanAndExecuteAgent, AgentConfig, Tool
    from agents.specialized import create_agent, create_researcher_agent, create_coder_agent, create_assistant_agent
    from config.settings import get_settings, Settings, LLMSettings
    from memory.memory import MemoryStore, ConversationMemory, MemoryEntry
    from skills.skills import SkillManager, Skill, SkillManifest
    from commands.commands import create_command_registry, CommandRegistry, CommandContext
    from tools.file_tools import get_file_tools
    from tools.web_tools import get_web_tools
    from tools.code_tools import get_code_tools


def test_mock_llm():
    """Test Mock LLM"""
    from models.local_llm import MockLLM
    llm = MockLLM(responses={"hello": "world"})
    assert llm.generate("hello") == "world"
    assert llm.chat([{"role": "user", "content": "hello"}]) == "world"


def test_llm_factory():
    """Test LLM factory"""
    from models.local_llm import create_llm
    llm = create_llm("mock")
    assert llm is not None


def test_agent_creation():
    """Test agent creation"""
    from models.local_llm import create_llm
    from agents.specialized import create_agent
    llm = create_llm("mock")
    agent = create_agent("assistant", llm)
    assert agent is not None
    assert agent.config.name == "Assistant"

    agent = create_agent("researcher", llm)
    assert agent.config.name == "Researcher"

    agent = create_agent("coder", llm)
    assert agent.config.name == "Coder"


def test_settings():
    """Test settings"""
    from config.settings import get_settings
    settings = get_settings()
    assert settings is not None
    assert settings.settings.llm.backend == "auto"


def test_memory():
    """Test memory system"""
    from config.settings import get_settings
    from memory.memory import create_memory_store, ConversationMemory, MemoryEntry
    settings = get_settings()
    store = create_memory_store(settings)
    assert store is not None
    
    conv = ConversationMemory(store)
    entry_id = conv.add_user_message("Hello")
    assert entry_id is not None
    
    entry_id = conv.add_assistant_message("Hi there")
    assert entry_id is not None
    
    recent = conv.get_recent_context(limit=10)
    assert len(recent) == 2


def test_skills():
    """Test skills system"""
    from skills.skills import SkillManager, create_builtin_skills
    manager = SkillManager()
    skills = create_builtin_skills()
    for skill in skills:
        assert skill.initialize()
    for skill in skills:
        manager._tool_registry.update({name: {'skill_name': 'builtin', 'tool_info': info} for name, info in skill.get_tools().items()})
    
    tools = manager.get_all_tools()
    assert "read_file" in tools
    assert "write_file" in tools
    assert "run_python" in tools
    assert "web_search" in tools


def test_commands():
    """Test command registry"""
    from commands.commands import create_command_registry, CommandRegistry
    from config.settings import get_settings
    
    class MockApp:
        def __init__(self):
            self.settings = get_settings()
            self.command_registry = None
            self.sessions = {}
            self.current_session_id = "test"
            self.current_agent_type = "assistant"
            self.dark = False
            from models.local_llm import create_llm
            from memory.memory import create_memory_store, ConversationMemory
            from skills.skills import SkillManager, create_builtin_skills
            from agents.base_agent import ReActAgent, AgentConfig, Tool
            
            self.llm = create_llm("mock")
            self.memory_store = create_memory_store(self.settings)
            self.skill_manager = SkillManager()
            for skill in create_builtin_skills():
                skill.initialize()
                for tool_name, tool_info in skill.get_tools().items():
                    self.skill_manager._tool_registry[tool_name] = {'skill_name': 'builtin', 'tool_info': tool_info}
            
            self.add_message = lambda role, content: None
            self.update_sidebar = lambda: None
            self.refresh_status = lambda: None
            self.action_clear_chat = lambda: None
            self.action_reload_skills = lambda: None
            self.action_toggle_theme = lambda: None
            self.create_session = lambda agent_type="assistant": "test-session"
            self.switch_session = lambda session_id: None
            self._create_agent_instance = lambda agent_type, session_id: (None, None)
    
    app = MockApp()
    registry = create_command_registry(app)
    commands = registry.list_commands()
    assert len(commands) > 20
    
    # Test help command
    cmd = registry.get("help")
    assert cmd is not None
    assert cmd.name == "help"


def test_tools():
    """Test tool definitions"""
    from tools.file_tools import get_file_tools
    from tools.web_tools import get_web_tools
    from tools.code_tools import get_code_tools
    
    file_tools = get_file_tools()
    assert len(file_tools) == 8
    
    web_tools = get_web_tools()
    assert len(web_tools) == 2
    
    code_tools = get_code_tools()
    assert len(code_tools) == 3
    
    # Check tool structure
    for tool in file_tools + web_tools + code_tools:
        assert "name" in tool
        assert "description" in tool
        assert "function" in tool
        assert "parameters" in tool


if __name__ == "__main__":
    pytest.main([__file__, "-v"])