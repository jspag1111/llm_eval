# modules/graph_generator.py

import re
import string
import itertools

def assign_letters(items, start_index=0):
    """
    Assigns letters to items starting from a given index.
    Supports more than 26 items by using double letters (e.g., AA, AB).
    Returns a dictionary mapping item to its assigned letter.
    """
    letters = []
    for i in range(start_index, start_index + len(items)):
        if i < 26:
            letters.append(string.ascii_uppercase[i])
        else:
            first = (i // 26) - 1
            second = i % 26
            letters.append(string.ascii_uppercase[first] + string.ascii_uppercase[second])
    return {item: letter for item, letter in zip(items, letters)}

def find_variables_in_content(content, variables_set):
    """
    Finds variables enclosed in {{ }} within the content.
    Returns a set of variable names that are used.
    """
    pattern = r"\{\{([^}]+)\}\}"
    matches = re.findall(pattern, content)
    found_vars = set()
    for match in matches:
        var = match.split("[")[0].split(".")[0].strip()
        if var in variables_set:
            found_vars.add(var)
    return found_vars

def find_variable_usages(content, variable_names):
    """
    Finds variable usages within {{ }} in the content.
    Returns a list of tuples (variable, path) where path can be empty or something like ['other_notes']
    """
    pattern = r"\{\{([^}]+)\}\}"
    matches = re.findall(pattern, content)
    usages = []
    for match in matches:
        var = match.split("[")[0].split(".")[0].strip()
        path = match[len(var):].strip()
        if var in variable_names:
            usages.append((var, path))
    return usages

def json_to_mermaid(json_data):
    """
    Converts workflow JSON data to a Mermaid.js flowchart string.
    Handles variables, calls, and functions, ensuring no duplicate edges.
    """

    # 1. Assign letters to variables
    variables = list(json_data.get('variables', {}).keys())
    var_letters = assign_letters(variables, start_index=0)  # A, B, C, ...

    # 2. Collect all calls and functions across all steps
    calls = []
    functions = []
    for step in json_data.get('steps', []):
        for call in step.get('calls', []):
            calls.append({
                'step_title': step['title'],
                'call_id': call['call_id'],
                'title': call['title'],
                'variable_name': call.get('variable_name', ''),
                'user_prompt': call.get('user_prompt', ''),
                'conversation': call.get('conversation', []),
                'output_type': call.get('output_type', 'text')
            })
        for func in step.get('functions', []):
            functions.append({
                'step_title': step['title'],
                'call_id': func['call_id'],
                'title': func['title'],
                'code': func['code'],
                'input_variables': func.get('input_variables', {}),
                'output_variable': func.get('output_variable', '')
            })

    # 3. Assign letters to calls
    call_labels = [f"Step {call['step_title']}, Call: {call['title']}" for call in calls]
    call_letters = assign_letters(call_labels, start_index=len(variables))

    # 4. Assign letters to functions (after calls)
    function_labels = [f"Step {func['step_title']}, Function: {func['title']}" for func in functions]
    function_letters = assign_letters(function_labels, start_index=len(variables) + len(calls))

    # 5. Assign letter to Final Response
    final_response_label = "Final Response"
    final_response_letter = assign_letters([final_response_label],
                                           start_index=len(variables) + len(calls) + len(functions))[final_response_label]

    # 6. Create Mermaid nodes
    mermaid_nodes = []
    # Add variable nodes
    for var, letter in var_letters.items():
        mermaid_nodes.append(f'{letter}["{var}"]')

    # Add call nodes
    for call in calls:
        label = f"Step {call['step_title']}, Call: {call['title']}"
        letter = call_letters[label]
        mermaid_nodes.append(f'{letter}["{label}"]')
        call['assigned_letter'] = letter

    # Add function nodes
    for func in functions:
        label = f"Step {func['step_title']}, Function: {func['title']}"
        letter = function_letters[label]
        mermaid_nodes.append(f'{letter}["{label}"]')
        func['assigned_letter'] = letter

    # Add Final Response node
    mermaid_nodes.append(f'{final_response_letter}["{final_response_label}"]')

    # 7. Create connections
    mermaid_connections = []
    variables_set = set(variables)

    # Mapping from variable_name to call letter
    varname_to_call_letter = {}
    for call in calls:
        var_name = call.get('variable_name')
        if var_name:
            varname_to_call_letter[var_name] = call['assigned_letter']

    # Mapping from variable_name to function letter
    varname_to_function_letter = {}
    for func in functions:
        out_var = func.get('output_variable', '')
        if out_var:
            varname_to_function_letter[out_var] = func['assigned_letter']

    # Connect variables to calls based on conversation usage
    for call in calls:
        call_letter = call['assigned_letter']
        used_vars = set()
        for convo in call.get('conversation', []):
            convo_content = convo.get('content', '')
            used_vars.update(find_variables_in_content(convo_content, variables_set))

        for var in used_vars:
            var_letter = var_letters.get(var, '')
            if var_letter:
                mermaid_connections.append(f'{var_letter} --> |"{var}"| {call_letter}')

    # Connect variables, calls, or function outputs to functions based on input_variables
    # This single loop handles all edges going into functions, preventing duplicates.
    for func in functions:
        func_letter = func['assigned_letter']
        for input_key, input_var_name in func['input_variables'].items():
            label = f"{input_key}:{input_var_name}"
            if input_var_name in var_letters:
                # Input from a global variable
                mermaid_connections.append(f'{var_letters[input_var_name]} --> |"{label}"| {func_letter}')
            elif input_var_name in varname_to_call_letter:
                # Input from a call's output variable
                mermaid_connections.append(f'{varname_to_call_letter[input_var_name]} --> |"{label}"| {func_letter}')
            elif input_var_name in varname_to_function_letter:
                # Input from another function's output variable
                mermaid_connections.append(f'{varname_to_function_letter[input_var_name]} --> |"{label}"| {func_letter}')

    # Connect calls to calls based on variable usage in conversation
    for call in calls:
        var_name = call.get('variable_name')
        if not var_name:
            continue
        source_letter = call['assigned_letter']
        for subsequent_call in calls:
            if subsequent_call == call:
                continue
            subsequent_letter = subsequent_call['assigned_letter']
            convo_contents = [c.get('content', '') for c in subsequent_call.get('conversation', [])]
            for content in convo_contents:
                usages = find_variable_usages(content, [var_name])
                for var, path in usages:
                    if var == var_name:
                        if path:
                            path_clean = path.strip("[]")
                            mermaid_connections.append(f'{source_letter} --> |"{var}{path}"| {subsequent_letter}')
                        else:
                            mermaid_connections.append(f'{source_letter} --> |"{var}"| {subsequent_letter}')

    # Connect function outputs to calls if used in conversation
    for func in functions:
        out_var = func.get('output_variable', '')
        if not out_var:
            continue
        source_letter = func['assigned_letter']
        for subsequent_call in calls:
            convo_contents = [c.get('content', '') for c in subsequent_call.get('conversation', [])]
            for content in convo_contents:
                usages = find_variable_usages(content, [out_var])
                for var, path in usages:
                    target_letter = subsequent_call['assigned_letter']
                    if path:
                        path_clean = path.strip("[]")
                        mermaid_connections.append(f'{source_letter} --> |"{var}{path}"| {target_letter}')
                    else:
                        mermaid_connections.append(f'{source_letter} --> |"{var}"| {target_letter}')

    # The loops connecting calls->functions or functions->functions again have been removed 
    # to prevent duplicate arrows. The input_variables loop already handles these edges.

    # Connect the last node to Final Response (if any calls or functions)
    if functions:
        last_func_letter = functions[-1]['assigned_letter']
        mermaid_connections.append(f'{last_func_letter} --> {final_response_letter}')
    elif calls:
        last_call_letter = calls[-1]['assigned_letter']
        mermaid_connections.append(f'{last_call_letter} --> {final_response_letter}')

    # Construct Mermaid flowchart
    mermaid_flow = ["flowchart TD"]
    mermaid_flow.extend(mermaid_nodes)
    mermaid_flow.extend(mermaid_connections)

    mermaid_text = "\n    ".join(mermaid_flow)
    print(mermaid_text)
    return mermaid_text

def generate_mermaid(workflow_dict):
    """
    Wrapper function to generate Mermaid.js flowchart from workflow dictionary.
    """
    return json_to_mermaid(workflow_dict)
