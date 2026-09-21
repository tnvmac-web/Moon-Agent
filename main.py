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

Commands:
  setup        Interactive configuration wizard
  assistant    General-purpose assistant (default)
  researcher   Web research and information gathering
  coder        Code writing, debugging, and explanation

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
  moon --backend nvidia-nim --model "nvidia/nemotron-3-ultra-550b-a55b" --task "Explain transformers"
  moon setup

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


def run_setup():
    """Interactive configuration wizard."""
    print("\n=== Moon AI Agent Setup ===\n")

    # 1. Backend selection
    print("Select LLM backend:")
    print("  1) auto    - Tries ollama, openai-compatible, nvidia-nim, then mock")
    print("  2) ollama  - Local Ollama server")
    print("  3) openai-compatible - LM Studio, vLLM, etc.")
    print("  4) nvidia-nim - NVIDIA cloud inference")
    print("  5) mock    - No model, for testing")
    backend_choice = input("\nChoice [1-5, default=1]: ").strip()
    backend_map = {"1": "auto", "2": "ollama", "3": "openai-compatible", "4": "nvidia-nim", "5": "mock"}
    backend = backend_map.get(backend_choice, "auto")

    # 2. Model
    model = input(f"Model name [{backend} default]: ").strip() or None

    # 3. Tools
    print("\nSelect tools to enable (comma-separated, default: all):")
    print("  file, web, code")
    tools_input = input("Tools [file,web,code]: ").strip()
    tools = [t.strip() for t in tools_input.split(",")] if tools_input else ["file", "web", "code"]

    # 4. API keys
    env_lines = []
    if backend == "nvidia-nim":
        key = input("\nNVIDIA_API_KEY (or press Enter to skip): ").strip()
        if key:
            env_lines.append(f"NVIDIA_API_KEY={key}")
    if backend == "openai-compatible":
        key = input("OpenAI API key (or press Enter to skip): ").strip()
        if key:
            env_lines.append(f"OPENAI_API_KEY={key}")

    # 5. Save config.yaml
    config = {
        "llm": {"backend": backend},
        "agent": {"enabled_tools": tools},
    }
    if model:
        config["llm"]["model"] = model

    import yaml
    with open("config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"\n✅ Saved config.yaml")

    # 6. Save .env
    if env_lines:
        with open(".env", "a") as f:
            f.write("\n")
            for line in env_lines:
                f.write(line + "\n")
        print(f"✅ Saved .env")

    print("\n=== Setup Complete ===")
    print(f"  Backend: {backend}")
    print(f"  Model: {model or 'default'}")
    print(f"  Tools: {', '.join(tools)}")
    print("\nRun 'moon assistant' to start.\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Moon AI Agent", add_help=False)
    parser.add_argument(
        "command",
        nargs="?",
        default="assistant",
        choices=["setup", "researcher", "coder", "assistant"],
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

    if args.command == "setup":
        run_setup()
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
    print(f"🤖 Creating {args.command} agent...")
    agent = create_agent(args.command, llm)
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
