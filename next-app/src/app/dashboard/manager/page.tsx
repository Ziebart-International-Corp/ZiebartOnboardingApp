import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { getNewHiresCount, getDocumentsCount } from "@/lib/neon-api";

export default async function ManagerPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard/manager");

  const role = (session.user as { role?: string }).role ?? "user";
  if (role !== "admin" && role !== "manager") redirect("/dashboard");

  const [newHiresCount, documentsCount] = await Promise.all([
    getNewHiresCount(),
    getDocumentsCount(),
  ]);

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 max-w-4xl">
      <h1 className="text-2xl font-bold text-black mb-6">Manager Console</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Link
          href="/dashboard/new-hires"
          className="block p-6 rounded-xl border border-gray-200 hover:border-[#FE0100]/50 transition"
        >
          <h3 className="font-semibold text-lg text-black">New Hires</h3>
          <p className="text-2xl font-bold text-[#FE0100] mt-2">{newHiresCount}</p>
        </Link>
        <Link
          href="/dashboard/documents"
          className="block p-6 rounded-xl border border-gray-200 hover:border-[#FE0100]/50 transition"
        >
          <h3 className="font-semibold text-lg text-black">Documents</h3>
          <p className="text-2xl font-bold text-[#FE0100] mt-2">{documentsCount}</p>
        </Link>
      </div>
    </div>
  );
}
