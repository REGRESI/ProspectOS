"use client";
import { useEffect, useState } from "react";
import { request } from "./api";
export function useData<T>(path: string, revision = 0) {
  const key = `${path}:${revision}`;
  const [result, setResult] = useState<{
    key: string;
    data: T | null;
    error: string;
  } | null>(null);
  useEffect(() => {
    let active = true;
    request<T>(path)
      .then((data) => {
        if (active) setResult({ key, data, error: "" });
      })
      .catch((e) => {
        if (active) setResult({ key, data: null, error: e.message });
      });
    return () => {
      active = false;
    };
  }, [path, revision, key]);
  // Keep showing the previous data for the same path while a refresh loads (no flicker).
  const samePath = !!result && result.key.slice(0, result.key.lastIndexOf(":")) === path;
  return {
    data: result?.key === key ? result.data : samePath ? result.data : null,
    error: result?.key === key ? result.error : "",
    loading: result?.key !== key,
  };
}
