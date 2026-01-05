import { createClient, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

// Check if Supabase is properly configured (not placeholder values)
const isValidUrl = (url: string | undefined): boolean => {
  if (!url) return false
  try {
    new URL(url)
    return url.startsWith('https://') && !url.includes('your-supabase')
  } catch {
    return false
  }
}

export const isSupabaseConfigured = isValidUrl(supabaseUrl) && !!supabaseAnonKey && !supabaseAnonKey.includes('your-supabase')

// Create client only if properly configured, otherwise create a mock
export const supabase: SupabaseClient = isSupabaseConfigured
  ? createClient(supabaseUrl!, supabaseAnonKey!)
  : createClient('https://placeholder.supabase.co', 'placeholder-key', {
      auth: { persistSession: false, autoRefreshToken: false },
    })

// User preferences type
export interface UserPreferences {
  id: string
  followed_states: string[]
  alert_frequency: 'daily' | 'weekly' | 'off'
  email_alerts: boolean
  created_at: string
  updated_at: string
}

// Helper to get or create user preferences
export async function getUserPreferences(userId: string): Promise<UserPreferences | null> {
  const { data, error } = await supabase
    .from('user_preferences')
    .select('*')
    .eq('id', userId)
    .single()

  if (error && error.code !== 'PGRST116') {
    console.error('Error fetching preferences:', error)
    return null
  }

  return data
}

export async function updateUserPreferences(
  userId: string,
  preferences: Partial<UserPreferences>
): Promise<UserPreferences | null> {
  const { data, error } = await supabase
    .from('user_preferences')
    .upsert({
      id: userId,
      ...preferences,
      updated_at: new Date().toISOString(),
    })
    .select()
    .single()

  if (error) {
    console.error('Error updating preferences:', error)
    return null
  }

  return data
}
