/**
 * API base URL for the Flask backend. In dev, use Flask's URL (e.g. http://127.0.0.1:5000).
 * For same-origin proxy, set NEXT_PUBLIC_API_URL to "" and use rewrites in next.config.
 */
const getApiBase = (): string => {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5000";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5000";
};

export const apiBase = getApiBase();

export function loginUrl(): string {
  return `${apiBase}/login`;
}

export function welcomeUrl(): string {
  return `${apiBase}/welcome`;
}

export function dashboardUrl(): string {
  return `${apiBase}/dashboard`;
}
