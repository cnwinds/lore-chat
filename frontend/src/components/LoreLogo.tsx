type LoreLogoProps = {
  className?: string;
  title?: string;
};

/** Lore Chat 品牌标记：展开的知识册页与对话弧线，currentColor 随主题着色。 */
export function LoreLogo({ className, title = "Lore Chat" }: LoreLogoProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      {/* soft plate */}
      <rect
        x="4"
        y="4"
        width="56"
        height="56"
        rx="18"
        fill="currentColor"
        fillOpacity="0.09"
      />
      {/* open lore book */}
      <path
        d="M32 20c-5.2-3.2-12.4-4.2-16.5-4.2-.9 0-1.5.6-1.5 1.4V39c0 .7.5 1.3 1.2 1.4 4.3.7 10.8 2 16.8 5.2 6-3.2 12.5-4.5 16.8-5.2.7-.1 1.2-.7 1.2-1.4V17.2c0-.8-.6-1.4-1.5-1.4C44.4 15.8 37.2 16.8 32 20Z"
        fill="currentColor"
        fillOpacity="0.14"
      />
      <path
        d="M32 20c-5.2-3.2-12.4-4.2-16.5-4.2-.9 0-1.5.6-1.5 1.4V39c0 .7.5 1.3 1.2 1.4 4.3.7 10.8 2 16.8 5.2M32 20c5.2-3.2 12.4-4.2 16.5-4.2.9 0 1.5.6 1.5 1.4V39c0 .7-.5 1.3-1.2 1.4-4.3.7-10.8 2-16.8 5.2"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M32 20v25.6"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      {/* page grain — organized notes */}
      <path
        d="M21.5 24.5c2.6-.2 5.2.1 7.5 1.1M21.5 29.2c2.4-.2 4.8.1 7 1M21.5 33.8c2-.1 4 .1 5.8.7"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeOpacity="0.55"
      />
      <path
        d="M42.5 24.5c-2.6-.2-5.2.1-7.5 1.1M42.5 29.2c-2.4-.2-4.8.1-7 1"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeOpacity="0.55"
      />
      {/* chat arc / retrieval spark */}
      <path
        d="M46.5 45.5c2.8 1.2 4.8 3.2 5.5 5.8"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeOpacity="0.75"
      />
      <circle cx="53.2" cy="53.2" r="2.6" fill="currentColor" />
    </svg>
  );
}
