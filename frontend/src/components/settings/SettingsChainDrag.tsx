import {
  useCallback,
  useState,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import { moveItem } from "./chainReorder";

type Identified = { id: string };

export function useSettingsChainDrag<T extends Identified>(
  items: T[],
  onChange: (next: T[]) => void,
  disabled = false,
) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  const moveByOffset = useCallback(
    (index: number, dir: -1 | 1) => {
      if (disabled) return;
      const next = moveItem(items, index, index + dir);
      if (next !== items) onChange(next);
    },
    [disabled, items, onChange],
  );

  function articleProps(id: string, index: number) {
    const dragging = dragId === id;
    const over = overIndex === index && dragId != null && dragId !== id;
    return {
      extraClass: [
        dragging ? "settings-model-candidate--dragging" : "",
        over ? "settings-model-candidate--drag-over" : "",
      ]
        .filter(Boolean)
        .join(" "),
      onDragOver: (e: DragEvent<HTMLElement>) => {
        if (disabled || !dragId || dragId === id) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOverIndex(index);
      },
      onDrop: (e: DragEvent<HTMLElement>) => {
        e.preventDefault();
        if (disabled || !dragId) return;
        const from = items.findIndex((x) => x.id === dragId);
        const next = moveItem(items, from, index);
        if (next !== items) onChange(next);
        setDragId(null);
        setOverIndex(null);
      },
    };
  }

  function gripProps(id: string, index: number) {
    return {
      disabled,
      onDragStart: (e: DragEvent<HTMLButtonElement>) => {
        if (disabled) {
          e.preventDefault();
          return;
        }
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", id);
        setDragId(id);
      },
      onDragEnd: () => {
        setDragId(null);
        setOverIndex(null);
      },
      onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => {
        if (e.key === "ArrowUp") {
          e.preventDefault();
          moveByOffset(index, -1);
        } else if (e.key === "ArrowDown") {
          e.preventDefault();
          moveByOffset(index, 1);
        }
      },
    };
  }

  return { articleProps, gripProps };
}

function GripDots() {
  return (
    <svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor" aria-hidden>
      <circle cx="2.5" cy="2.5" r="1.3" />
      <circle cx="7.5" cy="2.5" r="1.3" />
      <circle cx="2.5" cy="7" r="1.3" />
      <circle cx="7.5" cy="7" r="1.3" />
      <circle cx="2.5" cy="11.5" r="1.3" />
      <circle cx="7.5" cy="11.5" r="1.3" />
    </svg>
  );
}

type GripProps = {
  disabled?: boolean;
  onDragStart: (e: DragEvent<HTMLButtonElement>) => void;
  onDragEnd: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => void;
};

/** 左侧六点手柄：拖动改顺序；方向键也可微调。 */
export function SettingsChainGrip({
  disabled,
  onDragStart,
  onDragEnd,
  onKeyDown,
}: GripProps) {
  return (
    <button
      type="button"
      className="settings-chain-grip"
      draggable={!disabled}
      disabled={disabled}
      aria-label="拖动调整顺序"
      title="拖动调整顺序"
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onKeyDown={onKeyDown}
    >
      <GripDots />
    </button>
  );
}
