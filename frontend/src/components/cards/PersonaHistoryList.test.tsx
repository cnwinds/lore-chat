import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  listPersonaRevisions,
  rollbackPersonaRevision,
  type PersonaRevision,
} from "../../api";
import { PersonaHistoryList } from "./PersonaHistoryList";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listPersonaRevisions: vi.fn(),
    rollbackPersonaRevision: vi.fn(),
  };
});

const scope = "role:default";

const evolutionRevision: PersonaRevision = {
  id: "rev-1",
  source: "evolution",
  created_at: "2026-09-20T10:00:00",
  body: "新人设\n第二行",
  previous_body: "旧人设",
  rolled_back: false,
  can_rollback: true,
  reasons: [
    {
      op: "insert",
      reason: "依据卡片补充职责",
      before: "",
      after: "第二行",
      basis: ["卡片依据一", "卡片依据二"],
    },
  ],
  reverts: null,
};

const rollbackRevision: PersonaRevision = {
  id: "rev-2",
  source: "rollback",
  created_at: "2026-09-19T10:00:00",
  body: "旧人设",
  previous_body: "更旧",
  rolled_back: false,
  can_rollback: false,
  reasons: [],
  reverts: {
    id: "rev-old",
    source: "evolution",
    created_at: "2026-09-18T09:00:00",
  },
};

describe("PersonaHistoryList", () => {
  it("renders source labels, badges, reasons, and diff toggle", async () => {
    const user = userEvent.setup();
    vi.mocked(listPersonaRevisions).mockResolvedValueOnce({
      scope,
      revisions: [evolutionRevision, rollbackRevision],
    });

    render(<PersonaHistoryList scope={scope} />);

    expect(await screen.findByText("自动进化")).toBeInTheDocument();
    expect(screen.getByText("当前")).toBeInTheDocument();
    expect(screen.getByText("依据卡片补充职责")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "依据（2）" }),
    ).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "对照上一版" })[0]!);
    const removedLine = screen.getByText("旧人设").closest(".doc-diff-line");
    expect(removedLine).toHaveClass("doc-diff-line--removed");
    const addedLine = screen.getByText("第二行").closest(".doc-diff-line");
    expect(addedLine).toHaveClass("doc-diff-line--added");

    expect(screen.getByText(/回退了 .* 的自动进化/)).toBeInTheDocument();
  });

  it("calls rollback and onMutated on success", async () => {
    const user = userEvent.setup();
    const onMutated = vi.fn();
    vi.mocked(listPersonaRevisions)
      .mockResolvedValueOnce({ scope, revisions: [evolutionRevision] })
      .mockResolvedValueOnce({ scope, revisions: [] });
    vi.mocked(rollbackPersonaRevision).mockResolvedValueOnce({
      ok: true,
      body: "旧人设",
      revision: { ...evolutionRevision, can_rollback: false },
    });
    window.confirm = vi.fn(() => true);

    render(<PersonaHistoryList scope={scope} onMutated={onMutated} />);
    await screen.findByText("回退");
    await user.click(screen.getByRole("button", { name: "回退" }));

    await waitFor(() => {
      expect(rollbackPersonaRevision).toHaveBeenCalledWith(scope, "rev-1");
      expect(onMutated).toHaveBeenCalled();
    });
  });

  it("shows 409 detail below the row after rollback failure", async () => {
    const user = userEvent.setup();
    vi.mocked(listPersonaRevisions).mockResolvedValueOnce({
      scope,
      revisions: [evolutionRevision],
    });
    vi.mocked(rollbackPersonaRevision).mockRejectedValueOnce(
      new Error("这次改动之后，人设的同一处又改过，无法自动回退。请在角色设置里直接修改人设。"),
    );
    window.confirm = vi.fn(() => true);

    render(<PersonaHistoryList scope={scope} />);
    await user.click(await screen.findByRole("button", { name: "回退" }));

    expect(
      await screen.findByText(
        "这次改动之后，人设的同一处又改过，无法自动回退。请在角色设置里直接修改人设。",
      ),
    ).toBeInTheDocument();
  });
});
