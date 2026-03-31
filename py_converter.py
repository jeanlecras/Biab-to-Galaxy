import ast
import os


class BiabFunctionReplacer(ast.NodeTransformer):
    """
    Replace calls to biab_* funcions et .append() methods by their equivalents
    """
    
    def __init__(self):
        self.has_biab_warning = False
        self.has_warning_append = False
    
    def visit_Call(self, node):
        # Replaces biab_error_stop, biab_warning, biab_info
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            
            if func_name == 'biab_error_stop' and len(node.args) >= 1:
                # biab_error stop(message) -> raise Exception(message)
                return ast.Raise(
                    exc=ast.Call(
                        func=ast.Name(id='Exception', ctx=ast.Load()),
                        args=[node.args[0]],
                        keywords=[]
                    ),
                    cause=None
                )
            
            elif func_name == 'biab_warning' and len(node.args) >= 1:
                # biab_warning(message) -> warn(message)
                self.has_biab_warning = True
                return ast.Call(
                    func=ast.Name(id='warn', ctx=ast.Load()),
                    args=[node.args[0]],
                    keywords=[]
                )
            
            elif func_name == 'biab_info' and len(node.args) >= 1:
                # biab_info(message) -> print(message)
                return ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[node.args[0]],
                    keywords=[]
                )
        
        # Replace error.append, warning.append, info.append
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == 'append' and len(node.args) >= 1:
                obj = node.func.value
                
                if isinstance(obj, ast.Name):
                    if obj.id == 'error':
                        # error.append(message) -> raise Exception(message)
                        return ast.Raise(
                            exc=ast.Call(
                                func=ast.Name(id='Exception', ctx=ast.Load()),
                                args=[node.args[0]],
                                keywords=[]
                            ),
                            cause=None
                        )
                    
                    elif obj.id == 'warning':
                        # warning.append(message) -> warn(message)
                        self.has_warning_append = True
                        return ast.Call(
                            func=ast.Name(id='warn', ctx=ast.Load()),
                            args=[node.args[0]],
                            keywords=[]
                        )
                    
                    elif obj.id == 'info':
                        # info.append(message) -> print(message)
                        return ast.Call(
                            func=ast.Name(id='print', ctx=ast.Load()),
                            args=[node.args[0]],
                            keywords=[]
                        )
        
        return self.generic_visit(node)


class BiabOutputReplacer(ast.NodeTransformer):
    """
    Replace calls to biab_output by os.replace or handling of collections
    """
    
    def __init__(self, replacements):
        self.replacements = replacements
        self.found_outputs = set()
    
    def visit_Expr(self, node):
        # Check if this is a biab_output call
        if (isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Name) and
            node.value.func.id == 'biab_output' and
            len(node.value.args) >= 2):
            
            first_arg = node.value.args[0]
            if isinstance(first_arg, ast.Constant):
                output_name = first_arg.value
                
                if output_name in self.replacements:
                    self.found_outputs.add(output_name)
                    second_arg = node.value.args[1]
                    replacement_value = self.replacements[output_name]
                    
                    # Check if this is a collection (key == value)
                    if output_name == replacement_value:
                        # Collection : generate a loop
                        return self._create_collection_replacement(second_arg, output_name)
                    else:
                        # Simple file : os.replace
                        return self._create_simple_replacement(second_arg, replacement_value)
        
        return self.generic_visit(node)
    
    def _create_simple_replacement(self, second_arg, new_path):
        """
        Create os.replace(second_arg, new_path) for a simple file
        """
        return ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id='os', ctx=ast.Load()),
                    attr='replace',
                    ctx=ast.Load()
                ),
                args=[
                    second_arg,
                    ast.Constant(value=new_path)
                ],
                keywords=[]
            )
        )
    
    def _create_collection_replacement(self, second_arg, collection_name):
        """
        Create a loop to handle collections:
        for file_path in second_arg:
            filename = os.path.basename(file_path)
            os.replace(file_path, os.path.join(collection_name, filename))
        """
        return ast.For(
            target=ast.Name(id='file_path', ctx=ast.Store()),
            iter=second_arg,
            body=[
                # filename = os.path.basename(file_path)
                ast.Assign(
                    targets=[ast.Name(id='filename', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Attribute(
                                value=ast.Name(id='os', ctx=ast.Load()),
                                attr='path',
                                ctx=ast.Load()
                            ),
                            attr='basename',
                            ctx=ast.Load()
                        ),
                        args=[ast.Name(id='file_path', ctx=ast.Load())],
                        keywords=[]
                    )
                ),
                # os.replace(file_path, os.path.join(collection_name, filename))
                ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id='os', ctx=ast.Load()),
                            attr='replace',
                            ctx=ast.Load()
                        ),
                        args=[
                            ast.Name(id='file_path', ctx=ast.Load()),
                            ast.Call(
                                func=ast.Attribute(
                                    value=ast.Attribute(
                                        value=ast.Name(id='os', ctx=ast.Load()),
                                        attr='path',
                                        ctx=ast.Load()
                                    ),
                                    attr='join',
                                    ctx=ast.Load()
                                ),
                                args=[
                                    ast.Constant(value=collection_name),
                                    ast.Name(id='filename', ctx=ast.Load())
                                ],
                                keywords=[]
                            )
                        ],
                        keywords=[]
                    )
                )
            ],
            orelse=[]
        )


class BiabInputsReplacer(ast.NodeTransformer):
    """
    Replace var = biab_inputs() with a read of input.json
    """
    
    def visit_Assign(self, node):
        if (len(node.targets) == 1 and
            isinstance(node.targets[0], ast.Name) and
            isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Name) and
            node.value.func.id == 'biab_inputs'):
            
            var_name = node.targets[0].id
            
            # Create: with open('input.json', 'r') as f: var = json.load(f)
            with_stmt = ast.With(
                items=[
                    ast.withitem(
                        context_expr=ast.Call(
                            func=ast.Name(id='open', ctx=ast.Load()),
                            args=[
                                ast.Constant(value='input.json'),
                                ast.Constant(value='r')
                            ],
                            keywords=[]
                        ),
                        optional_vars=ast.Name(id='f', ctx=ast.Store())
                    )
                ],
                body=[
                    ast.Assign(
                        targets=[ast.Name(id=var_name, ctx=ast.Store())],
                        value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id='json', ctx=ast.Load()),
                                attr='load',
                                ctx=ast.Load()
                            ),
                            args=[ast.Name(id='f', ctx=ast.Load())],
                            keywords=[]
                        )
                    )
                ]
            )
            return ast.copy_location(with_stmt, node)
        
        return self.generic_visit(node)


def build_nested_dict(input_names):
    """
    Construct a nested dictionary from a list of paths with points.
    CRSBboxWGS84 is a special case: its attributes become a list.
    
    Args:
        input_names: List of strings such as ‘bboxCRS.CRSBboxWGS84.xmin’
    
    Returns:
        dict: Nested structure with indices sys.argv
    """
    
    nested_dict = {}
    crsbbox_values = {}
    
    for i, input_name in enumerate(input_names, start=1):
        parts = input_name.split('.')
        
        # Special case: CRSBboxWGS84
        if 'CRSBboxWGS84' in parts:
            crsbbox_index = parts.index('CRSBboxWGS84')
            path_to_crsbbox = parts[:crsbbox_index]
            attr_name = parts[crsbbox_index + 1] if crsbbox_index + 1 < len(parts) else None
            
            if attr_name:
                path_key = '.'.join(path_to_crsbbox + ['CRSBboxWGS84'])
                
                if path_key not in crsbbox_values:
                    crsbbox_values[path_key] = []
                
                crsbbox_values[path_key].append((attr_name, i))
        else:
            # Normal case
            current = nested_dict
            for j, part in enumerate(parts):
                if j == len(parts) - 1:
                    current[part] = i
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
    
    # Process CRSBboxWGS84
    for path_key, attrs in crsbbox_values.items():
        parts = path_key.split('.')
        
        current = nested_dict
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Sort in the order xmin, ymin, xmax, ymax
        attr_order = ['xmin', 'ymin', 'xmax', 'ymax']
        sorted_attrs = sorted(attrs, key=lambda x: attr_order.index(x[0]) if x[0] in attr_order else 999)
        
        current['CRSBboxWGS84'] = [idx for attr_name, idx in sorted_attrs]
    
    return nested_dict


def dict_to_ast(data):
    """
    Convert a python dict to ast
    """
    
    if isinstance(data, dict):
        return ast.Dict(
            keys=[ast.Constant(value=k) for k in data.keys()],
            values=[dict_to_ast(v) for v in data.values()]
        )
    elif isinstance(data, list):
        return ast.List(
            elts=[
                ast.Subscript(
                    value=ast.Attribute(
                        value=ast.Name(id='sys', ctx=ast.Load()),
                        attr='argv',
                        ctx=ast.Load()
                    ),
                    slice=ast.Constant(value=idx),
                    ctx=ast.Load()
                ) for idx in data
            ],
            ctx=ast.Load()
        )
    elif isinstance(data, int):
        return ast.Subscript(
            value=ast.Attribute(
                value=ast.Name(id='sys', ctx=ast.Load()),
                attr='argv',
                ctx=ast.Load()
            ),
            slice=ast.Constant(value=data),
            ctx=ast.Load()
        )
    else:
        return ast.Constant(value=data)


def replace_biab_functions(script_path):
    """
    Replace biab_* functions and .append() methods by their standard Python equivalent
    - biab_error_stop(message) -> raise Exception(message)
    - biab_warning(message) -> warn(message)
    - biab_info(message) -> print(message)
    - error.append(message) -> raise Exception(message)
    - warning.append(message) -> warn(message)
    - info.append(message) -> print(message)
    
    Args:
        script_path: path of the python script to be modified
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        source_code = f.read()
    
    tree = ast.parse(source_code)
    
    replacer = BiabFunctionReplacer()
    new_tree = replacer.visit(tree)
    
    # add import warnings if necessary
    if replacer.has_biab_warning or replacer.has_warning_append:
        has_warn_import = any(
            isinstance(node, ast.ImportFrom) and
            node.module == 'warnings' and
            any(alias.name == 'warn' for alias in node.names)
            for node in new_tree.body
        )
        
        if not has_warn_import:
            import_warn = ast.ImportFrom(
                module='warnings',
                names=[ast.alias(name='warn', asname=None)],
                level=0
            )
            new_tree.body.insert(0, import_warn)
    
    ast.fix_missing_locations(new_tree)
    new_code = ast.unparse(new_tree)
    
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(new_code)


def add_inputs_handling(script_path, input_names):
    """
    Modifie a Python script to handle inputs via sys.argv and a JSON file.
    Support nested structures (e.g., bboxCRS.CRSBboxWGS84.xmin).
    Add output_folder at the beginning of the script and handles output.json at the end.
    
    Args:
        script_path: Path to the Python script to be modified
        input_names: List of input names to handle (may contain periods)
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        source_code = f.read()
    
    # Replace sys.argv[1] by "."
    source_code = source_code.replace('sys.argv[1]', '"."')
    
    tree = ast.parse(source_code)
    
    # replace biab_inputs()
    replacer = BiabInputsReplacer()
    new_tree = replacer.visit(tree)
    
    # Add the imports at the very beginning (without verification)
    imports_to_add = [
        ast.Import(names=[ast.alias(name='json', asname=None)]),
        ast.Import(names=[ast.alias(name='sys', asname=None)]),
        ast.Import(names=[ast.alias(name='os', asname=None)])
    ]
    
    for imp in reversed(imports_to_add):
        new_tree.body.insert(0, imp)
    
    # Add output_folder = os.getcwd() after the imports
    output_folder_assign = ast.Assign(
        targets=[ast.Name(id='output_folder', ctx=ast.Store())],
        value=ast.Call(
            func=ast.Attribute(
                value=ast.Name(id='os', ctx=ast.Load()),
                attr='getcwd',
                ctx=ast.Load()
            ),
            args=[],
            keywords=[]
        )
    )
    new_tree.body.insert(len(imports_to_add), output_folder_assign)
    
    # Build inputs_dict
    if input_names:
        nested_dict = build_nested_dict(input_names)
        
        inputs_dict_assign = ast.Assign(
            targets=[ast.Name(id='inputs_dict', ctx=ast.Store())],
            value=dict_to_ast(nested_dict)
        )
        new_tree.body.insert(len(imports_to_add) + 1, inputs_dict_assign)
        
        # Create input.json
        write_json = ast.With(
            items=[
                ast.withitem(
                    context_expr=ast.Call(
                        func=ast.Name(id='open', ctx=ast.Load()),
                        args=[
                            ast.Constant(value='input.json'),
                            ast.Constant(value='w')
                        ],
                        keywords=[]
                    ),
                    optional_vars=ast.Name(id='f', ctx=ast.Store())
                )
            ],
            body=[
                ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id='json', ctx=ast.Load()),
                            attr='dump',
                            ctx=ast.Load()
                        ),
                        args=[
                            ast.Name(id='inputs_dict', ctx=ast.Load()),
                            ast.Name(id='f', ctx=ast.Load())
                        ],
                        keywords=[
                            ast.keyword(arg='indent', value=ast.Constant(value=2))
                        ]
                    )
                )
            ]
        )
        new_tree.body.insert(len(imports_to_add) + 2, write_json)
    
    ast.fix_missing_locations(new_tree)
    new_code = ast.unparse(new_tree)
    
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(new_code)


def add_outputs_handling(script_path, replacements):
    """
    Replace biab_output calls with os.replace in a Python script.
    Add code at the end to handle outputs from output.json.
    
    Args:
        script_path: Path to the Python script to modify
        replacements: dict with {output_name: new_file_path}
    
    Raises:
        ValueError: If an output_name was not found in the script or output.json
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        source_code = f.read()
    
    tree = ast.parse(source_code)
    
    # Replace biab_output()
    replacer = BiabOutputReplacer(replacements)
    new_tree = replacer.visit(tree)
    
    found_in_script = replacer.found_outputs
    expected_in_json = set(replacements.keys()) - found_in_script
    
    # Check the import os
    has_os = any(
        isinstance(node, ast.Import) and any(alias.name == 'os' for alias in node.names)
        for node in new_tree.body
    )
    
    if not has_os:
        new_tree.body.insert(0, ast.Import(names=[ast.alias(name='os', asname=None)]))
    
    # Add import json if necessary for output.json
    if expected_in_json:
        has_json = any(
            isinstance(node, ast.Import) and any(alias.name == 'json' for alias in node.names)
            for node in new_tree.body
        )
        
        if not has_json:
            new_tree.body.insert(0, ast.Import(names=[ast.alias(name='json', asname=None)]))
        
        # Generate the code as a string
        all_outputs_mapping = {name: replacements[name] for name in sorted(expected_in_json)}
        outputs_mapping_repr = repr(all_outputs_mapping)
        expected_outputs_repr = repr(set(sorted(expected_in_json)))
        
        output_json_code = f"""
outputs_mapping = {outputs_mapping_repr}
output_json_path = os.path.join(output_folder, 'output.json')
if os.path.exists(output_json_path):
    with open(output_json_path, 'r') as f:
        outputs_from_json = json.load(f)
    expected_outputs = {expected_outputs_repr}
    missing_outputs = expected_outputs - set(outputs_from_json.keys())
    if missing_outputs:
        raise ValueError(f"Les output_names suivants n'ont pas été trouvés dans output.json : {{', '.join(missing_outputs)}}")
    for output_name, target_path in outputs_mapping.items():
        if output_name in outputs_from_json:
            if output_name == target_path:
                # Collection : outputs_from_json[output_name] est une liste
                for file_path in outputs_from_json[output_name]:
                    filename = os.path.basename(file_path)
                    os.replace(file_path, os.path.join(target_path, filename))
            else:
                # Fichier simple
                os.replace(outputs_from_json[output_name], target_path)
"""
        
        # Parse this code and add it to the tree
        output_nodes = ast.parse(output_json_code).body
        new_tree.body.extend(output_nodes)
    
    ast.fix_missing_locations(new_tree)
    new_code = ast.unparse(new_tree)
    
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(new_code)


def find_env_vars(filepath: str) -> list[str]:
    """
    Parse a Python script and return all environment variable names
    accessed via os.getenv(), os.environ.get(), or os.environ[].
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    env_vars = []

    for node in ast.walk(tree):
        # os.getenv("VAR") or os.getenv("VAR", default)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "getenv"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            env_vars.append(node.args[0].value)

        # os.environ.get("VAR") or os.environ.get("VAR", default)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "environ"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "os"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            env_vars.append(node.args[0].value)

        # os.environ["VAR"]
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "environ"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and isinstance(node.slice, ast.Constant)
        ):
            env_vars.append(node.slice.value)

    return list(set(env_vars))