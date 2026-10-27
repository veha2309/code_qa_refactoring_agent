"""Process-local workaround for CPython bpo-45757 on 3.10.0/3.10.1 only.

https://bugs.python.org/issue45757
No system or dependency files are edited. Prefer a newer Python for future builds.
"""
import dis
import os
import sys

# Do not collect document-tool DLLs (notably a different ICU ABI) from the
# host's injected PATH. Qt 6 uses the Windows operating-system ICU library.
os.environ["PATH"] = os.pathsep.join(
    item for item in os.environ.get("PATH", "").split(os.pathsep)
    if "codex-runtimes" not in item.lower()
)


if sys.version_info[:2] == (3, 10) and sys.version_info.micro < 2:
    def unpack_opargs(code):
        extended_arg = 0
        for offset in range(0, len(code), 2):
            opcode = code[offset]
            if opcode >= dis.HAVE_ARGUMENT:
                argument = code[offset + 1] | extended_arg
                extended_arg = argument << 8 if opcode == dis.EXTENDED_ARG else 0
            else:
                argument = None
                extended_arg = 0
            yield offset, opcode, argument
    dis._unpack_opargs = unpack_opargs

if __name__ == "__main__":
    from PyInstaller.__main__ import run
    run(sys.argv[1:])
