"""
Code Executor: Execute Python code in the RLM sandbox.

This module provides:
1. Code block detection in responses
2. Safe execution via Docker sandbox
3. Automatic package installation for external dependencies
4. Result injection back into responses
5. Execution logging for verification

When Vecna generates a response containing Python code blocks,
this module can detect and execute them, replacing hallucinated
output with real verified output.

External packages (numpy, pandas, requests, etc.) are automatically
installed via pip when detected in import statements.
"""

import re
import ast
import logging
from typing import List, Tuple, Set, Dict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from vecna.tools.types import ToolExecutionContext, ToolResult

logger = logging.getLogger("vecna.code_executor")

# Execution log stored in ~/.vecna/
EXECUTION_LOG_PATH = Path.home() / ".vecna" / "execution_log.jsonl"

# Python 3.11 standard library modules (no pip install needed)
STDLIB_MODULES: Set[str] = {
    "abc",
    "aifc",
    "argparse",
    "array",
    "ast",
    "asynchat",
    "asyncio",
    "asyncore",
    "atexit",
    "audioop",
    "base64",
    "bdb",
    "binascii",
    "binhex",
    "bisect",
    "builtins",
    "bz2",
    "calendar",
    "cgi",
    "cgitb",
    "chunk",
    "cmath",
    "cmd",
    "code",
    "codecs",
    "codeop",
    "collections",
    "colorsys",
    "compileall",
    "concurrent",
    "configparser",
    "contextlib",
    "contextvars",
    "copy",
    "copyreg",
    "cProfile",
    "crypt",
    "csv",
    "ctypes",
    "curses",
    "dataclasses",
    "datetime",
    "dbm",
    "decimal",
    "difflib",
    "dis",
    "distutils",
    "doctest",
    "email",
    "encodings",
    "enum",
    "errno",
    "faulthandler",
    "fcntl",
    "filecmp",
    "fileinput",
    "fnmatch",
    "fractions",
    "ftplib",
    "functools",
    "gc",
    "getopt",
    "getpass",
    "gettext",
    "glob",
    "graphlib",
    "grp",
    "gzip",
    "hashlib",
    "heapq",
    "hmac",
    "html",
    "http",
    "idlelib",
    "imaplib",
    "imghdr",
    "imp",
    "importlib",
    "inspect",
    "io",
    "ipaddress",
    "itertools",
    "json",
    "keyword",
    "lib2to3",
    "linecache",
    "locale",
    "logging",
    "lzma",
    "mailbox",
    "mailcap",
    "marshal",
    "math",
    "mimetypes",
    "mmap",
    "modulefinder",
    "multiprocessing",
    "netrc",
    "nis",
    "nntplib",
    "numbers",
    "operator",
    "optparse",
    "os",
    "ossaudiodev",
    "pathlib",
    "pdb",
    "pickle",
    "pickletools",
    "pipes",
    "pkgutil",
    "platform",
    "plistlib",
    "poplib",
    "posix",
    "posixpath",
    "pprint",
    "profile",
    "pstats",
    "pty",
    "pwd",
    "py_compile",
    "pyclbr",
    "pydoc",
    "queue",
    "quopri",
    "random",
    "re",
    "readline",
    "reprlib",
    "resource",
    "rlcompleter",
    "runpy",
    "sched",
    "secrets",
    "select",
    "selectors",
    "shelve",
    "shlex",
    "shutil",
    "signal",
    "site",
    "smtpd",
    "smtplib",
    "sndhdr",
    "socket",
    "socketserver",
    "spwd",
    "sqlite3",
    "ssl",
    "stat",
    "statistics",
    "string",
    "stringprep",
    "struct",
    "subprocess",
    "sunau",
    "symtable",
    "sys",
    "sysconfig",
    "syslog",
    "tabnanny",
    "tarfile",
    "telnetlib",
    "tempfile",
    "termios",
    "test",
    "textwrap",
    "threading",
    "time",
    "timeit",
    "tkinter",
    "token",
    "tokenize",
    "tomllib",
    "trace",
    "traceback",
    "tracemalloc",
    "tty",
    "turtle",
    "turtledemo",
    "types",
    "typing",
    "unicodedata",
    "unittest",
    "urllib",
    "uu",
    "uuid",
    "venv",
    "warnings",
    "wave",
    "weakref",
    "webbrowser",
    "winreg",
    "winsound",
    "wsgiref",
    "xdrlib",
    "xml",
    "xmlrpc",
    "zipapp",
    "zipfile",
    "zipimport",
    "zlib",
    "zoneinfo",
}

# Map import names to pip package names (when they differ)
IMPORT_TO_PACKAGE: Dict[str, str] = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "google": "google-cloud",
}


def extract_imports(code: str) -> List[str]:
    """
    Extract all import module names from Python code.

    Args:
        code: Python source code

    Returns:
        List of top-level module names being imported
    """
    imports = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Can't parse - let execution handle the syntax error
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Get top-level module name
                module_name = alias.name.split(".")[0]
                imports.append(module_name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Get top-level module name
                module_name = node.module.split(".")[0]
                imports.append(module_name)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for imp in imports:
        if imp not in seen:
            seen.add(imp)
            unique.append(imp)

    return unique


def get_packages_to_install(imports: List[str]) -> List[str]:
    """
    Determine which packages need to be pip installed.

    Args:
        imports: List of import module names

    Returns:
        List of pip package names to install
    """
    packages = []

    for module_name in imports:
        # Skip stdlib modules
        if module_name in STDLIB_MODULES:
            continue

        # Map import name to package name if needed
        package_name = IMPORT_TO_PACKAGE.get(module_name, module_name)
        packages.append(package_name)

    return packages


@dataclass
class ExecutionResult:
    """Result from code execution."""

    code: str
    stdout: str
    stderr: str
    return_code: int
    execution_time_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    packages_installed: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "packages_installed": self.packages_installed,
        }


@dataclass
class CodeBlock:
    """A detected code block from a response."""

    code: str
    language: str
    start_pos: int
    end_pos: int
    original_text: str  # The full ```python ... ``` block


def detect_code_blocks(text: str) -> List[CodeBlock]:
    """
    Detect Python code blocks in text.

    Looks for:
    - ```python ... ```
    - ```py ... ```
    - ``` ... ``` (if it looks like Python)
    """
    blocks = []

    # Pattern for fenced code blocks
    pattern = r"```(python|py|)\n(.*?)```"

    for match in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
        language = match.group(1).lower() or "python"
        code = match.group(2).strip()

        # Skip if it's not Python-like
        if language not in ("python", "py", ""):
            continue

        # For unlabeled blocks, check if it looks like Python
        if language == "":
            if not _looks_like_python(code):
                continue
            language = "python"

        blocks.append(
            CodeBlock(
                code=code,
                language=language,
                start_pos=match.start(),
                end_pos=match.end(),
                original_text=match.group(0),
            )
        )

    return blocks


def _looks_like_python(code: str) -> bool:
    """Heuristic check if code looks like Python."""
    python_indicators = [
        "def ",
        "class ",
        "import ",
        "from ",
        "print(",
        "if __name__",
        "for ",
        "while ",
        "return ",
        "    ",
        "elif ",
        "except ",
        "try:",
        "with ",
    ]
    return any(indicator in code for indicator in python_indicators)


async def execute_code_block(code: str, timeout: int = 60) -> ExecutionResult:
    """
    Execute a Python code block in the RLM sandbox.

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds (default 60 for pip installs)

    Returns:
        ExecutionResult with stdout, stderr, and status

    Note:
        External packages are automatically installed via pip when detected.
        The first execution with new packages may take longer due to installation.
    """
    from vecna.memory.rlm_bridge import get_rlm_bridge, DockerNotAvailableError

    start_time = datetime.now()
    packages_installed = []

    try:
        bridge = get_rlm_bridge()

        if not bridge.is_docker_available():
            return ExecutionResult(
                code=code,
                stdout="",
                stderr="Docker not available - cannot execute code",
                return_code=-1,
                execution_time_ms=0,
                success=False,
            )

        # Extract imports and determine packages to install
        imports = extract_imports(code)
        packages = get_packages_to_install(imports)

        # Install packages if needed
        if packages:
            logger.info(f"Installing packages: {packages}")
            install_success, install_output = await bridge.install_packages(packages)

            if install_success:
                packages_installed = packages
                logger.info(f"Successfully installed: {packages}")
            else:
                # Package install failed - return error
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                return ExecutionResult(
                    code=code,
                    stdout="",
                    stderr=f"Failed to install packages {packages}:\n{install_output}",
                    return_code=-1,
                    execution_time_ms=execution_time,
                    success=False,
                )

        # Execute the code
        stdout, stderr, return_code = await bridge.execute_code(code)

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        result = ExecutionResult(
            code=code,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            execution_time_ms=execution_time,
            success=(return_code == 0),
            packages_installed=packages_installed,
        )

        # Log the execution
        _log_execution(result)

        return result

    except DockerNotAvailableError as e:
        return ExecutionResult(
            code=code,
            stdout="",
            stderr=f"RLM sandbox unavailable: {e}",
            return_code=-1,
            execution_time_ms=0,
            success=False,
        )
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        return ExecutionResult(
            code=code,
            stdout="",
            stderr=f"Execution error: {e}",
            return_code=-1,
            execution_time_ms=execution_time,
            success=False,
        )


def _log_execution(result: ExecutionResult) -> None:
    """Log execution to file for verification."""
    import json

    try:
        EXECUTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(EXECUTION_LOG_PATH, "a") as f:
            f.write(json.dumps(result.to_dict()) + "\n")

        logger.info(
            f"Code executed: {result.return_code == 0}, time={result.execution_time_ms:.1f}ms"
        )

    except Exception as e:
        logger.warning(f"Failed to log execution: {e}")


async def execute_and_inject(
    response: str,
    auto_execute: bool = True,
) -> Tuple[str, List[ExecutionResult]]:
    """
    Detect code blocks in a response, execute them, and inject real results.

    Args:
        response: The model's response text
        auto_execute: If True, automatically execute detected code

    Returns:
        (modified_response, list_of_execution_results)
    """
    if not auto_execute:
        return response, []

    blocks = detect_code_blocks(response)

    if not blocks:
        return response, []

    results = []
    modified = response

    # Process blocks in reverse order (so positions stay valid)
    for block in reversed(blocks):
        result = await execute_code_block(block.code)
        results.append(result)

        # Build the replacement text
        if result.success:
            pkg_note = ""
            if result.packages_installed:
                pkg_note = f" (installed: {', '.join(result.packages_installed)})"

            replacement = f"""```python
{block.code}
```

**Executed in RLM sandbox** (took {result.execution_time_ms:.1f}ms{pkg_note}):
```
{result.stdout.strip() if result.stdout else "(no output)"}
```"""
        else:
            replacement = f"""```python
{block.code}
```

**Execution failed**:
```
{result.stderr.strip() if result.stderr else "Unknown error"}
```"""

        # Replace the original block with the executed version
        modified = modified[: block.start_pos] + replacement + modified[block.end_pos :]

    return modified, list(reversed(results))  # Reverse back to original order


async def execute_code_tool(args: dict, context: ToolExecutionContext) -> ToolResult:
    code = args.get("code", "")
    result = await execute_code_block(code)
    return ToolResult(
        tool_name="python_exec",
        success=result.success,
        output=result.stdout,
        error=result.stderr,
        metadata={
            "return_code": result.return_code,
            "execution_time_ms": result.execution_time_ms,
            "packages_installed": result.packages_installed,
        },
    )


def get_execution_log(limit: int = 20) -> List[dict]:
    """
    Read recent execution log entries.

    Args:
        limit: Maximum number of entries to return

    Returns:
        List of execution log entries (most recent first)
    """
    import json

    if not EXECUTION_LOG_PATH.exists():
        return []

    entries = []
    try:
        with open(EXECUTION_LOG_PATH, "r") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
    except Exception as e:
        logger.warning(f"Failed to read execution log: {e}")
        return []

    # Return most recent first
    return entries[-limit:][::-1]


def clear_execution_log() -> bool:
    """Clear the execution log file."""
    try:
        if EXECUTION_LOG_PATH.exists():
            EXECUTION_LOG_PATH.unlink()
        return True
    except Exception as e:
        logger.warning(f"Failed to clear execution log: {e}")
        return False
