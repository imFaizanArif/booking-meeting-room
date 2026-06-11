import type { NextConfig } from "next";

// Flask backend origin. On Vercel set BACKEND_URL to the backend deployment,
// e.g. https://kodifly-meeting-room-api.vercel.app
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:5000";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
      { protocol: "https", hostname: "**.supabase.co" },
      { protocol: "https", hostname: "api.dicebear.com" },
    ],
  },
  async rewrites() {
    // Proxy same-origin /api/* requests to the Flask backend so the browser
    // never needs CORS and the API is reachable at <frontend-url>/api/*.
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
