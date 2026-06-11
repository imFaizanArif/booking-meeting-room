"use client";

import { Loader2, UserPlus } from "lucide-react";
import Link from "next/link";
import { useActionState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { signupAction, type AuthState } from "../actions";

const initialState: AuthState = {};

export default function SignupPage() {
  const [state, formAction, pending] = useActionState(signupAction, initialState);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <Card className="border-none shadow-glass">
        <CardHeader className="space-y-2">
          <CardTitle className="text-2xl">Create your account</CardTitle>
          <CardDescription>
            Use your <span className="font-medium text-foreground">@kodifly.com</span> email
            to join the workspace.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={formAction} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Full name</Label>
              <Input id="name" name="name" placeholder="Ada Lovelace" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Company email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                placeholder="ada@kodifly.com"
                autoComplete="email"
                required
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="department">Department</Label>
                <Input id="department" name="department" placeholder="Engineering" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="designation">Designation</Label>
                <Input id="designation" name="designation" placeholder="Software Engineer" />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                placeholder="At least 8 characters"
                autoComplete="new-password"
                minLength={8}
                required
              />
            </div>

            {state.error && (
              <p className="rounded-xl bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {state.error}
              </p>
            )}
            {state.success && (
              <p className="rounded-xl bg-accent/10 px-3 py-2 text-sm text-accent">
                {state.success}
              </p>
            )}

            <Button type="submit" className="w-full" size="lg" disabled={pending}>
              {pending ? <Loader2 className="animate-spin" /> : <UserPlus />}
              Sign up
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-primary hover:underline">
              Log in
            </Link>
          </p>
        </CardContent>
      </Card>
    </motion.div>
  );
}
