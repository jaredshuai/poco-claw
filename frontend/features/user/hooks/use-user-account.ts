import { useEffect, useState } from "react";
import type { UserCredits, UserProfile } from "@/features/user/types";
import { userService } from "@/features/user/api/user-api";

/**
 * Client hook: loads the current user profile and credits from GET /users/me.
 */
export function useUserAccount() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [credits, setCredits] = useState<UserCredits | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchUserData = async () => {
      try {
        const me = await userService.getMe();
        setProfile(me.profile);
        setCredits(me.credits);
      } catch (error) {
        console.error("Failed to fetch user data", error);
      } finally {
        setIsLoading(false);
      }
    };

    void fetchUserData();
  }, []);

  return {
    profile,
    credits,
    isLoading,
  };
}
