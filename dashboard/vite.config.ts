import { defineConfig } from "vitest/config";

export default defineConfig({
  build: {
    outDir: "dist",
    sourcemap: false,
    emptyOutDir: true
  },
  test: {
    environment: "happy-dom",
    include: ["tests/**/*.test.ts"],
    setupFiles: ["tests/setup.ts"],
    chaiConfig: {
      truncateThreshold: 200
    }
  }
});
