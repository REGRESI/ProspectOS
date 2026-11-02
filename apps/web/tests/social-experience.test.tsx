import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  ContentCalendar,
  GenerationTools,
  PostInspector,
} from "../components/social-tools";
import type { Post } from "../lib/api";
import type { Write } from "../components/growth-modules";
import { request } from "../lib/api";
vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  request: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
beforeEach(() => {
  vi.mocked(request).mockImplementation(async (path) =>
    path.endsWith("/requirements")
      ? {
          configured: false,
          requirements: [
            "IMAGE_API_KEY",
            "IMAGE_MODEL",
            "IMAGE_MAX_COST_USD_CENTS",
          ],
        }
      : ({
          items: [
            {
              revision: 1,
              snapshot: { caption: "Original stored revision", asset_ids: [] },
              created_at: "2026-11-02T10:00:00Z",
            },
          ],
        } as never),
  );
});
const post: Post = {
  id: "post-a",
  caption: "A persisted scheduled article",
  alt_text: "",
  state: "scheduled",
  version: 1,
  approved_revision: 1,
  scheduled_at: new Date().toISOString(),
  created_at: "2026-11-02T10:00:00Z",
  asset_ids: [],
};
describe("Connected Social Studio controls", () => {
  it("opens the same persisted post from month, week and list without publishing", () => {
    const open = vi.fn();
    render(<ContentCalendar posts={[post]} onOpen={open} />);
    fireEvent.click(screen.getByRole("button", { name: /Beitrag öffnen:/ }));
    expect(open).toHaveBeenLastCalledWith(post);
    fireEvent.click(screen.getByRole("button", { name: "Woche" }));
    expect(document.querySelector(".calendar-week-grid")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Beitrag öffnen:/ }));
    expect(open).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Liste" }));
    expect(document.querySelector(".calendar-list")).not.toBeNull();
    expect(
      screen.getByRole("button", { name: /Beitrag öffnen:/ }),
    ).toBeTruthy();
  });
  it("surfaces missing real model credentials instead of inventing variants", async () => {
    const variants = vi.fn();
    const write = vi
      .fn()
      .mockRejectedValue(
        new Error("LLM_API_KEY und LLM_MODEL fehlen."),
      ) as Write;
    render(
      <GenerationTools
        base="/v1/workspaces/a"
        write={write}
        brands={[]}
        brandId=""
        topic="Existing topic"
        onVariants={variants}
        onAsset={vi.fn()}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Drei KI-Varianten anfordern" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("LLM_API_KEY"),
    );
    expect(variants).not.toHaveBeenCalled();
  });
  it("requires real image configuration and does not expose a fake generation result", async () => {
    const write = vi.fn() as Write;
    render(
      <GenerationTools
        base="/v1/workspaces/a"
        write={write}
        brands={[]}
        brandId=""
        topic=""
        onVariants={vi.fn()}
        onAsset={vi.fn()}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "KI-Bild" }));
    await waitFor(() =>
      expect(screen.getByText("Bildanbieter einrichten")).toBeTruthy(),
    );
    expect(
      (
        screen.getByRole("button", {
          name: "Echtes Bild anfordern",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      screen.queryByText("Nach Prüfung in Bibliothek übernehmen"),
    ).toBeNull();
    expect(write).not.toHaveBeenCalled();
  });
  it("edits the current revision through the real update contract and shows stored history", async () => {
    const write = vi
      .fn()
      .mockResolvedValue({
        ...post,
        caption: "Reviewed change",
        state: "needs_review",
        version: 2,
        approved_revision: null,
        scheduled_at: null,
      });
    const changed = vi.fn();
    render(
      <PostInspector
        base="/v1/workspaces/a"
        post={post}
        write={write as Write}
        onChange={changed}
        onClose={vi.fn()}
      />,
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Beitrag im Kalender bearbeiten" }),
      { target: { value: "Reviewed change" } },
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Änderung speichern und Freigabe zurücksetzen",
      }),
    );
    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    expect(write).toHaveBeenCalledWith(
      "/social/posts/post-a",
      {
        caption: "Reviewed change",
        alt_text: "",
        brand_id: null,
        asset_ids: [],
        version: 1,
      },
      "PATCH",
    );
    expect(screen.getByText("In Prüfung")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Redaktionellen Termin speichern" }),
    ).toBeNull();
    await waitFor(() =>
      expect(screen.getByText("Original stored revision")).toBeTruthy(),
    );
  });
});

it("keeps a real provider image out of the selected library until explicit review/save", async () => {
  const asset = {
    id: "asset-real",
    filename: "generated.jpg",
    url: "/v1/workspaces/a/assets/asset-real/content",
    content_type: "image/jpeg",
    size: 123,
    alt_text: "Provider output for review",
    created_at: "2026-11-02T10:00:00Z",
  };
  vi.mocked(request).mockImplementation(async (path) =>
    path.endsWith("/requirements")
      ? { configured: true, requirements: [], max_cost_minor: 25 }
      : ({
          id: "image-job",
          status: "succeeded",
          result: { asset, provider: "openai_images" },
        } as never),
  );
  const write = vi
    .fn()
    .mockImplementation(async (path: string) =>
      path.endsWith("/save")
        ? asset
        : { id: "image-job", status: "queued", result: {} },
    );
  const selected = vi.fn();
  render(
    <GenerationTools
      base="/v1/workspaces/a"
      write={write as Write}
      brands={[]}
      brandId=""
      topic=""
      onVariants={vi.fn()}
      onAsset={selected}
      onChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "KI-Bild" }));
  fireEvent.change(screen.getByLabelText("Bildidee"), {
    target: { value: "An original geometric illustration" },
  });
  fireEvent.change(
    screen.getByLabelText("Alternativtext für das erzeugte Motiv"),
    { target: { value: "Provider output for review" } },
  );
  fireEvent.click(
    screen.getByLabelText(
      "Ich prüfe die Nutzungsrechte und das Ergebnis vor der Verwendung.",
    ),
  );
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Echtes Bild anfordern",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Echtes Bild anfordern" }),
  );
  await waitFor(
    () =>
      expect(
        screen.getByText(
          "Das echte Anbieterbild ist privat gespeichert, aber noch nicht zur Bibliothek freigegeben.",
        ),
      ).toBeTruthy(),
    { timeout: 3500 },
  );
  expect(selected).not.toHaveBeenCalled();
  expect(
    (
      screen.getByRole("button", {
        name: "Nach Prüfung in Bibliothek übernehmen",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.click(
    screen.getByLabelText("Motiv, Nutzungsrechte und Alternativtext geprüft."),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: "Nach Prüfung in Bibliothek übernehmen",
    }),
  );
  await waitFor(() => expect(selected).toHaveBeenCalledWith(asset));
  expect(write).toHaveBeenLastCalledWith("/social/images/image-job/save", {
    rights_confirmed: true,
  });
});
