import React from "react";
import { afterEach, describe, it, expect, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import WorkspaceApp from "../components/workspace-app";
vi.mock("next/navigation", () => ({
  usePathname: () => "/overview",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
function response(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}
describe("Authentication mode is a server decision", () => {
  it("never prefills demo credentials or uses demo login when production identity is enabled", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.endsWith("/auth/config"))
        return response(200, { mode: "supabase", demo_enabled: false });
      if (url.endsWith("/me"))
        return response(401, { message: "Nicht angemeldet." });
      if (url.endsWith("/auth/login"))
        return response(200, {
          user: { id: "user", name: "Kunde", email: "kunde@example.com" },
          csrf_token: "test-csrf",
          workspaces: [],
        });
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<WorkspaceApp />);
    const button = await screen.findByRole("button", { name: "Anmelden" });
    const email = screen.getByLabelText("E-Mail-Adresse") as HTMLInputElement;
    const password = screen.getByLabelText("Passwort") as HTMLInputElement;
    expect(email.value).toBe("");
    expect(password.value).toBe("");
    expect(
      screen.queryByRole("button", { name: "Demo-Workspace öffnen" }),
    ).toBeNull();
    fireEvent.change(email, { target: { value: "kunde@example.com" } });
    fireEvent.change(password, { target: { value: "example-not-a-secret" } });
    fireEvent.click(button);
    await waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) => url.endsWith("/auth/login")),
      ).toBe(true),
    );
    expect(fetcher.mock.calls.some(([url]) => url.endsWith("/auth/demo"))).toBe(
      false,
    );
  });
  it("leaves authentication disabled when the server configuration cannot be read", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/auth/config")
          ? response(503, { message: "Anmeldedienst nicht erreichbar." })
          : response(401, {}),
      ),
    );
    render(<WorkspaceApp />);
    const button = await screen.findByRole("button", { name: "Anmelden" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Anmeldedienst nicht erreichbar.",
    );
    expect((screen.getByLabelText("Passwort") as HTMLInputElement).value).toBe(
      "",
    );
  });
  it("offers clearly labelled development login only when the server explicitly allows it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/auth/config")
          ? response(200, { mode: "demo", demo_enabled: true })
          : response(401, {}),
      ),
    );
    render(<WorkspaceApp />);
    await screen.findByRole("button", { name: "Demo-Workspace öffnen" });
    expect(
      (screen.getByLabelText("E-Mail-Adresse") as HTMLInputElement).value,
    ).toBe("demo@prospectos.local");
    expect(screen.getByText("Transparent im Demo-Modus")).toBeTruthy();
  });
});
