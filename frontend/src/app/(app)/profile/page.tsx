"use client";

import { BadgeCheck, Loader2, LogOut, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe, useUpdateMe } from "@/hooks/use-users";
import { createClient } from "@/lib/supabase/client";
import { getInitials } from "@/lib/utils";

export default function ProfilePage() {
  const router = useRouter();
  const { data: me, isLoading } = useMe();
  const updateMe = useUpdateMe();

  const [name, setName] = useState("");
  const [department, setDepartment] = useState("");
  const [designation, setDesignation] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");

  useEffect(() => {
    if (me) {
      setName(me.name);
      setDepartment(me.department);
      setDesignation(me.designation);
      setAvatarUrl(me.avatar_url ?? "");
    }
  }, [me]);

  async function handleLogout() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    updateMe.mutate({
      name: name.trim(),
      department: department.trim(),
      designation: designation.trim(),
      avatar_url: avatarUrl.trim() || null,
    });
  }

  if (isLoading || !me) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Skeleton className="h-9 w-44" />
        <Skeleton className="h-96 w-full rounded-3xl" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Profile</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage how you appear to your colleagues.
        </p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <Card>
          <CardHeader className="flex-row items-center gap-4 space-y-0">
            <Avatar className="h-16 w-16">
              <AvatarImage src={avatarUrl || undefined} alt={me.name} />
              <AvatarFallback className="text-lg">
                {getInitials(me.name || me.email)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <CardTitle className="flex flex-wrap items-center gap-2">
                {me.name || "Unnamed"}
                {me.role === "admin" && (
                  <Badge variant="accent" className="gap-1">
                    <BadgeCheck className="h-3 w-3" />
                    Admin
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="truncate">{me.email}</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="profile-name">Full name</Label>
                <Input
                  id="profile-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="profile-department">Department</Label>
                  <Input
                    id="profile-department"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="Engineering"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-designation">Designation</Label>
                  <Input
                    id="profile-designation"
                    value={designation}
                    onChange={(e) => setDesignation(e.target.value)}
                    placeholder="Software Engineer"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-avatar">Avatar URL</Label>
                <Input
                  id="profile-avatar"
                  type="url"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  placeholder="https://…"
                />
              </div>

              <div className="flex justify-end">
                <Button type="submit" disabled={updateMe.isPending}>
                  {updateMe.isPending ? <Loader2 className="animate-spin" /> : <Save />}
                  Save changes
                </Button>
              </div>
            </form>

            <Separator className="my-6" />

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium">Log out</p>
                <p className="text-xs text-muted-foreground">
                  Sign out from this device.
                </p>
              </div>
              <Button variant="outline" className="text-destructive" onClick={handleLogout}>
                <LogOut className="h-4 w-4" />
                Log out
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
