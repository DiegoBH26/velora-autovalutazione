-- Require an approved user to verify their email and choose a final password
-- before application data becomes accessible.

alter table public.profiles
  add column if not exists onboarding_required boolean not null default false,
  add column if not exists email_verified_at timestamptz;

alter table public.access_requests
  add column if not exists invited_at timestamptz;

-- Existing authorized accounts predate the onboarding gate and remain usable.
update public.profiles
set email_verified_at = coalesce(email_verified_at, created_at)
where authorized = true
  and onboarding_required = false;

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
        and profiles.onboarding_required = false
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
        and profiles.onboarding_required = false
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
        and profiles.onboarding_required = false
    )
  )
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1
      from public.profiles
      where profiles.user_id = (select auth.uid())
        and profiles.authorized = true
        and profiles.onboarding_required = false
    )
  );
