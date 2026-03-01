/**
 * Next.js configuration for TinyClaw Office Dashboard.
 *
 * This configuration sets up the Next.js 15 application with:
 * - React 19 support
 * - TypeScript configuration
 * - App Router structure
 * - Tailwind CSS styling
 *
 * @see https://nextjs.org/docs/app/api-reference/next-config-js
 */

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable React 19 features
  reactStrictMode: true,

  // Experimental features for Next.js 15
  experimental: {
    // Use typed routes for better TypeScript support
    typedRoutes: true,
  },

  // Output configuration
  output: "standalone",

  // Environment variables exposed to the browser
  env: {
    // Orchestration API URL
    NEXT_PUBLIC_ORCHESTRATION_URL: process.env.NEXT_PUBLIC_ORCHESTRATION_URL,
  },

  // Webpack configuration for additional module resolution
  webpack: (config, { isServer }) => {
    // Fixes npm packages that depend on `fs` module
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      };
    }
    return config;
  },

  // Headers for security
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "X-DNS-Prefetch-Control",
            value: "on",
          },
          {
            key: "X-Frame-Options",
            value: "SAMEORIGIN",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "Referrer-Policy",
            value: "origin-when-cross-origin",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
