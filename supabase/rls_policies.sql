-- ============================================================================
-- Kodifly Meeting Room Booking System — Row Level Security Policies
-- Run after schema.sql
-- ============================================================================

alter table public.profiles enable row level security;
alter table public.rooms    enable row level security;
alter table public.bookings enable row level security;
alter table public.attendees enable row level security;

-- ============================================================================
-- PROFILES
-- ============================================================================

-- Every authenticated employee can see colleagues (needed for attendee search).
drop policy if exists "profiles_select_authenticated" on public.profiles;
create policy "profiles_select_authenticated"
  on public.profiles for select
  to authenticated
  using (true);

-- Users may update their own profile (but not their role / active flag —
-- enforced by the column grant below).
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using (id = auth.uid())
  with check (id = auth.uid());

-- Admins may update anyone (role assignment, disabling users).
drop policy if exists "profiles_update_admin" on public.profiles;
create policy "profiles_update_admin"
  on public.profiles for update
  to authenticated
  using (public.is_admin())
  with check (public.is_admin());

-- Lock down privileged columns for non-admin self updates.
revoke update on public.profiles from authenticated;
grant  update (name, department, designation, avatar_url) on public.profiles to authenticated;
-- role / is_active changes go through the backend service-role client.

-- ============================================================================
-- ROOMS
-- ============================================================================

drop policy if exists "rooms_select_authenticated" on public.rooms;
create policy "rooms_select_authenticated"
  on public.rooms for select
  to authenticated
  using (true);

drop policy if exists "rooms_insert_admin" on public.rooms;
create policy "rooms_insert_admin"
  on public.rooms for insert
  to authenticated
  with check (public.is_admin());

drop policy if exists "rooms_update_admin" on public.rooms;
create policy "rooms_update_admin"
  on public.rooms for update
  to authenticated
  using (public.is_admin())
  with check (public.is_admin());

drop policy if exists "rooms_delete_admin" on public.rooms;
create policy "rooms_delete_admin"
  on public.rooms for delete
  to authenticated
  using (public.is_admin());

-- ============================================================================
-- BOOKINGS
-- ============================================================================

-- All employees can view bookings (required for the shared calendar +
-- conflict awareness).
drop policy if exists "bookings_select_authenticated" on public.bookings;
create policy "bookings_select_authenticated"
  on public.bookings for select
  to authenticated
  using (true);

-- Employees create bookings for themselves only.
drop policy if exists "bookings_insert_own" on public.bookings;
create policy "bookings_insert_own"
  on public.bookings for insert
  to authenticated
  with check (user_id = auth.uid());

-- Owner or admin can update (edit / cancel / approve / reject).
drop policy if exists "bookings_update_own_or_admin" on public.bookings;
create policy "bookings_update_own_or_admin"
  on public.bookings for update
  to authenticated
  using (user_id = auth.uid() or public.is_admin())
  with check (user_id = auth.uid() or public.is_admin());

-- Owner or admin can delete.
drop policy if exists "bookings_delete_own_or_admin" on public.bookings;
create policy "bookings_delete_own_or_admin"
  on public.bookings for delete
  to authenticated
  using (user_id = auth.uid() or public.is_admin());

-- ============================================================================
-- ATTENDEES
-- ============================================================================

drop policy if exists "attendees_select_authenticated" on public.attendees;
create policy "attendees_select_authenticated"
  on public.attendees for select
  to authenticated
  using (true);

-- Only the booking owner (or admin) manages the attendee list.
drop policy if exists "attendees_insert_owner_or_admin" on public.attendees;
create policy "attendees_insert_owner_or_admin"
  on public.attendees for insert
  to authenticated
  with check (
    exists (
      select 1 from public.bookings b
      where b.id = booking_id and (b.user_id = auth.uid() or public.is_admin())
    )
  );

drop policy if exists "attendees_delete_owner_or_admin" on public.attendees;
create policy "attendees_delete_owner_or_admin"
  on public.attendees for delete
  to authenticated
  using (
    exists (
      select 1 from public.bookings b
      where b.id = booking_id and (b.user_id = auth.uid() or public.is_admin())
    )
  );
