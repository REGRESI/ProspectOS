export type Workspace = {
  id: string;
  name: string;
  slug: string;
  role: string;
};
export type Session = {
  user: { id: string; name: string; email: string };
  csrf_token: string;
  workspaces: Workspace[];
};
export type Score = {
  value: number;
  factors: {
    name: string;
    points: number;
    max_points: number;
    reason: string;
  }[];
  missing_data: string[];
};
export type Contact = {
  id: string;
  first_name: string;
  last_name: string;
  company: string;
  job_title: string;
  location: string;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  status: string;
  source: string;
  version: number;
  score: Score;
};
export type Activity = {
  id: string;
  kind: string;
  description: string;
  created_at: string;
};
export type Dashboard = {
  contacts: number;
  companies: number;
  qualified: number;
  deals: number;
  pipeline_value: number;
  posts: number;
  activities: Activity[];
};
export type Deal = {
  id: string;
  title: string;
  contact_id?: string;
  amount: number;
  stage: string;
};
export type Post = {
  brand_id?: string | null;
  asset_ids?: string[];
  id: string;
  caption: string;
  alt_text: string;
  state: string;
  version: number;
  approved_revision: number | null;
  scheduled_at: string | null;
  created_at: string;
};
export type Icp = {
  name: string;
  locations: string[];
  roles: string[];
  industries: string[];
  weights: { location: number; role: number; industry: number };
};
export type Preview = {
  id: string;
  headers: string[];
  mapping: Record<string, string>;
  rows: {
    row: number;
    first_name: string;
    last_name: string;
    company: string;
    job_title: string;
    location: string;
    linkedin_url: string;
    errors: string[];
    duplicate: boolean;
  }[];
  total: number;
  valid: number;
  invalid: number;
  duplicates: number;
};
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  limit: number;
};
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
  csrf?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.message || body.detail;
    throw new ApiError(
      response.status,
      typeof detail === "string"
        ? detail
        : `Anfrage fehlgeschlagen (${response.status}). Bitte erneut versuchen.`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const number = (value: number) =>
  new Intl.NumberFormat("de-DE").format(value);
export const money = (value: number) =>
  new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value / 100);
export const dateTime = (value: string) =>
  new Intl.DateTimeFormat("de-DE", {
    timeZone: "Europe/Berlin",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
export const stageLabels: Record<string, string> = {
  new: "Neu",
  qualified: "Qualifiziert",
  contacted: "Kontaktiert",
  conversation: "Im Gespräch",
  proposal: "Angebot",
  won: "Gewonnen",
  lost: "Verloren",
};
export const postLabels: Record<string, string> = {
  draft: "Entwurf",
  needs_review: "In Prüfung",
  approved: "Freigegeben",
  scheduled: "Redaktionell geplant",
  published: "Veröffentlicht",
  cancelled: "Abgebrochen",
};
