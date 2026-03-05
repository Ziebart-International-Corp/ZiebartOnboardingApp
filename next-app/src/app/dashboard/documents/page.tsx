import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { getDocuments } from "@/lib/neon-api";

export default async function DocumentsPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard/documents");

  const documents = await getDocuments();

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <Link href="/dashboard" className="text-amber-500 hover:underline">← Dashboard</Link>
        <Link href="/api/auth/signout" className="text-sm text-zinc-400 hover:underline">Sign out</Link>
      </header>

      <div className="p-6 max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold mb-6">Documents</h1>

        {documents.length === 0 ? (
          <p className="text-zinc-400">No documents yet.</p>
        ) : (
          <ul className="space-y-2">
            {documents.map((d) => (
              <li key={d.id} className="flex items-center justify-between py-3 border-b border-zinc-800">
                <span className="font-medium">{d.display_name || d.original_filename}</span>
                <span className="text-sm text-zinc-400">{d.is_visible ? "Visible" : "Hidden"}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
