"""Inspect isolated Python definitions without rewriting literal whitespace."""
import ast


def symbol_node(symbol):
    source=symbol.source
    first=next((line for line in source.splitlines() if line.strip()),'')
    if first[:1].isspace():
        # Keep the original indentation, including flush-left lines inside
        # triple-quoted strings. This wrapper is parsed, never executed.
        return ast.parse('if True:\n'+source,filename=symbol.path).body[0].body[0]
    return ast.parse(source,filename=symbol.path).body[0]
