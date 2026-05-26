import { Router, Request, Response } from "express";
import { db } from "../db";

const router = Router();

// GET /users/:id — returns a single user object.
// Existing clients depend on the shape:
//   { userId: number, email: string, displayName: string, role: string }
router.get("/:id", async (req: Request, res: Response) => {
  const userId = parseInt(req.params.id, 10);
  if (isNaN(userId)) {
    return res.status(400).json({ error: "Invalid user id" });
  }

  const user = await db.users.findUnique({ where: { id: userId } });
  if (!user) {
    return res.status(404).json({ error: "User not found" });
  }

  return res.json({
    userId: user.id,
    email: user.email,
    displayName: user.displayName,
    role: user.role,
  });
});

// GET /users — list all users, returns an array.
// Existing clients iterate the top-level array directly.
router.get("/", async (_req: Request, res: Response) => {
  const users = await db.users.findMany({ orderBy: { id: "asc" } });

  return res.json(
    users.map((u) => ({
      userId: u.id,
      email: u.email,
      displayName: u.displayName,
      role: u.role,
    }))
  );
});

// POST /users — creates a new user and returns the created record.
// Adds a new optional field `avatarUrl` to the response — backward-compatible.
router.post("/", async (req: Request, res: Response) => {
  const { email, displayName, role } = req.body;

  const created = await db.users.create({
    data: { email, displayName, role: role ?? "viewer" },
  });

  return res.status(201).json({
    userId: created.id,
    email: created.email,
    displayName: created.displayName,
    role: created.role,
    avatarUrl: created.avatarUrl ?? null,
  });
});

export default router;
