/** The API origin: set in development, the same origin when served by `loupe serve`. */
export const API = process.env.NEXT_PUBLIC_LOUPE_API ?? "";

export type Health = { status: string; version: string; home: string };

export async function health(signal?: AbortSignal): Promise<Health> {
  const res = await fetch(`${API}/api/health`, { signal });
  if (!res.ok) throw new Error(`health ${res.status}`);
  return res.json();
}
