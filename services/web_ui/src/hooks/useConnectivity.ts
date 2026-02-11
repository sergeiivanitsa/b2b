import { useEffect, useState } from 'react'

function readOnlineState(): boolean {
  if (typeof navigator === 'undefined') {
    return true
  }
  return navigator.onLine
}

export function useConnectivity(): boolean {
  const [isOnline, setIsOnline] = useState<boolean>(() => readOnlineState())

  useEffect(() => {
    const markOnline = () => setIsOnline(true)
    const markOffline = () => setIsOnline(false)

    window.addEventListener('online', markOnline)
    window.addEventListener('offline', markOffline)

    return () => {
      window.removeEventListener('online', markOnline)
      window.removeEventListener('offline', markOffline)
    }
  }, [])

  return isOnline
}
