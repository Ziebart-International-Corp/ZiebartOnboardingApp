import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { getNewHires } from "@/lib/neon-api";

export default async function NewHiresPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard/new-hires");

  const newHires = await getNewHires(true);

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <Link href="/dashboard" className="text-amber-500 hover:underline">← Dashboard</Link>
        <Link href="/api/auth/signout" className="text-sm text-zinc-400 hover:underline">Sign out</Link>
      </header>

      <div className="p-6 max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold mb-6">New Hires</h1>

        {newHires.length === 0 ? (
          <p className="text-zinc-400">No new hires yet.</p>
        ) : (
          <ul className="space-y-2">
            {newHires.map((n) => (
              <li key={n.id} className="flex items-center justify-between py-3 border-b border-zinc-800">
                <div>
                  <span className="font-medium">{n.first_name} {n.last_name}</span>
                  <span className="text-zinc-400 ml-2">({n.email})</span>
                </div>
                <span className="text-sm text-zinc-400 capitalize">{n.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
