import { useState } from "react";

import { ApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface CommentItemProps {
  comment: { id: string; body: string; created_at: string; edited_at?: string | null };
  authorName: string;
  /** Only the comment's author may edit it. */
  canEdit: boolean;
  /** The author, or an Owner/Manager. */
  canDelete: boolean;
  onSave: (body: string) => Promise<void>;
  onDelete: () => Promise<void>;
}

// One comment in a task's or customer request's thread. The backend
// enforces who may edit/delete (app/comment_rules.py); `canEdit`/
// `canDelete` only decide which buttons appear.
export function CommentItem({ comment, authorName, canEdit, canDelete, onSave, onDelete }: CommentItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(comment.body);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const save = async () => {
    if (!draft.trim()) {
      setError("A comment can't be empty.");
      return;
    }
    setError(null);
    setIsSaving(true);
    try {
      await onSave(draft);
      setIsEditing(false);
    } catch (saveError) {
      setError(saveError instanceof ApiError ? saveError.message : "Could not save your changes.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">{authorName}</span>{" "}
          <time dateTime={comment.created_at}>{new Date(comment.created_at).toLocaleString()}</time>
          {comment.edited_at && <span title={new Date(comment.edited_at).toLocaleString()}> (edited)</span>}
        </p>
        {!isEditing && (canEdit || canDelete) && (
          <div className="flex gap-1">
            {canEdit && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                aria-label={`Edit comment by ${authorName}`}
                onClick={() => {
                  setDraft(comment.body);
                  setIsEditing(true);
                }}
              >
                Edit
              </Button>
            )}
            {canDelete && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs text-destructive"
                aria-label={`Delete comment by ${authorName}`}
                onClick={() => setIsConfirmingDelete(true)}
              >
                Delete
              </Button>
            )}
          </div>
        )}
      </div>

      {isEditing ? (
        <div className="mt-2 flex flex-col gap-2">
          <Label htmlFor={`edit-comment-${comment.id}`} className="sr-only">
            Edit comment
          </Label>
          <Textarea id={`edit-comment-${comment.id}`} value={draft} onChange={(event) => setDraft(event.target.value)} />
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button type="button" size="sm" disabled={isSaving} onClick={() => void save()}>
              {isSaving ? "Saving…" : "Save comment"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isSaving}
              onClick={() => {
                setIsEditing(false);
                setError(null);
              }}
            >
              Discard changes
            </Button>
          </div>
        </div>
      ) : (
        <p className="mt-1 whitespace-pre-wrap text-sm">{comment.body}</p>
      )}

      <ConfirmDialog
        open={isConfirmingDelete}
        onOpenChange={setIsConfirmingDelete}
        title="Delete this comment?"
        description="It will be removed from the thread for everyone. This can’t be undone."
        confirmLabel="Delete comment"
        destructive
        onConfirm={async () => {
          try {
            await onDelete();
          } catch (deleteError) {
            throw new Error(deleteError instanceof ApiError ? deleteError.message : "Could not delete the comment.");
          }
        }}
      />
    </div>
  );
}
