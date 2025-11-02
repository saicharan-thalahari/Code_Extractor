"""
extract_flow.py

A beginner-friendly Python script that:
- Scans a Java project directory for .java files.
- Parses each file using tree_sitter's Java grammar (requires a built language lib).
- Extracts package names, classes, methods, imports, extends/implements, and method invocations.
- Builds a dependency graph (networkx) with call edges and inheritance edges.
- For a given target class name, finds all connected classes (ancestors + descendants), topologically sorts them (or falls back to DFS order), and
  extracts exact code snippets (by AST byte spans) for classes/methods.
- Writes two outputs: <target>_flow.java and <target>_flow.json

Notes:
- This script expects a tree-sitter Java language shared library available at ./build/my-languages.so (with 'java' language).
  If you don't have it, the README explains how to build it.

Allowed libraries used: tree_sitter, networkx, os, json, re, pathlib

Usage:
  python extract_flow.py --project <path_to_java_project> --target <ClassName>

"""

from pathlib import Path
import os
import re
import json
import argparse
from collections import defaultdict, deque

import networkx as nx

# Tree-sitter imports are guarded so the script can print helpful errors if the language isn't available.
try:
    from tree_sitter import Language, Parser
except Exception:
    # We'll support a fallback parser mode (regex-based) so the script can be demoed
    # without building the tree-sitter language library. When possible prefer tree-sitter.
    Language = None
    Parser = None


# ----------------------------- Utility functions ---------------------------------

def find_java_files(root_path: Path):
    """Recursively collect .java files from root_path.

    Returns a list of absolute Path objects.
    """
    java_files = [p for p in root_path.rglob('*.java') if p.is_file()]
    print(f"Found {len(java_files)} Java files under {root_path}")
    return java_files


def load_java_language(lib_path: Path = Path('./build/my-languages.so')):
    """Load the tree-sitter Java language from a compiled shared library.

    If the library or the 'java' language symbol is missing, prints instructions and raises RuntimeError.
    """
    if Language is None:
        raise RuntimeError("tree_sitter package is not installed or failed to import. Install it with: pip install tree_sitter")

    if not lib_path.exists():
        raise RuntimeError(
            f"Language library {lib_path} not found.\n" 
            "Please build it (see README) or place a compiled shared lib at this path.\n"
        )

    try:
        JAVA_LANGUAGE = Language(str(lib_path), 'java')
    except Exception as e:
        raise RuntimeError(f"Failed to load Java language from {lib_path}: {e}")

    parser = Parser()
    parser.set_language(JAVA_LANGUAGE)
    print(f"Loaded Java language from {lib_path}")
    return parser


def extract_from_text_fallback(text: str):
    """A lightweight fallback parser using regex to extract a subset of metadata.

    This returns a structure similar to extract_from_tree so the rest of the pipeline
    can operate even when tree-sitter isn't available. It's heuristic-based and
    intended only for quick demos or small projects.
    """
    result = {
        'package': None,
        'imports': [],
        'classes': {},
        'method_calls': [],
    }

    # package
    m = re.search(r'package\s+([\w\.]+)\s*;', text)
    if m:
        result['package'] = m.group(1)

    # imports
    imports = re.findall(r'import\s+[^;]+;', text)
    result['imports'] = [i.strip() for i in imports]

    # classes (very simple): find class/interface/enum blocks by name using braces balance
    for m in re.finditer(r'(class|interface|enum)\s+(\w+)([^\{]*)\{', text):
        kind = m.group(1)
        name = m.group(2)
        # find matching closing brace by scanning text from m.end()
        start_idx = m.start()
        brace_pos = m.end() - 1
        depth = 0
        end_idx = None
        for i in range(brace_pos, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break
        snippet = text[start_idx:end_idx] if end_idx else text[start_idx: start_idx + 200]

        # methods: crude find method-like blocks inside snippet
        methods = {}
        for mm in re.finditer(r'([\w_<>\[\]]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^\)]*\)\s*\{', snippet):
            mname = mm.group(2)
            mstart = mm.start()
            # find end brace for method
            brace_pos2 = mm.end() - 1
            depth2 = 0
            end_idx2 = None
            for j in range(brace_pos2, len(snippet)):
                if snippet[j] == '{':
                    depth2 += 1
                elif snippet[j] == '}':
                    depth2 -= 1
                    if depth2 == 0:
                        end_idx2 = j + 1
                        break
            m_snip = snippet[mstart:end_idx2] if end_idx2 else snippet[mstart:mstart+200]

            # crude variable mapping inside method: Type var = ...
            vars_map = {}
            for vmatch in re.finditer(r'([A-Z][A-Za-z0-9_]*)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*(=|;)', m_snip):
                vtype = vmatch.group(1)
                vname = vmatch.group(2)
                vars_map[vname] = vtype

            methods[mname] = {
                'snippet': m_snip,
                'start_byte': None,
                'end_byte': None,
                'node': None,
                'vars': vars_map,
            }

        # collect extends/implements heuristically
        extends = []
        implements = []
        h = m.group(3)
        eh = re.search(r'extends\s+([\w\.,\s]+)', h)
        if eh:
            extends = [p.strip().split('.')[-1] for p in eh.group(1).split(',')]
        ih = re.search(r'implements\s+([\w\.,\s]+)', h)
        if ih:
            implements = [p.strip().split('.')[-1] for p in ih.group(1).split(',')]

        # class-level fields: Type name;
        class_vars = {}
        for fmatch in re.finditer(r'([A-Z][A-Za-z0-9_]*)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*(=|;)', snippet):
            ftype = fmatch.group(1)
            fname = fmatch.group(2)
            class_vars[fname] = ftype

        result['classes'][name] = {
            'node': None,
            'start_byte': None,
            'end_byte': None,
            'methods': methods,
            'extends': extends,
            'implements': implements,
            'full_snippet': snippet,
        }
        # attach class-level vars
        result['classes'][name]['class_vars'] = class_vars

    # method call heuristics: find tokens like X.y(...)
    calls = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\.', text)
    result['method_calls'] = calls
    return result


def read_file_bytes(path: Path):
    """Read file bytes and return bytes and decoded text (utf-8 with replacement)."""
    b = path.read_bytes()
    txt = b.decode('utf-8', errors='replace')
    return b, txt


# ----------------------------- AST extraction -----------------------------------

def node_text(node, source_bytes):
    """Return bytes slice for node as decoded string."""
    return source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


def extract_from_tree(tree, source_bytes):
    """Walk the AST and extract package, imports, classes, methods, method invocations, and spans.

    Returns a dict with collected metadata:
      - package (may be None)
      - imports: list of import strings
      - classes: dict[class_name] -> { 'node': node, 'start_byte','end_byte', 'methods': {name: {node, start_byte,end_byte}}, 'file_local_name': class_name }
      - method_calls: list of method invocation raw texts found in the file

    This function is intentionally tolerant: it uses node types typical in tree-sitter-java but also falls back on regex when needed.
    """
    root = tree.root_node
    result = {
        'package': None,
        'imports': [],
        'classes': {},  # classname -> metadata
        'method_calls': [],
    }

    # A simple recursive walker
    def walk(node):
        t = node.type
        # package declaration
        if t == 'package_declaration':
            try:
                result['package'] = node_text(node, source_bytes).strip().replace('\n', ' ')
            except Exception:
                pass

        # imports
        elif t == 'import_declaration':
            try:
                imp = node_text(node, source_bytes).strip()
                result['imports'].append(imp)
            except Exception:
                pass

        # class or interface declaration
        elif t in ('class_declaration', 'interface_declaration', 'enum_declaration'):
            # find identifier child
            name = None
            try:
                # many node types have a child named 'name' or an identifier child
                name_node = node.child_by_field_name('name')
                if name_node is not None:
                    name = node_text(name_node, source_bytes).strip()
                else:
                    # fallback: search for first child of type 'identifier'
                    for c in node.children:
                        if c.type == 'identifier':
                            name = node_text(c, source_bytes).strip()
                            break
            except Exception:
                pass

            if not name:
                # fallback try to regex on the snippet
                snippet = node_text(node, source_bytes)
                m = re.search(r'(class|interface|enum)\s+(\w+)', snippet)
                if m:
                    name = m.group(2)

            if name:
                # initialize entry
                cls_meta = {
                    'node': node,
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte,
                    'methods': {},  # method_name -> {node, start_byte,end_byte}
                    'extends': [],
                    'implements': [],
                    'full_snippet': node_text(node, source_bytes),
                }

                # extract extends/implements via regex on class snippet
                snippet = cls_meta['full_snippet']
                em = re.search(r'extends\s+([\w\.]+)', snippet)
                if em:
                    cls_meta['extends'].append(em.group(1).split('.')[-1])
                im = re.search(r'implements\s+([\w\.,\s]+)', snippet)
                if im:
                    parts = [p.strip() for p in im.group(1).split(',')]
                    cls_meta['implements'].extend([p.split('.')[-1] for p in parts if p])

                # scan child nodes for methods
                for child in node.walk():
                    pass

                # Direct child scan for method_declaration
                for child in node.children:
                    if child.type in ('method_declaration', 'constructor_declaration'):
                        # get method name
                        mname = None
                        try:
                            name_node = child.child_by_field_name('name')
                            if name_node is not None:
                                mname = node_text(name_node, source_bytes).strip()
                            else:
                                # some grammars use 'identifier' child
                                for cc in child.children:
                                    if cc.type == 'identifier':
                                        mname = node_text(cc, source_bytes).strip()
                                        break
                        except Exception:
                            pass

                        if not mname:
                            # fallback simple regex first token
                            snippet = node_text(child, source_bytes)
                            m = re.search(r'([\w_]+)\s*\(', snippet)
                            if m:
                                mname = m.group(1)

                        if not mname:
                            mname = '<anonymous>'

                        cls_meta['methods'][mname] = {
                            'node': child,
                            'start_byte': child.start_byte,
                            'end_byte': child.end_byte,
                            'snippet': node_text(child, source_bytes),
                        }

                result['classes'][name] = cls_meta

        # method invocation
        elif t in ('method_invocation', 'scoped_identifier', 'field_access'):
            try:
                txt = node_text(node, source_bytes).strip()
                # keep the short text for heuristics
                if txt:
                    result['method_calls'].append(txt)
            except Exception:
                pass

        # Recurse
        for c in node.children:
            walk(c)

    walk(root)
    return result


# ----------------------------- Graph building -----------------------------------

def build_dependency_graph(all_files_meta):
    """Given metadata for all files, construct a directed graph with classes as nodes.

    Edges:
      - A -> B when a method in A calls a method on B (heuristic: calls like B.method(...) or B.staticMethod(...)).
      - A -> B when A extends or implements B.

    all_files_meta: list of dicts: each entry has keys: path, package, imports, classes (as returned above)

    Returns a networkx.DiGraph and a mapping class_name -> {file, package}
    """
    G = nx.DiGraph()
    class_to_file = {}

    # register classes
    for meta in all_files_meta:
        path = meta['path']
        pkg = meta['package']
        for cls_name, cls_meta in meta['classes'].items():
            fq_name = cls_name  # we keep simple name; package-awareness can be added later
            if fq_name in class_to_file:
                print(f"Warning: duplicate class name {fq_name} found in {path} and {class_to_file[fq_name]['file']}")
            class_to_file[fq_name] = {
                'file': path,
                'package': pkg,
                'meta': cls_meta,
            }
            G.add_node(fq_name)

    # add inheritance edges
    for name, info in class_to_file.items():
        cls_meta = info['meta']
        for sup in cls_meta.get('extends', []) + cls_meta.get('implements', []):
            if sup in class_to_file:
                G.add_edge(name, sup)
                # label could be 'extends' but we just add the edge

    # add call edges using heuristics, variable-type mapping, and import/package resolution
    known_class_names = set(class_to_file.keys())

    # build simple name -> list of classes mapping (to detect duplicates)
    simple_map = defaultdict(list)
    for simple, info in class_to_file.items():
        pkg = info.get('package') or ''
        fq = f"{pkg}.{simple}" if pkg else simple
        simple_map[simple].append({'simple': simple, 'package': pkg, 'fq': fq, 'file': info['file']})

    for meta in all_files_meta:
        path = meta['path']
        file_pkg = meta.get('package') or ''
        imports = meta.get('imports', [])

        for cls_name, cls_meta in meta['classes'].items():
            caller = cls_name

            # collect class-level vars
            class_vars = cls_meta.get('class_vars', {})

            # inspect method bodies snippets for invocations
            for mname, mm in cls_meta['methods'].items():
                snippet = mm.get('snippet', '')

                # tokens like var.method or Class.method or package.Class.method
                tokens = re.findall(r'([A-Za-z_][A-Za-z0-9_\.]*?)\s*\.', snippet)
                method_vars = mm.get('vars', {}) if isinstance(mm, dict) else {}

                for tok in tokens:
                    if not tok or tok in ('this', 'super'):
                        continue

                    # determine simple name and attempt resolution
                    simple = tok.split('.')[-1]
                    resolved = None

                    # 1) if token is a variable, check method vars then class vars
                    if tok in method_vars:
                        candidate = method_vars[tok]
                        simple = candidate.split('.')[-1]
                    elif tok in class_vars:
                        candidate = class_vars[tok]
                        simple = candidate.split('.')[-1]

                    # 2) check explicit imports for exact class
                    for imp in imports:
                        # import com.example.service.AccountService;
                        m = re.match(r'import\s+([\w\.]+);', imp)
                        if m:
                            imp_fq = m.group(1)
                            if imp_fq.endswith('.' + simple):
                                resolved = simple
                                break
                            # wildcard import: import com.example.service.*;
                            if imp_fq.endswith('.*'):
                                pkg = imp_fq[:-2]
                                # if class exists in that package, pick it
                                if simple in simple_map:
                                    for cand in simple_map[simple]:
                                        if cand['package'] == pkg:
                                            resolved = simple
                                            break
                                if resolved:
                                    break

                    # 3) check same-package
                    if not resolved and file_pkg:
                        if simple in simple_map:
                            for cand in simple_map[simple]:
                                if cand['package'] == file_pkg:
                                    resolved = simple
                                    break

                    # 4) if unique in project, use it
                    if not resolved and simple in simple_map and len(simple_map[simple]) == 1:
                        resolved = simple

                    # finally, add edge if resolved
                    if resolved and resolved in known_class_names:
                        G.add_edge(caller, resolved)

            # Also check top-level file-level method_calls captured by parser heuristics
            for call_txt in meta.get('method_calls', []):
                tokens = re.findall(r'([A-Za-z_][A-Za-z0-9_\.]*?)\s*\.', call_txt)
                for tok in tokens:
                    simple = tok.split('.')[-1]
                    if simple in known_class_names:
                        G.add_edge(caller, simple)

    print(f"Built graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G, class_to_file


# ----------------------------- Graph traversal ----------------------------------

def collect_connected_classes(G: nx.DiGraph, target: str):
    """Return set of classes connected to target: descendants and predecessors (union).

    This captures both code that the target calls and code that calls target.
    """
    if target not in G:
        raise KeyError(f"Target class {target} not found in graph")

    # descendants (reachable from target)
    desc = set(nx.descendants(G, target))
    # predecessors (those that can reach target)
    preds = set(nx.ancestors(G, target))
    all_nodes = set([target]) | desc | preds
    print(f"Target {target}: {len(desc)} descendants, {len(preds)} ancestors => {len(all_nodes)} total connected classes")
    return all_nodes


def topologically_order_subgraph(G: nx.DiGraph, nodes_set):
    """Return a topological ordering of the subgraph induced by nodes_set.

    If cycles are present, fall back to a simple DFS-based order (not strictly topological).
    """
    sub = G.subgraph(nodes_set).copy()
    try:
        order = list(nx.topological_sort(sub))
        print("Topological sort successful")
        return order
    except Exception as e:
        print("Cycle detected: falling back to DFS order")
        # fallback: use DFS postorder
        visited = set()
        order = []

        def dfs(n):
            if n in visited:
                return
            visited.add(n)
            for nb in sub.successors(n):
                dfs(nb)
            order.append(n)

        for n in sub.nodes():
            dfs(n)
        order.reverse()
        return order


# -------------------------- Code extraction -------------------------------------

def extract_code_snippets(order, class_to_file, keep_methods_only=True):
    """Extract code snippets for classes in 'order'.

    For each class:
      - read the original file
      - if keep_methods_only=True: try to include only methods referenced (we don't do deep usage analysis here)
      - otherwise include the full class block

    Returns: imports_set, snippets_list where each snippet is dict {class, file, start_line,end_line, code}
    """
    imports_set = set()
    snippets = []

    for cls_name in order:
        info = class_to_file.get(cls_name)
        if not info:
            print(f"Warning: class {cls_name} has no file info; skipping")
            continue
        path = Path(info['file'])
        pkg = info.get('package')
        cls_meta = info['meta']

        b, txt = read_file_bytes(Path(path))
        # collect imports from the file
        # quick heuristic: match import lines
        file_imports = re.findall(r'^import\s+[^;]+;', txt, flags=re.MULTILINE)
        for imp in file_imports:
            imports_set.add(imp.strip())

        # If keep_methods_only: pick methods we have in cls_meta
        if keep_methods_only and cls_meta['methods']:
            # We'll include the class header (until first method) plus only method blocks
            class_snippet_parts = []
            # get class bytes
            class_bytes = b[cls_meta['start_byte']:cls_meta['end_byte']]
            class_text = class_bytes.decode('utf-8', errors='replace')

            # add a small header: extract upto first method or opening brace line
            header = ''
            m = re.search(r'\{', class_text)
            if m:
                # header upto the first '{' (class header)
                header = class_text[:m.end()] + '\n'
            else:
                header = class_text[:200] + '\n'

            class_snippet_parts.append(header)

            # add each method snippet
            for mname, mm in cls_meta['methods'].items():
                method_code = mm.get('snippet')
                class_snippet_parts.append('\n// ---- method: ' + mname + '\n')
                class_snippet_parts.append(method_code)

            # close the class with a closing brace if missing
            if not class_text.rstrip().endswith('}'):
                class_snippet_parts.append('\n}')

            full = '\n'.join(class_snippet_parts)
            # compute line numbers from start_byte/end_byte
            # compute start/end lines; if AST node info is missing (fallback parser),
            # compute heuristically by searching the file text for the class snippet.
            if cls_meta.get('node') is not None:
                start_line = cls_meta['node'].start_point[0] + 1
                end_line = cls_meta['node'].end_point[0] + 1
            else:
                # heuristic: find 'class <Name>' occurrence
                txt_lines = txt.splitlines()
                start_line = 1
                found = False
                for idx, line in enumerate(txt_lines):
                    if re.search(r'\b(class|interface|enum)\s+' + re.escape(cls_name) + r'\b', line):
                        start_line = idx + 1
                        found = True
                        break
                # end line: estimate from number of lines in the class snippet
                class_text_lines = class_text.splitlines()
                end_line = start_line + max(0, len(class_text_lines) - 1)

            snippets.append({
                'class': cls_name,
                'file': str(path),
                'start_line': start_line,
                'end_line': end_line,
                'code': full,
            })

        else:
            # include whole class
            class_text = cls_meta['full_snippet']
            start_line = cls_meta['node'].start_point[0] + 1
            end_line = cls_meta['node'].end_point[0] + 1
            snippets.append({
                'class': cls_name,
                'file': str(path),
                'start_line': start_line,
                'end_line': end_line,
                'code': class_text,
            })

    return imports_set, snippets


# -------------------------- Output writing --------------------------------------

def write_outputs(target, imports_set, snippets, out_dir: Path = Path('.')):
    """Write <target>_flow.java (merged) and <target>_flow.json (structured metadata).

    Ensures imports are deduplicated and printed at top. The merged Java file will be a readable reference (not guaranteed to compile as-is).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    java_out = out_dir / f"{target}_flow.java"
    json_out = out_dir / f"{target}_flow.json"

    # merge imports into a header
    header_lines = []
    if imports_set:
        header_lines.extend(sorted(imports_set))
        header_lines.append('\n')

    # assemble code sections
    merged_parts = header_lines[:]
    sequence = []
    for i, s in enumerate(snippets, start=1):
        merged_parts.append(f"// === {i}. {s['class']}  (from {s['file']} lines {s['start_line']}-{s['end_line']})\n")
        merged_parts.append(s['code'])
        merged_parts.append('\n\n')
        sequence.append({
            'index': i,
            'class': s['class'],
            'file': s['file'],
            'start_line': s['start_line'],
            'end_line': s['end_line'],
        })

    java_text = '\n'.join(merged_parts)
    java_out.write_text(java_text, encoding='utf-8')
    print(f"Wrote merged Java reference to {java_out}")

    meta = {
        'target': target,
        'sequence': sequence,
    }
    json_out.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(f"Wrote metadata JSON to {json_out}")


# -------------------------- Main workflow --------------------------------------

def run_flow(project_dir: str, target_class: str, output_dir: str = '.', no_tree_sitter: bool = False):
    """Main orchestration function.

    Steps:
      - scan files
      - parse
      - extract metadata
      - build graph
      - collect connected classes
      - order them
      - extract snippets
      - write outputs
    """
    root = Path(project_dir).expanduser().resolve()
    out_dir = Path(output_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project directory {root} does not exist")

    print(f"Scanning project at: {root}")
    java_files = find_java_files(root)
    if not java_files:
        print("No Java files found; exiting.")
        return

    parser = None
    if not no_tree_sitter:
        try:
            parser = load_java_language()
        except Exception as e:
            print(str(e))
            print("Falling back to regex parser. To avoid this, build the tree-sitter library (see README).")
            parser = None

    all_meta = []
    for jf in java_files:
        try:
            b, txt = read_file_bytes(jf)
            if parser is not None:
                tree = parser.parse(b)
                meta = extract_from_tree(tree, b)
            else:
                # fallback: heuristic text extraction
                meta = extract_from_text_fallback(txt)
            meta['path'] = str(jf)
            all_meta.append(meta)
            print(f"Parsed {jf} -> package={meta.get('package')} classes={list(meta.get('classes', {}).keys())}")
        except Exception as e:
            print(f"Failed to parse {jf}: {e}")

    # Build graph
    G, class_to_file = build_dependency_graph(all_meta)

    # Try to find target class exact match; also try without package
    if target_class not in G and target_class.split('.')[-1] in G:
        t = target_class.split('.')[-1]
        print(f"Mapping target {target_class} -> {t}")
        target_class = t

    try:
        connected = collect_connected_classes(G, target_class)
    except KeyError as e:
        print(str(e))
        print("Available classes (sample):", list(G.nodes())[:50])
        return

    order = topologically_order_subgraph(G, connected)
    print("Final sequence:")
    for i, c in enumerate(order, start=1):
        print(f"  {i}. {c}")

    imports_set, snippets = extract_code_snippets(order, class_to_file, keep_methods_only=True)

    write_outputs(target_class, imports_set, snippets, out_dir=out_dir)


# ------------------------------- CLI -------------------------------------------

def cli():
    parser = argparse.ArgumentParser(description='Extract Java feature flow for a target class using tree-sitter')
    parser.add_argument('--project', '-p', required=True, help='Path to Java project root')
    parser.add_argument('--target', '-t', required=True, help='Target class name (e.g. CreateAccount)')
    parser.add_argument('--out', '-o', default='.', help='Output directory for generated files')
    parser.add_argument('--no-tree-sitter', action='store_true', help='Use heuristic regex parser instead of tree-sitter (demo mode)')
    args = parser.parse_args()

    run_flow(args.project, args.target, args.out, no_tree_sitter=args.no_tree_sitter)


if __name__ == '__main__':
    cli()
