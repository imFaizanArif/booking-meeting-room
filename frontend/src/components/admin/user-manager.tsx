"use client";

import { Search, ShieldCheck, ShieldOff, UserCheck, UserX } from "lucide-react";
import { useState } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminUpdateUser, useMe, useUsers } from "@/hooks/use-users";
import { getInitials } from "@/lib/utils";

export function UserManager() {
  const [search, setSearch] = useState("");
  const { data: users, isLoading } = useUsers(search || undefined);
  const { data: me } = useMe();
  const adminUpdate = useAdminUpdateUser();

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search employees by name, email or department…"
          className="pl-9"
          aria-label="Search employees"
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {(users ?? []).map((user) => {
            const isSelf = user.id === me?.id;
            return (
              <Card key={user.id} className={!user.is_active ? "opacity-60" : undefined}>
                <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
                  <Avatar className="h-11 w-11">
                    <AvatarImage src={user.avatar_url ?? undefined} alt={user.name} />
                    <AvatarFallback>{getInitials(user.name || user.email)}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{user.name || "Unnamed"}</span>
                      {user.role === "admin" && <Badge variant="accent">Admin</Badge>}
                      {!user.is_active && <Badge variant="destructive">Disabled</Badge>}
                      {isSelf && <Badge variant="secondary">You</Badge>}
                    </div>
                    <p className="truncate text-sm text-muted-foreground">
                      {user.email}
                      {user.department && ` · ${user.department}`}
                      {user.designation && ` · ${user.designation}`}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={isSelf || adminUpdate.isPending}
                      onClick={() =>
                        adminUpdate.mutate({
                          id: user.id,
                          payload: {
                            role: user.role === "admin" ? "employee" : "admin",
                          },
                        })
                      }
                    >
                      {user.role === "admin" ? (
                        <>
                          <ShieldOff className="h-4 w-4" />
                          Revoke admin
                        </>
                      ) : (
                        <>
                          <ShieldCheck className="h-4 w-4" />
                          Make admin
                        </>
                      )}
                    </Button>
                    <Button
                      variant={user.is_active ? "outline" : "accent"}
                      size="sm"
                      disabled={isSelf || adminUpdate.isPending}
                      className={user.is_active ? "text-destructive" : undefined}
                      onClick={() =>
                        adminUpdate.mutate({
                          id: user.id,
                          payload: { is_active: !user.is_active },
                        })
                      }
                    >
                      {user.is_active ? (
                        <>
                          <UserX className="h-4 w-4" />
                          Disable
                        </>
                      ) : (
                        <>
                          <UserCheck className="h-4 w-4" />
                          Enable
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
          {(users ?? []).length === 0 && (
            <p className="rounded-2xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
              No employees found.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
