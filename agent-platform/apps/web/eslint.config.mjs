import next from "eslint-config-next";

export default [
  ...next,
  {
    rules: {
      "no-restricted-globals": ["error", { name: "fetch", message: "Use the generated API client (lib/api)." }],
    },
  },
  { files: ["lib/api/**", "e2e/**", "**/*.test.ts", "**/*.test.tsx"], rules: { "no-restricted-globals": "off" } },
  { ignores: [".next/**", "node_modules/**", "playwright-report/**"] },
];
