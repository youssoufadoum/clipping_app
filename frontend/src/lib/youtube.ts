/** Client-side mirror of the API's YouTube link validation (the server re-validates). */
const HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtu.be",
  "www.youtu.be",
  "youtube-nocookie.com",
  "www.youtube-nocookie.com",
]);
const ID = /^[A-Za-z0-9_-]{11}$/;
const PREFIXES = new Set(["shorts", "live", "embed", "v", "e"]);

export function parseYouTubeId(raw: string): string | null {
  let text = raw.trim();
  if (!text || text.length > 2048 || /\s/.test(text)) return null;
  if (!text.includes("://")) text = `https://${text}`;
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return null;
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
  if (url.port && !["80", "443"].includes(url.port)) return null;
  const host = url.hostname.toLowerCase();
  if (!HOSTS.has(host)) return null;
  const parts = url.pathname.split("/").filter(Boolean);
  let candidate: string | null = null;
  if (host.endsWith("youtu.be")) candidate = parts[0] ?? null;
  else if (parts[0] === "watch") candidate = url.searchParams.get("v");
  else if (parts.length >= 2 && PREFIXES.has(parts[0])) candidate = parts[1];
  return candidate && ID.test(candidate) ? candidate : null;
}
