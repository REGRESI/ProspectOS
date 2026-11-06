import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value:
              "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
          },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
  async rewrites() {
    const api = process.env.API_URL || "http://127.0.0.1:8000";
    return [
      // OAuth redirect URL registered at LinkedIn (no /api prefix): the browser lands
      // here and the request is proxied to the backend callback, cookies included.
      {
        source: "/v1/integrations/linkedin/callback",
        destination: `${api}/v1/integrations/linkedin/callback`,
      },
      {
        source: "/api/:path*",
        destination: `${api}/:path*`,
      },
    ];
  },
};
export default nextConfig;
