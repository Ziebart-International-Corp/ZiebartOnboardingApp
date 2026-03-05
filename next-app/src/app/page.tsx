import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="max-w-md w-full text-center space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Ziebart Onboarding</h1>
        <p className="text-zinc-400">Sign in to continue to the onboarding app.</p>
        <Link
          href="/login"
          className="inline-block w-full py-3 px-4 rounded-lg bg-amber-500 text-black font-semibold hover:bg-amber-400 transition"
        >
          Sign in
        </Link>
      </div>
    </main>
  );
}
