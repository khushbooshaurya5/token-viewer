// The page is a view: it shows the view-model the back end returns and turns
// clicks into commands. It decides how things look, not what they are. All
// text reaches the page through textContent, never as HTML, so a message is
// always shown, never executed.
import './style.css'
import {
  ApiError,
  getViewModel,
  loadCapture,
  loadModel,
  selectToken,
  selectView,
  setMessages,
} from './api.ts'
import type { Message, TokenView, ViewModel } from './api.ts'

// Find an element of index.html and check its type.
function element<T extends HTMLElement>(id: string, type: new () => T): T {
  const found = document.getElementById(id)
  if (!(found instanceof type)) {
    throw new Error(`index.html has no ${type.name} with the id ${id}`)
  }
  return found
}

const tokenizerLine = element('tokenizer', HTMLParagraphElement)
const notice = element('notice', HTMLParagraphElement)
const status = element('status', HTMLParagraphElement)
const statusText = element('status-text', HTMLSpanElement)
const retryButton = element('retry', HTMLButtonElement)
const modelForm = element('model-form', HTMLFormElement)
const repositoryInput = element('repository', HTMLInputElement)
const revisionInput = element('revision', HTMLInputElement)
const messagesForm = element('messages-form', HTMLFormElement)
const messagesInput = element('messages-input', HTMLTextAreaElement)
const captureForm = element('capture-form', HTMLFormElement)
const captureInput = element('capture-file', HTMLInputElement)
const messagesShown = element('messages', HTMLPreElement)
const viewSelect = element('view', HTMLSelectElement)
const count = element('count', HTMLSpanElement)
const chips = element('tokens', HTMLDivElement)
const detail = element('detail', HTMLPreElement)
const table = element('table', HTMLTableSectionElement)
const captureStatus = element('capture-status', HTMLParagraphElement)
const answer = element('answer', HTMLPreElement)
const reasoning = element('reasoning', HTMLPreElement)
const viewText = element('view-text', HTMLPreElement)
const more = element('more', HTMLElement)
const moreText = element('more-text', HTMLPreElement)
const captureMore = element('capture-more', HTMLDivElement)
const captureMoreText = element('capture-more-text', HTMLPreElement)

let currentView: string | null = null // the model's view, from the last view-model

// The fields render() draws itself. Every other field, such as one you add to
// a view-model in Python, appears as JSON, so the page shows it without a
// change to this file.
const drawnFields: ReadonlySet<string> = new Set([
  'tokenizer',
  'notice',
  'messages',
  'views',
  'current_view',
  'text',
  'tokens',
  'selected',
  'capture',
])
const drawnCaptureFields: ReadonlySet<string> = new Set(['name', 'answer', 'reasoning'])
const drawnTokenizerFields: ReadonlySet<string> = new Set(['repository', 'revision'])
const drawnViewFields: ReadonlySet<string> = new Set(['key', 'title'])

// The fields of a view-model, or of a part of it, that render() does not draw.
function undrawn(record: object, drawn: ReadonlySet<string>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(record).filter(([key]) => !drawn.has(key)))
}

// Draw the whole page from one view-model. Every command's answer comes here.
function render(viewModel: ViewModel): void {
  const tokenizer = viewModel.tokenizer
  tokenizerLine.textContent =
    tokenizer === null ? 'No model loaded.' : `${tokenizer.repository} · revision ${tokenizer.revision}`
  notice.hidden = viewModel.notice === null
  notice.textContent = viewModel.notice
  messagesShown.textContent = JSON.stringify(viewModel.messages, null, 2)

  viewSelect.replaceChildren(...viewModel.views.map((option) => new Option(option.title, option.key)))
  // Show the model's view. With none, select nothing: the browser would
  // otherwise show the first option as if it were chosen.
  viewSelect.value = viewModel.current_view ?? ''
  currentView = viewModel.current_view
  count.textContent = `${viewModel.tokens.length} tokens`
  viewText.textContent = viewModel.text

  // Keep the keyboard focus on the chips when they are drawn again.
  const chipHadFocus = chips.contains(document.activeElement)
  // One chip per token, showing token.text exactly as the controller set it:
  // what a chip shows is decided in Python.
  chips.replaceChildren(...viewModel.tokens.map((token) => chip(token, viewModel.selected)))
  if (chipHadFocus) {
    chips.querySelector<HTMLElement>('.chip.selected')?.focus()
  }
  detail.textContent =
    viewModel.selected === null ? 'Select a token.' : JSON.stringify(viewModel.selected, null, 2)
  table.replaceChildren(...viewModel.tokens.map((token) => row(token, viewModel.selected)))

  const capture = viewModel.capture
  captureStatus.textContent = capture === null ? 'No capture loaded.' : `Capture: ${capture.name}`
  answer.textContent = capture?.answer ?? ''
  reasoning.textContent = capture?.reasoning ?? ''
  const captureFields = capture === null ? {} : undrawn(capture, drawnCaptureFields)
  captureMore.hidden = Object.keys(captureFields).length === 0
  captureMoreText.textContent = JSON.stringify(captureFields, null, 2)

  // Further fields of the view-model, and of the two parts render() draws only
  // in part: the tokenizer line and the view selector.
  const moreFields = undrawn(viewModel, drawnFields)
  const tokenizerFields = tokenizer === null ? {} : undrawn(tokenizer, drawnTokenizerFields)
  if (Object.keys(tokenizerFields).length > 0) {
    moreFields.tokenizer = tokenizerFields
  }
  const viewFields = Object.fromEntries(
    viewModel.views
      .map((option) => [option.key, undrawn(option, drawnViewFields)] as const)
      .filter(([, fields]) => Object.keys(fields).length > 0),
  )
  if (Object.keys(viewFields).length > 0) {
    moreFields.views = viewFields
  }
  more.hidden = Object.keys(moreFields).length === 0
  moreText.textContent = JSON.stringify(moreFields, null, 2)
}

function chip(token: TokenView, selected: TokenView | null): HTMLSpanElement {
  const isSelected = token.index === selected?.index
  const span = document.createElement('span')
  span.className = 'chip'
  span.classList.toggle('special', token.special)
  span.classList.toggle('selected', isSelected)
  span.textContent = token.text
  span.title = `#${token.index} · ID ${token.id}`
  span.tabIndex = 0
  span.setAttribute('role', 'button')
  span.setAttribute('aria-pressed', String(isSelected))
  span.addEventListener('click', () => {
    void run(() => selectToken(token.index))
  })
  span.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault() // also on repeats: a held Space would scroll the page
      if (!event.repeat) {
        void run(() => selectToken(token.index))
      }
    }
  })
  return span
}

function row(token: TokenView, selected: TokenView | null): HTMLTableRowElement {
  const tr = document.createElement('tr')
  tr.classList.toggle('selected', token.index === selected?.index)
  const cells = [
    String(token.index),
    String(token.id),
    token.piece,
    JSON.stringify(token.text),
    `${token.start}–${token.end}`,
    token.special ? 'yes' : '',
  ]
  for (const text of cells) {
    const td = document.createElement('td')
    td.textContent = text
    tr.append(td)
  }
  tr.addEventListener('click', () => {
    void run(() => selectToken(token.index))
  })
  return tr
}

function showStatus(message: string | null, canRetry = false): void {
  status.hidden = message === null
  statusText.textContent = message
  retryButton.hidden = !canRetry
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    return `HTTP ${error.status}: ${error.message}`
  }
  // Any other error: Vite, the page's own server, did not answer, or
  // JSON.parse refused the messages.
  return error instanceof Error ? error.message : String(error)
}

// One command at a time. While the back end works, or waits at a
// breakpoint, the page says so and ignores further commands.
let busy = false

// Send one command and draw its answer, or show why it failed.
async function run(command: () => Promise<ViewModel>): Promise<void> {
  if (busy) {
    viewSelect.value = currentView ?? '' // an ignored command changes nothing
    return
  }
  busy = true
  const waiting = setTimeout(() => showStatus('Waiting for the back end…'), 300)
  try {
    render(await command())
    showStatus(null)
  } catch (error) {
    // A failed command changed nothing: undo the choice in the selector.
    viewSelect.value = currentView ?? ''
    showStatus(describe(error))
  } finally {
    clearTimeout(waiting)
    busy = false
  }
}

// The first view-model, under the same guard as a command. The compound debug
// configuration starts the back end and the browser at the same time. Until
// uvicorn listens on port 8000, Vite's proxy answers 502, so the page asks
// again, for up to 20 seconds.
async function firstLoad(): Promise<void> {
  if (busy) {
    return // a double-click on Retry
  }
  busy = true
  let waiting = setTimeout(() => showStatus('Waiting for the back end…'), 300)
  try {
    for (let attempt = 1; attempt <= 40; attempt += 1) {
      try {
        const viewModel = await getViewModel()
        // Fill only empty fields: keep what the user typed in the meantime.
        repositoryInput.value ||= viewModel.tokenizer?.repository ?? ''
        revisionInput.value ||= viewModel.tokenizer?.revision ?? ''
        messagesInput.value ||= JSON.stringify(viewModel.messages, null, 2)
        render(viewModel)
        showStatus(null)
        return
      } catch (error) {
        clearTimeout(waiting)
        if (!(error instanceof ApiError && error.status === 502)) {
          showStatus(describe(error), true)
          return
        }
        const starting = 'Waiting for the back end to start (HTTP 502)…'
        if (statusText.textContent !== starting) {
          showStatus(starting) // only when it changes: role=status reads it aloud
        }
        await new Promise((resolve) => setTimeout(resolve, 500))
        // A 502 comes back at once. If the next attempt waits, the back end
        // runs and works, or waits at a breakpoint: say so, as run() does.
        waiting = setTimeout(() => showStatus('Waiting for the back end…'), 300)
      }
    }
    showStatus('The back end does not answer (HTTP 502).', true)
  } finally {
    clearTimeout(waiting)
    busy = false
  }
}

modelForm.addEventListener('submit', (event) => {
  event.preventDefault()
  void run(() => loadModel(repositoryInput.value, revisionInput.value))
})

messagesForm.addEventListener('submit', (event) => {
  event.preventDefault()
  if (busy) {
    return // ignored, as run() ignores a command while another one runs
  }
  let messages: Message[]
  try {
    // The back end checks the shape and answers 422 if it does not fit.
    messages = JSON.parse(messagesInput.value) as Message[]
  } catch (error) {
    showStatus(`The messages are not valid JSON: ${describe(error)}`)
    return
  }
  void run(() => setMessages(messages))
})

captureForm.addEventListener('submit', (event) => {
  event.preventDefault()
  if (busy) {
    return // ignored, as run() ignores a command while another one runs
  }
  const file = captureInput.files?.[0]
  if (file === undefined) {
    showStatus('Choose a capture file first.')
    return
  }
  void run(async () => loadCapture(file.name, await file.text()))
})

viewSelect.addEventListener('change', () => {
  void run(() => selectView(viewSelect.value))
})
retryButton.addEventListener('click', () => {
  void firstLoad()
})

void firstLoad()
