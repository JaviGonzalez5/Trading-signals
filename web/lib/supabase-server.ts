import { createClient } from "@supabase/supabase-js";

// Server-only: SUPABASE_KEY es la service_role key. NUNCA usar NEXT_PUBLIC_
// para esto — expondría la clave al navegador. Esta función solo se llama
// desde Server Components / route handlers, nunca desde el cliente.
export function getServerSupabase() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_KEY;
  if (!url || !key) {
    throw new Error(
      "Faltan SUPABASE_URL/SUPABASE_KEY — configúralas como variables de entorno en Vercel."
    );
  }
  return createClient(url, key, { auth: { persistSession: false } });
}
