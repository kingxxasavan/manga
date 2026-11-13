"use client";

import { useActionState } from "react";
import { adminLogin } from "@/app/actions";

export default function AdminLoginPage() {
  const [message, action, pending] = useActionState(adminLogin, null);
  return (
    <div className="mx-auto max-w-sm pt-20">
      <h1 className="text-3xl font-extrabold">Owner login</h1>
      <form action={action} className="mt-6 space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold">Password</span>
          <input type="password" name="password" required autoComplete="current-password" className="h-12 w-full rounded-2xl border border-line bg-surface px-4 outline-none focus:border-accent" />
        </label>
        {message && <p role="alert" className="font-semibold text-accent">{message}</p>}
        <button disabled={pending} className="w-full rounded-full bg-accent py-3.5 font-bold text-accent-ink transition hover:brightness-110 disabled:opacity-60">
          {pending ? "Checking" : "Log in"}
        </button>
      </form>
    </div>
  );
}
