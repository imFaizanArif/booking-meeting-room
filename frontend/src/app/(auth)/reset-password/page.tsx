"use client";

import { Loader2, ShieldCheck } from "lucide-react";
import { useActionState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { resetPasswordAction, type AuthState } from "../actions";

const initialState: AuthState = {};

export default function ResetPasswordPage() {
  const [state, formAction, pending] = useActionState(resetPasswordAction, initialState);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <Card className="border-none shadow-glass">
        <CardHeader className="space-y-2">
          <CardTitle className="text-2xl">Choose a new password</CardTitle>
          <CardDescription>
            You&apos;re signed in via your reset link — set a new password below.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={formAction} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="password">New password</Label>
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
            <div className="space-y-2">
              <Label htmlFor="confirm">Confirm password</Label>
              <Input
                id="confirm"
                name="confirm"
                type="password"
                placeholder="Repeat your new password"
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

            <Button type="submit" className="w-full" size="lg" disabled={pending}>
              {pending ? <Loader2 className="animate-spin" /> : <ShieldCheck />}
              Update password
            </Button>
          </form>
        </CardContent>
      </Card>
    </motion.div>
  );
}
