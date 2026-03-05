import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard");

  const role = (session.user as { role?: string }).role ?? "user";
  const isAdmin = role === "admin";
  const isManager = role === "manager";
  const displayName = (session.user as { username?: string }).username ?? session.user.name ?? session.user.email ?? "User";

  return (
    <div className="min-h-screen bg-[#e5e5e5]">
      {/* Top header - black bar with logo, nav, notifications, user */}
      <header className="bg-black text-white px-6 py-3 flex flex-wrap items-center justify-between gap-4 shadow-md min-h-[60px] relative z-[100]">
        <div className="flex items-center gap-3">
          <div className="flex items-end gap-2">
            <div className="w-12 h-12 rounded bg-white/10 flex items-center justify-center text-red-500 font-bold text-lg shrink-0">
              Z
            </div>
            <span className="font-extrabold text-xl tracking-tight">Ziebart Onboarding</span>
          </div>
        </div>

        <nav className="hidden md:flex items-center gap-8">
          <Link href="/dashboard" className="text-white hover:text-[#FE0100] transition font-medium">
            Home
          </Link>
          <Link href="/dashboard/tasks" className="text-white hover:text-[#FE0100] transition font-medium">
            Tasks
          </Link>
          <Link href="/dashboard/documents" className="text-white hover:text-[#FE0100] transition font-medium">
            Files
          </Link>
          <Link href="/dashboard/videos" className="text-white hover:text-[#FE0100] transition font-medium">
            Videos
          </Link>
          <Link href="/dashboard/profile" className="text-white hover:text-[#FE0100] transition font-medium">
            Profile
          </Link>
          {(isAdmin || isManager) && (
            <Link
              href="/dashboard/manager"
              className="bg-white/10 hover:bg-white/20 px-4 py-2 rounded font-medium transition"
            >
              Manager Console
            </Link>
          )}
        </nav>

        <div className="flex items-center gap-4">
          <div className="relative text-xl cursor-pointer" title="Notifications">
            🔔
            <span className="sr-only">Notifications</span>
          </div>
          <div className="flex items-center gap-2 cursor-pointer py-1 px-2 rounded-full hover:bg-white/10 transition">
            <div className="w-8 h-8 rounded-full bg-[#FE0100] flex items-center justify-center text-white font-bold text-sm">
              {displayName.charAt(0).toUpperCase()}
            </div>
            <span className="font-medium">{displayName}</span>
            <span className="text-xs">▼</span>
          </div>
          <Link
            href="/api/auth/signout"
            className="text-sm text-white/80 hover:text-white ml-2"
          >
            Sign out
          </Link>
        </div>
      </header>

      <div className="max-w-[1200px] mx-auto w-full px-5 py-6">{children}</div>
    </div>
  );
}
