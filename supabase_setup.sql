create table if not exists public.readings (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  temperature real,
  humidity real,
  distance real,
  mq2 integer,
  mq135 integer,
  flags integer,
  status integer,
  relay integer,
  warmup integer
);

create index if not exists readings_ts_idx on public.readings (ts desc);

alter table public.readings enable row level security;
create policy "public read" on public.readings for select to anon using (true);
