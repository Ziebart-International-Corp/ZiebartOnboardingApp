import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { getDocuments } from "@/lib/neon-api";

export default async function DocumentsPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard/documents");

  const documents = await getDocuments();

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 max-w-4xl">
      <h1 className="text-2xl font-bold text-black mb-6">Files</h1>

      {documents.length === 0 ? (
        <p className="text-gray-500">No documents yet.</p>
      ) : (
        <ul className="space-y-2">
          {documents.map((d) => (
            <li key={d.id} className="flex items-center justify-between py-3 border-b border-gray-200">
              <span className="font-medium text-black">{d.display_name || d.original_filename}</span>
              <span className="text-sm text-gray-500">{d.is_visible ? "Visible" : "Hidden"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
