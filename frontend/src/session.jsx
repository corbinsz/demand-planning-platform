import { createContext, useContext, useEffect, useState } from 'react'
import { getSession } from './services/api'

const SessionContext = createContext({ session: null, loading: true, refresh: () => {} })

export function SessionProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = () => {
    setLoading(true)
    return getSession()
      .then((response) => setSession(response.data))
      .catch(() => setSession(null))
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  return (
    <SessionContext.Provider value={{ session, loading, refresh }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  return useContext(SessionContext)
}
