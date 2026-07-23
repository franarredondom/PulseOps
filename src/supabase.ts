import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "https://kpfqzyejzcirlavewmqi.supabase.co";
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || "sb_publishable_JYksltCemRN_zuY8ASF1ug_i5p_wXPl";

export const supabase = createClient(supabaseUrl, supabasePublishableKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
