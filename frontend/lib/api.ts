export const API=process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const token=()=>typeof window!=='undefined'?(sessionStorage.getItem('rv_token')||localStorage.getItem('rv_token')):null
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
export async function downloadReport(id:string|number,format:'docx'|'pdf'){const t=token();const r=await fetch(`${API}/api/analyses/${id}/report.${format}`,{headers:t?{Authorization:`Bearer ${t}`}:{}});if(!r.ok)throw new Error(await r.text());const blob=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`resume-analysis-${id}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
export function saveSession(data:any,remember=false){logout();const store=remember?localStorage:sessionStorage;store.setItem('rv_token',data.access_token);store.setItem('rv_user',JSON.stringify(data.user))}
export function setStoredUser(user:any){
  const store=sessionStorage.getItem('rv_token')?sessionStorage:localStorage;store.setItem('rv_user',JSON.stringify(user))
}
export function getStoredUser(){try{return JSON.parse(sessionStorage.getItem('rv_user')||localStorage.getItem('rv_user')||'null')}catch{return null}}
export function logout(){localStorage.removeItem('rv_token');localStorage.removeItem('rv_user');sessionStorage.removeItem('rv_token');sessionStorage.removeItem('rv_user');sessionStorage.removeItem('rv_last_analysis')}

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

export async function getCompanyEvidence(company:string,skill:string){return request(`/api/evidence?company=${encodeURIComponent(company)}&skill=${encodeURIComponent(skill)}`)}

export function forgotPassword(email:string){return request('/api/auth/forgot-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})})}
export function resetPassword(email:string,code:string,password:string){return request('/api/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,code,password})})}

export async function getCollectionStatus(){return request('/api/evidence/collection-status')}
export async function gmailStatus(){return request('/api/admin/gmail/status')}
export async function connectGmail(){return request('/api/admin/gmail/connect',{method:'POST'})}
