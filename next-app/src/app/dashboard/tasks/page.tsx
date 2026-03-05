import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";

export default async function TasksPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard/tasks");

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 max-w-4xl">
      <h1 className="text-2xl font-bold text-black mb-6">Tasks</h1>
      <p className="text-gray-500">View and complete your assigned tasks here.</p>
    </div>
  );
}
