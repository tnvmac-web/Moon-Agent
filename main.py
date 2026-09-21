#!/usr/bin/env python3
"""
Main entry point for Moon AI Agent
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.base_agent import BaseAgent
from agents.specialized import create_agent
from models.local_llm import create_llm


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                      MOON AI AGENT                            ║
║              Run AI agents locally on any device              ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_help():
    print("""
Usage: moon [agent_type] [options]

Agent Types:
  researcher   - Web research and information gathering
  coder        - Code writing, debugging, and explanation
  assistant    - General-purpose assistant (default)

Options:
  --backend    - LLM backend: ollama, openai-compatible, nvidia-nim, mock, auto (default: auto)
  --model      - Model name (for ollama/openai-compatible/nvidia-nim)
  --task       - Task to execute (if not provided, enters interactive mode)
  --help       - Show this help

Examples:
  moon assistant
  moon researcher --task "Research the latest developments in quantum computing"
  moon coder --backend ollama --model llama3.2 --task "Create a REST API in FastAPI"
  moon --backend mock --task "Hello, how are you?"
  moon --backend nvidia-nim --model "meta/llama-3.1-8b-instruct" --task "Explain transformers"

Backends:
  ollama           - Requires Ollama running (ollama serve)
  openai-compatible - Requires LM Studio, vLLM, or similar running
  nvidia-nim       - Requires NVIDIA_API_KEY env var (cloud inference)
  mock             - No model needed, for testing
  auto             - Tries ollama, then openai-compatible, then nvidia-nim, then mock
""")


def run_interactive(agent: BaseAgent):
    """Run interactive chat loop"""
    print(f"\n🤖 {agent.config.name} Agent - Interactive Mode")
    print("Type 'exit', 'quit', or Ctrl+C to quit\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
            if not user_input:
                continue

            print("Agent: ", end="", flush=True)
            response = agent.chat(user_input)
            print(response)
            print()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            break


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Moon AI Agent", add_help=False)
    parser.add_argument(
        "agent_type",
        nargs="?",
        default="assistant",
        choices=["researcher", "coder", "assistant"],
    )
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["ollama", "openai-compatible", "nvidia-nim", "mock", "auto"],
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--task", default=None)
    parser.add_argument("--help", action="store_true")

    args = parser.parse_args()

    if args.help:
        print_help()
        return

    print_banner()

    # Create LLM
    print(f"🔧 Initializing LLM backend: {args.backend}...")
    llm_kwargs = {}
    if args.model:
        llm_kwargs["model"] = args.model

    try:
        llm = create_llm(args.backend, **llm_kwargs)
        print(f"✅ LLM ready: {type(llm).__name__}")
    except Exception as e:
        print(f"❌ Failed to initialize LLM: {e}")
        print("Falling back to mock mode...")
        llm = create_llm("mock")

    # Create agent
    print(f"🤖 Creating {args.agent_type} agent...")
    agent = create_agent(args.agent_type, llm)
    print(f"✅ Agent ready: {agent.config.name}")

    # Run task or interactive
    if args.task:
        print(f"\n📋 Task: {args.task}\n")
        print("Agent: ", end="", flush=True)
        response = agent.run(args.task)
        print(response)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
