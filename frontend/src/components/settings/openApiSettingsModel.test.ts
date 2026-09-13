import { describe, expect, it } from "vitest";
import {
  EMPTY_CREATE_DRAFT,
  buildCreateKeyRequest,
  canSubmitCreateKey,
  chatCurlExample,
  formatOpenApiWhen,
} from "./openApiSettingsModel";

describe("canSubmitCreateKey", () => {
  it("needs a name for the default voice", () => {
    expect(canSubmitCreateKey(EMPTY_CREATE_DRAFT)).toBe(false);
    expect(canSubmitCreateKey({ ...EMPTY_CREATE_DRAFT, name: "周报" })).toBe(
      true,
    );
  });

  it("needs a persona when reusing one", () => {
    expect(
      canSubmitCreateKey({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "existing",
      }),
    ).toBe(false);
    expect(
      canSubmitCreateKey({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "existing",
        personaId: "p1",
      }),
    ).toBe(true);
  });

  it("needs a persona name when creating one", () => {
    expect(
      canSubmitCreateKey({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "new",
      }),
    ).toBe(false);
    expect(
      canSubmitCreateKey({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "new",
        personaName: "周报助手",
      }),
    ).toBe(true);
  });

  it("needs a role when copying", () => {
    expect(
      canSubmitCreateKey({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "copy",
      }),
    ).toBe(false);
    expect(
      canSubmitCreateKey({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "copy",
        copyRoleId: "default",
      }),
    ).toBe(true);
  });
});

describe("buildCreateKeyRequest", () => {
  it("sends only the key name for the default path", () => {
    expect(
      buildCreateKeyRequest({ ...EMPTY_CREATE_DRAFT, name: " 周报脚本 " }),
    ).toEqual({ name: "周报脚本" });
  });

  it("attaches an existing persona", () => {
    expect(
      buildCreateKeyRequest({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "existing",
        personaId: "p1",
      }),
    ).toEqual({ name: "脚本", persona_id: "p1" });
  });

  it("creates a persona inline", () => {
    expect(
      buildCreateKeyRequest({
        ...EMPTY_CREATE_DRAFT,
        name: "脚本",
        voice: "new",
        personaName: "周报助手",
        personaPrompt: "写周报",
      }),
    ).toEqual({
      name: "脚本",
      persona_name: "周报助手",
      persona_prompt: "写周报",
    });
  });
});

describe("chatCurlExample", () => {
  it("embeds the token in a copy-paste curl", () => {
    const sample = chatCurlExample("lc_live_secret");
    expect(sample).toContain("POST \"$LORECHAT_URL/api/v1/chat\"");
    expect(sample).toContain("Authorization: Bearer lc_live_secret");
    expect(sample).toContain("你好");
  });
});

describe("formatOpenApiWhen", () => {
  it("falls back when unused", () => {
    expect(formatOpenApiWhen(null)).toBe("尚未调用");
    expect(formatOpenApiWhen(undefined)).toBe("尚未调用");
  });
});
