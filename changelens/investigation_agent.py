"""A bounded, source-backed investigation using static tools and a local model."""
from .brief import brief_markdown
from .core import ensure_fresh, impact_paths
from .languages import NAMES, language_for
from .model_context import fit_text, related_context


def investigate(client, snapshot, symbol_id, question, cancel=None, progress=lambda *_: None):
    """Gather evidence, ask the model, and return an inspectable investigation.

    This workflow does not execute tests or modify files. Static paths and model
    interpretations are reported separately and neither proves completeness.
    """
    question = question.strip()
    if not question:
        raise ValueError("Enter a question about the focused function.")
    if symbol_id not in snapshot.symbols:
        raise ValueError("The focused function is not in the saved-source index.")
    ensure_fresh(snapshot, cancel)
    symbol = snapshot.symbols[symbol_id]
    progress("Gathering saved-source definitions and potential impact paths…")
    budget = client.related_context_budget()
    context = fit_text(related_context(snapshot, symbol, budget=budget), budget)
    paths = impact_paths(snapshot, [symbol_id], cancel=cancel)
    impacted = [row["symbol"] for row in paths if row["symbol"] != symbol_id and not snapshot.symbols[row["symbol"]].is_test]
    tests = [row["symbol"] for row in paths if snapshot.symbols[row["symbol"]].is_test]
    progress("Asking the local model to answer from the gathered source and identify missing evidence…")
    instruction = ("Question: " + question[:400] + "\nAnswer only if the provided code establishes the answer. "
                   "If a definition or setting is missing or uncertain, say what is needed in uncertainty; do not guess. "
                   "Distinguish source evidence from inference and do not claim tests were run.")
    answer = client.assist(symbol.source, instruction, context=context, cancel=cancel,
                           structured=True, language=NAMES.get(language_for(symbol.path), "Source"))
    model_brief = brief_markdown(answer)
    ensure_fresh(snapshot, cancel)
    return {"focus": symbol_id, "question": question, "context": context,
            "impacted": impacted, "tests": tests, "model_brief": model_brief}


def format_investigation(result):
    def items(values, empty):
        return "\n".join("- `" + value.replace("`", "") + "`" for value in values[:12]) if values else empty
    return ("# Investigation\n\n**Question:** " + result["question"].replace("\n", " ") +
            "\n\n**Focused function:** `" + result["focus"] + "`\n\n" +
            result["model_brief"] +
            "\n\n## Potentially affected code (static analysis)\n\n" +
            items(result["impacted"], "No caller paths were found.") +
            "\n\n## Linked test candidates (not executed)\n\n" +
            items(result["tests"], "No linked tests were found.") +
            "\n\n## Source context supplied to the model\n\n```text\n" +
            result["context"].replace("```", "\x60\x60 \x60") + "\n```\n\n" +
            "Static links and model interpretations may be incomplete. Inspect the Lens for path evidence.")
