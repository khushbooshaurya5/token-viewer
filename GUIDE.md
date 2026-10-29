# Starter guide

How your group gets its own copy, what the starter gives you and what to try first, how to debug it, and why its versions are pinned. The [README](README.md) is yours: it holds the steps your group follows live.

## Your group's repository

This repository is a template on GitHub. One member of the group makes the group's own copy from it:

1. On the [template's GitHub page](https://github.com/L3GJ0N/eaas_token_viewer_starter), click **Use this template**, then **Create a new repository**.
2. Under **Owner**, choose your account. Give the repository a name, and choose **Public** or **Private**.
3. Click **Create repository from template**.

With the GitHub CLI, one command does the same and clones the new repository: `gh repo create <name> --template L3GJ0N/eaas_token_viewer_starter --private --clone`.

The new repository has the starter's files in a single first commit, without the starter's history. It is your group's own, not a fork, and private if you chose so. To add the other members, open its **Settings**, click **Collaborators** in the **Access** section, then **Add people**; each of them accepts the invitation GitHub sends by e-mail. Then everyone clones the group's repository and works there, and in class your group runs it from there.

Later changes to the template do not reach your repository by themselves: the two histories are unrelated, so they cannot be merged. If the course announces a fix, copy the change by hand.

## What the starter provides

The starter runs end to end before any token logic exists. A fake controller answers every command with made-up data, so the page, the proxy, the generated types and the debugger work from the first day. The rest is yours:

| Part | The starter provides | Yours |
|---|---|---|
| Page, `frontend/` | layout, view selector, token chips, detail panel, table, API client; it shows every field of the view-model | nothing: change it only if you want nicer drawing |
| Routes, `backend/src/token_viewer/api.py` | one thin route per command, with 400 and 422 answers | routes for the commands you add |
| View-models, `view_models.py` | a first version | extend them, then regenerate the types |
| Controller, `controller.py` | the interface; a fake controller with a stand-in model in `fake_controller.py` | your controller, plugged in at `wiring.py` |
| Model | nothing | everything: files, revision, chat template, encoding, captures |
| Terminal view | nothing | your first view, on the same controller and model classes as the page |

Keep `fake_controller.py` when your own controller works: the route tests use it. When you add a command to `Controller` or a field to a view-model, add it to the fake too.

In the code and in `backend/pyproject.toml`, a note that begins with `Yours:`, in a comment or a docstring, marks each place where your work goes. To list them all, select **Edit > Find in Files** (Ctrl+Shift+F, on macOS Cmd+Shift+F) and search for `Yours:`. Delete each `Yours:` note once your code is there.

### Python only

Everything the task asks for can be done in Python, because the page shows whatever the view-model carries:

- A chip shows `TokenView.text` exactly as your controller sets it. What a chip shows, for example for a character split across tokens, is decided in Python.
- The detail panel shows every field of the selected token: a field you add to `TokenView` appears there.
- Any further field of `ViewModel`, of `TokenizerView` or of a `ViewOption` appears as JSON under **More from the view-model**, and any further field of `CaptureView` under **Response metadata**.
- Another token sequence, such as the answer re-tokenized, is another view: add it to `views`, and the view selector offers it.
- **Text of this view** shows `ViewModel.text`.

After you change a view-model, restart the back end and run `npm run types` in `frontend`, so that the generated types follow; `npm run types:check` says when they do not ([The contract](#the-contract)).

When your controller works, plug it in at `wiring.py`. The page, written by someone else, then shows your model's tokens without any change to your model or your controller: the proof that the views are separate.

## Running

`npm ci` installs exactly the versions in `package-lock.json`, as `uv sync` does with `uv.lock`. The README's troubleshooting table explains what <http://127.0.0.1:8000> and its `/docs` page show.

## Try the starter

Before you change anything, try the starter, with the back end and the page running as in section 1 of the README. Until `wiring.py` builds your own controller, all the data on the page comes from the fake controller in `fake_controller.py`: every token is made up.

- Under the title, one line shows the model repository and its revision, `fake/example · revision fake`, and a notice says "Made-up data from the fake controller: no tokenizer has run."
- **Token boundaries** shows the seven tokens of the chat after the made-up template, `<fake>Show me fake tokens.</fake>`, as chips; the two special tokens are outlined and bold. Click a chip: **Selected token** shows all its fields. Click **All tokens of this view** to open a table of every token, and **Text of this view** to see the text the tokens cover.
- Under **View**, choose **Text alone** instead of **Chat, after a made-up template**: the text without the made-up template, in five tokens. Switching clears the selection.
- Type another **Repository** and **Revision**, for example `owner/name` and `main`, and click **Load model**: only the line under the title changes.
- In **Messages as JSON**, change `"Show me fake tokens."` to `"Hello"` and click **Set messages**: **Messages** shows the new message, and the tokens and the text stay the same.
- Under **Capture file**, choose any JSON file, for example `frontend/package.json`, and click **Load capture**: **Provider response** shows the file's name and a made-up answer. The page sends the file's name and content; the fake ignores the content.
- **More from the view-model** and **Response metadata**, which [Python only](#python-only) mentions, stay hidden: the fake's view-models have no further fields.

<http://127.0.0.1:8000/docs> lists every route and, under **Schemas**, every class the page and the back end exchange. It loads its scripts from the internet. Send one command from there:

1. Click **POST /api/selection**, then **Try it out**.
2. In **Request body**, replace the example with `{"index": 99}` and click **Execute**. Under **Server response**, **Code** shows 400: the controller ran, the stand-in model in `fake_controller.py` refused the command, and `detail` says why.
3. Replace the body with `{"index": "3"}` and click **Execute** again. **Code** shows 422: FastAPI refused the request before the controller ran. The request classes in `api.py` are strict: `"3"` is a string, not an int.

Neither answer changed anything. Then follow one click through the processes with the debugger, as the next section shows. Your own controller and model take over in the order the [task sheet](https://github.com/L3GJ0N/engineering_agentic_ai_systems_hs_aalen/blob/main/exercises/token_viewer/README.md#what-to-deliver-in-this-order) gives: first in your terminal view, then on the page, after a change to `wiring.py` only.

## Debugging

The debugger starts its own back end on port 8000, so first stop the back end from section 1 of the README: close its terminal with its trash-can icon, **Kill Terminal**, or press **Ctrl+C** in it (Control, also on macOS). Vite can keep running; if it does not run, start it in a terminal in `frontend` with `npm run dev`, because no debug configuration starts it. Then select **Run and Debug**, choose **Full stack: back end + browser** and click **Start Debugging**. The page opens in VS Code's integrated browser, a tab inside VS Code; it needs neither Edge nor Chrome. **Front end: browser (Edge)** and **Front end: browser (Chrome)** open an external browser instead; start them after **Back end: uvicorn**.

- **Python breakpoints:** in the route `select` in `api.py`, in your controller's `select_token` and in your model. In the starter, use `FakeController.select_token` and `_FakeModel.select` in `fake_controller.py`. Click a chip. When the debugger stops in `_FakeModel.select`, **Call Stack** shows, innermost first, the model's `select`, the controller's lambda, `_carry_out` and `select_token`, and the route `select`; click the frame `select` of `api.py` to see `body`, the request as FastAPI parsed it, in **Variables**. The paused thread is an **AnyIO worker thread**: FastAPI runs routes written with `def` in a pool of worker threads, and the lock in `api.py` lets one command at a time reach the controller.
- **TypeScript breakpoints:** in `main.ts`, in the function `chip`, on the line `void run(() => selectToken(token.index))` in its `click` handler, and in `api.ts` on the line `if (!response.ok)`, where `data` holds the parsed answer, the view-model. The click stops in TypeScript first, then, after **Continue**, in Python.
- **Network:** the Run and Debug sidebar shows the views of the session selected in **Call Stack**. Select **Front end: integrated browser** to see **Network**, the page's requests. While Python is paused, `POST /api/selection` waits for its answer, and the page says "Waiting for the back end…".
- **No `--reload`:** with `--reload`, uvicorn starts the server again in a new process each time you save a `.py` file, so the state starts from scratch. On Windows, uvicorn 0.54 sometimes does not restart at all and stays at "Reloading..." ([uvicorn issue #1972](https://github.com/Kludex/uvicorn/issues/1972), still open on 21 October 2026). So the debug configuration runs without it. After changing Python code, restart the back end: in **Call Stack**, hover over **Back end: uvicorn** and click its **Restart** icon. The toolbar's **Restart** acts on the session chosen in its list, which may be the browser.

The starter reads no key, so **Variables** shows nothing secret. If your code ever reads a key or a Hugging Face token, collapse **Variables** before you share your screen. The course's [debugging guide](https://github.com/L3GJ0N/engineering_agentic_ai_systems_hs_aalen/blob/main/llm_inference/debugging.md) explains why, and the debugger's buttons and panels.

## The contract

The views receive view-models: the classes in `backend/src/token_viewer/view_models.py`. FastAPI describes them at <http://127.0.0.1:8000/openapi.json>. In `frontend`, `npm run types` turns that description into `src/schema.d.ts`, and `npm run build` checks the page against it with the TypeScript compiler. After changing a view-model, restart the back end, then run `npm run types`: a back end started before the change still describes the old classes, and the generator writes the old types again without an error.

Two words have two meanings here. The model is MVC's model: the domain and its state. `load_model` chooses a language model on Hugging Face, whose tokenizer and chat template your model then uses. A view is MVC's view: the page or the terminal view. `select_view` switches between token sequences, such as the chat after the chat template and the text alone.

## Versions

TypeScript stays at 5.9 because openapi-typescript 7.13, the newest release on 21 October 2026, supports TypeScript 5 only. Do not upgrade TypeScript to 6 or 7 before openapi-typescript supports it.
