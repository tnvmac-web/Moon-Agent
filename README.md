# Moon AI Agent
A framework for running AI agents locally on any device.

## Features

- **Multiple Agent Types**: Researcher, Coder, and General Assistant
- **Local-First**: Runs with Ollama, LM Studio, vLLM, NVIDIA NIM (cloud), or mock mode (no API keys needed)
- **Tool Support**: File operations, web search, code execution, and more
- **Extensible**: Easy to add new agents and tools
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Quick Start

### Option 1: Mock Mode (No Setup Required)
```bash
moon assistant --backend mock
moon researcher --backend mock --task "Research topic"
moon coder --backend mock --task "Write a Python function"
```

### Option 2: Ollama (Recommended for Local Models)
1. Install Ollama: https://ollama.ai
2. Start server: `ollama serve`
3. Pull a model: `ollama pull llama3.2`
4. Run: `moon assistant --backend ollama --model llama3.2`

### Option 3: LM Studio / vLLM (OpenAI-Compatible)
1. Start LM Studio or vLLM server on port 1234
2. Run: `moon assistant --backend openai-compatible`

### Option 4: NVIDIA NIM (Cloud Inference)
1. Get API key from https://build.nvidia.com/
2. Export: `export NVIDIA_API_KEY=your_key_here`
3. Run: `moon assistant --backend nvidia-nim --model "nvidia/nemotron-3-ultra-550b-a55b"`

## Project Structure

```
moon/
├── agents/
│   ├── __init__.py
│   ├── base_agent.py      # Base agent classes (ReAct, PlanAndExecute)
│   └── specialized.py     # Specialized agents (Researcher, Coder, Assistant)
├── models/
│   ├── __init__.py
│   └── local_llm.py       # LLM backends (Ollama, OpenAI-compatible, NVIDIA NIM, Mock)
├── tools/
│   ├── __init__.py
│   ├── file_tools.py      # File operations
│   ├── web_tools.py       # Web search and fetching
│   └── code_tools.py      # Code execution
├── main.py                # Main entry point
├── demo.py                # Demo with mock LLM
├── requirements.txt
└── README.md
```

## Agent Types

| Agent | Best For |
|-------|----------|
| `researcher` | Web research, information gathering, fact-checking |
| `coder` | Writing, debugging, and explaining code |
| `assistant` | General-purpose tasks, conversation, mixed workloads |

## Available Tools

### File Tools
- `read_file` - Read file contents
- `write_file` - Write content to file
- `list_files` - List directory contents
- `delete_file` - Delete a file
- `create_directory` - Create directory
- `file_exists` - Check if file exists
- `read_json` / `write_json` - JSON file operations

### Web Tools
- `web_search` - Search the web (DuckDuckGo, no API key)
- `fetch_url` - Extract text from a URL

### Code Tools
- `run_python` - Execute Python code
- `run_shell` - Execute shell commands
- `install_package` - Install Python packages

## Example Usage

```bash
# Research a topic
moon researcher --backend ollama --model llama3.2 --task "Research the latest developments in AI agents"

# Write code
moon coder --backend ollama --model llama3.2 --task "Create a FastAPI REST API with authentication"

# General assistance
moon assistant --backend ollama --model llama3.2

# Interactive mode (no --task flag)
moon assistant --backend ollama --model llama3.2

# Using NVIDIA NIM (cloud)
moon assistant --backend nvidia-nim --model "nvidia/nemotron-3-ultra-550b-a55b"
moon researcher --backend nvidia-nim --task "Explain quantum computing"
```

## Running the Demo

```bash
python demo.py
```

## Requirements

- Python 3.10+
- requests (for web tools and Ollama backend)

Install with:
```bash
pip install -r requirements.txt
```

## Architecture

The framework uses a ReAct (Reasoning + Acting) pattern where agents:
1. Receive a task
2. Reason about what to do
3. Call tools if needed
4. Observe results
5. Repeat until task is complete

The `PlanAndExecuteAgent` (used by Coder) first creates a plan, then executes it step by step.

## Extending

### Adding a New Tool
1. Create a function in `tools/your_tools.py`
2. Add it to a `get_your_tools()` function
3. Import and use in `agents/specialized.py`

### Adding a New Agent
1. Create a new function in `agents/specialized.py` or new file
2. Use `create_agent()` factory or instantiate directly
3. Add to the agent types in `main.py`

## License

MIT