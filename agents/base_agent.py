"""
Base agent class and agent implementations
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import json


@dataclass
class Tool:
    """Represents a tool the agent can use"""
    name: str
    description: str
    function: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration for an agent"""
    name: str
    description: str
    system_prompt: str
    tools: List[Tool] = field(default_factory=list)
    model_config: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(self, llm, config: AgentConfig):
        self.llm = llm
        self.config = config
        self.tools = {tool.name: tool for tool in config.tools}
        self.history = []
    
    def add_tool(self, tool: Tool):
        self.tools[tool.name] = tool
    
    def remove_tool(self, name: str):
        self.tools.pop(name, None)
    
    def _build_system_prompt(self) -> str:
        tools_desc = "\n".join([
            f"- {name}: {tool.description}"
            for name, tool in self.tools.items()
        ]) if self.tools else "No tools available."
        
        return f"""{self.config.system_prompt}

Available tools:
{tools_desc}

When you need to use a tool, respond with:
TOOL_CALL: {{"name": "tool_name", "arguments": {{"arg1": "value1", "arg2": "value2"}}}}

The tool result will be provided in the next message.
"""
    
    def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self.tools:
            return f"Error: Tool '{name}' not found"
        try:
            return self.tools[name].function(**arguments)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"
    
    def _parse_tool_call(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse tool call from response"""
        if "TOOL_CALL:" in response:
            try:
                start = response.index("TOOL_CALL:") + len("TOOL_CALL:")
                end = response.index("}", start) + 1
                return json.loads(response[start:end])
            except:
                pass
        return None
    
    @abstractmethod
    def run(self, task: str) -> str:
        pass
    
    def chat(self, message: str) -> str:
        """Simple chat interface"""
        self.history.append({"role": "user", "content": message})
        response = self.run(message)
        self.history.append({"role": "assistant", "content": response})
        return response


class ReActAgent(BaseAgent):
    """ReAct (Reasoning + Acting) agent"""
    
    def run(self, task: str, max_steps: int = 10) -> str:
        self.history.append({"role": "user", "content": task})
        
        for step in range(max_steps):
            # Build messages for LLM
            messages = [
                {"role": "system", "content": self._build_system_prompt()}
            ] + self.history
            
            # Get response from LLM
            response = self.llm.chat(messages, **self.config.model_config)
            
            # Check for tool call
            tool_call = self._parse_tool_call(response)
            
            if tool_call:
                # Execute tool
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})
                result = self._execute_tool(tool_name, tool_args)
                
                # Add tool result to history
                self.history.append({"role": "assistant", "content": response})
                self.history.append({"role": "tool", "content": str(result), "tool_name": tool_name})
            else:
                # No tool call, return response
                self.history.append({"role": "assistant", "content": response})
                return response
        
        return "Max steps reached without completion"


class PlanAndExecuteAgent(BaseAgent):
    """Plan-and-execute agent that plans first, then executes"""
    
    def run(self, task: str, max_steps: int = 20) -> str:
        self.history.append({"role": "user", "content": task})
        
        # Step 1: Create plan
        plan_prompt = f"""Create a step-by-step plan to accomplish this task:
{task}

Return your plan as a numbered list. Be specific about what each step does."""
        
        messages = [{"role": "system", "content": self._build_system_prompt()}] + self.history + [{"role": "user", "content": plan_prompt}]
        plan_response = self.llm.chat(messages, **self.config.model_config)
        
        # Add plan to history
        self.history.append({"role": "assistant", "content": f"PLAN:\n{plan_response}"})
        
        # Step 2: Execute plan
        for step in range(max_steps):
            messages = [
                {"role": "system", "content": self._build_system_prompt()}
            ] + self.history + [
                {"role": "user", "content": f"Current plan:\n{plan_response}\n\nExecute the next step. If all steps are done, respond with 'TASK_COMPLETE' and a summary."}
            ]
            
            response = self.llm.chat(messages, **self.config.model_config)
            
            if "TASK_COMPLETE" in response:
                self.history.append({"role": "assistant", "content": response})
                return response
            
            tool_call = self._parse_tool_call(response)
            
            if tool_call:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})
                result = self._execute_tool(tool_name, tool_args)
                
                self.history.append({"role": "assistant", "content": response})
                self.history.append({"role": "tool", "content": str(result), "tool_name": tool_name})
            else:
                self.history.append({"role": "assistant", "content": response})
        
        return "Max steps reached"