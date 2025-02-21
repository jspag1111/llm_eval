# modules/function_executor.py
import RestrictedPython
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safe_builtins

ALLOWED_BUILTINS = {
    '__builtins__': {
        **safe_builtins,
        '_getiter_': RestrictedPython.Eval.default_guarded_getiter,
        '_getattr_': RestrictedPython.Guards.safer_getattr,
        'str': str,
        'int': int,
        'float': float,
        'list': list,
        'dict': dict,
        'len': len,
        'isinstance': isinstance,
        'range': range,
        'enumerate': enumerate
    }
}

class FunctionExecutionError(Exception):
    """Custom exception for errors during function execution."""
    pass

def execute_function(code_string, input_values, allowed_modules=None):
    """
    Executes Python code in a restricted environment using RestrictedPython.

    Args:
        code_string: The Python code to execute (as a string).
        input_values: A dictionary of input variables for the function.
        allowed_modules: A list of allowed external modules (e.g., ['math', 'random']).

    Returns:
        The 'return_value' from the executed code.

    Raises:
        FunctionExecutionError: If there's an error during code compilation or execution.
    """
    try:
        # Compile the code with restrictions
        byte_code = compile_restricted(code_string, '<inline>', 'exec')

        # Create a restricted globals dictionary
        restricted_globals = {}
        restricted_globals.update(ALLOWED_BUILTINS)

        # Add allowed modules if any
        if allowed_modules:
            for module_name in allowed_modules:
                try:
                    restricted_globals['__builtins__'][module_name] = __import__(module_name)
                except ImportError:
                    raise FunctionExecutionError(f"Module not allowed: {module_name}")

        # Set up local variables (inputs)
        local_vars = {}
        local_vars.update(input_values)

        # Execute the code
        exec(byte_code, restricted_globals, local_vars)

        return local_vars.get("return_value")

    except SyntaxError as e:
        raise FunctionExecutionError(f"Syntax error in function code: {e}")
    except RestrictedPython.Errors.RestrictionError as e:
        raise FunctionExecutionError(f"Forbidden operation in function code: {e}")
    except Exception as e:
        raise FunctionExecutionError(f"Error executing function: {e}")