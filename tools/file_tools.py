"""
File operation tools for agents
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, List


def read_file(path: str) -> str:
    """Read a file's contents"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(path: str, content: str) -> str:
    """Write content to a file"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def list_files(path: str = ".") -> str:
    """List files in a directory"""
    try:
        files = []
        for entry in os.scandir(path):
            files.append(f"{'[DIR]' if entry.is_dir() else '[FILE]'} {entry.name}")
        return "\n".join(files) if files else "Directory is empty"
    except Exception as e:
        return f"Error listing files: {str(e)}"


def delete_file(path: str) -> str:
    """Delete a file"""
    try:
        os.remove(path)
        return f"Deleted {path}"
    except Exception as e:
        return f"Error deleting file: {str(e)}"


def create_directory(path: str) -> str:
    """Create a directory"""
    try:
        os.makedirs(path, exist_ok=True)
        return f"Created directory: {path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"


def file_exists(path: str) -> str:
    """Check if a file exists"""
    exists = os.path.exists(path)
    return f"File {'exists' if exists else 'does not exist'}: {path}"


def read_json(path: str) -> str:
    """Read and parse a JSON file"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return json.dumps(data, indent=2)
    except Exception as e:
        return f"Error reading JSON: {str(e)}"


def write_json(path: str, data: Dict[str, Any]) -> str:
    """Write data as JSON to a file"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return f"Successfully wrote JSON to {path}"
    except Exception as e:
        return f"Error writing JSON: {str(e)}"


def get_file_tools() -> List[Dict[str, Any]]:
    """Get all file tools as a list of tool definitions"""
    return [
        {
            "name": "read_file",
            "description": "Read the contents of a file",
            "function": read_file,
            "parameters": {"path": {"type": "string", "description": "Path to the file"}}
        },
        {
            "name": "write_file",
            "description": "Write content to a file",
            "function": write_file,
            "parameters": {
                "path": {"type": "string", "description": "Path to the file"},
                "content": {"type": "string", "description": "Content to write"}
            }
        },
        {
            "name": "list_files",
            "description": "List files in a directory",
            "function": list_files,
            "parameters": {"path": {"type": "string", "description": "Directory path (default: current)"}}
        },
        {
            "name": "delete_file",
            "description": "Delete a file",
            "function": delete_file,
            "parameters": {"path": {"type": "string", "description": "Path to the file"}}
        },
        {
            "name": "create_directory",
            "description": "Create a directory",
            "function": create_directory,
            "parameters": {"path": {"type": "string", "description": "Directory path"}}
        },
        {
            "name": "file_exists",
            "description": "Check if a file exists",
            "function": file_exists,
            "parameters": {"path": {"type": "string", "description": "Path to check"}}
        },
        {
            "name": "read_json",
            "description": "Read and parse a JSON file",
            "function": read_json,
            "parameters": {"path": {"type": "string", "description": "Path to the JSON file"}}
        },
        {
            "name": "write_json",
            "description": "Write data as JSON to a file",
            "function": write_json,
            "parameters": {
                "path": {"type": "string", "description": "Path to the file"},
                "data": {"type": "object", "description": "Data to write as JSON"}
            }
        }
    ]