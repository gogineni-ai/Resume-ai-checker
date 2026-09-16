'use client'
import {useEffect,useState} from 'react';
import {useParams} from 'next/navigation';
import Link from 'next/link';
import AppShell from '../../../components/AppShell';
import {getAnalysis, chatWithAnalysis, rewriteAnalysis} from '../../../lib/api';

export default function Results(){
  const {id} = useParams();
  const [r, setR] = useState<any>(null);
  const [chat, setChat] = useState<any>(null);
  const [draft, setDraft] = useState('What is the biggest problem with my resume?');
  const [rewrite, setRewrite] = useState('');
  const [saveState, setSaveState] = useState('');

  useEffect(() => {
    const cached = sessionStorage.getItem('rv_last_analysis');
    if (cached) {
      const x = JSON.parse(cached);
      if (String(x.analysis_id) === String(id)) {
        setR(x);
        return;
      }
    }
    getAnalysis(String(id)).then(x => setR({ ...x.result, analysis_id: x.id }));
  }, [id]);

  useEffect(() => {
    if (id) setRewrite(localStorage.getItem(`rv_resume_draft_${id}`) || '');
  }, [id]);

  async function askCoach() {
    if (!id) return;
    const response = await chatWithAnalysis(String(id), draft || 'What is the biggest problem with my resume?');
    setChat(response);
  }

  async function generateRewrite() {
    if (!id) return;
    const response = await rewriteAnalysis(String(id), 'confident');
    setRewrite(response.full_resume);
    setSaveState('Draft generated');
  }

  function saveRewrite() {
    if (!id || !rewrite.trim()) return;
    localStorage.setItem(`rv_resume_draft_${id}`, rewrite);
    setSaveState('Saved on this device');
  }

  function downloadRewrite() {
    if (!rewrite.trim()) return;
    const blob = new Blob([rewrite], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'resume-draft.txt';
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!r) {
    return <AppShell><div className="pageLoader"><div className="spinner"/>Loading analysis…</div></AppShell>;
  }

  const pct = Math.round(r.overall_score || 0);
  const ai = r.ai_insights?.status === 'complete' ? r.ai_insights.insights : null;

  return <AppShell>
    <div className="pageTitle">
      <div>
        <Link href="/dashboard">← Dashboard</Link>
        <h1>Analysis Results</h1>
      </div>
      <div className="actions">
        <button className="outline">⇩ Download Report</button>
        <button className="outline">↗ Share</button>
      </div>
    </div>

    <section className="panel resultHead">
      <div>
        <span className="docIcon">▤</span>
        <b>{r.target_title || 'Resume Evidence Analysis'}{r.target_company ? ` - ${r.target_company}` : ''}</b>
        <small>{r.resume_filename}</small>
      </div>
    </section>

    <div className="resultGrid">
      <section className="panel scoreCard">
        <div className="donut" style={{ '--p': `${pct * 3.6}deg` } as any}><div><strong>{pct}%</strong></div></div>
        <h3>Overall Match Score</h3>
        <b className="greenText">{pct >= 80 ? 'Great Match!' : pct >= 60 ? 'Good Match' : 'Needs Improvement'}</b>
      </section>

      <section className="panel metricCard">
        <Metric name="Skills Match" value={r.ats_score} />
        <Metric name="Experience Evidence" value={r.evidence_score} />
        <Metric name="Timeline Consistency" value={r.timeline_score} />
        <Metric name="Semantic Similarity" value={Math.round((r.semantic_similarity || 0) * 100)} />
      </section>
    </div>

    <div className="threeCols">
      <SkillBox title={`Matched Skills (${r.matched_skills?.length || 0})`} items={r.matched_skills} kind="match" />
      <SkillBox title={`Missing Skills (${r.missing_skills?.length || 0})`} items={r.missing_skills} kind="miss" />
      <SkillBox title="Evidence Summary" items={(r.skills || []).slice(0, 7).map((s: any) => `${s.skill} — ${s.status}`)} kind="info" />
    </div>

    {ai && <section className="panel aiInsights">
      <div className="aiHeader">
        <div>
          <h3>AI Review</h3>
          <p className="muted">Grounded in retrieved job postings</p>
        </div>
        <span className="aiConfidence">{Math.round((ai.confidence || 0) * 100)}% confidence</span>
      </div>
      <p>{ai.summary}</p>
      <div className="aiColumns">
        <InsightList title="Strengths" items={ai.strengths} />
        <InsightList title="Gaps" items={ai.gaps} />
        <InsightList title="Recommendation" items={ai.recommendations} />
      </div>
    </section>}

    <section className="panel checklist">
      <h3>Resume Coach</h3>
      <p className="muted">The resume is close, but the biggest issue is likely the gap between your current experience and the required role skills.</p>

      <div className="chatBox">
        <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={3} />
        <button className="primary" onClick={askCoach}>Ask coach</button>
      </div>

      {chat && <div className="coachOutput">
        <p><strong>Issue:</strong> {chat.issue || chat.issues?.[0]}</p>
        <ul>
          {(chat.recommendations || chat.suggestions || []).slice(0, 5).map((item: string, index: number) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </div>}

      <div className="rewriteBox">
        <div className="rewriteHeader">
          <div>
            <h3>Edit your resume</h3>
            <p className="muted">Generate a draft, then edit every line before downloading it.</p>
          </div>
          <div className="rewriteActions">
            <button className="outline" onClick={generateRewrite}>Generate draft</button>
            <button className="primary" onClick={saveRewrite} disabled={!rewrite.trim()}>Save draft</button>
            <button className="outline" onClick={downloadRewrite} disabled={!rewrite.trim()}>Download .txt</button>
          </div>
        </div>
        <textarea className="resumeEditor" value={rewrite} onChange={e => { setRewrite(e.target.value); setSaveState('Unsaved changes'); }} placeholder="Your rewritten resume will appear here..." rows={18} />
        {saveState && <span className="saveState">{saveState}</span>}
      </div>
    </section>
  </AppShell>;
}

function Metric({ name, value }: { name: string; value: number }) {
  return <div className="metric"><div><b>{name}</b><strong>{Math.round(value || 0)}%</strong></div><div className="bar"><span style={{ width: `${Math.min(100, Math.max(0, value || 0))}%` }} /></div></div>;
}

function SkillBox({ title, items = [], kind }: { title: string; items?: string[]; kind: string }) {
  return <section className="panel skillBox"><h3>{title}</h3>{items?.length ? items.slice(0, 8).map((x: string, i: number) => <div className={`skillLine ${kind}`} key={i}><span>{kind === 'match' ? '✓' : kind === 'miss' ? '×' : 'i'}</span>{x}</div>) : <p className="muted">No items to display.</p>}</section>;
}

function InsightList({ title, items = [] }: { title: string; items?: string[] }) {
  return <div><b>{title}</b>{items.length ? <ul>{items.slice(0, 5).map((item: string, index: number) => <li key={index}>{item}</li>)}</ul> : <p className="muted">None reported.</p>}</div>;
}
