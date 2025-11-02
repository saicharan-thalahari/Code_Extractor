import unittest
from pathlib import Path
import json

# Import functions from the script
from extract_flow import find_java_files, read_file_bytes, extract_from_text_fallback, build_dependency_graph

class TestExtractorFallback(unittest.TestCase):
    def setUp(self):
        self.root = Path('sample_project')
        self.java_files = find_java_files(self.root)
        self.all_meta = []
        for jf in self.java_files:
            b, txt = read_file_bytes(jf)
            meta = extract_from_text_fallback(txt)
            meta['path'] = str(jf)
            self.all_meta.append(meta)

    def test_build_graph_contains_expected_edges(self):
        G, cmap = build_dependency_graph(self.all_meta)
        # Expect CreateAccount -> AccountService edge (via AccountService svc = new AccountService())
        self.assertIn('CreateAccount', G.nodes)
        self.assertIn('AccountService', G.nodes)
        self.assertTrue(G.has_edge('CreateAccount', 'AccountService'))
        # Expect AccountService -> Helper (AccountService.openAccount calls Helper.log)
        self.assertIn('Helper', G.nodes)
        self.assertTrue(G.has_edge('AccountService', 'Helper'))

if __name__ == '__main__':
    unittest.main()
