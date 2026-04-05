import type { UserCredits, UserProfile } from "@/features/user/types";
import { API_ENDPOINTS, apiClient } from "@/services/api-client";

/** Response body `data` from GET /api/v1/users/me (standard envelope unwrapped by apiFetch). */
export interface UserMeResponse {
  profile: UserProfile;
  credits: UserCredits;
}

/**
 * Loads profile and credits in a single request (preferred over separate getProfile/getCredits).
 */
async function getMe(): Promise<UserMeResponse> {
  return apiClient.get<UserMeResponse>(API_ENDPOINTS.usersMe);
}

export const userService = {
  getMe,

  /** Returns profile only; performs one GET /users/me. */
  getProfile: async (): Promise<UserProfile> => {
    const me = await getMe();
    return me.profile;
  },

  /** Returns credits only; performs one GET /users/me. */
  getCredits: async (): Promise<UserCredits> => {
    const me = await getMe();
    return me.credits;
  },
};
