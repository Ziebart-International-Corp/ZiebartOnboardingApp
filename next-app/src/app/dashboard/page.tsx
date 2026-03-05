import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { getNewHiresCount, getDocumentsCount } from "@/lib/neon-api";

export default async function DashboardPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard");

  const role = (session.user as { role?: string }).role ?? "user";
  const isAdmin = role === "admin";
  const isManager = role === "manager";

  const [newHiresCount, documentsCount] = await Promise.all([
    getNewHiresCount(),
    getDocumentsCount(),
  ]);

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">Ziebart Onboarding</h1>
        <div className="flex items-center gap-4">
          <span className="text-zinc-400 text-sm">{session.user.email}</span>
          <Link
            href="/api/auth/signout"
            className="text-sm text-amber-500 hover:underline"
          >
            Sign out
          </Link>
        </div>
      </header>

      <div className="p-6 max-w-4xl mx-auto space-y-8">
        <h2 className="text-2xl font-semibold">Welcome back</h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link
            href="/dashboard/new-hires"
            className="block p-6 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-amber-500/50 transition"
          >
            <h3 className="font-semibold text-lg">New Hires</h3>
            <p className="text-3xl font-bold text-amber-500 mt-2">{newHiresCount}</p>
            <p className="text-zinc-400 text-sm mt-1">View and manage new hires</p>
          </Link>
          <Link
            href="/dashboard/documents"
            className="block p-6 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-amber-500/50 transition"
          >
            <h3 className="font-semibold text-lg">Documents</h3>
            <p className="text-3xl font-bold text-amber-500 mt-2">{documentsCount}</p>
            <p className="text-zinc-400 text-sm mt-1">Onboarding documents</p>
          </Link>
        </div>

        {(isAdmin || isManager) && (
          <div className="pt-4 border-t border-zinc-800">
            <h3 className="font-semibold mb-2">Admin</h3>
            <ul className="flex flex-wrap gap-3">
              <li>
                <Link href="/dashboard/new-hires" className="text-amber-500 hover:underline">
                  New Hires
                </Link>
              </li>
              <li>
                <Link href="/dashboard/documents" className="text-amber-500 hover:underline">
                  Documents
                </Link>
              </li>
              {isAdmin && (
                <>
                  <li>
                    <Link href="/dashboard/users" className="text-amber-500 hover:underline">
                      Users
                    </Link>
                  </li>
                  <li>
                    <Link href="/dashboard/settings" className="text-amber-500 hover:underline">
                      Settings
                    </Link>
                  </li>
                </>
              )}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}
