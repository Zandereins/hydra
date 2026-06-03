import { db } from "../db";
import { sendMail } from "../mailer";

const TOKEN_TTL_MS = 1000 * 60 * 30;

export async function requestPasswordReset(email: string): Promise<void> {
  const user = await db.users.findByEmail(email);
  if (!user) return;
  const token = generateResetToken();
  await db.resetTokens.insert({ userId: user.id, token, expiresAt: Date.now() + TOKEN_TTL_MS });
  await sendMail(email, `Reset link: https://app.example.com/reset?token=${token}`);
}
