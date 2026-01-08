'use client'

// This component is deprecated - watchlist and suggestions features are not yet implemented in the new API

interface QuickAddSectionProps {
  watchedDocketIds: string[]
  onDocketAdded: () => void
}

export function QuickAddSection({ watchedDocketIds, onDocketAdded }: QuickAddSectionProps) {
  // Watchlist and suggestions features are not yet available
  return null
}
