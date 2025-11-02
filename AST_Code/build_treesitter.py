"""
build_treesitter.py

Helper script to build the Tree-sitter language shared library `build/my-languages.so`.

Usage:
  - Clone the tree-sitter-java grammar into `build/tree-sitter-java`:
      git clone https://github.com/tree-sitter/tree-sitter-java.git build/tree-sitter-java
  - Then run:
      python build_treesitter.py

This script calls tree_sitter.Language.build_library which produces a shared library containing the Java grammar.
If you don't have git or network access, download the grammar manually and place it under build/tree-sitter-java.
"""
from tree_sitter import Language
from pathlib import Path

out = Path('./build/my-languages.so')
repos = [str(Path('build') / 'tree-sitter-java')]
print('Building', out, 'from', repos)
Language.build_library(str(out), repos)
print('Done. Place the resulting shared library at', out)
