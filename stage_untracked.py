import os
import subprocess

def stage_untracked():
    # Get all untracked files from git status
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    
    untracked_paths = []
    for line in lines:
        if line.startswith('?? '):
            path = line[3:].strip()
            # Handle potential quotes in path
            if path.startswith('"') and path.endswith('"'):
                path = path[1:-1]
            untracked_paths.append(path)
            
    print(f"Found {len(untracked_paths)} untracked paths.")
    
    success_count = 0
    fail_count = 0
    
    for path in untracked_paths:
        try:
            # Check if path exists before adding
            if os.path.exists(path):
                subprocess.run(['git', 'add', path], check=True, capture_output=True)
                success_count += 1
            else:
                print(f"Skipping non-existent path: {path}")
                fail_count += 1
        except subprocess.CalledProcessError as e:
            print(f"Failed to add {path}: {e.stderr}")
            fail_count += 1
            
    print(f"Successfully staged {success_count} paths.")
    print(f"Failed to stage {fail_count} paths.")

if __name__ == "__main__":
    stage_untracked()
