// The API client: one function per route of the back end. Every request goes
// to the page's own origin; Vite's development server passes /api on to
// FastAPI. Each command answers with the whole view-model.
import type { components } from './schema.d.ts'

// Types generated from the back end's OpenAPI description by npm run types.
export type ViewModel = components['schemas']['ViewModel']
export type TokenView = components['schemas']['TokenView']
export type Message = components['schemas']['Message']
type Refusal = components['schemas']['Refusal']
type ValidationProblem = components['schemas']['HTTPValidationError']

// An answer the page cannot use: a status outside 200-299, or a body that is
// not JSON. The message is for the status line.
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getViewModel(): Promise<ViewModel> {
  return send('GET', '/api/view-model')
}

export function loadModel(repository: string, revision: string): Promise<ViewModel> {
  const body: components['schemas']['RepositoryChoice'] = { repository, revision }
  return send('POST', '/api/model', body)
}

export function setMessages(messages: Message[]): Promise<ViewModel> {
  const body: components['schemas']['MessageList'] = { messages }
  return send('POST', '/api/messages', body)
}

export function loadCapture(name: string, content: string): Promise<ViewModel> {
  const body: components['schemas']['CaptureFile'] = { name, content }
  return send('POST', '/api/capture', body)
}

export function selectView(key: string): Promise<ViewModel> {
  const body: components['schemas']['ViewChoice'] = { key }
  return send('POST', '/api/view', body)
}

export function selectToken(index: number): Promise<ViewModel> {
  const body: components['schemas']['Selection'] = { index }
  return send('POST', '/api/selection', body)
}

async function send(method: 'GET' | 'POST', path: string, body?: object): Promise<ViewModel> {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      // FastAPI reads a request body only when it is declared as JSON.
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    // fetch gets no answer at all only when the page's own server, Vite, is down.
    throw new Error("No answer from the page's server. Is npm run dev still running?")
  }
  // Not every answer is JSON: when the back end is down, Vite's proxy answers
  // 502 with an empty body.
  const data = parseJson(await response.text())
  if (!response.ok) {
    throw new ApiError(response.status, describeProblem(response, data))
  }
  if (data === null) {
    // Vite answers a GET outside /api with index.html: the path is not proxied.
    throw new ApiError(response.status, `the answer to ${path} is not JSON`)
  }
  return data as ViewModel
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function describeProblem(response: Response, data: unknown): string {
  if (isRefusal(data)) {
    // 400: the controller refused the command. FastAPI's own errors, such as
    // 404, also carry a string detail.
    return data.detail
  }
  if (isValidationProblem(data)) {
    // 422: the JSON did not fit the request class, so the controller never ran.
    return (data.detail ?? [])
      .map((problem) => {
        const where = problem.loc.slice(1).join('.') // e.g. messages.0.content
        return where === '' ? problem.msg : `${where}: ${problem.msg}`
      })
      .join('; ')
  }
  return response.statusText || 'no details'
}

function isRefusal(data: unknown): data is Refusal {
  return typeof data === 'object' && data !== null && typeof (data as Refusal).detail === 'string'
}

function isValidationProblem(data: unknown): data is ValidationProblem {
  return (
    typeof data === 'object' && data !== null && Array.isArray((data as ValidationProblem).detail)
  )
}
