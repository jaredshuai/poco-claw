import Aegis from "aegis-web-sdk";

let rumClient: Aegis | null = null;
let rumInitAttempted = false;

function getAegisId(): string {
  return process.env.NEXT_PUBLIC_AEGIS_ID?.trim() ?? "";
}

function getAegisUin(): string | undefined {
  const uin = process.env.NEXT_PUBLIC_AEGIS_UIN?.trim();
  return uin ? uin : undefined;
}

function normalizeError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }

  if (typeof error === "string" && error.trim()) {
    return new Error(error);
  }

  try {
    return new Error(JSON.stringify(error));
  } catch {
    return new Error("Unknown error");
  }
}

export function initRumClient(): Aegis | null {
  if (rumClient) {
    return rumClient;
  }

  if (rumInitAttempted || typeof window === "undefined") {
    return null;
  }

  const aegisId = getAegisId();
  if (!aegisId) {
    return null;
  }

  rumInitAttempted = true;

  try {
    rumClient = new Aegis({
      id: aegisId,
      // Pass a stable user identifier when it is safe to expose in the browser.
      uin: getAegisUin(),
      spa: true,
    });
  } catch (error) {
    rumClient = null;

    if (process.env.NODE_ENV !== "production") {
      console.warn("[RUM] Failed to initialize Aegis", error);
    }
  }

  return rumClient;
}

export function reportToRum(
  error: unknown,
  context?: Record<string, unknown>,
): void {
  if (typeof window === "undefined") {
    return;
  }

  const client = initRumClient();
  if (!client) {
    return;
  }

  try {
    const reportableError = normalizeError(error);

    if (context && Object.keys(context).length > 0) {
      client.error(reportableError, context);
      return;
    }

    client.error(reportableError);
  } catch (reportError) {
    if (process.env.NODE_ENV !== "production") {
      console.warn("[RUM] Failed to report error", reportError);
    }
  }
}
