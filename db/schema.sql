-- Agent 1 — Memory & Knowledge Layer
-- Recursive Creator Intelligence System
--
-- Frozen schema per Agent 1 spec section 5. Column names here are the
-- contract other agents' code (and this repo's Python) must match.
-- Apply with: psql "$SUPABASE_DB_URL" -f db/schema.sql
-- or paste into the Supabase SQL editor.

create extension if not exists vector;

create table if not exists runs (
  id bigint generated always as identity primary key,
  started_at timestamptz not null default now(),
  metrics jsonb
);

create table if not exists episodes (
  id bigint generated always as identity primary key,
  run_id bigint references runs(id),
  ts timestamptz not null default now(),
  kind text not null check (kind in
    ('observation','recommendation','outcome','feedback','research_finding','onboarding_finding')),
  payload jsonb not null,
  consolidated boolean not null default false,
  embedding vector(1024)
);

create table if not exists insights (
  id bigint generated always as identity primary key,
  statement text not null,
  category text,                 -- format | topic | timing | audience | style
  confidence real not null,
  status text not null check (status in
    ('hypothesis','validated','core','deprecated')),
  evidence_for int not null default 0,
  evidence_against int not null default 0,
  supporting_episode_ids bigint[] not null default '{}',
  volatility text not null default 'semi_stable',
  expires_at timestamptz,
  created_run bigint,
  last_updated_run bigint,
  embedding vector(1024)
);

create table if not exists nodes (
  id bigint generated always as identity primary key,
  type text not null,
  name text not null,
  attrs jsonb,
  unique (type, name)
);

create table if not exists edges (
  src bigint references nodes(id),
  dst bigint references nodes(id),
  relation text not null,
  weight real not null default 1.0,
  attrs jsonb,
  primary key (src, dst, relation)
);

create table if not exists insight_snapshots (
  run_id bigint references runs(id),
  taken_at timestamptz not null default now(),
  insights jsonb not null
);

create index if not exists episodes_embedding_idx on episodes
  using hnsw (embedding vector_cosine_ops);
create index if not exists insights_embedding_idx on insights
  using hnsw (embedding vector_cosine_ops);

create index if not exists episodes_consolidated_idx on episodes (consolidated) where not consolidated;
create index if not exists insights_status_idx on insights (status);
create index if not exists edges_src_idx on edges (src);
create index if not exists edges_dst_idx on edges (dst);

-- Enable Realtime for the live brain-viewer dashboard.
alter publication supabase_realtime add table insights;
alter publication supabase_realtime add table edges;

-- ---------------------------------------------------------------------
-- pgvector similarity RPCs (PostgREST can't order by <=> directly, so
-- these back the dedup step in consolidation and the relevant_insights
-- lookup in get_context).
-- ---------------------------------------------------------------------

create or replace function match_insights(
  query_embedding vector(1024),
  match_threshold real default 0.0,
  match_count int default 10,
  exclude_status text default 'deprecated'
)
returns table (
  id bigint,
  statement text,
  category text,
  confidence real,
  status text,
  volatility text,
  expires_at timestamptz,
  similarity real
)
language sql stable
as $$
  select
    insights.id,
    insights.statement,
    insights.category,
    insights.confidence,
    insights.status,
    insights.volatility,
    insights.expires_at,
    1 - (insights.embedding <=> query_embedding) as similarity
  from insights
  where insights.status <> exclude_status
    and insights.embedding is not null
    and 1 - (insights.embedding <=> query_embedding) > match_threshold
  order by insights.embedding <=> query_embedding
  limit match_count;
$$;

