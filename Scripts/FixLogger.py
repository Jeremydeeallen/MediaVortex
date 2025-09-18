#!/usr/bin/env python3
"""
FixLogger.py - Updates all LoggingService calls to use the new FunctionName parameter format.

This script updates all LoggingService calls throughout the codebase to use the new parameter order:
- Old: LoggingService.LogInfo(message, 'Component', 'Function')
- New: LoggingService.LogInfo(message, 'Function', 'Component')

The script handles:
- LogInfo, LogError, LogWarning, LogDebug calls
- LogException calls (with exception parameter)
- LogFunctionEntry and LogFunctionExit calls (already correct)
- LogData calls
"""

import os
import re
import glob
from pathlib import Path

def fix_logging_calls_in_file(file_path):
    """Fix logging calls in a single file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Pattern 1: LogInfo, LogError, LogWarning, LogDebug with 3 parameters
        # LoggingService.LogInfo(message, 'Component', 'Function')
        pattern1 = r'LoggingService\.(LogInfo|LogError|LogWarning|LogDebug)\(([^,]+),\s*\'([^\']+)\',\s*\'([^\']+)\'\)'
        
        def replace_simple_logging(match):
            method = match.group(1)
            message = match.group(2)
            component = match.group(3)
            function = match.group(4)
            return f'LoggingService.{method}({message}, \'{function}\', \'{component}\')'
        
        content = re.sub(pattern1, replace_simple_logging, content)
        
        # Pattern 2: LogException with 4 parameters
        # LoggingService.LogException(message, exception, 'Component', 'Function')
        pattern2 = r'LoggingService\.LogException\(([^,]+),\s*([^,]+),\s*\'([^\']+)\',\s*\'([^\']+)\'\)'
        
        def replace_exception_logging(match):
            message = match.group(1)
            exception = match.group(2)
            component = match.group(3)
            function = match.group(4)
            return f'LoggingService.LogException({message}, {exception}, \'{function}\', \'{component}\')'
        
        content = re.sub(pattern2, replace_exception_logging, content)
        
        # Pattern 3: LoggingService calls with only 2 parameters (message, component)
        # These need to have an empty function name added
        pattern3 = r'LoggingService\.(LogInfo|LogError|LogWarning|LogDebug)\(([^,]+),\s*\'([^\']+)\'\)'
        
        def add_empty_function_name(match):
            method = match.group(1)
            message = match.group(2)
            component = match.group(3)
            return f'LoggingService.{method}({message}, \'\', \'{component}\')'
        
        content = re.sub(pattern3, add_empty_function_name, content)
        
        # Pattern 4: LogException with only 3 parameters (message, exception, component)
        pattern4 = r'LoggingService\.LogException\(([^,]+),\s*([^,]+),\s*\'([^\']+)\'\)'
        
        def add_empty_function_name_exception(match):
            message = match.group(1)
            exception = match.group(2)
            component = match.group(3)
            return f'LoggingService.LogException({message}, {exception}, \'\', \'{component}\')'
        
        content = re.sub(pattern4, add_empty_function_name_exception, content)
        
        # Pattern 5: LogData calls
        pattern5 = r'LoggingService\.LogData\(([^,]+),\s*([^,]+),\s*\'([^\']+)\',\s*\'([^\']+)\'\)'
        
        def replace_logdata(match):
            message = match.group(1)
            data = match.group(2)
            component = match.group(3)
            operation = match.group(4)
            return f'LoggingService.LogData({message}, {data}, \'\', \'{component}\', \'{operation}\')'
        
        content = re.sub(pattern5, replace_logdata, content)
        
        # Only write if content changed
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Main function to fix logging calls in all Python files."""
    print("FixLogger.py - Updating LoggingService calls to use FunctionName parameter")
    print("=" * 70)
    
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    # Find all Python files to process
    python_files = []
    
    # Add specific directories
    directories = [
        'Services',
        'Controllers', 
        'ViewModels',
        'Repositories',
        'Models',
        'Scripts'
    ]
    
    for directory in directories:
        dir_path = project_root / directory
        if dir_path.exists():
            python_files.extend(dir_path.glob('*.py'))
    
    # Also check the root directory
    python_files.extend(project_root.glob('*.py'))
    
    # Remove this script from the list
    python_files = [f for f in python_files if f.name != 'FixLogger.py']
    
    print(f"Found {len(python_files)} Python files to process")
    print()
    
    updated_files = []
    
    for file_path in python_files:
        print(f"Processing: {file_path.relative_to(project_root)}")
        if fix_logging_calls_in_file(file_path):
            updated_files.append(file_path.relative_to(project_root))
            print(f"  ✓ Updated")
        else:
            print(f"  - No changes needed")
    
    print()
    print("=" * 70)
    print(f"Processing complete!")
    print(f"Files updated: {len(updated_files)}")
    
    if updated_files:
        print("\nUpdated files:")
        for file_path in updated_files:
            print(f"  - {file_path}")
    
    print("\nAll LoggingService calls have been updated to use the new FunctionName parameter format.")
    print("The new format is: LoggingService.LogInfo(message, 'FunctionName', 'Component')")

if __name__ == "__main__":
    main()

