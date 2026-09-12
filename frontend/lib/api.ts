export const API=process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const token=()=>typeof window!=='undefined'?localStorage.getItem('rv_token'):null
async function request(path:string, init:RequestInit={}){
  const headers:any={...(init.headers||{})}; const t=token(); if(t)headers.Authorization=`Bearer ${t}`
  const r=await fetch(`${API}${path}`,{...init,headers});
  if(!r.ok){let msg=await r.text();try{msg=JSON.parse(msg).detail||msg}catch{};throw new Error(msg)}
  return r.json()
}
export async function register(data:{name:string,email:string,phone:string,date_of_birth:string|null,password:string}){return request('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
export async function login(data:{email:string,password:string}){return request('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
export async function me(){return request('/api/auth/me')}
export async function updateProfile(data:{name:string,phone:string}){
  return request('/api/auth/profile',{
    method:'PUT',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data)
  })
}
export async function changePassword(data:{current_password:string,new_password:string}){
  return request('/api/auth/password',{
    method:'PUT',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data)
  })
}
export async function uploadResume(file:File){const f=new FormData();f.append('file',file);return request('/api/resumes',{method:'POST',body:f})}
export async function getJobs(){return request('/api/jobs')}
export async function createJob(data:{company:string,title:string,description:string}){return request('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
export async function analyze(resumeId:number,jobId?:number){const q=jobId?`?target_job_id=${jobId}`:'';return request(`/api/analyze/${resumeId}${q}`,{method:'POST'})}
export async function getHistory(){return request('/api/analyses')}
export async function getAnalysis(id:string|number){return request(`/api/analyses/${id}`)}
export function saveSession(data:any){localStorage.setItem('rv_token',data.access_token);localStorage.setItem('rv_user',JSON.stringify(data.user))}
export function setStoredUser(user:any){
  localStorage.setItem('rv_user',JSON.stringify(user))
}
export function getStoredUser(){try{return JSON.parse(localStorage.getItem('rv_user')||'null')}catch{return null}}
export function logout(){localStorage.removeItem('rv_token');localStorage.removeItem('rv_user')}

export async function requestOtp(channel:'email'|'phone'){
  return request('/api/auth/request-otp',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({channel})
  })
}

export async function verifyOtp(channel:'email'|'phone',code:string){
  return request('/api/auth/verify-otp',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({channel,code})
  })
}
