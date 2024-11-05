import re
from tree_sitter import Language, Parser
from config.constants import TREE_SITTER_JAVA_LIB
import json
import os
JAVA_LANGUAGE = Language(TREE_SITTER_JAVA_LIB, 'java')

def parse_java_file(file_path):
    with open(file_path, 'r', encoding='utf8', errors='replace') as file:
        code = file.read()

    parser = Parser()
    parser.set_language(JAVA_LANGUAGE)
    tree = parser.parse(bytes(code, 'utf8'))

    def walk_tree(node):
        names = []
        if node.type in ['class_declaration', 'interface_declaration']:
            header = code[node.start_byte:node.end_byte]
            name_keyword = 'class' if 'class' in header else 'interface'
            pattern = re.compile(rf'\b{name_keyword}\s+(\w+)')
            match = pattern.search(header)
            if match:
                class_name = match.group(1)
                name = class_name
            else:
                name = None
            names.append(name)
        for child in node.children:
            names.extend(walk_tree(child))
        return names

    root_node = tree.root_node
    return walk_tree(root_node)


def generate_summary(code_base, output_base):
    summary = {}
    for root, dirs, files in os.walk(code_base):
        for file in files:
            if file.endswith(".java"):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, code_base)
                names = parse_java_file(full_path)
                # Update summary
                summary[relative_path] = names

    summary_path = os.path.join(output_base, 'summary.json')
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, 'w') as file:
        json.dump(summary, file, indent=4)
    print(f"Summary JSON saved to {summary_path}")



