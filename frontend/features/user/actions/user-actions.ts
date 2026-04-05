import { userService } from "@/features/user/api/user-api";

/** Server action: full /users/me payload (one backend round-trip). */
export async function getUserMeAction() {
  return userService.getMe();
}

export async function getUserProfileAction() {
  return userService.getProfile();
}

export async function getUserCreditsAction() {
  return userService.getCredits();
}
