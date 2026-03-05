"use client";

import { useState, Suspense } from "react";
import { signIn } from "next-auth/react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") ?? "/dashboard";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const res = await signIn("credentials", {
      email: email.trim(),
      password,
      redirect: false,
      callbackUrl,
    });
    setLoading(false);
    if (res?.error) {
      setError("Invalid email or password. Please try again.");
      return;
    }
    if (res?.url) window.location.href = res.url;
    else window.location.href = callbackUrl;
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-6 bg-zinc-950">
      <div className="w-full max-w-sm space-y-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Ziebart Onboarding</h1>
          <p className="mt-2 text-zinc-400 text-sm">Sign in with your email</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-zinc-300 mb-1">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="you@ziebart.com"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-zinc-300 mb-1">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 px-4 rounded-lg bg-amber-500 text-black font-semibold hover:bg-amber-400 disabled:opacity-50 transition"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-center text-zinc-500 text-sm">
          <Link href="/" className="text-amber-500 hover:underline">Back to home</Link>
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <main className="min-h-screen flex items-center justify-center bg-zinc-950">
        <p className="text-zinc-400">Loading…</p>
      </main>
    }>
      <LoginForm />
    </Suspense>
  );
}
