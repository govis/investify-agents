import os
from typing import Optional
from crewai.tools import tool

@tool("thesis_reader")
def thesis_reader(thesis_name: Optional[str] = None) -> str:
    """Read all files in the Theses folder or a specific thesis subfolder and return their content."""
    base_path = os.path.join("..", "Theses") # Path relative to current folder
    if thesis_name: base_path = os.path.join(base_path, thesis_name)
    if not os.path.exists(base_path): return f"Path {base_path} not found."
    
    content = ""
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content += f"\n--- File: {file_path} ---\n{f.read()}"
    return content
