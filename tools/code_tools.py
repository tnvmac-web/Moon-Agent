"""
Code execution tools for agents
"""
import subprocess
import sys
import os
import tempfile
from typing import Dict, Any, List


def run_python(code: str, timeout: int = 30) -> str:
    """Execute Python code and return output"""
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.returncode != 0:
                output += f"\nReturn code: {result.returncode}"
            return output
        finally:
            os.unlink(temp_path)
    except subprocess.TimeoutExpired:
        return f"Error: Code execution timed out after {timeout} seconds"
    except Exception as e:
        return f"Error executing code: {str(e)}"


def run_shell(command: str, timeout: int = 30, cwd: str = None) -> str:
    """Execute a shell command"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nReturn code: {result.returncode}"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def install_package(package: str) -> str:
    """Install a Python package using pip"""
    return run_shell(f"{sys.executable} -m pip install {package}")


def get_code_tools() -> List[Dict[str, Any]]:
    """Get all code tools as a list of tool definitions"""
    return [
        {
            "name": "run_python",
            "description": "Execute Python code and return the output",
            "function": run_python,
            "parameters": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
            }
        },
        {
            "name": "run_shell",
            "description": "Execute a shell command",
            "function": run_shell,
            "parameters": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                "cwd": {"type": "string", "description": "Working directory", "default": "."}
            }
        },
        {
            "name": "install_package",
            "description": "Install a Python package using pip",
            "function": install_package,
            "parameters": {
                "package": {"type": "string", "description": "Package name to install"}
            }
        }
    ]