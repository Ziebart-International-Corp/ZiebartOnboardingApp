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
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 max-w-4xl">
      <h1 className="text-2xl font-bold text-black mb-6">New Hires</h1>

        {newHires.length === 0 ? (
          <p className="text-gray-500">No new hires yet.</p>
        ) : (
          <ul className="space-y-2">
            {newHires.map((n) => (
              <li key={n.id} className="flex items-center justify-between py-3 border-b border-gray-200">
                <div>
                  <span className="font-medium text-black">{n.first_name} {n.last_name}</span>
                  <span className="text-gray-500 ml-2">({n.email})</span>
                </div>
                <span className="text-sm text-gray-500 capitalize">{n.status}</span>
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}
