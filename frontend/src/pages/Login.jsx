import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { login, register } from '../services/api'
import { useSession } from '../session'

export default function Login() {
  const [mode, setMode] = useState('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [workspaceName, setWorkspaceName] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const { refresh } = useSession()

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    try {
      const response = mode === 'signin'
        ? await login({ email, password })
        : await register({ email, password, workspace_name: workspaceName })
      sessionStorage.setItem('ii_token', response.data.token)
      await refresh()
      navigate('/today')
    } catch (err) {
      setError(err.response?.data?.detail || 'That didn’t work. Check the fields and try again.')
    }
  }

  return (
    <div className="landing">
      <h1>{mode === 'signin' ? 'Sign in' : 'Create a workspace'}</h1>
      <p className="lead">One workspace is one brand. The sample brand does not need an account.</p>
      <form className="form" onSubmit={submit}>
        {mode === 'register' && (
          <>
            <label htmlFor="brand">Brand name</label>
            <input id="brand" value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} required />
          </>
        )}
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={mode === 'register' ? 10 : 1} />
        {error && <p role="alert">{error}</p>}
        <button className="btn primary" type="submit">{mode === 'signin' ? 'Sign in' : 'Create workspace'}</button>
      </form>
      <p style={{ marginTop: 16 }}>
        <button type="button" className="explain-btn" onClick={() => setMode(mode === 'signin' ? 'register' : 'signin')}>
          {mode === 'signin' ? 'Need a workspace?' : 'Already have an account?'}
        </button>
      </p>
      <p><Link to="/today">Continue with the sample brand</Link> · <Link to="/">Back</Link></p>
    </div>
  )
}
