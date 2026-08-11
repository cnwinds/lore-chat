export type CooldownStatus = Record<
  string,
  {
    available?: boolean;
    disabled?: boolean;
    cooldown_remaining_sec?: number;
    last_error?: string | null;
  }
>;
