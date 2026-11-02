import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { LeadDatabase } from "../components/journey-workspaces";
import { ICPBuilder } from "../components/icp-builder";
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
it("sends validated lead filters as JSON and preserves the read-only contract", async () => {
  vi.mocked(request).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    limit: 25,
  } as never);
  render(<LeadDatabase {...props} />);
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "/v1/workspaces/a/leads/query",
      expect.objectContaining({ method: "POST", body: expect.any(String) }),
      "synthetic-csrf",
    ),
  );
  const call = vi
    .mocked(request)
    .mock.calls.find(([path]) => path.endsWith("/leads/query"));
  const body = JSON.parse(String(call?.[1]?.body));
  expect(body.sort).toBe("created");
  expect(body.limit).toBe(25);
  await waitFor(() =>
    expect(screen.getByText("Keine Kontakte für diese Filter")).toBeTruthy(),
  );
});
it("creates and updates a structured ICP without posting server metadata", async () => {
  vi.mocked(request).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    limit: 25,
  } as never);
  const write = vi
    .fn()
    .mockImplementation(async (_path, body) => ({
      ...body,
      id: "profile-a",
      version: 1,
      created_at: "2026-11-02T00:00:00Z",
    }));
  render(<ICPBuilder {...props} write={write} />);
  fireEvent.change(screen.getByLabelText("Profilname"), {
    target: { value: "Synthetic ICP" },
  });
  fireEvent.change(
    screen.getByLabelText("Regionen und Standorte", { selector: "input" }),
    { target: { value: "Berlin" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Regionen und Standorte hinzufügen" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "ICP-Profil speichern" }));
  await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
  expect(write.mock.calls[0][1].locations).toEqual(["Berlin"]);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Profil bearbeiten" }),
    ).toBeTruthy(),
  );
  fireEvent.click(screen.getByRole("button", { name: "ICP-Profil speichern" }));
  await waitFor(() => expect(write).toHaveBeenCalledTimes(2));
  expect(write.mock.calls[1][0]).toBe("/icp-profiles/profile-a");
  expect(write.mock.calls[1][1]).not.toHaveProperty("created_at");
  expect(write.mock.calls[1][1]).not.toHaveProperty("version");
});
