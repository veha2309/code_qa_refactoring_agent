# Change Lens: panel demonstration

## Prepare

Start Change Lens, press **Ctrl+Shift+P**, and choose **Project: Open sample**. The expanded retail project opens as an editable working copy under `%LOCALAPPDATA%\ChangeLens\retail-sample-project`. Your previous `sample-project` folder is left in place. Edits in the new working copy are also preserved between launches, so rehearse with a clean copy before presenting. Configure a Python interpreter if you plan to run tests. For the AI investigation, start Ollama, prepare the local review model in **More → Tools → Code notes → Model settings**, and connect it. Check this before the presentation; model downloads require internet.

The project includes a product catalogue, discount rules, delivery charges, stock checks, pricing, order placement, returns and sales reports. There are 34 tests, including focused unit tests and cross-file workflow tests.

## Opening (about 30 seconds)

> “When a developer changes code, a small function can affect other files and tests. When an AI assistant sees only part of that code, it may also give a confident answer without the definition it needs. Change Lens helps explore the relevant source and tests, with links back to evidence.”

## Live walkthrough (about five minutes)

1. **Show the project.** Open `orders.py`. Explain that `place_order` checks stock and then calls pricing. Open `pricing.py`: `quote_order` uses the catalogue, promotions, invoice tax and delivery rules.
2. **Investigate a change.** Open `invoice.py`, put the cursor in `calculate_invoice_total`, and choose **Review function** in Review. In Lens, follow the path through `pricing.py:quote_order` to `orders.py:place_order`, and open a source link. The tool reports potential impact, not a guarantee that each result is broken or complete.
3. **Inspect tests.** Open **Linked tests**. Show direct invoice tests and tests of pricing or order placement. If the interpreter is configured, run a selected test. Explain that a recommendation is a candidate; a test result comes only from executing it.
4. **Show a second path.** Review `promotions.py:discount_rate`. Follow it through `discount_amount` to pricing and order-related tests. This gives the panel a different change scenario and demonstrates cross-file dependencies.
5. **Preview a refactor.** Place the cursor on `subtotal` in `invoice.py` and press **Ctrl+.** Enter `net_amount` and preview the diff. Optionally apply and undo it. Explain that the developer reviews the proposed patch.
6. **Show structure.** Open Design and briefly explore the generated structure. Close with the sequence: change → related evidence → candidate tests → reviewed action.

For an actual edit, change a calculation, save it and choose **Review changes**. Restore it afterward. Rehearse the exact interaction before presenting.

## Demonstrate the AI investigation

1. With the retail sample open, put the cursor inside `calculate_invoice_total` in `invoice.py`. Save edits and refresh the saved analysis if prompted.
2. Open **More → Tools → Code notes**. Enter “If the tax calculation changes, which code and tests could be affected?” and choose **Investigate with AI**.
3. Show the investigation: the app gathers bounded source context and potential impact paths, asks the local model to answer and identify uncertainty, and displays linked test candidates. Read the source context in the result to show what was provided to the model. Tests are not run by this action.
4. Open Lens to inspect the source evidence, and run selected tests separately if configured. Explain that this is a guided, fixed sequence of tools with model interpretation—not an autonomous system deciding which tools to call.

For a context-focused question, put the cursor in `discount_amount` in `promotions.py` and ask “What does discount_amount(200, 'SAVE10') return, and what definition determines it?” Inspect whether the displayed context includes the rate before trusting the model answer. If source is omitted or the model guesses, say so. The model is instructed to identify missing evidence but its response is not guaranteed to do so.

## Connect the demo to the research paper

Your paper, *When Should an LLM Ask for More Code?*, asks whether an LLM can recognize when a coding question depends on a missing source definition. It evaluates full source, a missing required file, and a missing unrelated file in a separate controlled experiment. The experiment is not a measurement of Change Lens itself.

Use this sample as an illustration, not a replication of the experiment:

- Ask: “What does `discount_amount(200, 'SAVE10')` return?” Show the caller in `promotions.py` while covering the `DISCOUNT_RATES` definition. Without that definition, the exact answer is not established by the caller alone. Reveal the definition: the rate is 0.10, so the answer is 20.0.
- `display.py` provides an unrelated display helper. Omitting it does not prevent answering the discount question. Explain why asking for all files is different from asking for the specific missing evidence.
- In Change Lens, demonstrate the existing source relationships and evidence. Say that they support inspecting context; do **not** claim the app reliably detects missing context, asks for the right file, or improves the paper's scores unless those capabilities are separately evaluated.

The paper reports that, in its tested settings, Qwen2.5-Coder 3B gave unsupported answers in 142 of 144 required-source-missing trials, while Llama 3.2 1B withheld 275 times across 288 sufficient-source trials. A tracing instruction did not increase correct abstentions when required source was missing. These are descriptive results for the tested models and controlled cases, not claims about every model or real repository. The paper proposes a future two-stage experiment to identify the needed definition, provide it, and measure the subsequent answer.

## Likely panel questions

**How is this different from an IDE?** IDEs already provide navigation, refactoring and testing. Change Lens brings potential impact paths, supporting evidence and test candidates together around a selected change. A comparative study would be needed to establish whether that helps users perform better or faster.

**Does the paper prove Change Lens solves hallucination?** No. The paper studies missing context using a separate experimental runner. The app is a prototype for exploring source relationships; its ability to improve model decisions remains to be evaluated.

**Are the links and test recommendations complete?** No. Static analysis can miss dynamic dispatch and other relationships. Recommendations are potential impacts, and passing tests do not prove a change is safe.
