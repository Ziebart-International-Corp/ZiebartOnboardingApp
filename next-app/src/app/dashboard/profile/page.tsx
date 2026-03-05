import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";

export default async function ProfilePage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard/profile");

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 max-w-4xl">
      <h1 className="text-2xl font-bold text-black mb-6">Profile</h1>
      <p className="text-gray-500">Email: {session.user.email}</p>
    </div>
  );
}
