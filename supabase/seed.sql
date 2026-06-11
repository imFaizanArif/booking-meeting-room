-- ============================================================================
-- Kodifly Meeting Room Booking System — Seed Data
-- Run after schema.sql and rls_policies.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Sample rooms
-- ---------------------------------------------------------------------------
insert into public.rooms (name, capacity, floor, description, image_url, color, is_active)
values
  (
    'Meeting Room Alpha',
    6,
    1,
    'Cozy 6-seater with a 55" display, whiteboard and video conferencing. Perfect for team syncs and 1:1s.',
    'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=1200&q=80',
    '#2563EB',
    true
  ),
  (
    'Meeting Room Beta',
    8,
    1,
    'Bright 8-seater with dual displays, acoustic panels and a Jabra speakerphone. Great for client calls.',
    'https://images.unsplash.com/photo-1497366811353-6870744d04b2?w=1200&q=80',
    '#14B8A6',
    true
  ),
  (
    'Conference Hall',
    20,
    2,
    'Our largest space — seats 20 around an executive table. Projector, ceiling mics and stage lighting.',
    'https://images.unsplash.com/photo-1517502884422-41eaead166d4?w=1200&q=80',
    '#7C3AED',
    true
  ),
  (
    'Brainstorm Room',
    10,
    2,
    'Creative space with floor-to-ceiling whiteboards, bean bags, sticky-note walls and a standing table.',
    'https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=1200&q=80',
    '#F59E0B',
    true
  )
on conflict (name) do nothing;

-- ---------------------------------------------------------------------------
-- Promote the first admin
-- Sign up via the app with admin@kodifly.com first, then run:
-- ---------------------------------------------------------------------------
-- update public.profiles set role = 'admin' where email = 'admin@kodifly.com';

-- ---------------------------------------------------------------------------
-- Sample bookings (uncomment after at least one user has signed up).
-- Replace the email below with a real signed-up user.
-- ---------------------------------------------------------------------------
-- with u as (select id from public.profiles where email = 'admin@kodifly.com' limit 1),
--      r as (select id from public.rooms where name = 'Meeting Room Alpha' limit 1)
-- insert into public.bookings (room_id, user_id, title, purpose, start_time, end_time, status)
-- select r.id, u.id,
--        'Sprint Planning',
--        'Plan the upcoming two-week sprint and assign tickets.',
--        date_trunc('hour', now() + interval '1 day'),
--        date_trunc('hour', now() + interval '1 day') + interval '1 hour',
--        'confirmed'
-- from u, r;
