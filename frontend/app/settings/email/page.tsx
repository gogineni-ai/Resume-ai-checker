'use client'

import {useEffect,useState} from 'react'
import AppShell from '../../../components/AppShell'
import {gmailStatus,connectGmail} from '../../../lib/api'

export default function EmailSettings(){
  const [status,setStatus]=useState<any>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{gmailStatus().then(setStatus).catch(e=>setError(e.message))},[])
  async function connect(){
    setBusy(true);setError('')
    try{
      const result=await connectGmail()
      const url=new URL(result.url)
      if(url.origin!=='https://accounts.google.com')throw new Error('Invalid connection destination')
      window.location.assign(url.href)
    }catch(e:any){setError(e.message);setBusy(false)}
  }
  return <AppShell><section className="panel settingsCard">
    <h1>Verification email sender</h1>
    {status&&<>
      <p>Sender: {status.sender}</p>
      <p>{status.connected?'Gmail connected.':'Gmail is not connected.'} {status.active?'Gmail delivery is enabled.':'Gmail delivery is not enabled yet.'}</p>
      <p>Connect the sender account to send verification emails. Google will ask for permission to send email.</p>
      <button disabled={busy} onClick={connect}>{busy?'Opening Google…':status.connected?'Reconnect Gmail':'Connect Gmail'}</button>
    </>}
    {error&&<p role="alert">{error}</p>}
    {!status&&!error&&<p>Loading sender settings…</p>}
  </section></AppShell>
}
