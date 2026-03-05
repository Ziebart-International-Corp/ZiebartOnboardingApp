"use client";

import Link from "next/link";
import { loginUrl, welcomeUrl } from "@/lib/api";

export default function LoginPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-6 bg-zinc-950">
      <div className="w-full max-w-sm space-y-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Ziebart Onboarding</h1>
          <p className="mt-2 text-zinc-400 text-sm">Sign in with your email</p>
        </div>

        {/* Form POSTs directly to Flask so session cookie and redirect work without CORS */}
        <form
          method="post"
          action={loginUrl()}
          className="space-y-4"
        >
          <input type="hidden" name="next" value={welcomeUrl()} />
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
              className="w-full px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
          <button
            type="submit"
            className="w-full py-3 px-4 rounded-lg bg-amber-500 text-black font-semibold hover:bg-amber-400 transition"
          >
            Sign in
          </button>
        </form>

        <p className="text-center text-zinc-500 text-sm">
          <Link href="/" className="text-amber-500 hover:underline">Back to home</Link>
        </p>
      </div>
    </main>
  );
}
