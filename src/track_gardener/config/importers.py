"""Generic utilities for dynamically importing Python functions.

This module provides low-level helper functions to load a Python function
by name from two different kinds of sources: an installed module or an
arbitrary Python script file path.
"""

import importlib
import importlib.util
import os
from typing import Callable


def load_function_from_module(
    module_name: str, function_name: str
) -> tuple[bool, Callable | str]:
    """Loads a function from an installed module.

    Args:
        module_name: The name of the module (e.g., 'skimage.measure').
        function_name: The name of the function to load from the module.

    Returns:
        A tuple containing a success flag and either the loaded function
        or an error message string.
    """
    try:
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        return True, func
    except (ImportError, AttributeError) as e:
        return (
            False,
            f"Function '{function_name}' could not be loaded from module "
            f"'{module_name}': {e}",
        )


def load_function_from_path(
    file_path: str, function_name: str
) -> tuple[bool, Callable | str]:
    """Dynamically loads a function from a Python file path.

    Args:
        file_path: The absolute or relative path to the .py file.
        function_name: The name of the function to load.

    Returns:
        A tuple containing a success flag and either the loaded function
        or an error message string.
    """
    if not os.path.exists(file_path):
        return False, f"File '{file_path}' does not exist."

    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if not spec or not spec.loader:
        return False, f"Could not create module spec from '{file_path}'."

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        func = getattr(module, function_name)
        return True, func
    except (FileNotFoundError, AttributeError) as e:
        return (
            False,
            f"Function '{function_name}' not loaded from '{file_path}': {e}",
        )
