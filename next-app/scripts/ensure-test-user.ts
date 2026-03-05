/**
 * Ensures test user asymons@ziebart.com exists with password "password".
 * Run from next-app: npx tsx scripts/ensure-test-user.ts
 */
import { readFileSync, existsSync } from "fs";
import { resolve } from "path";
const envPath = resolve(process.cwd(), ".env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const m = line.match(/^([^#=]+)=(.*)$/);
    if (m) process.env[m[1].trim()] = m[2].trim().replace(/^["']|["']$/g, "");
  }
}
import { hash } from "bcryptjs";
import { getUserByEmail, createUser, updateUserPasswordByEmail } from "../src/lib/neon-api";

const TEST_EMAIL = "asymons@ziebart.com";
const TEST_PASSWORD = "password";

async function main() {
  const user = await getUserByEmail(TEST_EMAIL);
  const passwordHash = await hash(TEST_PASSWORD, 10);

  if (user) {
    await updateUserPasswordByEmail(TEST_EMAIL, passwordHash);
    console.log("Updated password for", TEST_EMAIL, "to", TEST_PASSWORD);
  } else {
    await createUser({
      username: TEST_EMAIL.split("@")[0],
      email: TEST_EMAIL,
      password_hash: passwordHash,
      full_name: "Test Admin",
      role: "admin",
    });
    console.log("Created test user:", TEST_EMAIL, "with password:", TEST_PASSWORD);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
