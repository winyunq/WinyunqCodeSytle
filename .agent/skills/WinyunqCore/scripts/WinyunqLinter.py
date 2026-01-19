import os
import re
import sys

def check_file(file_path):
    violations = []
    
    # 1. Check filename (PascalCase, no underscore)
    filename = os.path.basename(file_path)
    if "_" in filename and not filename.startswith("Gemini"):
        violations.append(f"Filename contains underscore: {filename}")
    if filename[0].islower() and not filename.startswith("Gemini"):
        violations.append(f"Filename should start with uppercase: {filename}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines):
            # 2. Check for underscores in identifiers (rough regex)
            # Note: ignore complex cases, focus on variable/function lookalikes
            if re.search(r"\b[a-zA-Z]+_[a-zA-Z]+\b", line):
                # Ignore common C++ stuff if necessary, but Winyunq says NO underscores
                violations.append(f"Line {i+1}: Identifier with underscore found.")

            # 3. Check for physical empty lines
            if i > 0 and line.strip() == "" and lines[i-1].strip().startswith(("/", "*")):
                 violations.append(f"Line {i+1}: Forbidden empty line after/before comment.")

    except Exception as e:
        violations.append(f"Error reading file: {e}")

    return violations

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python WinyunqLinter.py <file_or_dir>")
        sys.exit(1)

    target = sys.argv[1]
    all_violations = []

    if os.path.isfile(target):
        all_violations.extend(check_file(target))
    elif os.path.isdir(target):
        for root, dirs, files in os.walk(target):
            for file in files:
                if file.endswith((".cpp", ".hpp", ".h", ".py")):
                    all_violations.extend(check_file(os.path.join(root, file)))

    print(f"--- Winyunq Linter Report for {target} ---")
    if not all_violations:
        print("[SUCCESS] No violations found!")
    else:
        for v in all_violations:
            print(f"[VIOLATION] {v}")
        print(f"\nTotal violations: {len(all_violations)}")
