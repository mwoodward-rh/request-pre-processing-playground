import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {kinds, segments} from './evidence.mjs';
import './style.css';

const examples = [
  'Review the Atlas API in ./src/api.py and explain why the upload fails. Keep the data local.',
  'Compare the caching approaches in the documentation and summarize their tradeoffs.',
  'Using our previous design, add a keyboard shortcut to the search panel. Do not change the public API.',
];
const percent = n => typeof n === 'number' ? `${(n*100).toFixed(1)}%` : '—';
function Panel({index, title, children, className = ''}) {
  return <section className={`panel ${className}`}><div className="eyebrow">{index}</div><h2>{title}</h2>{children}</section>;
}
function Scores({scores}) {
  return <div className="scores">{Object.entries(scores || {}).sort((a,b)=>b[1]-a[1]).map(([label, score])=><div className="score" key={label}><span>{label}</span><meter min="0" max="1" value={score} aria-label={label}/><strong>{percent(score)}</strong></div>)}</div>;
}
function Graph({spans}) {
  const visible = spans.slice(0, 8);
  return <><svg className="graph" viewBox="0 0 700 380" role="img" aria-label="Request linked to extracted mentions">
    {visible.map((s,i)=>{const angle = i * Math.PI*2/visible.length;const x=350+240*Math.cos(angle), y=190+140*Math.sin(angle);
      return <g key={s.id}><line x1="350" y1="190" x2={x} y2={y}/><circle cx={x} cy={y} r="43" className={s.kind}/><text x={x} y={y-3} textAnchor="middle">{s.value.length > 18 ? s.value.slice(0,16)+'…' : s.value}<title>{s.value}</title></text><text className="subtext" x={x} y={y+17} textAnchor="middle">{s.kind.replace('_', ' ')}</text></g>;})}
    <circle cx="350" cy="190" r="49" className="request"/><text x="350" y="194" textAnchor="middle">User request</text>
  </svg><p className="muted">Source mentions, not verified facts. {spans.length>8 ? `Showing 8 of ${spans.length} nodes; all mentions are listed below.` : ''}</p>
  <ul className="edges">{spans.map(s=><li key={s.id}>request <span>→ mentions {s.kind} →</span> {s.value}</li>)}</ul></>;
}
function App() {
  const [text,setText]=useState(examples[0]); const [context,setContext]=useState('');
  const [analysis,setAnalysis]=useState(null); const [busy,setBusy]=useState(false); const [error,setError]=useState('');
  const [service,setService]=useState(null);
  useEffect(()=>{
    const controller=new AbortController();
    fetch('/api/health',{signal:controller.signal}).then(response=>{
      if(!response.ok) throw new Error('Service configuration unavailable');
      return response.json();
    }).then(setService).catch(error=>{
      if(error.name!=='AbortError') setError('Service configuration unavailable. Reload to retry.');
    });
    return ()=>controller.abort();
  },[]);
  async function analyze(e) {
    e.preventDefault(); if(!service) return; setBusy(true); setError(''); setAnalysis(null);
    try {
      const response=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,context})});
      const result=await response.json();
      if(!response.ok) throw new Error(typeof result.detail==='string' ? result.detail : `Request rejected (${response.status}). Check input limits.`);
      setAnalysis(result);
    } catch(e) {setError(e.message || 'Analysis unavailable');} finally {setBusy(false);}
  }
  const jev=analysis?.stages.jev.result, semantic=analysis?.stages.langextract.result, spans=semantic?.spans || [];
  return <main>
    <header><div><div className="eyebrow">PASSIVE REQUEST ANALYSIS</div><h1>Request Intelligence <span>Lab</span></h1><p>See how OpenJev decisions and LangExtract semantics turn a request into inspectable metadata.</p></div><span className="badge">Standalone example</span></header>
    <div className="notice">{!service ? 'Checking extraction destination. ' : service.remote_extraction ? `Remote extraction (${service.extraction_provider}): request text and explicit context are sent to the configured provider; its retention policies apply. ` : 'Text goes to your configured local/private model services. '}Jev uses your configured service. No task execution or application chat history. <strong>No PII redaction: use synthetic or non-sensitive prompts.</strong></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="grid">
      <Panel index="01 · INPUT SURFACE" title="Prompt the system"><form onSubmit={analyze}>
        <label htmlFor="prompt">Current request</label><textarea id="prompt" required maxLength={12000} value={text} onChange={e=>setText(e.target.value)} disabled={busy}/>
        <div className="examples">{examples.map(example=><button type="button" className="example" key={example} disabled={busy} onClick={()=>setText(example)}>{example}</button>)}</div>
        <details><summary>Optional prior conversation context</summary><p className="muted">Explicit context only—nothing is retrieved or remembered between submissions.</p><label htmlFor="context">Prior context (up to 6,000 characters)</label><textarea id="context" className="context" maxLength={6000} value={context} onChange={e=>setContext(e.target.value)} disabled={busy}/></details>
        <div className="actions"><span className="muted">{text.trim().split(/\s+/).filter(Boolean).length} words · {text.length} characters</span><button className="primary" disabled={busy || !service || !text.trim()}>{busy ? 'Analyzing…' : '↗ Analyze request'}</button></div>
      </form></Panel>
      <Panel index="02 · OPENJEV DECISIONS" title="Intent classification">
        <div aria-live="polite"><span className={`badge ${analysis?.status || ''}`}>{busy ? 'Processing both model stages' : analysis?.status || 'Ready for a request'}</span>
        {jev ? <><h3>{jev.label}{jev.uncertain && <small> · uncertain</small>}</h3><p className="muted">{percent(jev.confidence)} model score · not calibrated on your requests</p><Scores scores={jev.probabilities}/><p className="muted">{jev.tokens} current-request tokens · {jev.chunks} chunks · {jev.context_tokens_used} prior-context tokens used{jev.context_truncated ? ' · prior context truncated' : ''}</p></> : <p className="placeholder">{analysis?.stages.jev.error || 'OpenJev chooses among explicit intent labels. It does not generate a response.'}</p>}</div>
        <div className="footnote">Observation only. Uncertainty thresholds are provisional. No complexity score or routing decision is inferred here.</div>
      </Panel>
      <Panel index="03 · LANGEXTRACT SOURCE GROUNDING" title="What was extracted" className="wide">
        {semantic ? <><div className="source">{segments(analysis.source,spans).map((part,i)=>part.kind ? <mark key={i} className={part.kind} title={part.kind}>{part.text}</mark> : <React.Fragment key={i}>{part.text}</React.Fragment>)}</div>
        <div className="legend">{kinds.map(kind=><span key={kind} className={kind}>{kind.replace('_',' ')}</span>)}</div>
        {spans.length === 0 && <p className="notice">The model returned no grounded spans. A completed stage does not guarantee useful extraction; try a clearer request or another extraction model.</p>}
        <div className="span-list">{spans.map(span=><div key={span.id}><strong className={span.kind}>{span.value}</strong><span className="muted">{span.kind} · {span.start}:{span.end}</span>{Object.keys(span.attributes).length>0 && <small>{JSON.stringify(span.attributes)}</small>}</div>)}</div>
        <p className="muted">{spans.length} grounded spans · {semantic.rejected_ungrounded} rejected spans · offsets use browser UTF-16. Exact matching establishes provenance, not truth.</p></> : <p className="placeholder">{analysis?.stages.langextract.error || 'LangExtract uses the configured model service to identify goals, artifacts, entities, systems, constraints, and references. Only exact source-aligned spans are displayed.'}</p>}
      </Panel>
      <Panel index="04 · CONTEXT-REFERENCE SIGNALS" title="References and memory value">
        {jev ? <><div className="score"><span>Prior-work reference</span><strong>{percent(jev.memory_probability)}</strong></div><div className="score"><span>Multiple tasks</span><strong>{percent(jev.multiple_probability)}</strong></div><h4>Provisional memory-value scores</h4><Scores scores={jev.signal_probabilities}/></> : <p className="placeholder">Signals appear after Jev completes.</p>}
        <div className="footnote">These are model assessments—not retrieval results, saved memories, or retention decisions.</div>
      </Panel>
      <Panel index="05 · PASSIVE MENTIONS" title="Request graph">{semantic ? <Graph spans={spans}/> : <p className="placeholder">Extracted mentions will connect to the request here.</p>}</Panel>
      <Panel index="06 · PROCESSING TRACE" title="Model stages"><div aria-live="polite">{analysis ? <>{Object.entries(analysis.stages).map(([name,stage])=><div className="stage" key={name}><strong>{name==='jev' ? 'OpenJev intent' : 'LangExtract semantics'} · {stage.status} · {stage.duration_ms} ms</strong><p className="muted">{stage.result?.model || stage.error}</p></div>)}<p>Total elapsed: {analysis.elapsed_ms} ms · stages run concurrently</p><details><summary>Structured analysis and semantic attributes</summary><pre>{JSON.stringify(analysis,null,2)}</pre></details></> : <p className="placeholder">{busy ? 'Inference in progress.' : 'No timing estimates or synthetic model scores are shown.'}</p>}</div></Panel>
    </div><footer>OpenJev makes typed decisions. LangExtract aligns semantic extractions to source text. Application code renders the metadata. Nothing here executes the request.</footer>
  </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
