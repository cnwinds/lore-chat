export type Role = {
  id: string;
  name: string;
  avatar?: string | null;
  system_prompt?: string | null;
  created_at: string;
  updated_at: string;
};

export type RoleSchedule = {
  id: string;
  role_id: string;
  cron: string;
  prompt: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type CreateRoleBody = {
  name: string;
  avatar?: string | null;
  system_prompt?: string | null;
};

export type UpdateRoleBody = Partial<CreateRoleBody>;
