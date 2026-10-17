import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim();
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();

const isConfigured = Boolean(
  supabaseUrl &&
  supabaseAnonKey &&
  supabaseUrl.startsWith('http')
);

if (!isConfigured) {
  console.warn(
    '[MedCode Frontend] Missing or empty VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. ' +
    'Please copy src/frontend/.env.example to src/frontend/.env and provide your Supabase credentials. ' +
    'Real-time Postgres listeners will remain dormant until configured.'
  );
}

// Fallback dummy channel to safely prevent crashes if Supabase env vars are not yet configured
const dummyChannel = {
  on: () => dummyChannel,
  subscribe: () => dummyChannel,
};

const dummyClient = {
  channel: () => dummyChannel,
  removeChannel: () => {},
};

export const isSupabaseConfigured = isConfigured;
export const supabase = isConfigured
  ? createClient(supabaseUrl, supabaseAnonKey)
  : dummyClient;

