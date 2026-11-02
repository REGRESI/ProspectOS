import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { VoiceProfiles } from "../components/voice-profiles";
import { StudioMedia } from "../components/studio-media";
import { StudioRefinements } from "../components/studio-refinements";
import type { Asset, Write } from "../components/growth-modules";
import { request } from "../lib/api";
vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  request: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
beforeEach(() => {
  vi.mocked(request).mockResolvedValue({ items: [] });
});

it("creates a reusable voice with a labeled example and only closes on persisted success", async () => {
  const write = vi
    .fn()
    .mockRejectedValueOnce(new Error("Speichern fehlgeschlagen"))
    .mockResolvedValue({ id: "saved-voice" });
  const select = vi.fn();
  const change = vi.fn();
  render(
    <VoiceProfiles
      base="/v1/workspaces/a"
      write={write as Write}
      value=""
      onSelect={select}
      revision={0}
      onChange={change}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Schreibprofil erstellen" }),
  );
  fireEvent.change(screen.getByLabelText("Profilname"), {
    target: { value: "Meine Stimme" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Beispiel hinzufügen" }));
  fireEvent.change(screen.getByLabelText("Beispiel 1 · Bezeichnung"), {
    target: { value: "persönlich" },
  });
  fireEvent.change(screen.getByLabelText("Beispiel 1 · Beitrag"), {
    target: { value: "Mein eigener, konkreter Ausgangstext." },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Schreibprofil speichern" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain(
      "Speichern fehlgeschlagen",
    ),
  );
  expect(select).not.toHaveBeenCalled();
  expect(
    screen.getByText(/weder kopieren noch eng paraphrasieren/),
  ).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Schreibprofil speichern" }),
  );
  await waitFor(() => expect(select).toHaveBeenCalledWith("saved-voice"));
  expect(write).toHaveBeenLastCalledWith(
    "/social/voices",
    expect.objectContaining({
      name: "Meine Stimme",
      no_em_dash: true,
      examples: [
        { label: "persönlich", text: "Mein eigener, konkreter Ausgangstext." },
      ],
    }),
    "POST",
  );
  expect(screen.queryByRole("dialog")).toBeNull();
});

const assets: Asset[] = [
  {
    id: "team",
    filename: "team.jpg",
    title: "Team",
    tags: ["Zusammenarbeit"],
    url: "/team",
    alt_text: "Team illustration",
    size: 100,
    content_type: "image/jpeg",
    created_at: "2026-11-02T12:00:00Z",
  },
  {
    id: "office",
    filename: "office.jpg",
    title: "Büro",
    tags: ["Arbeitsplatz"],
    url: "/office",
    alt_text: "Office illustration",
    size: 100,
    content_type: "image/jpeg",
    created_at: "2026-11-02T12:00:00Z",
  },
];
it("searches thumbnails by tags and allows manual override of an automatic suggestion", async () => {
  const select = vi.fn();
  const write = vi
    .fn()
    .mockResolvedValue({ asset: assets[0], reason: "Metadaten-Abgleich" });
  render(
    <StudioMedia
      write={write as Write}
      assets={assets}
      mode="auto"
      onMode={vi.fn()}
      onAsset={select}
      onChange={vi.fn()}
      topic="Team"
      brandId="brand"
      voiceId="voice"
      selectedId=""
      loading={false}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Passendes Bild vorschlagen" }),
  );
  await waitFor(() => expect(select).toHaveBeenCalledWith(assets[0], "auto"));
  expect(screen.getByText("Metadaten-Abgleich")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Bilder durchsuchen"), {
    target: { value: "Arbeitsplatz" },
  });
  expect(
    screen.queryByRole("button", { name: "Bild wählen: Team" }),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Bild wählen: Büro" }));
  expect(select).toHaveBeenLastCalledWith(assets[1], "manual");
});
it("shows an empty/random gallery failure without selecting invented assets", async () => {
  const select = vi.fn();
  const write = vi
    .fn()
    .mockRejectedValue(new Error("Keine geprüften Bilder vorhanden"));
  render(
    <StudioMedia
      write={write as Write}
      assets={[]}
      mode="random"
      onMode={vi.fn()}
      onAsset={select}
      onChange={vi.fn()}
      topic=""
      brandId=""
      voiceId=""
      selectedId=""
      loading={false}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Zufälliges Bild wählen" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain(
      "Keine geprüften Bilder",
    ),
  );
  expect(select).not.toHaveBeenCalled();
});
it("refines the current text with its voice context and keeps it unchanged on provider failure", async () => {
  const select = vi.fn();
  const write = vi.fn().mockRejectedValue(new Error("LLM_API_KEY fehlt"));
  render(
    <StudioRefinements
      base="/v1/workspaces/a"
      write={write as Write}
      caption="Mein aktueller Entwurf"
      voiceId="voice"
      brandId="brand"
      onSelect={select}
      revision={0}
      onChange={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText("Überarbeitung"), {
    target: { value: "mehr wie ich" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Überarbeitung anfordern" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain("LLM_API_KEY"),
  );
  expect(write).toHaveBeenCalledWith(
    "/social/refine",
    expect.objectContaining({
      text: "Mein aktueller Entwurf",
      action: "mehr wie ich",
      voice_profile_id: "voice",
      brand_id: "brand",
    }),
  );
  expect(select).not.toHaveBeenCalled();
});
