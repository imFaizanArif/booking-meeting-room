"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { BRAND_ICON } from "@/components/shell/nav";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useLogin } from "@/features/auth/queries";
import { ApiError } from "@/lib/api/client";

const schema = z.object({
  email: z.string().trim().email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const login = useLogin();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const serverError =
    login.error instanceof ApiError
      ? login.error.code === "RATE_LIMITED"
        ? "Too many attempts. Wait a minute and try again."
        : login.error.message
      : login.error
        ? "Could not reach the server."
        : null;

  async function onSubmit(values: Values) {
    await login.mutateAsync(values).then(
      () => {
        const next = params.get("next");
        router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
      },
      () => undefined,
    );
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-3" noValidate>
      <Field label="Email" htmlFor="email" error={form.formState.errors.email?.message}>
        <Input id="email" type="email" autoComplete="username" autoFocus aria-invalid={!!form.formState.errors.email} {...form.register("email")} />
      </Field>
      <Field label="Password" htmlFor="password" error={form.formState.errors.password?.message}>
        <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!form.formState.errors.password} {...form.register("password")} />
      </Field>
      {serverError ? (
        <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">
          {serverError}
        </p>
      ) : null}
      <Button type="submit" variant="primary" loading={login.isPending} className="mt-1">
        Sign in
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const Brand = BRAND_ICON;
  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg px-6">
      <div className="w-full max-w-[340px]">
        <div className="mb-8 flex items-center gap-2">
          <Brand className="size-5" aria-hidden />
          <span className="text-base font-semibold tracking-[-0.01em]">Agent Platform</span>
        </div>
        <h1 className="text-xl font-semibold tracking-[-0.01em]">Sign in</h1>
        <p className="mb-6 mt-1 text-sm text-fg-muted">Approvals, executions and configuration for your agent pipelines.</p>
        <React.Suspense>
          <LoginForm />
        </React.Suspense>
        {process.env.NODE_ENV !== "production" ? (
          <p className="mt-8 border-t border-border pt-4 text-xs text-fg-subtle">
            Demo accounts: <span className="font-mono">admin@example.com</span> / <span className="font-mono">admin-password</span> (owner),{" "}
            <span className="font-mono">operator@example.com</span> / <span className="font-mono">operator-password</span>.
          </p>
        ) : null}
      </div>
    </div>
  );
}
