"use client";

import { useId, useRef, useState, type DragEvent } from "react";
import s from "./file-drop.module.css";

const MAX_MB = 20;

function kb(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

/** PDF picker with drag-and-drop. Validates type and size before upload. */
export function FileDrop({
  file,
  onFile,
  label = "Invoice PDF",
  compact,
  disabled,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  label?: string;
  compact?: boolean;
  disabled?: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function accept(f: File | undefined) {
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setError("That isn't a PDF.");
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`PDFs up to ${MAX_MB} MB.`);
      return;
    }
    setError(null);
    onFile(f);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    if (!disabled) accept(e.dataTransfer.files[0]);
  }

  return (
    <div className={s.field}>
      <span className={s.label} id={`${id}-label`}>
        {label}
      </span>
      <div
        className={`${s.zone} ${compact ? s.compact : ""}`}
        data-over={over || undefined}
        data-filled={file ? true : undefined}
        data-invalid={error ? true : undefined}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <input
          ref={input}
          id={id}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          aria-labelledby={`${id}-label`}
          disabled={disabled}
          onChange={(e) => {
            accept(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        {file ? (
          <div className={s.chosen}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden className={s.icon}>
              <path d="M4 1.5h5.5L13 5v9.5H4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
              <path d="M9.5 1.5V5H13" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            <span className={s.name}>{file.name}</span>
            <span className={s.size}>{kb(file.size)}</span>
            <button
              type="button"
              className={s.link}
              onClick={() => onFile(null)}
              disabled={disabled}
            >
              Remove
            </button>
          </div>
        ) : (
          <label htmlFor={id} className={s.prompt}>
            <span>
              Drop a PDF here or <span className={s.browse}>browse</span>
            </span>
            <span className={s.hint}>Up to {MAX_MB} MB</span>
          </label>
        )}
      </div>
      {error && (
        <span className={s.error} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
