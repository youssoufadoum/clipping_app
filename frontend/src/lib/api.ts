import { config } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public correlationId: string | null = null,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }

  get retryable(): boolean {
    return Boolean(this.details.retryable) || this.status >= 500 || this.status === 429;
  }
}

type TokenGetter = () => Promise<string | null>;
type UnauthorizedHandler = () => void;

let getToken: TokenGetter = async () => null;
let onUnauthorized: UnauthorizedHandler = () => {};

/** Called once by the AuthProvider so every request carries the current token. */
export function configureApi(tokenGetter: TokenGetter, unauthorized: UnauthorizedHandler): void {
  getToken = tokenGetter;
  onUnauthorized = unauthorized;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  signal?: AbortSignal;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false) {
    const token = await getToken();
    if (!token) {
      onUnauthorized();
      throw new ApiError(401, "UNAUTHORIZED", "Please sign in to continue.");
    }
    headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${config.apiBaseUrl}${path}`, {
      method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
      cache: "no-store",
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the Virello API. Check your connection and try again.");
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; correlation_id?: string; details?: Record<string, unknown> } } | null)?.error;
    const apiErr = new ApiError(
      res.status,
      err?.code ?? "HTTP_ERROR",
      err?.message ?? `Request failed (${res.status}).`,
      err?.correlation_id ?? res.headers.get("x-correlation-id"),
      err?.details ?? {},
    );
    if (res.status === 401 && opts.auth !== false) onUnauthorized();
    throw apiErr;
  }
  return data as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
