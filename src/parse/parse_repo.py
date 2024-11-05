from tree_sitter import Language, Parser
from config.constants import TREE_SITTER_JAVA_LIB
import json
import os
from src.tools.auxiliary import detect_file_encoding

JAVA_LANGUAGE = Language(TREE_SITTER_JAVA_LIB, 'java')


def parse_java_file(file_path,encoding='utf-8'):
    # Read and parse Java files
    with open(file_path, 'rb') as file:
        code = file.read()
    parser = Parser()
    parser.set_language(JAVA_LANGUAGE)
    tree = parser.parse(code)
    def walk_tree(node):
        results = []
        if node.type in ['class_declaration', 'interface_declaration', 'method_declaration','constructor_declaration']:
            entity = {
                'type': node.type.replace('_declaration', ''),  # Simplify type names
                'name': '',
                'start_line': node.start_point[0] + 1,
                'end_line': node.end_point[0] + 1,
                'children': []
            }

            if node.type in ['class_declaration', 'interface_declaration','method_declaration','constructor_declaration']:
                identifier = next((child for child in node.children if child.type == 'identifier'), None)
                if identifier:
                    entity['name'] = identifier.text.decode(encoding)

            for child in node.children:
                entity['children'].extend(walk_tree(child))
            results.append(entity)

        else:
            for child in node.children:
                results.extend(walk_tree(child))

        return results

    root_node = tree.root_node
    json_data = walk_tree(root_node)
    return json_data


def process_java_files(code_base, output_base):
    for root, dirs, files in os.walk(code_base):
        for file in files:
            if file.endswith(".java"):
                full_path = os.path.join(root, file)
                print("Processing file: ", full_path)
                relative_path = os.path.relpath(full_path, code_base)
                output_dir = os.path.join(output_base, os.path.dirname(relative_path))
                os.makedirs(output_dir, exist_ok=True)
                json_data = parse_java_file(full_path,encoding=detect_file_encoding(full_path))
                json_output_path = os.path.join(output_dir, file[:-5] + ".json")
                with open(json_output_path, 'w') as json_file:
                    json.dump(json_data, json_file, indent=4)
                print(f"Processed {full_path} to {json_output_path}")

