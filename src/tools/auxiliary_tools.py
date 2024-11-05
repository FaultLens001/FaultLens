import os
from tree_sitter import Language, Parser
from config.constants import TREE_SITTER_JAVA_LIB
from src.tools.auxiliary import extract_methods_from_class,detect_file_encoding

JAVA_LANGUAGE = Language(TREE_SITTER_JAVA_LIB, 'java')

parser = Parser()
parser.set_language(JAVA_LANGUAGE)


def _get_package_name(file_path):
    """Get the package name of the specified file."""
    with open(file_path, 'rb') as file:
        code = file.read()

    tree = parser.parse(code)
    root_node = tree.root_node

    for child in root_node.children:
        if child.type == 'package_declaration':
            package_name = code[child.start_byte:child.end_byte].decode('utf-8', errors='replace').strip()
            return package_name

    return ''


def _get_imports(file_path):
    """Retrieve a list of libraries imported in the specified file."""
    with open(file_path, 'rb') as file:
        code = file.read()

    tree = parser.parse(code)
    root_node = tree.root_node

    imports = []
    for child in root_node.children:
        if child.type == 'import_declaration':
            imports.append(code[child.start_byte:child.end_byte].decode('utf-8', errors='replace').strip())

    return imports





