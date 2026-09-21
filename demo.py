#!/usr/bin/env python3
"""
Demo script showing the agent capabilities with mock LLM that simulates tool usage
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.specialized import create_agent
from models.local_llm import MockLLM


def demo_file_operations():
    """Demo file operations"""
    print("=" * 60)
    print("DEMO: File Operations")
    print("=" * 60)

    # Create a mock LLM that responds with tool calls
    responses = {
        "Create a file called hello.txt with content 'Hello, World!'": 'TOOL_CALL: {"name": "write_file", "arguments": {"path": "hello.txt", "content": "Hello, World!"}}',
        "Read the file hello.txt": 'TOOL_CALL: {"name": "read_file", "arguments": {"path": "hello.txt"}}',
        "List files in current directory": 'TOOL_CALL: {"name": "list_files", "arguments": {"path": "."}}',
    }

    llm = MockLLM(responses)
    agent = create_agent("assistant", llm)

    tasks = [
        "Create a file called hello.txt with content 'Hello, World!'",
        "Read the file hello.txt",
        "List files in current directory",
    ]

    for task in tasks:
        print(f"\n📋 Task: {task}")
        response = agent.run(task)
        print(f"Agent: {response}")


def demo_code_execution():
    """Demo code execution"""
    print("\n" + "=" * 60)
    print("DEMO: Code Execution")
    print("=" * 60)

    responses = {
        "Calculate 2 + 2 using Python": 'TOOL_CALL: {"name": "run_python", "arguments": {"code": "print(2 + 2)"}}',
        "Create a fibonacci function and test it": 'TOOL_CALL: {"name": "run_python", "arguments": {"code": "def fib(n):\\n    a, b = 0, 1\\n    for _ in range(n):\\n        a, b = b, a + b\\n    return a\\n\\nprint([fib(i) for i in range(10)])"}}',
    }

    llm = MockLLM(responses)
    agent = create_agent("coder", llm)

    tasks = [
        "Calculate 2 + 2 using Python",
        "Create a fibonacci function and test it",
    ]

    for task in tasks:
        print(f"\n📋 Task: {task}")
        response = agent.run(task)
        print(f"Agent: {response}")


def demo_web_search():
    """Demo web search"""
    print("\n" + "=" * 60)
    print("DEMO: Web Search")
    print("=" * 60)

    responses = {
        "Search for Python 3.12 new features": 'TOOL_CALL: {"name": "web_search", "arguments": {"query": "Python 3.12 new features", "max_results": 3}}',
    }

    llm = MockLLM(responses)
    agent = create_agent("researcher", llm)

    task = "Search for Python 3.12 new features"
    print(f"\n📋 Task: {task}")
    response = agent.run(task)
    print(f"Agent: {response}")


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                   MOON AI AGENT - DEMO                        ║
║         Demonstrating tool usage with Mock LLM               ║
╚══════════════════════════════════════════════════════════════╝
""")

    demo_file_operations()
    demo_code_execution()
    demo_web_search()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("""
To use with real models:
1. Install Ollama: https://ollama.ai
2. Run: ollama serve
3. Pull a model: ollama pull llama3.2
4. Run: moon assistant --backend ollama --model llama3.2

Or use LM Studio / vLLM with --backend openai-compatible
""")


if __name__ == "__main__":
    main()
