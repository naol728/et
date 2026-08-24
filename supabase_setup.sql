-- =======================================================
-- ABYSSINIA MARKET BOT — SUPABASE DATABASE SETUP
-- =======================================================
-- Run this in your Supabase Dashboard -> SQL Editor -> Run

create table if not exists public.bot_store (
    key text primary key,
    data jsonb not null default '{}'::jsonb,
    updated_at timestamp with time zone default now()
);

-- Enable Row Level Security (RLS)
alter table public.bot_store enable row level security;

-- Drop existing policies if any
drop policy if exists "Allow full access to bot_store" on public.bot_store;

-- Create policy to allow full access with anon key
create policy "Allow full access to bot_store"
on public.bot_store
for all
to public, anon, authenticated
using (true)
with check (true);
