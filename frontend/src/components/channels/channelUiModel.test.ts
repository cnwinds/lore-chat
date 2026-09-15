import { describe, expect, it } from "vitest";
import type { ApiPersona } from "../../api/openApi";
import type { ChannelInstance } from "../../api/channelPlugins";
import {
  credentialChip,
  isExclusiveTo,
  personaOptionLabel,
  personaUsage,
  personasSelectableFor,
  revokeTabLabel,
  typeBadgeLabel,
} from "./channelUiModel";

const persona = (id: string, name: string): ApiPersona => ({
  id,
  name,
  system_prompt: "",
  created_at: "",
  updated_at: "",
});

const inst = (
  id: string,
  personaId: string,
  typeId = "script_api",
): ChannelInstance => ({
  id,
  type_id: typeId,
  name: id,
  enabled: true,
  status: "enabled",
  persona_id: personaId,
  created_at: "",
});

describe("channelUiModel", () => {
  it("treats a persona used by one instance as exclusive to that channel", () => {
    const usage = personaUsage([inst("a", "p1"), inst("b", "p2")]);
    expect(isExclusiveTo("p1", "a", usage)).toBe(true);
    expect(isExclusiveTo("p1", "b", usage)).toBe(false);
    expect(personaOptionLabel(persona("p1", "anti"), "a", usage)).toBe(
      "本通道专属 · anti",
    );
    expect(personaOptionLabel(persona("p1", "anti"), "b", usage)).toBe(
      "anti（共用）",
    );
  });

  it("hides another channel's exclusive persona from the picker", () => {
    const usage = personaUsage([inst("a", "p1"), inst("b", "p2")]);
    const options = personasSelectableFor(
      [persona("p1", "anti"), persona("p2", "客服"), persona("p3", "闲置")],
      "a",
      usage,
    );
    expect(options.map((item) => item.id)).toEqual(["p1", "p3"]);
  });

  it("labels script keys vs IM credentials on the chip", () => {
    expect(
      credentialChip({
        ...inst("a", "p1"),
        config: { key_prefix: "lc_live_abcd" },
      }),
    ).toEqual({
      kind: "token",
      text: "lc_live_abcd…",
      copyable: true,
    });
    expect(credentialChip(inst("b", "p1", "feishu"))).toEqual({
      kind: "secrets",
      text: "凭证已保存",
      copyable: true,
    });
    expect(
      credentialChip({
        ...inst("a", "p1"),
        enabled: false,
        status: "disabled",
        config: { key_prefix: "lc_live_abcd" },
      }),
    ).toEqual({ kind: "revoked", text: "", copyable: false });
    expect(revokeTabLabel("script_api")).toBe("吊销");
    expect(revokeTabLabel("feishu")).toBe("删除");
  });

  it("uses a short type badge next to the channel name", () => {
    expect(typeBadgeLabel("script_api")).toBe("脚本");
    expect(typeBadgeLabel("feishu")).toBe("飞书");
  });
});
