'use client'
import Link from 'next/link';import {usePathname,useRouter} from 'next/navigation';import {useEffect,useState} from 'react';import Logo from './Logo';import {getStoredUser,logout,me} from '../lib/api'
const links=[['/dashboard','⌂','Dashboard'],['/dashboard','▤','Analyze Resume'],['/verification','◉','Skills Verification'],['/history','↻','History'],['/settings','⚙','Settings']]
export default function AppShell({children}:{children:React.ReactNode}){
 const path=usePathname(),router=useRouter();const [user,setUser]=useState<any>(null)
 useEffect(()=>{const u=getStoredUser();if(!u){router.replace('/login');return}setUser(u);me().catch(()=>{logout();router.replace('/login')})},[router])
 if(!user)return <div className="pageLoader"><div className="spinner"/>Loading…</div>
 const initials=user.name?.split(' ').map((x:string)=>x[0]).slice(0,2).join('').toUpperCase()||'RV'
 return <div className="app"><header className="topbar"><Logo/><div className="topActions"><button className="iconBtn" aria-label="Search">⌕</button><button className="iconBtn" aria-label="Notifications">♢</button><div className="avatar">{initials}</div><div className="userMini"><strong>{user.name}</strong><span>{user.email}</span></div><button className="chev" onClick={()=>{logout();router.push('/login')}} title="Sign out">⌄</button></div></header><aside className="sidebar">{links.map(([href,icon,label],i)=><Link key={i} href={href} className={(path===href&&!(href==='/dashboard'&&i===1))?'nav active':'nav'}><span>{icon}</span>{label}</Link>)}</aside><main className="content">{children}</main></div>
}
