import { Logo } from "@/components/layout/logo";
import { AuthIllustration } from "@/components/illustrations/meeting-illustration";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-secondary p-12 text-secondary-foreground lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            background:
              "radial-gradient(60% 50% at 20% 10%, rgba(37,99,235,0.45) 0%, transparent 70%), radial-gradient(50% 40% at 90% 90%, rgba(20,184,166,0.35) 0%, transparent 70%)",
          }}
        />
        <div className="relative z-10">
          <Logo className="[&_span]:text-secondary-foreground [&_span:last-child]:text-secondary-foreground/60" />
        </div>
        <div className="relative z-10 flex justify-center">
          <AuthIllustration className="h-80 w-80" />
        </div>
        <div className="relative z-10 space-y-2">
          <h2 className="text-2xl font-bold tracking-tight">
            Every meeting needs a room.
          </h2>
          <p className="max-w-md text-sm text-secondary-foreground/70">
            Find a free room in seconds, invite your team and never double-book again.
            Built for the 50 humans of Kodifly.
          </p>
        </div>
      </div>

      {/* Form panel */}
      <div className="flex flex-col items-center justify-center p-6 sm:p-12">
        <div className="mb-8 lg:hidden">
          <Logo />
        </div>
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  );
}
