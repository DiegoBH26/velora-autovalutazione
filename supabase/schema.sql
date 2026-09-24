-- Velora Autovalutazione Online
-- Schema applicativo. Le richieste pubbliche passano esclusivamente dalle Edge Functions.

create extension if not exists pgcrypto;

create table if not exists public.access_requests (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  full_name text not null,
  phone text,
  preferred_channel text not null default 'email',
  status text not null default 'pending',
  approval_token_hash text not null unique,
  approval_token_expires_at timestamptz not null default (now() + interval '7 days'),
  approval_used_at timestamptz,
  registration_code_hash text,
  registration_code_expires_at timestamptz,
  code_attempts smallint not null default 0,
  request_ip_hash text,
  admin_email_id text,
  user_email_id text,
  notification_error text,
  user_id uuid references auth.users(id) on delete set null,
  requested_at timestamptz not null default now(),
  approved_at timestamptz,
  registered_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint access_requests_email_format check (email = lower(email) and length(email) <= 254),
  constraint access_requests_name_length check (char_length(full_name) between 2 and 100),
  constraint access_requests_channel_check check (preferred_channel in ('email', 'phone')),
  constraint access_requests_status_check check (status in ('pending', 'approved', 'registered', 'rejected', 'expired')),
  constraint access_requests_attempts_check check (code_attempts between 0 and 10)
);

create unique index if not exists access_requests_one_active_email_idx
  on public.access_requests (lower(email))
  where status in ('pending', 'approved');

create index if not exists access_requests_requested_at_idx
  on public.access_requests (requested_at desc);

create index if not exists access_requests_user_id_idx
  on public.access_requests (user_id)
  where user_id is not null;

create index if not exists access_requests_ip_rate_idx
  on public.access_requests (request_ip_hash, requested_at desc)
  where request_ip_hash is not null;

create table if not exists public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text not null,
  authorized boolean not null default false,
  authorized_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profiles_email_format check (email = lower(email) and length(email) <= 254),
  constraint profiles_name_length check (char_length(full_name) between 2 and 100)
);

create unique index if not exists profiles_email_unique_idx
  on public.profiles (lower(email));

create table if not exists public.assessment_drafts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  constraint assessment_drafts_payload_object check (jsonb_typeof(payload) = 'object')
);

alter table public.access_requests enable row level security;
alter table public.profiles enable row level security;
alter table public.assessment_drafts enable row level security;

revoke all on table public.access_requests from anon, authenticated;
revoke all on table public.profiles from anon;
revoke all on table public.profiles from authenticated;
revoke all on table public.assessment_drafts from anon;
revoke all on table public.assessment_drafts from authenticated;

grant select on table public.profiles to authenticated;
grant select, insert, update on table public.assessment_drafts to authenticated;

drop policy if exists "access_requests_no_direct_access" on public.access_requests;
create policy "access_requests_no_direct_access"
  on public.access_requests
  for all
  to anon, authenticated
  using (false)
  with check (false);

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
  on public.profiles
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "authorized_users_select_own_draft" on public.assessment_drafts;
create policy "authorized_users_select_own_draft"
  on public.assessment_drafts
  for select
  to authenticated
  using (
    (select auth.uid()) = user_id
    and exists (
      select 1
      from public.profiles
      where profiles.user_id = (select auth.uid())
        and profiles.authorized = true
    )
  );

drop policy if exists "authorized_users_insert_own_draft" on public.assessment_drafts;
create policy "authorized_users_insert_own_draft"
  on public.assessment_drafts
  for insert
  to authenticated
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1
      from public.profiles
      where profiles.user_id = (select auth.uid())
        and profiles.authorized = true
    )
  );

drop policy if exists "authorized_users_update_own_draft" on public.assessment_drafts;
create policy "authorized_users_update_own_draft"
  on public.assessment_drafts
  for update
  to authenticated
  using (
    (select auth.uid()) = user_id
    and exists (
      select 1
      from public.profiles
      where profiles.user_id = (select auth.uid())
        and profiles.authorized = true
    )
  )
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1
      from public.profiles
      where profiles.user_id = (select auth.uid())
        and profiles.authorized = true
    )
  );
