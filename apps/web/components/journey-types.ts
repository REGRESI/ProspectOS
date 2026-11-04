import type { Contact, Score } from "@/lib/api";
import type { ModuleProps } from "./growth-modules";
export type JourneyProps = ModuleProps & {
  onNavigate?: (path: string) => void;
  onImport?: () => void;
};
export type Completeness = {
  present: number;
  total: number;
  percent: number;
  missing: string[];
};
export type Lead = Contact & {
  company_id: string | null;
  tags: string[];
  owner_id: string | null;
  completeness: Completeness;
  provenance: { source: string; reviewed: boolean };
};
export type Company = {
  id: string;
  name: string;
  location: string;
  industry: string;
  source: string;
  website?: string | null;
  contact_count: number;
  deal_count: number;
  completeness?: Completeness;
  provenance?: Record<string, unknown>;
};
export type LeadFilters = {
  search: string;
  statuses: string[];
  sources: string[];
  company_id: string | null;
  location: string;
  job_title: string;
  tags: string[];
  owner_id: string | null;
  has_email: "any" | "present" | "missing";
  min_score: number;
  page: number;
  limit: number;
  sort: "name" | "created" | "score";
  direction: "asc" | "desc";
  icp_id?: string | null;
};
export const initialLeadFilters: LeadFilters = {
  search: "",
  statuses: [],
  sources: [],
  company_id: null,
  location: "",
  job_title: "",
  tags: [],
  owner_id: null,
  has_email: "any",
  min_score: 0,
  page: 1,
  limit: 25,
  sort: "created",
  direction: "desc",
};
export type SearchFilters = {
  country: string;
  city: string;
  region: string;
  radius_km: number | null;
  industries: string[];
  excluded_industries: string[];
  min_employees: number | null;
  max_employees: number | null;
  keywords: string[];
  job_titles: string[];
  seniority: string[];
  exclude_customers: boolean;
  max_results: number;
  provider: "synthetic" | "pdl" | "osm";
};
export const initialSearchFilters: SearchFilters = {
  country: "germany",
  city: "",
  region: "",
  radius_km: null,
  industries: [],
  excluded_industries: [],
  min_employees: null,
  max_employees: null,
  keywords: [],
  job_titles: [],
  seniority: [],
  exclude_customers: true,
  max_results: 5,
  provider: "synthetic",
};
export type SearchDefinition = {
  id: string;
  name: string;
  briefing: string;
  filters: SearchFilters;
  created_at: string;
};
export type Candidate = {
  key: string;
  entity_kind: "company" | "person";
  company: string;
  first_name?: string;
  last_name?: string;
  location: string;
  industry: string;
  job_title?: string;
  domain?: string | null;
  source: string;
  observed_at: string;
  confidence: string;
  score: Score & {
    not_applicable?: { name: string; max_points: number }[];
    notice?: string;
  };
  completeness: Completeness;
  imported: boolean;
  address?: string;
  website?: string | null;
  distance_km?: number | null;
  source_url?: string | null;
  attribution?: string | null;
  license?: string | null;
  company_id?: string | null;
  duplicate_of?: {
    company_id: string;
    name: string;
    reason: "domain" | "name_location";
    explanation: string;
  } | null;
};
export type DiscoveryProvider = {
  id: "osm" | "pdl" | "synthetic";
  label: string;
  available: boolean;
  reason: string | null;
  supports: string[];
  unsupported: string[];
  license: string;
  attribution?: string;
  cost: string;
};
export type Campaign = {
  id: string;
  name: string;
  goal: string;
  status: string;
  contacts: number;
  channel?: "linkedin_manual" | "email";
};
export type Draft = {
  id: string;
  contact_id: string;
  content: string;
  subject: string;
  revision: number;
  state: string;
  approved_revision: number | null;
  source?: string;
  contact?: Lead;
  campaign?: Campaign | null;
  blocked_reasons?: string[];
};
export const list = (value: FormDataEntryValue | null) =>
  String(value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
