Extract Flow README

This README explains how to build the tree-sitter Java language library, install dependencies, and run the `extract_flow.py` script.

1) Install Python dependencies

Open PowerShell and run:

```powershell
python -m pip install --upgrade pip
pip install tree_sitter networkx
```

2) Build tree-sitter Java language shared library

The `tree_sitter` Python package needs a compiled shared library containing the Java grammar. You must clone the `tree-sitter-java` grammar and build a small shared library containing it. Example steps (PowerShell):

```powershell
# create build dir
mkdir build; cd build
# clone tree-sitter-java (if you have git)
git clone https://github.com/tree-sitter/tree-sitter-java.git
# go back to workspace root
cd ..
# Python code will use tree_sitter.Language.build_library; you can also build via Python
python - <<'PY'
from tree_sitter import Language
# Adjust the paths if you cloned into build/tree-sitter-java
Language.build_library(
  'build/my-languages.so',
  ['build/tree-sitter-java']
)
print('Built build/my-languages.so')
PY
```

If you cannot use git in this environment, download the `tree-sitter-java` repo and place it under `build/tree-sitter-java` and then run the Python snippet above.

3) Run the script

From the workspace root (where `extract_flow.py` lives). There are two modes:

- Preferred: build the tree-sitter Java language library (see above) and run normally.
- Demo/fallback: if you don't want to build the tree-sitter library, use the `--no-tree-sitter` flag; the script will use a heuristic regex parser instead (good for small demos).

Example (demo mode using bundled sample project):

```powershell
# Run using the fallback regex parser (no tree-sitter required)
python .\extract_flow.py --project .\sample_project --target CreateAccount --out .\demo_output --no-tree-sitter
```

Example (with tree-sitter available):

```powershell
python .\extract_flow.py --project C:\path\to\java\project --target CreateAccount --out C:\path\to\output_dir
```

Outputs created:
- <target>_flow.java — a merged, readable reference Java file containing needed imports and class/method snippets in execution-relevant order. This is for reading and tracing; it may need small edits to compile because we include method bodies in isolation and not all sibling definitions.

- <target>_flow.json — structured JSON listing the ordered sequence of classes included with their original file paths and line ranges. Example structure:

{
  "target": "CreateAccount",
  "sequence": [
    {"index": 1, "class": "CreateAccount", "file": "C:/.../CreateAccount.java", "start_line": 10, "end_line": 220},
    {"index": 2, "class": "AccountService", "file": "C:/.../AccountService.java", "start_line": 15, "end_line": 300}
  ]
}

Notes and limitations:
- The script uses heuristics to map method invocations to class names (static calls like Class.method() and qualified tokens with initial uppercase). It won't perform full type inference, so calls on local variables won't always resolve to the correct class.
- If multiple classes share the same simple name across packages, the script will warn and may pick one of them; you can extend the script to prefer fully-qualified names.
- The produced merged Java file is intended as a readable reference for humans, not necessarily a compile-ready file.

If you want me to extend the script to support fully-qualified class resolution or to include field/type inference heuristics, tell me which approach you prefer (e.g., basic import/type mapping or using a lightweight Java parser with symbol resolution).
