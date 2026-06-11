import { redirect } from "next/navigation";

export default function RootPage() {
  // Middleware redirects authenticated users to /dashboard;
  // everyone else lands on /login.
  redirect("/login");
}
