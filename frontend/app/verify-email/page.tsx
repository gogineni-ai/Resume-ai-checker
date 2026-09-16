'use client'
import {useEffect,useState} from 'react'
import {useRouter} from 'next/navigation'
import {me,requestOtp,verifyOtp,setStoredUser,logout} from '../../lib/api'
import Logo from '../../components/Logo'
export default function VerifyEmail(){
 const router=useRouter()
 const [user,setUser]=useState<any>(null),[code,setCode]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[cooldown,setCooldown]=useState(0)
 useEffect(()=>{me().then(u=>{setUser(u);setStoredUser(u);if(u.email_verified)router.replace('/dashboard')}).catch(()=>router.replace('/login'));const sent=sessionStorage.getItem('rv_otp_sent');sessionStorage.removeItem('rv_otp_sent');if(sent==='yes'){setMessage('Verification code sent to your email. It expires in 10 minutes.');setCooldown(60)}else if(sent==='no')setError('Your account was created, but the email could not be sent. Please request a code.');},[router])
 useEffect(()=>{if(!cooldown)return;const timer=setTimeout(()=>setCooldown(c=>c-1),1000);return()=>clearTimeout(timer)},[cooldown])
 async function send(){setBusy(true);setError('');setMessage('');try{await requestOtp('email');setCode('');setCooldown(60);setMessage('Verification code sent to your email. Use the latest code.')}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function verify(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const result=await verifyOtp('email',code);setStoredUser(result.user);setCode('');router.replace('/dashboard')}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 return <div className="authPage soft"><header className="publicHeader"><Logo/></header><main className="signupWrap"><section className="signupCard"><h1>Verify your email</h1><p>Complete this step to finish setting up your account.</p><p>{user?.email}</p><form onSubmit={verify}><label>6-digit verification code<div className="field"><input aria-label="6-digit verification code" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,'').slice(0,6))}/></div></label><button className="primary" disabled={busy||code.length!==6||!user}>{busy?'Please wait…':'Verify email'}</button></form><button className="outline" onClick={send} disabled={busy||cooldown>0||!user}>{cooldown?`Resend in ${cooldown}s`:'Send verification code'}</button>{message&&<p role="status">{message}</p>}{error&&<p className="formError" role="alert">{error}</p>}<button className="outline" onClick={()=>{logout();router.replace('/login')}}>Sign out</button></section></main></div>
}
