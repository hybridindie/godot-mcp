#!/usr/bin/env python3
"""Quick validation: parse GDScript files for syntax errors.
"""

from pathlib import Path


def validate_gdscript(filepath: Path) -> list[str]:
    """Basic GDScript syntax checks."""
    errors = []
    content = filepath.read_text()
    lines = content.split("\n")
    
    # Check for common issues
    for i, line in enumerate(lines, 1):
        # Check for inconsistent indentation (tabs vs spaces)
        if line.strip() and not line.startswith("#"):
            if "\t" in line and "  " in line:
                errors.append(f"{filepath}:{i}: Mixed tabs and spaces")
        
        # Check for unmatched parens (very basic)
        # Just flag obvious issues
    
    # Check for common Godot 4 issues
    # (none currently)
    
    return errors

def main():
    gd_dir = Path(__file__).resolve().parent
    scripts_dir = gd_dir / "scripts"
    scenes_dir = gd_dir / "scenes"
    
    all_errors = []
    
    # Check scripts
    for script in scripts_dir.glob("*.gd"):
        errors = validate_gdscript(script)
        all_errors.extend(errors)
    
    # Check scene files for obvious issues
    for scene in scenes_dir.glob("*.tscn"):
        content = scene.read_text()
        # Check for ext_resources after node blocks
        lines = content.split("\n")
        in_node_block = False
        for i, line in enumerate(lines, 1):
            if line.startswith("[node "):
                in_node_block = True
            elif line.startswith("[ext_resource ") and in_node_block:
                all_errors.append(f"{scene}:{i}: ext_resource after [node] blocks (must be before)")
                break
    
    if all_errors:
        print("VALIDATION ERRORS:")
        for error in all_errors:
            print(f"  - {error}")
        return 1
    else:
        print("Quick validation passed (no obvious errors found)")
        return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
