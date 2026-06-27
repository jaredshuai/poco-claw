"""Office save status constants.

Kept separate from office_editing_service to avoid circular imports with
the repositories that reference these values.
"""

SAVE_STATUS_PENDING = "pending"
SAVE_STATUS_SAVING = "saving"
SAVE_STATUS_CALLBACK_RECEIVED = "callback_received"
SAVE_STATUS_STAGED = "staged"
SAVE_STATUS_COMMITTING = "committing"  # legacy alias
SAVE_STATUS_SAVED = "saved"
SAVE_STATUS_FAILED = "failed"
ACTIVE_SAVE_STATUSES = {
    SAVE_STATUS_PENDING,
    SAVE_STATUS_SAVING,
    SAVE_STATUS_CALLBACK_RECEIVED,
    SAVE_STATUS_STAGED,
    SAVE_STATUS_COMMITTING,
}
