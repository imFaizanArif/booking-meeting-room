import { cn } from "@/lib/utils";

/** Standard page padding and width. Builder-style pages opt out with `full`. */
export function PageContainer({ children, className, full }: { children: React.ReactNode; className?: string; full?: boolean }) {
  return <div className={cn("flex flex-col gap-6 px-8 py-6", !full && "mx-auto w-full max-w-[1280px]", className)}>{children}</div>;
}
