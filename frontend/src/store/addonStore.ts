import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface AddonDef {
  id: string
  name: string
  description: string
  icon: string
}

export const ADDONS: AddonDef[] = [
  {
    id: 'equipment-inventory',
    name: 'Equipment Inventory',
    description: 'Manage all NVR devices — cameras, Raspberry Pis, displays — with one-click SSH terminal.',
    icon: 'Server',
  },
  {
    id: 'floor-plan',
    name: 'Floor Plan',
    description: 'Interactive 2D floor plans with drag & drop camera placement, real-time status and live view.',
    icon: 'Building2',
  },
]

interface AddonState {
  enabled: Record<string, boolean>
  enable: (id: string) => void
  disable: (id: string) => void
  isEnabled: (id: string) => boolean
}

export const useAddonStore = create<AddonState>()(
  persist(
    (set, get) => ({
      enabled: {},
      enable: (id) => set((s) => ({ enabled: { ...s.enabled, [id]: true } })),
      disable: (id) => set((s) => ({ enabled: { ...s.enabled, [id]: false } })),
      isEnabled: (id) => get().enabled[id] === true,
    }),
    { name: 'nvr-addons', storage: createJSONStorage(() => localStorage) }
  )
)
