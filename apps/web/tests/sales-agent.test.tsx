import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { CampaignAgent, CompanyEvidence } from "../components/sales-agent";
import { request } from "../lib/api";

vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  request: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const props = {
  base: "/v1/workspaces/a",
  csrf: "synthetic-csrf",
  write: vi.fn(),
  revision: 0,
  onChange: vi.fn(),
  notify: vi.fn(),
};

const capabilities = {
  channels: {
    simulator: { available: true, reason: null, scope: "synthetic" },
    manual: { available: true, reason: null, scope: "manual" },
    official: { available: false, reason: "Keine API", scope: null },
  },
  limits: { connection_requests_per_day: 20, messages_per_day: 40 },
  usage: { connection_requests_last_24h: 1, messages_last_24h: 0 },
  rules: ["Jede Nachricht benötigt eine freigegebene aktuelle Entwurfsrevision."],
};

function row(overrides: object) {
  return {
    contact_id: "c1",
    name: "Anna Keller (synthetisch)",
    simulator_account: true,
    linkedin_url: null,
    suppressed: false,
    connection: "none",
    replied: false,
    completed_steps: [],
    next_step: 0,
    next_due_at: null,
    next_draft: null,
    stopped: false,
    actions: [],
    ...overrides,
  };
}

function mockAgent(rows: object[]) {
  vi.mocked(request).mockImplementation(async (path: string) => {
    if (path.endsWith("/linkedin/capabilities")) return capabilities as never;
    return {
      steps: [{ position: 0, delay_days: 0 }],
      contacts: rows,
      notice: "Planung",
    } as never;
  });
}

it("shows the official channel as unavailable and simulates a connection only for synthetic accounts", async () => {
  mockAgent([row({}), row({ contact_id: "c2", name: "Real Person", simulator_account: false })]);
  const write = vi.fn().mockResolvedValue({ id: "x", simulated: true, handoff: null });
  render(<CampaignAgent {...props} write={write} campaignId="camp" onRefresh={vi.fn()} />);
  await waitFor(() => expect(screen.getByText("Offizielle API: nicht verfügbar")).toBeTruthy());
  expect(screen.getByRole("button", { name: /Anfrage manuell übergeben/ })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Anfrage simulieren/ }));
  await waitFor(() => expect(write).toHaveBeenCalled());
  expect(write.mock.calls[0]).toEqual([
    "/linkedin/actions",
    {
      contact_id: "c1",
      campaign_id: "camp",
      channel: "simulator",
      action: "connection_request",
      draft_id: undefined,
    },
  ]);
});

it("requires an approved draft before a message can be handed off and shows the handoff package", async () => {
  mockAgent([
    row({ contact_id: "c3", name: "Unapproved", simulator_account: false, connection: "accepted", next_draft: { draft_id: "d0", state: "draft", approved: false } }),
    row({ contact_id: "c4", name: "Approved", simulator_account: false, connection: "accepted", next_draft: { draft_id: "d1", state: "approved", approved: true } }),
  ]);
  const write = vi.fn().mockResolvedValue({
    id: "a1",
    simulated: false,
    handoff: { profile_url: null, text: "Hallo Approved", steps: ["Selbst senden"], missing_profile_url: true },
  });
  render(<CampaignAgent {...props} write={write} campaignId="camp" onRefresh={vi.fn()} />);
  await waitFor(() => expect(screen.getByText("Entwurf für nächsten Schritt freigeben")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: /Nachricht übergeben/ }));
  await waitFor(() => expect(screen.getByRole("dialog", { name: "Manuelle LinkedIn-Übergabe" })).toBeTruthy());
  expect(write.mock.calls[0][1]).toMatchObject({ channel: "manual", action: "message", draft_id: "d1" });
  expect(screen.getByText("Hallo Approved")).toBeTruthy();
  expect(screen.getByText(/Keine Profil-URL gespeichert/)).toBeTruthy();
});

it("lists cited company facts with their source", async () => {
  vi.mocked(request).mockResolvedValue({
    items: [
      {
        id: "f1",
        field: "Kategorie",
        value: "Steuerberatung",
        source_url: "https://www.openstreetmap.org/node/1",
        source_kind: "openstreetmap",
        confidence: "community_reported",
        created_at: "2026-11-03T00:00:00Z",
      },
    ],
    research_jobs: [],
    notice: "Nur belegte Angaben.",
  } as never);
  render(<CompanyEvidence {...props} companyId="co" website={null} />);
  await waitFor(() => expect(screen.getByText("Steuerberatung")).toBeTruthy());
  expect(screen.getByText("OpenStreetMap")).toBeTruthy();
  expect(screen.getByRole("link", { name: /Quelle/ }).getAttribute("href")).toBe(
    "https://www.openstreetmap.org/node/1",
  );
});
