"""
Skills system with plugin architecture for extensible agent capabilities.
"""

import asyncio
import importlib
import importlib.util
import inspect
import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillManifest:
    """Skill manifest/metadata"""

    name: str
    version: str
    description: str
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    entry_point: str = "skill_main"  # function or class name
    config_schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Skill(ABC):
    """Base class for all skills"""

    def __init__(self, config: dict[str, Any] = None):
        self.config = config or {}
        self._tools: dict[str, Callable] = {}
        self._event_handlers: dict[str, list[Callable]] = {}

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the skill, return True if successful"""

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up resources"""

    def register_tool(
        self,
        name: str,
        func: Callable,
        description: str = "",
        parameters: dict[str, Any] = None,
    ):
        """Register a tool provided by this skill"""
        self._tools[name] = {
            "function": func,
            "description": description,
            "parameters": parameters or {},
        }

    def get_tools(self) -> dict[str, dict[str, Any]]:
        """Get all tools provided by this skill"""
        return self._tools

    def register_event_handler(self, event: str, handler: Callable):
        """Register an event handler"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def emit_event(self, event: str, data: Any = None):
        """Emit an event to all handlers"""
        for handler in self._event_handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(data))
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in event handler for {event}: {e}")

    def get_manifest(self) -> SkillManifest:
        """Get skill manifest"""
        return SkillManifest(
            name=self.__class__.__name__,
            version="1.0.0",
            description=self.__doc__ or "",
        )


class SkillManager:
    """Manages skill discovery, loading, and lifecycle"""

    def __init__(self, skills_dir: str = "skills", config: dict[str, Any] = None):
        self.skills_dir = Path(skills_dir)
        self.config = config or {}
        self.skills: dict[str, Skill] = {}
        self.manifests: dict[str, SkillManifest] = {}
        self._tool_registry: dict[str, dict[str, Any]] = (
            {}
        )  # tool_name -> {skill_name, tool_info}
        self._event_handlers: dict[str, list[Callable]] = {}

        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def discover_skills(self) -> list[Path]:
        """Discover skill directories"""
        skills = []
        for item in self.skills_dir.iterdir():
            if (
                item.is_dir()
                and (item / "skill.yaml").exists()
                or item.is_dir()
                and (item / "skill.json").exists()
            ):
                skills.append(item)
            elif item.is_dir() and (item / "__init__.py").exists():
                # Python package skill
                skills.append(item)
        return skills

    def load_skill(self, skill_path: Path) -> Skill | None:
        """Load a skill from a directory"""
        try:
            # Load manifest
            manifest_path = skill_path / "skill.yaml"
            if not manifest_path.exists():
                manifest_path = skill_path / "skill.json"

            if manifest_path.exists():
                if manifest_path.suffix == ".yaml":
                    import yaml

                    with open(manifest_path) as f:
                        manifest_data = yaml.safe_load(f)
                else:
                    with open(manifest_path) as f:
                        manifest_data = json.load(f)
                manifest = SkillManifest.from_dict(manifest_data)
            else:
                # Auto-generate from directory name
                manifest = SkillManifest(
                    name=skill_path.name,
                    version="1.0.0",
                    description=f"Auto-discovered skill: {skill_path.name}",
                )

            # Load skill module
            module_path = skill_path / "__init__.py"
            if not module_path.exists():
                logger.warning(f"No __init__.py in skill: {skill_path}")
                return None

            spec = importlib.util.spec_from_file_location(
                f"skill_{skill_path.name}", module_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find skill class or factory function
            skill_class = None
            skill_factory = None

            # Look for class inheriting from Skill
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, Skill) and obj != Skill:
                    skill_class = obj
                    break

            # Look for factory function
            if not skill_class:
                for name, obj in inspect.getmembers(module):
                    if inspect.isfunction(obj) and name in (
                        "create_skill",
                        "skill_main",
                        "get_skill",
                    ):
                        skill_factory = obj
                        break

            if skill_class:
                skill = skill_class(self.config.get(manifest.name, {}))
            elif skill_factory:
                skill = skill_factory(self.config.get(manifest.name, {}))
            else:
                logger.warning(f"No skill class or factory found in: {skill_path}")
                return None

            # Initialize
            if not skill.initialize():
                logger.warning(f"Skill initialization failed: {manifest.name}")
                return None

            # Register tools
            for tool_name, tool_info in skill.get_tools().items():
                if tool_name in self._tool_registry:
                    logger.warning(
                        f"Tool name conflict: {tool_name} (from {self._tool_registry[tool_name]['skill_name']} and {manifest.name})"
                    )
                self._tool_registry[tool_name] = {
                    "skill_name": manifest.name,
                    "tool_info": tool_info,
                }

            # Store
            self.skills[manifest.name] = skill
            self.manifests[manifest.name] = manifest

            logger.info(f"Loaded skill: {manifest.name} v{manifest.version}")
            return skill

        except Exception as e:
            logger.error(f"Failed to load skill {skill_path}: {e}")
            return None

    def load_all_skills(self) -> int:
        """Load all discovered skills"""
        count = 0
        for skill_path in self.discover_skills():
            if self.load_skill(skill_path):
                count += 1
        return count

    def unload_skill(self, name: str) -> bool:
        """Unload a skill"""
        if name in self.skills:
            skill = self.skills[name]
            try:
                skill.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down skill {name}: {e}")

            # Unregister tools
            for tool_name in list(self._tool_registry.keys()):
                if self._tool_registry[tool_name]["skill_name"] == name:
                    del self._tool_registry[tool_name]

            del self.skills[name]
            if name in self.manifests:
                del self.manifests[name]

            logger.info(f"Unloaded skill: {name}")
            return True
        return False

    def get_skill(self, name: str) -> Skill | None:
        """Get a loaded skill by name"""
        return self.skills.get(name)

    def get_tool(self, name: str) -> Callable | None:
        """Get a tool function by name"""
        if name in self._tool_registry:
            return self._tool_registry[name]["tool_info"]["function"]
        return None

    def get_all_tools(self) -> dict[str, dict[str, Any]]:
        """Get all available tools from all skills"""
        return {name: info["tool_info"] for name, info in self._tool_registry.items()}

    def get_tool_descriptions(self) -> dict[str, str]:
        """Get tool descriptions for LLM"""
        return {
            name: info["tool_info"].get("description", "")
            for name, info in self._tool_registry.items()
        }

    def list_skills(self) -> list[SkillManifest]:
        """List all loaded skills"""
        return list(self.manifests.values())

    def register_global_event_handler(self, event: str, handler: Callable):
        """Register a global event handler"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def emit_global_event(self, event: str, data: Any = None):
        """Emit event to all global handlers"""
        for handler in self._event_handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(data))
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in global event handler for {event}: {e}")

    def shutdown_all(self):
        """Shutdown all skills"""
        for name in list(self.skills.keys()):
            self.unload_skill(name)


# Built-in skill templates
class CodeExecutionSkill(Skill):
    """Built-in skill for code execution"""

    def initialize(self) -> bool:
        self.register_tool(
            "run_python",
            self.run_python,
            "Execute Python code and return output",
            {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "default": 30},
            },
        )
        self.register_tool(
            "run_shell",
            self.run_shell,
            "Execute shell command",
            {
                "command": {"type": "string", "description": "Shell command"},
                "timeout": {"type": "integer", "default": 30},
            },
        )
        return True

    def shutdown(self):
        pass

    def run_python(self, code: str, timeout: int = 30) -> str:
        import subprocess
        import sys
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name
        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"
            return output
        except subprocess.TimeoutExpired:
            return f"Timeout after {timeout}s"
        finally:
            os.unlink(temp_path)

    def run_shell(self, command: str, timeout: int = 30) -> str:
        import subprocess

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"
            return output
        except subprocess.TimeoutExpired:
            return f"Timeout after {timeout}s"


class FileOperationsSkill(Skill):
    """Built-in skill for file operations"""

    def initialize(self) -> bool:
        self.register_tool(
            "read_file",
            self.read_file,
            "Read file contents",
            {"path": {"type": "string", "description": "File path"}},
        )
        self.register_tool(
            "write_file",
            self.write_file,
            "Write content to file",
            {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to write"},
            },
        )
        self.register_tool(
            "list_files",
            self.list_files,
            "List directory contents",
            {
                "path": {
                    "type": "string",
                    "description": "Directory path",
                    "default": ".",
                }
            },
        )
        self.register_tool(
            "delete_file",
            self.delete_file,
            "Delete a file",
            {"path": {"type": "string", "description": "File path"}},
        )
        return True

    def shutdown(self):
        pass

    def read_file(self, path: str) -> str:
        try:
            with open(path) as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}"

    def write_file(self, path: str, content: str) -> str:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"Written to {path}"
        except Exception as e:
            return f"Error: {e}"

    def list_files(self, path: str = ".") -> str:
        try:
            files = list(Path(path).iterdir())
            return "\n".join(
                f"{'[DIR]' if f.is_dir() else '[FILE]'} {f.name}" for f in files
            )
        except Exception as e:
            return f"Error: {e}"

    def delete_file(self, path: str) -> str:
        try:
            os.remove(path)
            return f"Deleted {path}"
        except Exception as e:
            return f"Error: {e}"


class WebSearchSkill(Skill):
    """Built-in skill for web search"""

    def initialize(self) -> bool:
        self.register_tool(
            "web_search",
            self.web_search,
            "Search the web",
            {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 5},
            },
        )
        self.register_tool(
            "fetch_url",
            self.fetch_url,
            "Fetch and extract text from URL",
            {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_chars": {"type": "integer", "default": 5000},
            },
        )
        return True

    def shutdown(self):
        pass

    def web_search(self, query: str, max_results: int = 5) -> str:
        from urllib.parse import quote_plus

        import requests

        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=10)
            # Simple extraction
            from html.parser import HTMLParser

            class Parser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results = []
                    self.in_result = False

            parser = Parser()
            parser.feed(response.text)
            results = parser.results[:max_results]
            return (
                "\n".join(f"{i+1}. {r}" for i, r in enumerate(results))
                if results
                else "No results"
            )
        except Exception as e:
            return f"Search error: {e}"

    def fetch_url(self, url: str, max_chars: int = 5000) -> str:
        import requests

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=15)
            from html.parser import HTMLParser

            class Extractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.ignore = False

                def handle_starttag(self, tag, attrs):
                    if tag in ("script", "style", "noscript"):
                        self.ignore = True

                def handle_endtag(self, tag):
                    if tag in ("script", "style", "noscript"):
                        self.ignore = False

                def handle_data(self, data):
                    if not self.ignore and data.strip():
                        self.text.append(data.strip())

            extractor = Extractor()
            extractor.feed(response.text)
            full = " ".join(extractor.text)
            return full[:max_chars] + ("..." if len(full) > max_chars else "")
        except Exception as e:
            return f"Fetch error: {e}"


def create_builtin_skills(config: dict[str, Any] = None) -> list[Skill]:
    """Create all built-in skills"""
    return [
        CodeExecutionSkill(config.get("code_execution") if config else None),
        FileOperationsSkill(config.get("file_operations") if config else None),
        WebSearchSkill(config.get("web_search") if config else None),
    ]
