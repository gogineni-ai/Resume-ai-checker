'use client'

import {useEffect,useMemo,useState} from 'react'
import AppShell from '../../components/AppShell'
import CompanyEvidence from '../../components/CompanyEvidence'
import {getHistory,getStoredUser,requestOtp,verifyOtp,setStoredUser} from '../../lib/api'

export default function Verification(){
  const [skills,setSkills]=useState<any[]>([])
  const [tab,setTab]=useState<'timeline'|'company'>('timeline')
  const [loading,setLoading]=useState(true)
  const [user,setUser]=useState<any>(null)
  const [otp,setOtp]=useState('')
  const [otpBusy,setOtpBusy]=useState(false)
  const [otpMsg,setOtpMsg]=useState('')
  const [otpErr,setOtpErr]=useState('')

  useEffect(()=>{
    setUser(getStoredUser())
    getHistory()
      .then((h:any[])=>{
        setSkills(h[0]?.result?.skills||[])
      })
      .catch(()=>setOtpErr('Unable to load verification data. Please retry.'))
      .finally(()=>setLoading(false))
  },[])

  const evidence=useMemo(
    ()=>skills.flatMap((s:any)=>
      (s.examples||[]).map((e:any)=>({
        ...e,
        skill:s.skill,
        status:s.status
      }))
    ),
    [skills]
  )

  return (
    <AppShell>
      <div className="pageTitle">
        <div>
          <h1>Skills Verification</h1>
          <p>
            Technology timeline and historical
            job-posting evidence.
          </p>
        </div>
      </div>

      {otpErr&&<p role="alert">{otpErr}</p>}<CompanyEvidence/><section className="panel verifyPanel">

        <div className="tabs">
          <button type="button"
            onClick={()=>setTab('timeline')}
            style={{
              cursor:'pointer',
              opacity:tab==='timeline'?1:.5
            }}
          >
            Technology Timeline
          </button>

          <button type="button"
            onClick={()=>setTab('company')}
            style={{
              cursor:'pointer',
              opacity:tab==='company'?1:.5
            }}
          >
            Company Evidence
          </button>
        </div>

        {loading&&
          <div className="empty">
            <b>Loading verification data...</b>
          </div>
        }

        {!loading&&tab==='timeline'&&
          (skills.length
            ? skills.map((s:any,i:number)=>(
              <div className="timeline" key={s.skill}>
                <div className={`techIcon t${i%4}`}>
                  ↯
                </div>

                <div className="techMain">
                  <div className="techTop">
                    <h3>{s.skill}</h3>

                    <span className={`status ${
                      s.status==='supported'
                        ?'ok'
                        :s.status==='timeline conflict'
                        ?'badStatus'
                        :'maybe'
                    }`}>
                      {s.status}
                    </span>
                  </div>

                  <p>
                    {s.evidence_count||0} matching job
                    postings found. Release year:{' '}
                    {s.release_year||'unknown'} · First
                    seen:{' '}
                    {s.first_seen_in_archive||
                      'not in archive'}.
                  </p>

                  <div className="timelineBar">
                    <span
                      style={{
                        width:`${Math.min(
                          100,
                          25+(s.evidence_count||0)*3
                        )}%`
                      }}
                    />
                  </div>

                  <div className="years">
                    <span>2010</span>
                    <span>2015</span>
                    <span>2020</span>
                    <span>2026</span>
                  </div>
                </div>
              </div>
            ))
            :(
              <div className="empty">
                <b>No verification data yet.</b>
                <p>
                  Run an analysis first to see
                  technology evidence.
                </p>
              </div>
            )
          )
        }

        {!loading&&tab==='company'&&
          (evidence.length
            ?(
              <div style={{
                display:'grid',
                gap:14,
                padding:'18px'
              }}>
                {evidence.map((e:any,i:number)=>(
                  <div
                    key={`${e.job_id}-${e.skill}-${i}`}
                    style={{
                      border:'1px solid #e5e7eb',
                      borderRadius:14,
                      padding:16
                    }}
                  >
                    <div style={{
                      display:'flex',
                      justifyContent:'space-between',
                      alignItems:'center',
                      gap:12
                    }}>
                      <div>
                        <h3 style={{margin:'0 0 4px'}}>
                          {e.company||
                            'Unknown company'}
                        </h3>

                        <p style={{
                          margin:0,
                          fontWeight:700
                        }}>
                          {e.title||'Job posting'}
                        </p>
                      </div>

                      <span className={`status ${
                        e.status==='supported'
                          ?'ok'
                          :e.status==='timeline conflict'
                          ?'badStatus'
                          :'maybe'
                      }`}>
                        {e.status}
                      </span>
                    </div>

                    <p style={{
                      margin:'12px 0 6px'
                    }}>
                      Skill evidence:{' '}
                      <b>{e.skill}</b>
                      {e.year?` · ${e.year}`:''}
                    </p>

                    {e.source_url
                      ?(
                        <a
                          href={e.source_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          View source posting
                        </a>
                      )
                      :(
                        <span style={{opacity:.65}}>
                          Source URL not available
                        </span>
                      )
                    }
                  </div>
                ))}
              </div>
            )
            :(
              <div className="empty">
                <b>No company evidence found.</b>
                <p>
                  The current archive has no matching
                  job postings for the skills in your
                  latest analysis. Import or add job
                  postings and run the analysis again.
                </p>
              </div>
            )
          )
        }

      </section>
    </AppShell>
  )
}
