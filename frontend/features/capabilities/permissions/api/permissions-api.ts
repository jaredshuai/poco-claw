import { apiClient, API_ENDPOINTS } from "@/services/api-client";
import type { PermissionPolicy } from "../types";

/**
 * Loads the user's permission policy via the dedicated execution-settings endpoint.
 */
export async function getPermissionPolicy(): Promise<PermissionPolicy> {
  return apiClient.get<PermissionPolicy>(
    API_ENDPOINTS.executionSettingsPermissions,
    { cache: "no-store" },
  );
}

/**
 * Persists the permission policy via PATCH /execution-settings/permissions.
 * The backend merges with the stored policy (partial updates supported).
 */
export async function updatePermissionPolicy(
  policy: PermissionPolicy,
): Promise<PermissionPolicy> {
  return apiClient.patch<PermissionPolicy>(
    API_ENDPOINTS.executionSettingsPermissions,
    policy,
  );
}
