#!/usr/bin/env python3
"""
Unified entry point for Moon AI Agent - all interfaces.
"""
import sys
import os
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(
        description="Moon AI Agent - Run AI agents locally on any device",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Interfaces:
  tui         Rich terminal interface (default)
  web         Web server with WebSocket support
  desktop     Native desktop app (PyWebView)
  cli         Command-line interface

Examples:
  moon                          # Start TUI
  moon tui                      # Start TUI
  moon web                      # Start web server
  moon desktop                  # Start desktop app
  moon cli --task "Hello"       # Run single task
        """
    )

    parser.add_argument(
        "interface",
        nargs="?",
        default="tui",
        choices=["tui", "web", "desktop", "cli"],
        help="Interface to launch (default: tui)"
    )

    # Common options
    parser.add_argument("--backend", default="auto",
                       choices=["auto", "ollama", "openai-compatible", "nvidia-nim", "mock"],
                       help="LLM backend")
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--agent", default="assistant",
                       choices=["assistant", "researcher", "coder"],
                       help="Default agent type")
    parser.add_argument("--config", default=None, help="Config file path")
    parser.add_argument("--task", default=None, help="Task to run (cli mode)")

    # Web options
    parser.add_argument("--host", default=None, help="Web server host")
    parser.add_argument("--port", type=int, default=None, help="Web server port")

    # Desktop options
    parser.add_argument("--width", type=int, default=1200, help="Desktop window width")
    parser.add_argument("--height", type=int, default=800, help="Desktop window height")

    args = parser.parse_args()

    # Set environment variables for settings
    if args.backend:
        os.environ["LLM__BACKEND"] = args.backend
    if args.model:
        os.environ["LLM__MODEL"] = args.model
    if args.agent:
        os.environ["AGENT__DEFAULT_AGENT"] = args.agent
    if args.config:
        os.environ["CONFIG_PATH"] = args.config
    if args.host:
        os.environ["WEB__HOST"] = args.host
    if args.port:
        os.environ["WEB__PORT"] = str(args.port)
    if args.width:
        os.environ["DESKTOP__WIDTH"] = str(args.width)
    if args.height:
        os.environ["DESKTOP__HEIGHT"] = str(args.height)

    # Launch interface
    if args.interface == "tui":
        from terminal.tui import run_tui
        run_tui()

    elif args.interface == "web":
        from web.server import run_server
        run_server(host=args.host, port=args.port)

    elif args.interface == "desktop":
        from desktop.app import create_desktop_app
        create_desktop_app()

    elif args.interface == "cli":
        from main import main as cli_main
        # Reconstruct argv for cli main
        sys.argv = [
            "main.py",
            args.agent or "assistant",
            "--backend", args.backend or "auto"
        ]
        if args.model:
            sys.argv.extend(["--model", args.model])
        if args.task:
            sys.argv.extend(["--task", args.task])
        cli_main()


if __name__ == "__main__":
    main()