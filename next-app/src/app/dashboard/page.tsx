import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import {
  getExternalLinks,
  getUserTasks,
  getDocumentAssignmentsWithDoc,
} from "@/lib/neon-api";

export default async function DashboardPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login?callbackUrl=/dashboard");

  const username = (session.user as { username?: string }).username ?? session.user.email?.split("@")[0] ?? "";

  const [externalLinks, userTasks, docAssignments] = await Promise.all([
    getExternalLinks(),
    getUserTasks(username),
    getDocumentAssignmentsWithDoc(username),
  ]);

  // Build task list: user_tasks + document assignments as "Sign Document: ..."
  const taskItems: { id: string; title: string; description: string; type: "document" | "general"; documentId: number | null; completed: boolean }[] = [];

  for (const t of userTasks) {
    taskItems.push({
      id: `task-${t.id}`,
      title: t.task_title,
      description: t.task_description || "Complete this task",
      type: t.task_type === "document" ? "document" : "general",
      documentId: t.document_id,
      completed: !!t.completed_at,
    });
  }
  for (const a of docAssignments) {
    if (taskItems.some((x) => x.documentId === a.document_id && x.type === "document")) continue;
    const docName = a.document_display_name || "Document";
    taskItems.push({
      id: `doc-${a.id}`,
      title: `Sign Document: ${docName}`,
      description: `Please review and sign the document: ${docName}`,
      type: "document",
      documentId: a.document_id,
      completed: a.is_completed,
    });
  }

  const totalTasks = taskItems.length;
  const completedTasks = taskItems.filter((t) => t.completed).length;
  const progressPercentage = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
  const incompleteTasks = taskItems.filter((t) => !t.completed);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 mt-6">
      {/* Left: TASKS */}
      <div className="min-w-0">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 min-h-[280px] flex flex-col">
          <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
            <h2 className="text-[0.95em] font-bold text-gray-800 uppercase tracking-wider border-b-2 border-gray-200 pb-2.5 m-0">
              Tasks
            </h2>
            <Link
              href="/dashboard/tasks"
              className="px-4 py-2 rounded-lg bg-[#FE0100]/10 text-[#FE0100] text-sm font-semibold hover:bg-[#FE0100] hover:text-white transition"
            >
              Complete items &gt;
            </Link>
          </div>

          {totalTasks > 0 ? (
            <>
              <div className="flex items-center gap-3 mb-3">
                <div className="flex-1 min-w-0 h-[30px] bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-[#FE0100] to-[#cc0000] transition-all duration-300"
                    style={{ width: `${progressPercentage}%` }}
                  />
                </div>
                <span className="text-sm font-semibold text-gray-800 shrink-0">{progressPercentage}%</span>
              </div>
              <p className="text-center text-gray-500 text-sm mb-4">
                {completedTasks} of {totalTasks} tasks completed
              </p>

              {incompleteTasks.length > 0 ? (
                <div className="space-y-3 flex-1 min-h-0 overflow-y-auto">
                  {incompleteTasks.slice(0, 5).map((task) => (
                    <div
                      key={task.id}
                      className="bg-white rounded-lg p-5 flex items-center gap-4 border-l-4 border-[#dc3545] shadow-sm"
                    >
                      <div className="text-2xl w-12 h-12 flex items-center justify-center shrink-0">
                        {task.type === "document" ? "✍️" : "📋"}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-[1.1em] font-semibold text-black mb-1">{task.title}</h3>
                        <p className="text-gray-500 text-sm">{task.description}</p>
                      </div>
                      {task.type === "document" && task.documentId ? (
                        <Link
                          href="/dashboard/documents"
                          className="shrink-0 px-6 py-3 bg-[#FE0100] text-white rounded-lg font-semibold hover:opacity-90 transition"
                        >
                          Sign Document &gt;
                        </Link>
                      ) : (
                        <Link
                          href="/dashboard/tasks"
                          className="shrink-0 px-6 py-3 bg-[#FE0100] text-white rounded-lg font-semibold hover:opacity-90 transition"
                        >
                          View Task &gt;
                        </Link>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-10 text-green-600 flex-1 flex flex-col items-center justify-center">
                  <div className="text-4xl mb-4">✓</div>
                  <h3 className="text-xl font-extrabold text-black mb-2">All Tasks Completed!</h3>
                  <p className="text-gray-500">Great job! You&apos;ve completed all your onboarding tasks.</p>
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 flex items-center">
              <p className="text-gray-500 text-sm">No tasks assigned yet. Check back soon or contact HR.</p>
            </div>
          )}
        </div>
      </div>

      {/* Right: EXTERNAL LINKS */}
      {externalLinks.length > 0 && (
        <div className="min-w-0">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 min-h-[280px] flex flex-col">
            <h2 className="text-[0.95em] font-bold text-gray-800 uppercase tracking-wider border-b-2 border-gray-200 pb-2.5 mb-4">
              External Links
            </h2>
            <div className="flex flex-col gap-3 flex-1 min-h-0 overflow-y-auto">
              {externalLinks.map((link) => (
                <a
                  key={link.id}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-4 p-4 bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-md hover:translate-x-1 transition text-black no-underline"
                >
                  <div className="w-20 h-20 rounded-xl border border-gray-200 flex items-center justify-center text-3xl shrink-0 bg-white overflow-hidden">
                    {link.image_filename ? "🖼️" : link.title.toLowerCase().includes("mobile") || link.title.toLowerCase().includes("app") ? "📱" : "🔗"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-gray-900">{link.title}</div>
                    {link.description && (
                      <div className="text-sm text-gray-500 mt-0.5">{link.description}</div>
                    )}
                  </div>
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
