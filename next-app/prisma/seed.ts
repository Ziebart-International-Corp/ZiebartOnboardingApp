import "dotenv/config";
import { hash } from "bcryptjs";
import { getUserByEmail, createUser } from "../src/lib/neon-api";

async function main() {
  const email = (process.env.SEED_ADMIN_EMAIL ?? "admin@ziebart.com").trim().toLowerCase();
  const password = process.env.SEED_ADMIN_PASSWORD ?? "ChangeMe123!";
  const existing = await getUserByEmail(email);
  if (existing) {
    console.log("Admin user already exists:", email);
    return;
  }
  const passwordHash = await hash(password, 10);
  await createUser({
    username: email.split("@")[0],
    email,
    password_hash: passwordHash,
    role: "admin",
    full_name: "Admin",
  });
  console.log(
    "Created admin user:",
    email,
    "(password: " + (process.env.SEED_ADMIN_PASSWORD ? "[from env]" : password) + ")"
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
