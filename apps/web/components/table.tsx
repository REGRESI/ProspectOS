"use client";
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Search } from "lucide-react";

/* Shared list table: search, sort by column header, simple select filters. */

export type SortDir = "asc" | "desc";

export function useTable<T>(
  items: T[],
  {
    search,
    initialSort,
    initialDir = "asc",
  }: {
    search: (item: T) => string;
    initialSort?: string;
    initialDir?: SortDir;
  },
  accessors: Record<string, (item: T) => string | number>,
) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<string | undefined>(initialSort);
  const [dir, setDir] = useState<SortDir>(initialDir);
  const rows = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("de");
    const filtered = q ? items.filter((i) => search(i).toLocaleLowerCase("de").includes(q)) : items;
    if (!sort || !accessors[sort]) return filtered;
    const get = accessors[sort];
    return [...filtered].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      const r =
        typeof x === "number" && typeof y === "number"
          ? x - y
          : String(x).localeCompare(String(y), "de", { sensitivity: "base" });
      return dir === "asc" ? r : -r;
    });
    // accessors/search are stable per render site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, query, sort, dir]);
  function toggle(key: string, defaultDir: SortDir = "asc") {
    if (sort === key) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setDir(defaultDir);
    }
  }
  return { rows, query, setQuery, sort, dir, toggle };
}

export function SortHeader({
  label,
  column,
  table,
  defaultDir = "asc",
  className = "",
}: {
  label: string;
  column: string;
  table: { sort?: string; dir: SortDir; toggle: (k: string, d?: SortDir) => void };
  defaultDir?: SortDir;
  className?: string;
}) {
  const active = table.sort === column;
  return (
    <th
      className={`sortable ${className}`}
      aria-sort={active ? (table.dir === "asc" ? "ascending" : "descending") : "none"}
      onClick={() => table.toggle(column, defaultDir)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          table.toggle(column, defaultDir);
        }
      }}
      tabIndex={0}
      scope="col"
    >
      {label}
      {active && (table.dir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
    </th>
  );
}

export function SearchInput({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  placeholder?: string;
}) {
  return (
    <span className="search">
      <Search size={14} />
      <input
        type="search"
        aria-label={label}
        placeholder={placeholder || label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </span>
  );
}

export function SkeletonTable({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="table-wrap" aria-busy="true" aria-label="Lädt">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i}>
          {Array.from({ length: cols }, (_, j) => (
            <span
              className="skeleton"
              key={j}
              style={{ width: j === 0 ? 180 : 90, marginLeft: j === cols - 1 ? "auto" : undefined }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
