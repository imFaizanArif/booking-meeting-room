import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@agent-platform/api-client"],
  output: "standalone",
  poweredByHeader: false,
  devIndicators: false,
  async rewrites() {
    // Same-origin API: session cookies and CSRF work without CORS.
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default config;
