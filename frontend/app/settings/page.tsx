'use client'

import {useState} from 'react'
import AppShell from '../../components/AppShell'
import {
  changePassword,
  getStoredUser,
  setStoredUser,
  updateProfile
} from '../../lib/api'

export default function Settings(){
  const u=typeof window!=='undefined'?getStoredUser():null

  const [name,setName]=useState(u?.name||'')
  const [phone,setPhone]=useState(u?.phone||'')
  const [currentPassword,setCurrentPassword]=useState('')
  const [newPassword,setNewPassword]=useState('')
  const [confirmPassword,setConfirmPassword]=useState('')
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const [saving,setSaving]=useState(false)

  async function saveProfile(){
    setSaving(true)
    setMessage('')
    setError('')

    try{
      const r=await updateProfile({name,phone})
      setStoredUser(r.user)
      setMessage('Profile updated successfully.')
    }catch(e:any){
      setError(e.message||'Unable to update profile')
    }finally{
      setSaving(false)
    }
  }

  async function savePassword(){
    setMessage('')
    setError('')

    if(newPassword!==confirmPassword){
      setError('New passwords do not match.')
      return
    }

    setSaving(true)

    try{
      await changePassword({
        current_password:currentPassword,
        new_password:newPassword
      })

      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setMessage('Password updated successfully.')
    }catch(e:any){
      setError(e.message||'Unable to update password')
    }finally{
      setSaving(false)
    }
  }

  return (
    <AppShell>
      <div className="pageTitle">
        <div>
          <h1>Account Settings</h1>
          <p>Edit your profile and password.</p>
        </div>
      </div>

      <section className="panel settingsCard">
        <h2>Profile</h2>

        <label>
          Full Name
          <input
            value={name}
            onChange={e=>setName(e.target.value)}
          />
        </label>

        <label>
          Email Address
          <input value={u?.email||''} readOnly/>
        </label>

        <label>
          Phone Number
          <input
            value={phone}
            onChange={e=>setPhone(e.target.value)}
          />
        </label>

        <button
          onClick={saveProfile}
          disabled={saving}
          style={{
            padding:'12px 18px',
            borderRadius:10,
            border:0,
            fontWeight:700,
            cursor:'pointer'
          }}
        >
          {saving?'Saving...':'Save Profile'}
        </button>

        <hr style={{
          margin:'28px 0',
          border:0,
          borderTop:'1px solid #e5e7eb'
        }}/>

        <h2>Change Password</h2>

        <label>
          Current Password
          <input
            type="password"
            value={currentPassword}
            onChange={e=>setCurrentPassword(e.target.value)}
          />
        </label>

        <label>
          New Password
          <input
            type="password"
            value={newPassword}
            onChange={e=>setNewPassword(e.target.value)}
          />
        </label>

        <label>
          Confirm New Password
          <input
            type="password"
            value={confirmPassword}
            onChange={e=>setConfirmPassword(e.target.value)}
          />
        </label>

        <button
          onClick={savePassword}
          disabled={saving}
          style={{
            padding:'12px 18px',
            borderRadius:10,
            border:0,
            fontWeight:700,
            cursor:'pointer'
          }}
        >
          Update Password
        </button>

        {message&&
          <p style={{marginTop:16,fontWeight:700}}>
            {message}
          </p>
        }

        {error&&
          <p style={{
            marginTop:16,
            color:'#b91c1c',
            fontWeight:700
          }}>
            {error}
          </p>
        }
      </section>
    </AppShell>
  )
}
