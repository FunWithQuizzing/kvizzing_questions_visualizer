import { createClient } from '@supabase/supabase-js';

const SUPABASE_URL = 'https://agquxbdhrvqisjgljrhm.supabase.co';
const SUPABASE_KEY = 'sb_publishable_kTrC7PoqosRc7jjcCgp-Rg_4IZ--0ZF';

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
