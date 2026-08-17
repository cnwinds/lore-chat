import { providerApiKeyUrl } from "./providerApiKeyUrls";

type Props = {
  /** 厂家预设 id；custom / 未知不展示链接 */
  providerId: string;
  /** 字段标题，默认 API Key */
  label?: string;
};

/** API Key 字段标题；有厂家时附带「获取 Key」外链。 */
export function ProviderApiKeyLabel({ providerId, label = "API Key" }: Props) {
  const url = providerApiKeyUrl(providerId);
  return (
    <span className="settings-field-label-row">
      <span>{label}</span>
      {url ? (
        <a
          className="settings-provider-key-link"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          title="在新页面打开厂家 Key 管理"
          onClick={(e) => e.stopPropagation()}
        >
          获取 Key
        </a>
      ) : null}
    </span>
  );
}
