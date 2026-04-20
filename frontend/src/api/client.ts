export type ApiError = {
  status: number;
  message: string;
};

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(path);
  const text = await resp.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!resp.ok) {
    const msg = (data && typeof data === "object" && "detail" in data) ? String((data as any).detail) : `HTTP ${resp.status}`;
    const err: ApiError = { status: resp.status, message: msg };
    throw err;
  }
  return data as T;
}

