import Link from "next/link";
import { Button } from "@/components/ui/button";
import { EmptyStateIllustration } from "@/components/illustrations/meeting-illustration";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <EmptyStateIllustration className="h-48 w-64 text-foreground" />
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        The page you are looking for doesn&apos;t exist or has been moved.
      </p>
      <Button asChild>
        <Link href="/dashboard">Back to dashboard</Link>
      </Button>
    </div>
  );
}
