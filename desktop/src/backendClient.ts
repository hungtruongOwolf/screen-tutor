import type { ExplainTurnRequest, ExplainTurnResponse, StreamEvent } from "./contract";

export class BackendError extends Error {}

export async function explainTurn(
  backendUrl: string,
  accessToken: string | undefined,
  request: ExplainTurnRequest,
  timeoutMs = 60_000,
): Promise<ExplainTurnResponse> {
  let response: Response;
  try {
    response = await fetch(`${backendUrl}/explain-turn`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify(request),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    throw new BackendError(
      `Cannot reach the backend at ${backendUrl}. Is it running? (${(error as Error).message})`,
    );
  }
  if (!response.ok) {
    throw new BackendError(`Backend answered ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as ExplainTurnResponse;
}

// The same turn as explainTurn, delivered as events while the model is still
// writing: onEvent is called for each one as it arrives. Resolves when the stream
// ends. Throws BackendError when the service cannot be reached or refuses.
export async function explainTurnStream(
  backendUrl: string,
  accessToken: string | undefined,
  request: ExplainTurnRequest,
  onEvent: (event: StreamEvent) => void,
  cancel?: AbortSignal,
  timeoutMs = 120_000,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${backendUrl}/explain-turn/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify(request),
      signal: cancel ? AbortSignal.any([AbortSignal.timeout(timeoutMs), cancel]) : AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    throw new BackendError(
      `Cannot reach the backend at ${backendUrl}. Is it running? (${(error as Error).message})`,
    );
  }
  if (!response.ok || !response.body) {
    throw new BackendError(`Backend answered ${response.status}: ${await response.text()}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    let newline = pending.indexOf("\n");
    while (newline >= 0) {
      const line = pending.slice(0, newline).trim();
      pending = pending.slice(newline + 1);
      if (line) onEvent(JSON.parse(line) as StreamEvent);
      newline = pending.indexOf("\n");
    }
  }
  const last = pending.trim();
  if (last) onEvent(JSON.parse(last) as StreamEvent);
}

// One step's caption as spoken words (the backend asks an NVIDIA Nemotron model). Returns undefined when
// it cannot help (older backend, slow, failed): the caller then reads the caption itself.
export async function narrate(
  backendUrl: string,
  accessToken: string | undefined,
  request: { caption: string; question: string; earlier: string[] },
  timeoutMs = 4000,
): Promise<string | undefined> {
  try {
    const response = await fetch(`${backendUrl}/narrate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify(request),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return undefined;
    const body = (await response.json()) as { spoken?: string; source?: string };
    return body.source && body.source !== "caption" && body.spoken ? body.spoken : undefined;
  } catch {
    return undefined;
  }
}
