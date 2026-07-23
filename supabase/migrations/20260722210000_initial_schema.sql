create table if not exists public.monitors (
  id varchar(36) primary key,
  owner_id varchar(36),
  name varchar(120) not null,
  url text not null,
  interval_minutes integer not null default 5 check (interval_minutes between 1 and 1440),
  timeout_seconds integer not null default 8 check (timeout_seconds between 1 and 30),
  expected_status integer not null default 200 check (expected_status between 100 and 599),
  latency_threshold_ms integer not null default 750 check (latency_threshold_ms between 50 and 30000),
  is_active boolean not null default true,
  status varchar(20) not null default 'unknown' check (status in ('unknown', 'operational', 'degraded', 'down', 'paused')),
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  last_latency_ms double precision,
  last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.check_results (
  id varchar(36) primary key,
  monitor_id varchar(36) not null references public.monitors(id) on delete cascade,
  status varchar(20) not null check (status in ('unknown', 'operational', 'degraded', 'down', 'paused')),
  status_code integer,
  latency_ms double precision,
  error text,
  checked_at timestamptz not null default now()
);

create index if not exists ix_check_results_monitor_checked
  on public.check_results (monitor_id, checked_at desc);

create table if not exists public.incidents (
  id varchar(36) primary key,
  monitor_id varchar(36) not null references public.monitors(id) on delete cascade,
  title varchar(180) not null,
  status varchar(20) not null default 'open' check (status in ('open', 'resolved')),
  cause text,
  started_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index if not exists ix_incidents_monitor_status
  on public.incidents (monitor_id, status);

create table if not exists public.website_audits (
  id varchar(36) primary key,
  owner_id varchar(36),
  url text not null,
  final_url text not null,
  hostname varchar(255) not null,
  status_code integer not null,
  latency_ms double precision not null,
  size_bytes integer not null,
  overall_score integer not null check (overall_score between 0 and 100),
  performance_score integer not null check (performance_score between 0 and 100),
  seo_score integer not null check (seo_score between 0 and 100),
  accessibility_score integer not null check (accessibility_score between 0 and 100),
  security_score integer not null check (security_score between 0 and 100),
  report jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists ix_website_audits_created
  on public.website_audits (created_at desc);

create index if not exists ix_monitors_owner_id on public.monitors (owner_id);
create index if not exists ix_website_audits_owner_id on public.website_audits (owner_id);

comment on table public.monitors is 'HTTP endpoints managed by PulseOps.';
comment on table public.check_results is 'Immutable history of uptime probes.';
comment on table public.incidents is 'Incidents opened and resolved by the failure engine.';
comment on table public.website_audits is 'Persisted technical audits of public websites.';

alter table public.monitors enable row level security;
alter table public.check_results enable row level security;
alter table public.incidents enable row level security;
alter table public.website_audits enable row level security;

-- The FastAPI service connects with a PostgreSQL connection string and does not
-- expose these tables through Supabase Data API. No anonymous RLS policies are
-- created intentionally.
