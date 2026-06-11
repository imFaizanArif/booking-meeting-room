-- ============================================================================
-- Kodifly Meeting Room Booking System — Database Schema
-- Target: Supabase PostgreSQL
-- Run order: schema.sql -> rls_policies.sql -> seed.sql
-- ============================================================================

-- Extensions ------------------------------------------------------------------
create extension if not exists "pgcrypto";
create extension if not exists "btree_gist"; -- required for booking overlap exclusion

-- Enums -----------------------------------------------------------------------
do $$ begin
  create type public.user_role as enum ('employee', 'admin');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.booking_status as enum ('pending', 'confirmed', 'rejected', 'cancelled');
exception when duplicate_object then null; end $$;

-- ============================================================================
-- PROFILES
-- Mirrors auth.users; one row per employee.
-- ============================================================================
create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  name        text not null default '',
  email       text not null unique,
  department  text not null default '',
  designation text not null default '',
  avatar_url  text,
  role        public.user_role not null default 'employee',
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

create index if not exists idx_profiles_email on public.profiles (email);
create index if not exists idx_profiles_role  on public.profiles (role);

-- ============================================================================
-- ROOMS
-- ============================================================================
create table if not exists public.rooms (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  capacity    integer not null check (capacity > 0),
  floor       integer not null,
  description text not null default '',
  image_url   text,
  color       text not null default '#2563EB',
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

create index if not exists idx_rooms_is_active on public.rooms (is_active);

-- ============================================================================
-- BOOKINGS
-- ============================================================================
create table if not exists public.bookings (
  id         uuid primary key default gen_random_uuid(),
  room_id    uuid not null references public.rooms (id) on delete cascade,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  title      text not null check (char_length(title) between 3 and 120),
  purpose    text not null default '',
  start_time timestamptz not null,
  end_time   timestamptz not null,
  status     public.booking_status not null default 'confirmed',
  created_at timestamptz not null default now(),

  constraint bookings_time_valid check (end_time > start_time),

  -- Hard conflict prevention at the database level:
  -- no two active bookings of the same room may overlap in time.
  constraint bookings_no_overlap exclude using gist (
    room_id with =,
    tstzrange(start_time, end_time) with &&
  ) where (status in ('pending', 'confirmed'))
);

create index if not exists idx_bookings_room_id    on public.bookings (room_id);
create index if not exists idx_bookings_user_id    on public.bookings (user_id);
create index if not exists idx_bookings_start_time on public.bookings (start_time);
create index if not exists idx_bookings_status     on public.bookings (status);

-- ============================================================================
-- ATTENDEES
-- ============================================================================
create table if not exists public.attendees (
  id         uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings (id) on delete cascade,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),

  constraint attendees_unique unique (booking_id, user_id)
);

create index if not exists idx_attendees_booking_id on public.attendees (booking_id);
create index if not exists idx_attendees_user_id    on public.attendees (user_id);

-- ============================================================================
-- TRIGGER: auto-create a profile when a user signs up via Supabase Auth
-- ============================================================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, name, email, department, designation, avatar_url)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'name', split_part(new.email, '@', 1)),
    new.email,
    coalesce(new.raw_user_meta_data ->> 'department', ''),
    coalesce(new.raw_user_meta_data ->> 'designation', ''),
    new.raw_user_meta_data ->> 'avatar_url'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ============================================================================
-- HELPER: is the current authenticated user an admin?
-- (security definer so it can be used inside RLS policies without recursion)
-- ============================================================================
create or replace function public.is_admin()
returns boolean
language sql
security definer set search_path = public
stable
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin' and is_active = true
  );
$$;
