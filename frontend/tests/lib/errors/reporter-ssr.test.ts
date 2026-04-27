// @vitest-environment node

import { describe, expect, it } from "vitest";

describe("RUM reporter SSR behavior", () => {
  it("can be imported without a browser window", async () => {
    const reporter = await import("@/lib/errors/reporter");

    expect(reporter.initRumClient()).toBeNull();
    expect(() => reporter.reportToRum(new Error("server error"))).not.toThrow();
  });
});
