import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

function origin(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

// Origins the browser legitimately talks to: the API, Supabase Auth, and the
// object-storage host that serves presigned upload/download URLs.
const apiOrigin = origin(process.env.NEXT_PUBLIC_API_BASE_URL) ?? "http://localhost:8000";
const supabaseOrigin = origin(process.env.NEXT_PUBLIC_SUPABASE_URL);
const storageOrigins = (process.env.NEXT_PUBLIC_STORAGE_ORIGINS ?? "")
  .split(",")
  .map((o) => origin(o.trim()))
  .filter((o): o is string => Boolean(o));

const connect = ["'self'", apiOrigin, supabaseOrigin, ...storageOrigins].filter(Boolean);
const media = ["'self'", "blob:", apiOrigin, ...storageOrigins];

const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${[apiOrigin, ...storageOrigins].join(" ")}`,
  `media-src ${media.join(" ")}`,
  `connect-src ${connect.join(" ")}${isDev ? " ws: wss:" : ""}`,
  "font-src 'self' data:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
