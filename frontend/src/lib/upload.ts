import type { UploadTarget } from "@/lib/types";

export const ACCEPTED_EXTENSIONS = [".mp4", ".m4v", ".mov", ".webm"];
export const ACCEPT_ATTR = "video/mp4,video/quicktime,video/webm,.mp4,.m4v,.mov,.webm";

export function validateVideoFile(file: File, maxBytes: number | null): string | null {
  const name = file.name.toLowerCase();
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  if (!ACCEPTED_EXTENSIONS.includes(ext)) {
    return "Unsupported file type. Upload an MP4, MOV or WebM video.";
  }
  if (file.size === 0) return "This file is empty.";
  if (maxBytes != null && file.size > maxBytes) {
    const gb = (maxBytes / 1024 ** 3).toFixed(1);
    return `This file is larger than your plan's ${gb} GB upload limit.`;
  }
  return null;
}

export function contentTypeFor(file: File): string {
  if (file.type) return file.type;
  const name = file.name.toLowerCase();
  if (name.endsWith(".mov")) return "video/quicktime";
  if (name.endsWith(".webm")) return "video/webm";
  return "video/mp4";
}

export interface UploadHandle {
  promise: Promise<void>;
  abort: () => void;
}

/**
 * PUT the file straight to object storage using the presigned target.
 * Progress comes from the browser's real upload events.
 */
export function putToStorage(
  file: File,
  target: UploadTarget,
  onProgress: (loaded: number, total: number) => void,
): UploadHandle {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<void>((resolve, reject) => {
    xhr.open(target.method, target.url);
    for (const [k, v] of Object.entries(target.headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded, e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed (${xhr.status}). Please retry.`));
    };
    xhr.onerror = () => reject(new Error("The upload was interrupted. Check your connection and retry."));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}
