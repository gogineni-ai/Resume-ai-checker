 'use client'
import Link from 'next/link'
import {usePathname,useRouter} from 'next/navigation'
import {useEffect,useState} from 'react'
import Logo from './Logo'
import {logout,me,setStoredUser,getHistory} from '../lib/api'
const links=[['/dashboard','⌂','Dashboard'],['/dashboard#upload','▤','Analyze Resume'],['/verification','◉','Skills Verification'],['/history','↻','History'],['/settings','⚙','Settings']]
export default function AppShell({children}:{children:React.ReactNode}){
 const path=usePathname(),router=useRouter()
 const [user,setUser]=useState<any>(null),[panel,setPanel]=useState(''),[query,setQuery]=useState(''),[history,setHistory]=useState<any[]>([]),[error,setError]=useState('')
 useEffect(()=>{me().then(u=>{setStoredUser(u);if(!u.email_verified){router.replace('/verify-email');return}setUser(u)}).catch(e=>setError(e.message))},[router])
 useEffect(()=>{if(panel==='search')getHistory().then(setHistory).catch(e=>setError(e.message))},[panel])
 useEffect(()=>{setPanel('')},[path])
 if(error&&!user)return <main className="signupCard"><p role="alert">{error}</p><Link href="/login">Return to login</Link></main>
 if(!user)return <div className="pageLoader">Loading account…</div>
 const initials=user.name?.split(' ').map((x:string)=>x[0]).slice(0,2).join('').toUpperCase()||'RV'
 const toggle=(name:string)=>setPanel(panel===name?'':name)
 const results=[...links.map(([href,,label])=>({href,label})),...history.map(h=>({href:`/results/${h.id}`,label:h.result?.resume_filename||`Analysis ${h.id}`}))].filter(x=>x.label.toLowerCase().includes(query.toLowerCase()))
 return <div className="app"><header className="topbar"><Logo/><div className="topActions"><button className="iconBtn" aria-label="Search" aria-expanded={panel==='search'} onClick={()=>toggle('search')}>⌕</button><button className="iconBtn" aria-label="Notifications" aria-expanded={panel==='notifications'} onClick={()=>toggle('notifications')}>♢</button><div className="avatar">{initials}</div><div className="userMini"><strong>{user.name}</strong><span>{user.email}</span></div><button className="chev" aria-label="Account menu" aria-expanded={panel==='account'} onClick={()=>toggle('account')}>⌄</button></div></header>{panel&&<section className="headerPanel" aria-label={panel} onKeyDown={e=>{if(e.key==='Escape')setPanel('')}}><button className="outline" onClick={()=>setPanel('')} aria-label="Close panel">×</button>{panel==='search'?<><label>Search pages and analyses<input autoFocus value={query} onChange={e=>setQuery(e.target.value)}/></label>{error&&<p role="alert">{error}</p>}{results.length?results.map((x,i)=><Link key={i} href={x.href} onClick={()=>setPanel('')}>{x.label}</Link>):<p>No matching pages or analyses.</p>}</>:panel==='notifications'?<><h2>Account activity</h2><p>Email verified.</p><Link href="/history">View your analysis history</Link></>:<><Link href="/settings">Account settings</Link><button className="outline" onClick={()=>{logout();router.push('/login')}}>Sign out</button></>}</section>}<aside className="sidebar">{links.map(([href,icon,label])=><Link key={label} href={href} className={path===href?'nav active':'nav'}><span>{icon}</span>{label}</Link>)}</aside><main className="content">{children}</main></div>
}
