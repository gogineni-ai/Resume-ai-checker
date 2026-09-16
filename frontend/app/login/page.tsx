'use client'
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import Logo from '../../components/Logo';
import {API,login,saveSession} from '../../lib/api'

export default function Login(){
  const r=useRouter();
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[err,setErr]=useState(''),[busy,setBusy]=useState(false)

  async function submit(e:any){
    e.preventDefault();
    setBusy(true);setErr('');
    try{const d=await login({email,password});saveSession(d);r.push('/dashboard')}
    catch(x:any){setErr(x.message)}
    finally{setBusy(false)}
  }

  async function handleSocialLogin(provider:string){
    setBusy(true);setErr('');
    try{
      const res=await fetch(`${API}/api/auth/social/${provider.toLowerCase()}/start`);
      const data=await res.json();
      if(!res.ok) throw new Error(data.detail || `${provider} sign-in is unavailable`);
      window.location.href=data.auth_url;
    }catch(x:any){
      setErr(x.message);setBusy(false)
    }
  }

  useEffect(()=>{
    const params=new URLSearchParams(window.location.search);
    const token=params.get('token');
    const name=params.get('name');
    const emailParam=params.get('email');
    if(params.get('auth_success')==='1' && token){
      saveSession({access_token:token,user:{name:name||'OAuth User',email:emailParam||''}});
      window.history.replaceState({},'', '/login');
      r.push('/dashboard');
    }
  },[r])

  return <div className="authPage"><header className="publicHeader"><Logo/><nav><Link href="#features">Features</Link><Link href="#">About</Link><Link href="/login">Login</Link><Link className="primarySmall" href="/signup">Sign Up</Link></nav></header><div className="authSplit"><section className="authHero"><div className="glow one"/><div className="glow two"/><div className="authCopy"><span className="kicker">AI career intelligence</span><h1>Get Hired<br/>With Confidence</h1><p>Analyze, verify, compare, succeed. Validate resume technologies against real job-market evidence and understand exactly how well you match.</p><div className="featureLine"><i>▣</i><span><b>AI Resume Analysis</b><small>Understand skills, gaps and relevance</small></span></div><div className="featureLine"><i>⌁</i><span><b>Job Market Verification</b><small>Compare claims with job descriptions</small></span></div><div className="featureLine"><i>◫</i><span><b>Historical Company Data</b><small>See technology evidence over time</small></span></div></div></section><section className="authFormSide"><form className="authCard" onSubmit={submit}><h2>Welcome Back</h2><p>Login to your account</p><label>Email address<div className="field"><span>✉</span><input type="email" required value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></div></label><label>Password<div className="field"><span>▣</span><input type="password" required value={password} onChange={e=>setPassword(e.target.value)} placeholder="Your password"/></div></label>{err&&<div className="formError">{err}</div>}<div className="formRow"><label className="check"><input type="checkbox"/> Remember me</label><a href="#">Forgot password?</a></div><button className="primary" disabled={busy}>{busy?'Signing in…':'Login'}</button><div className="or"><span/>or continue with<span/></div><button type="button" className="social" onClick={()=>handleSocialLogin('Google')} disabled={busy}>G&nbsp;&nbsp; Continue with Google</button><button type="button" className="social" onClick={()=>handleSocialLogin('Microsoft')} disabled={busy}>▦&nbsp;&nbsp; Continue with Microsoft</button><p className="authBottom">Need an account? <Link href="/signup">Create one</Link></p></form></section></div></div>
}
