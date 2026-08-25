"use client";
import { useEffect, useRef, type RefObject } from "react";
import type { LucideIcon } from "lucide-react";

/** Close whatever is open when the user presses outside `ref`. */
export function useClickOutside<T extends HTMLElement>(
  onClose: () => void,
  active: boolean,
): RefObject<T | null> {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!active) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [active, onClose]);
  return ref;
}

export interface DropdownItem {
  icon: LucideIcon;
  label: string;
  danger?: boolean;
  dividerBefore?: boolean;
  /** 悬停提示（如上传入口注明支持的格式） */
  title?: string;
  onClick: () => void;
}

/** Absolutely-positioned menu panel. Render inside a `relative` wrapper. */
export function Dropdown({ items, onClose }: { items: DropdownItem[]; onClose: () => void }) {
  return (
    <div className="absolute right-0 top-6 z-50 w-44 rounded-lg border border-border bg-surface shadow-lg p-1">
      {items.map((item, i) => (
        <div key={i}>
          {item.dividerBefore && <div className="border-t border-border-light my-0.5" />}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onClose();
              item.onClick();
            }}
            title={item.title}
            className={`flex items-center gap-2 w-full rounded-md px-2 py-1.5 text-xs transition-colors ${
              item.danger ? "text-danger hover:bg-danger/10" : "text-fg-secondary hover:bg-surface-hover"
            }`}
          >
            <item.icon size={12} /> {item.label}
          </button>
        </div>
      ))}
    </div>
  );
}
