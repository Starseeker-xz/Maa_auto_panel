import React from "react";

type RenameKey = string | number;

export function useInlineRename<T extends RenameKey>(onCommit: (key: T, draft: string) => void) {
  const [renamingKey, setRenamingKey] = React.useState<T | null>(null);
  const [renameDraft, setRenameDraft] = React.useState("");
  const skipBlurCommit = React.useRef(false);

  function startRename(key: T, value: string) {
    skipBlurCommit.current = false;
    setRenamingKey(key);
    setRenameDraft(value);
  }

  function commitRename() {
    if (skipBlurCommit.current) {
      skipBlurCommit.current = false;
      return;
    }
    if (renamingKey === null) return;
    onCommit(renamingKey, renameDraft);
    setRenamingKey(null);
    setRenameDraft("");
  }

  function cancelRename() {
    skipBlurCommit.current = true;
    setRenamingKey(null);
    setRenameDraft("");
  }

  return {
    renamingKey,
    renameDraft,
    setRenameDraft,
    startRename,
    commitRename,
    cancelRename
  };
}
