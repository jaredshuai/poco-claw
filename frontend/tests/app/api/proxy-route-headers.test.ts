import { describe, expect, it } from "vitest";

import { stripForwardedHeaders } from "@/app/api/v1/[...path]/route";

describe("API proxy forwarded headers", () => {
  it("removes caller-controlled identity headers", () => {
    const headers = stripForwardedHeaders(
      new Headers({
        host: "localhost:3000",
        connection: "keep-alive",
        "x-user-id": "attacker",
        "x-user-id-token": "fake-token",
        "x-internal-token": "fake-internal",
        "x-request-id": "request-1",
      }),
    );

    expect(headers.has("host")).toBe(false);
    expect(headers.has("connection")).toBe(false);
    expect(headers.has("x-user-id")).toBe(false);
    expect(headers.has("x-user-id-token")).toBe(false);
    expect(headers.has("x-internal-token")).toBe(false);
    expect(headers.get("x-request-id")).toBe("request-1");
  });
});
