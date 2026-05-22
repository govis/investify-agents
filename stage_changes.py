import os
import subprocess

def stage_all():
    # Get all changes and untracked files
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    
    for line in lines:
        # Status can be M, A, D, R, C, U, ??, !!
        status = line[:2]
        path = line[3:].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
            
        print(f"Adding {path} ({status})")
        try:
            if status == ' D':
                subprocess.run(['git', 'rm', path], capture_output=True)
            else:
                subprocess.run(['git', 'add', path], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to add {path}: {e.stderr}")

if __name__ == "__main__":
    stage_all()
