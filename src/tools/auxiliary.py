import chardet
from tree_sitter import Language, Parser
from config.constants import TREE_SITTER_JAVA_LIB

JAVA_LANGUAGE = Language(TREE_SITTER_JAVA_LIB, 'java')
parser = Parser()
parser.set_language(JAVA_LANGUAGE)


def detect_file_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
        # print(encoding)
    if encoding is None:
        encoding = 'utf-8'
    return encoding


def find_target_and_comments_change(file_path, name, start_line, flag=0):
    with open(file_path, 'rb') as file:
        code = file.read()

    tree = parser.parse(code)
    root_node = tree.root_node

    comments = []
    encoding = detect_file_encoding(file_path)

    def walk_tree(node, encoding):
        if node.type in ['comment', 'line_comment', 'block_comment']:
            comment_line = node.start_point[0] + 1
            if comment_line < start_line:
                comments.append(code[node.start_byte:node.end_byte].decode(encoding, errors='replace').strip())

        declaration = 'method_declaration'
        if flag == 1:
            declaration = 'class_declaration'
        elif flag == 2:
            declaration = 'constructor_declaration'
        if node.type == declaration:
            name_node = next((n for n in node.children if n.type == 'identifier'), None)
            if name_node and code[name_node.start_byte:name_node.end_byte].decode(encoding,
                                                                                  errors='replace').strip() == name:
                if node.start_point[0] + 1 == start_line:
                    return node

                else:
                    comments.clear()
            else:
                comments.clear()

        elif node.type not in ['comment', 'line_comment', 'block_comment']:
            comments.clear()

        for child in node.children:
            result = walk_tree(child, encoding)
            if result:
                return result

    node = walk_tree(root_node, encoding)

    if node:
        content = code[node.start_byte:node.end_byte].decode(encoding, errors='replace').strip()
        # print(comments)
        return {
            'content': content,
            'comments': "\n".join(comments)
        }
    else:
        return None


def find_method_node(file_path, method_name, start_line):
    with open(file_path, 'rb') as file:
        code = file.read()

    tree = parser.parse(code)
    root_node = tree.root_node

    encoding = detect_file_encoding(file_path)

    def walk_tree(node, encoding):
        if (node.type == 'method_declaration') or (node.type == 'constructor_declaration'):
            name_node = next((n for n in node.children if n.type == 'identifier'), None)
            if name_node and code[name_node.start_byte:name_node.end_byte].decode(encoding,
                                                                                  errors='replace').strip() == method_name:
                if node.start_point[0] + 1 == start_line:
                    return node
        for child in node.children:
            result = walk_tree(child, encoding)
            if result:
                return result

    node = walk_tree(root_node, encoding)

    return node


def find_target_and_comments(file_path, name, start_line, flag=0):
    with open(file_path, 'rb') as file:
        code = file.read()

    tree = parser.parse(code)
    root_node = tree.root_node

    comments = []
    encoding = detect_file_encoding(file_path)

    def walk_tree(node, encoding):
        if node.type in ['comment', 'line_comment', 'block_comment']:
            comment_line = node.start_point[0] + 1
            if comment_line < start_line:
                comments.append(code[node.start_byte:node.end_byte].decode(encoding, errors='replace').strip())

        declaration = 'method_declaration'
        if flag == 1:
            declaration = 'class_declaration'
        elif flag == 2:
            declaration = 'constructor_declaration'
        elif flag == 3:
            declaration = 'interface_declaration'
        if node.type == declaration:
            name_node = next((n for n in node.children if n.type == 'identifier'), None)
            if name_node and code[name_node.start_byte:name_node.end_byte].decode(encoding,
                                                                                  errors='replace').strip() == name:
                if node.start_point[0] + 1 == start_line:
                    return node
                else:
                    comments.clear()
            else:
                comments.clear()
        elif node.type not in ['comment', 'line_comment', 'block_comment']:
            comments.clear()

        for child in node.children:
            result = walk_tree(child, encoding)
            if result:
                return result

    node = walk_tree(root_node, encoding)

    if node:
        content = code[node.start_byte:node.end_byte]
        return {
            'content': content,
            'comments': "\n".join(comments)
        }
    else:

        return None


def extract_signature_changed(node, constructor_name=None, encoding='utf-8'):
    method_name = None
    params = []

    identifier = next((child for child in node.children if child.type == 'identifier'), None)
    if identifier:
        method_name = identifier.text.decode(encoding, errors='replace').strip()
    params_node = next((child for child in node.children if child.type == 'formal_parameters'), None)
    if params_node:
        for param in params_node.children:

            if param.type == 'spread_parameter':
                param_type = ""
                for i, child in enumerate(param.children):
                    if child.type == "modifiers" or child.type == "variable_declarator":
                        continue
                    param_type += child.text.decode(encoding, errors='replace').strip()
                if param_type != "":
                    params.append(param_type)

            if param.type == 'formal_parameter':
                type_node = param.child_by_field_name('type')
                name_node = param.child_by_field_name('name')
                dimensions_node = param.child_by_field_name('dimensions')

                if type_node:
                    param_type = type_node.text.decode(encoding, errors='replace').strip()
                    if dimensions_node:
                        # dimentions = method_content[dimentions_node.start_byte:dimentions_node.end_byte].decode(encoding, errors='replace').strip()
                        dimensions = dimensions_node.text.decode(encoding, errors='replace').strip()
                        param_type += dimensions

                    params.append(param_type)

    if method_name and params:
        return f"{method_name}({', '.join(params)})"
    elif method_name:
        return f"{method_name}()"
    elif params:
        return f"{constructor_name}({', '.join(params)})"
    elif constructor_name:
        return f"{constructor_name}()"
    else:
        return None



def extract_methods_from_class(class_content, file_path, shift, encoding='utf-8'):
    comments = []
    methods = []

    tree = parser.parse(class_content)
    root_node = tree.root_node
    class_declaration = next(
        (node for node in root_node.children if node.type in ['class_declaration', 'interface_declaration']), None)
    class_name = ""
    class_actual_type = "class"
    if class_declaration:
        if class_declaration.type == 'interface_declaration':
            class_actual_type = "interface"
            # print_and_log("Really an interface for bug location!")

        identifier = next((child for child in class_declaration.children if child.type == 'identifier'), None)
        if identifier:

            class_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                         errors='replace').strip()


        class_body = next((child for child in class_declaration.children if child.type == f'{class_actual_type}_body'),
                          None)
        if class_body:
            for node in class_body.children:

                if node.type == 'method_declaration' or node.type == 'constructor_declaration':
                    content = class_content[node.start_byte:node.end_byte]
                    start_line = node.start_point[0] + 1 + shift

                    signature = extract_signature_changed(node, encoding=encoding)
                    methods.append(signature)

                    identifier = next((child for child in node.children if child.type == 'identifier'), None)
                    result = {}
                    if identifier and node.type == 'method_declaration':
                        method_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,errors='replace').strip()
                        result = find_target_and_comments(file_path, method_name, start_line)
                    elif node.type == 'constructor_declaration':
                        method_name = class_name
                        result = find_target_and_comments(file_path, method_name, start_line, 2)
                    if result:
                        comment = result.get("comments")
                    else:
                        comment = ""
                    comments.append(comment)
    # print(inner_classes)
    return {"methods_signature_list": methods, "methods_comment_list": comments}


def extract_info_from_innerclass(class_content, shift, encoding='utf-8'):
    methods_info = []
    fields_list = []

    tree = parser.parse(class_content)
    root_node = tree.root_node
    class_declaration = next(
        (node for node in root_node.children if node.type in ['class_declaration', 'interface_declaration']), None)
    class_name = ""
    class_actual_type = "class"
    if class_declaration:
        if class_declaration.type == 'interface_declaration':
            class_actual_type = "interface"
            # print_and_log("Really an interface for bug location!")

        identifier = next((child for child in class_declaration.children if child.type == 'identifier'), None)
        if identifier:
            class_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                         errors='replace').strip()
            # print("Class name:", class_name)
        class_body = next((child for child in class_declaration.children if child.type == f'{class_actual_type}_body'),
                          None)
        if class_body:
            for node in class_body.children:
                if node.type == 'field_declaration':
                    fields_list.append(class_content[node.start_byte:node.end_byte].decode(encoding,
                                                                                           errors='replace').strip())

                if node.type == 'method_declaration' or node.type == 'constructor_declaration':
                    content = class_content[node.start_byte:node.end_byte]
                    start_line = node.start_point[0] + 1 + shift
                    end_line = node.end_point[0] + 1 + shift
                    methods_info.append({"start_line": start_line, "end_line": end_line})
    return methods_info, fields_list


def find_class_from_file(file_path, class_name):
    """Provide the file path and class name to get a list of method signatures with comments."""

    def find_class_declaration(node, class_name, code1, encoding='utf-8'):
        if node.type == 'class_declaration' or node.type == 'interface_declaration':
            for child in node.children:
                if child.type == 'identifier' and code1[child.start_byte:child.end_byte].decode(encoding,
                                                                                                errors='replace').strip() == class_name:
                    return node
        for child in node.children:
            result = find_class_declaration(child, class_name, code1, encoding)
            if result:
                return result
        return None

    with open(file_path, 'rb') as file:
        code = file.read()

    encoding = detect_file_encoding(file_path)
    tree = parser.parse(code)
    root_node = tree.root_node
    class_node = find_class_declaration(root_node, class_name, code, encoding)

    if class_node:
        class_content = code[class_node.start_byte:class_node.end_byte]
        start_line = class_node.start_point[0]
        children = extract_methods_from_class(class_content, file_path, start_line, encoding)
        methods_signature_list = children.get("methods_signature_list")
        methods_comment_list = children.get("methods_comment_list")
        return 1, methods_signature_list, methods_comment_list

    return 0, [], []


def extract_children_from_class(file_path, class_content, shift, encoding='utf-8', actual_type="class"):
    """ extract the overview of the class, including fields, covered methods, inner classes."""
    fields = []
    methods = []
    inner_classes = []
    inner_interfaces = []
    tree = parser.parse(class_content)
    root_node = tree.root_node
    class_declaration = next((node for node in root_node.children if node.type == f'{actual_type}_declaration'), None)
    class_name = ""
    if class_declaration:
        identifier = next((child for child in class_declaration.children if child.type == 'identifier'), None)
        if identifier:
            class_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                         errors='replace').strip()

        class_body = next((child for child in class_declaration.children if child.type == f'{actual_type}_body'), None)
        if class_body:
            for child in class_body.children:
                if child.type == 'field_declaration':
                    fields.append(class_content[child.start_byte:child.end_byte].decode(encoding,
                                                                                        errors='replace').strip())
                elif child.type == 'method_declaration' or child.type == 'constructor_declaration':
                    content = class_content[child.start_byte:child.end_byte]
                    start_line = child.start_point[0] + 1 + shift
                    end_line = child.end_point[0] + 1 + shift
                    signature = extract_signature_changed(child, encoding=encoding)

                    methods.append({"signature": signature, "start_line": start_line, "end_line": end_line})

                elif child.type == 'class_declaration':
                    identifier = next((c for c in child.children if c.type == 'identifier'), None)
                    if identifier:
                        start_line = child.start_point[0] + 1 + shift
                        end_line = child.end_point[0] + 1 + shift
                        inner_class_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                                           errors='replace').strip()
                        inner_classes.append({"inner_class_name": inner_class_name, "start_line": start_line,
                                              "end_line": end_line})

                elif child.type == 'interface_declaration':
                    identifier = next((c for c in child.children if c.type == 'identifier'), None)
                    if identifier:
                        start_line = child.start_point[0] + 1 + shift
                        end_line = child.end_point[0] + 1 + shift
                        inner_interface_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                                               errors='replace').strip()
                        inner_interfaces.append({"inner_interface_name": inner_interface_name, "start_line": start_line,
                                                 "end_line": end_line})

    return {"fields": fields, "methods_signature_list": methods, "inner_classes": inner_classes,
            "inner_interfaces": inner_interfaces}


def extract_inheritance_info(class_content):
    tree = parser.parse(class_content)
    root_node = tree.root_node

    base_class_name = None
    interface_names = []
    class_declaration = root_node.children[0]
    superclass_node = None
    super_interfaces_node = None

    for child in class_declaration.children:
        if child.type == 'superclass':
            superclass_node = child
        elif child.type == 'super_interfaces':
            super_interfaces_node = child

    if superclass_node:
        base_class_name = superclass_node.children[1].text.decode('utf8')
        # print("Base class:", base_class_name)

    if super_interfaces_node:
        # print(super_interfaces_node.children)
        type_list = super_interfaces_node.children[1]
        for type_id in type_list.children:
            if type_id.type == 'type_identifier':
                interface_names.append(type_id.text.decode('utf8'))
        # print("Implemented interfaces:", interface_names)
    return base_class_name, interface_names


def extract_imports(file_path):
    encoding = detect_file_encoding(file_path)
    with open(file_path, 'r', encoding=encoding) as file:
        source_code = file.read()

    tree = parser.parse(bytes(source_code, encoding))
    root_node = tree.root_node

    imports = []
    for node in root_node.children:
        if node.type == 'import_declaration':
            import_statement = source_code[node.start_byte:node.end_byte]
            imports.append(import_statement)

    return imports


def byte_to_character_position(code_line, byte_position):
    substring = code_line[:byte_position]
    return len(substring)


def is_abstract_method(method_code: str) -> bool:
    """Check if a given method code is abstract."""
    tree = parser.parse(bytes(method_code, 'utf8'))
    root_node = tree.root_node
    for node in root_node.children:
        if node.type == 'method_declaration':
            for n in node.children:
                if n.type == 'modifiers':
                    for child in n.children:
                        if child.type == 'abstract' and method_code[child.start_byte:child.end_byte] == 'abstract':
                            return True
    return False


def extract_innerclass_from_class(outer_type, class_content, inner_class, encoding='utf-8'):
    tree = parser.parse(class_content)
    root_node = tree.root_node
    if outer_type == "class":
        class_declaration = next((node for node in root_node.children if node.type == 'class_declaration'), None)
    else:
        class_declaration = next((node for node in root_node.children if node.type == 'interface_declaration'), None)
    class_name = ""
    target = ""
    target_type = "class"
    target_start_line = -99
    target_byte = b""
    if class_declaration:
        identifier = next((child for child in class_declaration.children if child.type == 'identifier'), None)
        if identifier:
            class_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                         errors='replace').strip()
            # print("Class name:", class_name)

        class_body = next((child for child in class_declaration.children if child.type == f'{outer_type}_body'), None)
        if class_body:

            for child in class_body.children:
                if child.type == 'class_declaration':
                    identifier = next((c for c in child.children if c.type == 'identifier'), None)
                    if identifier:
                        inner_class_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                                           errors='replace').strip()
                        if inner_class_name == inner_class:
                            target = class_content[child.start_byte:child.end_byte].decode(encoding,
                                                                                           errors='replace').strip()
                            target_type = "class"
                            target_start_line = child.start_point[0]
                            target_byte = class_content[child.start_byte:child.end_byte]
                            break


                elif child.type == 'interface_declaration':
                    identifier = next((c for c in child.children if c.type == 'identifier'), None)
                    if identifier:
                        inner_interface_name = class_content[identifier.start_byte:identifier.end_byte].decode(encoding,
                                                                                                               errors='replace').strip()
                        if inner_interface_name == inner_class:
                            target = class_content[child.start_byte:child.end_byte].decode(encoding,
                                                                                           errors='replace').strip()
                            target_type = "interface"
                            target_start_line = child.start_point[0]
                            target_byte = class_content[child.start_byte:child.end_byte]
                            break

    return target, target_type, target_start_line, target_byte





