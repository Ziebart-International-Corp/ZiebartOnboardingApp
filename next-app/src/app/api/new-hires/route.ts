import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { authOptions } from "@/lib/auth";
import { getNewHires } from "@/lib/neon-api";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const newHires = await getNewHires(true);

  return NextResponse.json(
    newHires.map((n) => ({
      id: n.id,
      username: n.username,
      firstName: n.first_name,
      lastName: n.last_name,
      email: n.email,
      department: n.department,
      position: n.position,
      status: n.status,
      startDate: n.start_date?.slice(0, 10) ?? null,
      createdAt: n.created_at,
    }))
  );
}
