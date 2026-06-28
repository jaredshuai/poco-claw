import type { SlashCommandSuggestion } from "@/features/capabilities/slash-commands/types";

export const SLASH_COMMAND_SUGGESTIONS_INVALIDATED_EVENT =
  "poco:slash-command-suggestions-invalidated";

let cachedSuggestions: SlashCommandSuggestion[] | null = null;
let cachedSuggestionsAt = 0;
let invalidatedAt = 0;
let inflightSuggestionsRequest: Promise<SlashCommandSuggestion[]> | null = null;

export function getSlashCommandSuggestionsInvalidatedAt(): number {
  return invalidatedAt;
}

export function getCachedSlashCommandSuggestions():
  SlashCommandSuggestion[] | null {
  if (cachedSuggestions === null) return null;
  if (cachedSuggestionsAt < invalidatedAt) return null;
  return cachedSuggestions;
}

export function setCachedSlashCommandSuggestions(
  suggestions: SlashCommandSuggestion[],
): void {
  cachedSuggestions = suggestions;
  cachedSuggestionsAt = Date.now();
}

export function hasFreshSlashCommandSuggestionsCache(ttlMs: number): boolean {
  if (cachedSuggestions === null) return false;
  if (cachedSuggestionsAt < invalidatedAt) return false;
  return Date.now() - cachedSuggestionsAt < ttlMs;
}

export function shouldSkipPreloadedSlashCommandSuggestions(): boolean {
  return invalidatedAt > cachedSuggestionsAt;
}

export function getInflightSlashCommandSuggestionsRequest(): Promise<
  SlashCommandSuggestion[]
> | null {
  return inflightSuggestionsRequest;
}

export function setInflightSlashCommandSuggestionsRequest(
  request: Promise<SlashCommandSuggestion[]>,
): void {
  inflightSuggestionsRequest = request;
}

export function clearInflightSlashCommandSuggestionsRequest(
  request?: Promise<SlashCommandSuggestion[]>,
): void {
  if (!request || inflightSuggestionsRequest === request) {
    inflightSuggestionsRequest = null;
  }
}

export function markSlashCommandSuggestionsInvalidated(): void {
  invalidatedAt = Date.now();
  cachedSuggestions = null;
  cachedSuggestionsAt = 0;
  inflightSuggestionsRequest = null;

  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(SLASH_COMMAND_SUGGESTIONS_INVALIDATED_EVENT));
}
