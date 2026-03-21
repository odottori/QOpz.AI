"""
Transform trade_lifecycle.html: 16 steps → 24 steps with 2-level phase bar.

Original steps 1-16 → new steps 6-21 (shift +5)
New steps added:  1-5 (ANTE), 22 (METRICHE), 23-24 (POST)
"""
import re

SRC = 'docs/guide/trade_lifecycle.html'
with open(SRC, 'r', encoding='utf-8') as f:
    content = f.read()

# ═══════════════════════════════════════════════════════
# 1. RENUMBER existing steps 1-16 → 6-21 (high→low to avoid conflicts)
# Also update step labels inside HTML ("Step N —" → "Step N+5 —")
# and TOC items
# ═══════════════════════════════════════════════════════
for n in range(16, 0, -1):
    new = n + 5
    content = content.replace(f'data-step="{n}"', f'data-step="X{new}"')
    content = content.replace(f'onclick="goTo({n})"', f'onclick="goTo(X{new})"')
    content = content.replace(f'<span class="toc-num">{n}</span>', f'<span class="toc-num">X{new}</span>')
    # Step labels in slide content
    content = content.replace(f'Step {n} —', f'Step X{new} —')

# Remove X prefix
content = content.replace('data-step="X', 'data-step="')
content = content.replace('onclick="goTo(X', 'onclick="goTo(')
content = content.replace('<span class="toc-num">X', '<span class="toc-num">')
content = content.replace('Step X', 'Step ')

# ═══════════════════════════════════════════════════════
# 2. INSERT 5 new ANTE steps before the stage's first step
# ═══════════════════════════════════════════════════════
ante_html = '''  <!-- STEP 1 — ANTE/DATI: Ingest pipeline -->
  <div class="step active" data-step="1">
    <div class="step-header">
      <div class="step-icon">🌙</div>
      <div class="step-meta">
        <div class="step-label">Step 1 — DATI</div>
        <div class="step-title">La pipeline si avvia</div>
        <div class="step-subtitle">08:45 ET — ingest feed attivo</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Cosa fa il sistema</div>
        <div class="description">
          Prima che i mercati aprano, la pipeline si connette al provider e ingerisce la catena completa di opzioni. Ogni record viene validato e scritto in DuckDB con i metadati di qualità: <strong>asof_ts</strong>, <strong>received_ts</strong>, <strong>DATA_MODE</strong>.
        </div>
        <div class="data-grid">
          <div class="data-item">
            <div class="data-label">Pipeline</div>
            <div class="data-value ok">ATTIVA</div>
            <div class="data-sub">ingest pre-market</div>
          </div>
          <div class="data-item">
            <div class="data-label">Record ricevuti</div>
            <div class="data-value blue">1.247</div>
            <div class="data-sub">catena SPY completa</div>
          </div>
          <div class="data-item">
            <div class="data-label">DATA_MODE</div>
            <div class="data-value ok" style="font-size:12px">VENDOR_REAL</div>
            <div class="data-sub">catena reale</div>
          </div>
          <div class="data-item">
            <div class="data-label">Latenza feed</div>
            <div class="data-value ok">0.8s</div>
            <div class="data-sub">asof→received</div>
          </div>
        </div>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">ingest_pipeline.log — pre-market</div>
        </div>
        <div class="screen-body">
<span class="dim">[08:45:00.012]</span> <span class="hlg">INFO</span>  pre-market routine start<br>
<span class="dim">[08:45:00.031]</span> <span class="hlg">INFO</span>  feed connected — provider: tradier<br>
<span class="dim">[08:45:01.204]</span> <span class="hlb">RECV</span>  SPY chain — 1247 records<br>
<span class="dim">[08:45:01.210]</span> <span class="hlt">META</span>  asof_ts = 08:44:59.841<br>
<span class="dim">[08:45:01.211]</span> <span class="hlt">META</span>  DATA_MODE = <span class="hlg">VENDOR_REAL_CHAIN</span><br>
<span class="dim">[08:45:01.220]</span> <span class="hlg">INFO</span>  validation OK — writing to DuckDB<br>
          <div class="section">
            <div class="row"><span>Record scritti DuckDB</span><span class="hlg">1.247</span></div>
            <div class="row"><span>source_quality</span><span class="hlt">A+</span></div>
            <div class="row"><span>Prossima fase</span><span class="hl">consolidamento</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- STEP 2 — ANTE/DATI: Consolidamento -->
  <div class="step" data-step="2">
    <div class="step-header">
      <div class="step-icon">📚</div>
      <div class="step-meta">
        <div class="step-label">Step 2 — DATI</div>
        <div class="step-title">I trade di ieri si chiudono</div>
        <div class="step-subtitle">08:46 ET — consolidamento journal</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Consolidamento automatico</div>
        <div class="description">
          La pipeline consolida i trade chiusi nelle sessioni precedenti: il P&amp;L realizzato viene scritto nel journal, le statistiche ricalcolate, la History Readiness avanza di un giorno. I trade ancora aperti vengono aggiornati con i prezzi di chiusura.
        </div>
        <div class="data-grid">
          <div class="data-item">
            <div class="data-label">Trade consolidati</div>
            <div class="data-value ok">1</div>
            <div class="data-sub">SPY 490/485P &#x2192; +$64</div>
          </div>
          <div class="data-item">
            <div class="data-label">Trade storici totali</div>
            <div class="data-value blue">47</div>
            <div class="data-sub">su 50 richiesti per Kelly</div>
          </div>
          <div class="data-item">
            <div class="data-label">History Readiness</div>
            <div class="data-value warn">69%</div>
            <div class="data-sub">34 giorni su 50</div>
          </div>
          <div class="data-item">
            <div class="data-label">P&amp;L cumulato</div>
            <div class="data-value ok">+$1.240</div>
            <div class="data-sub">da inizio paper</div>
          </div>
        </div>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">consolidation.log</div>
        </div>
        <div class="screen-body">
<span class="dim">[08:46:00.001]</span> <span class="hlg">INFO</span>  consolidation start<br>
<span class="dim">[08:46:00.014]</span> <span class="hlg">INFO</span>  SPY 490/485P &#x2192; <span class="hlg">CLOSED</span><br>
<span class="dim">[08:46:00.015]</span> <span class="hlt">META</span>  P&amp;L = <span class="hlg">+$64.00</span>  ROI = <span class="hlg">+15.6%</span><br>
<span class="dim">[08:46:00.022]</span> <span class="hlg">INFO</span>  journal updated &#x2014; 47 trade storici<br>
<span class="dim">[08:46:00.031]</span> <span class="hlg">INFO</span>  statistiche ricalcolate &#x2713;<br>
          <div class="section">
            <div class="row"><span>History Readiness</span><span class="hly">69% (34/50g)</span></div>
            <div class="row"><span>Kelly gate</span><span class="hlr">DISABILITATO (47/50)</span></div>
            <div class="row"><span>Prossima fase</span><span class="hl">analisi regime 09:00</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- STEP 3 — ANTE/ANALISI: Regime calcolato -->
  <div class="step" data-step="3">
    <div class="step-header">
      <div class="step-icon">🔬</div>
      <div class="step-meta">
        <div class="step-label">Step 3 — ANALISI</div>
        <div class="step-title">Il mercato classificato</div>
        <div class="step-subtitle">09:00 ET — HMM in esecuzione</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Regime di mercato</div>
        <div class="description">
          L'algoritmo HMM analizza le ultime 20 sessioni: volatilità realizzata, volatilità implicita, struttura dei prezzi, microstructura. Il risultato è il <strong>regime del giorno</strong> — NORMAL, CAUTION o SHOCK — che governa sizing e strategie ammesse.
        </div>
        <div class="data-grid">
          <div class="data-item full">
            <div class="data-label">Regime calcolato</div>
            <div class="data-value ok" style="font-size:28px">NORMAL</div>
            <div class="data-sub">confidenza 89% — operatività piena, sizing 100%</div>
          </div>
          <div class="data-item">
            <div class="data-label">VIX</div>
            <div class="data-value ok">18.4</div>
            <div class="data-sub">sotto soglia allerta</div>
          </div>
          <div class="data-item">
            <div class="data-label">RVol 10d</div>
            <div class="data-value ok">14.2%</div>
            <div class="data-sub">mercato ordinato</div>
          </div>
          <div class="data-item">
            <div class="data-label">Sizing consentito</div>
            <div class="data-value ok">100%</div>
            <div class="data-sub">vs 50% CAUTION / 0% SHOCK</div>
          </div>
          <div class="data-item">
            <div class="data-label">HMM confidence</div>
            <div class="data-value ok">89%</div>
            <div class="data-sub">classificazione robusta</div>
          </div>
        </div>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">regime_engine.py — HMM</div>
        </div>
        <div class="screen-body">
<span class="dim">[09:00:00.001]</span> <span class="hlg">INFO</span>  HMM analysis start<br>
<span class="dim">[09:00:00.412]</span> <span class="hlt">META</span>  sessions analyzed: 20<br>
<span class="dim">[09:00:00.413]</span> <span class="hlt">META</span>  regime = <span class="hlg">NORMAL</span>  confidence = <span class="hlg">89.1%</span><br>
<span class="dim">[09:00:00.414]</span> <span class="hlt">META</span>  VIX = 18.4  RVol10d = 14.2%<br>
          <div class="section">
            <div class="row"><span>Regime</span><span class="badge normal">&#x25cf; NORMAL</span></div>
            <div class="row"><span class="dim">IVol / RVol</span><span class="hlg">1.57 &#x2713;</span></div>
            <div class="row"><span>Prossima fase</span><span class="hl">scoring segnali</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- STEP 4 — ANTE/ANALISI: Segnali pronti -->
  <div class="step" data-step="4">
    <div class="step-header">
      <div class="step-icon">&#x26a1;</div>
      <div class="step-meta">
        <div class="step-label">Step 4 — ANALISI</div>
        <div class="step-title">8 opportunità identificate</div>
        <div class="step-subtitle">09:01 ET — scoring completato</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Risultato scoring pre-market</div>
        <div class="description">
          Il motore scansiona 1.247 candidati. Dopo i filtri duri restano 91 opportunità, di cui 8 superano la soglia score 6.5. Sono ordinate per rank e pronte per essere presentate all'operatore non appena i mercati apriranno.
        </div>
        <div class="data-grid">
          <div class="data-item">
            <div class="data-label">Candidati totali</div>
            <div class="data-value blue">1.247</div>
            <div class="data-sub">intera catena SPY</div>
          </div>
          <div class="data-item">
            <div class="data-label">Passano i filtri</div>
            <div class="data-value ok">91</div>
            <div class="data-sub">ammessi allo scoring</div>
          </div>
          <div class="data-item">
            <div class="data-label">Score &#x2265; 6.5</div>
            <div class="data-value ok">8</div>
            <div class="data-sub">da presentare</div>
          </div>
          <div class="data-item full">
            <div class="data-label">Top segnale</div>
            <div class="data-value orange">SPY 490/485P</div>
            <div class="data-sub">score 7.82 &#x2014; IVR=42, DTE=35</div>
          </div>
        </div>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">scoring_engine.py &#x2014; pre-market run</div>
        </div>
        <div class="screen-body">
<span class="dim">[09:01:01.001]</span> <span class="hlg">INFO</span>  scoring run &#x2014; 1247 candidates<br>
<span class="dim">[09:01:01.891]</span> <span class="hlg">INFO</span>  hard filter: <span class="hlr">1156 eliminati</span><br>
<span class="dim">[09:01:01.892]</span> <span class="hlg">INFO</span>  scoring: 91 valutati<br>
<span class="dim">[09:01:01.944]</span> <span class="hlg">INFO</span>  soglia 6.5: <span class="hlg">8 opportunit&#xe0;</span><br>
<br>
<span class="dim">[09:01:01.950]</span> <span class="hl">RANK</span>  #1 SPY 490/485P  score=<span class="hlg">7.82</span><br>
<span class="dim">[09:01:01.951]</span> <span class="hl">RANK</span>  #2 SPY 485/480P  score=<span class="hlg">7.41</span><br>
<span class="dim">[09:01:01.952]</span> <span class="hl">RANK</span>  #3 QQQ 440/435P  score=<span class="hlg">6.93</span><br>
          <div class="section">
            <div class="row"><span>Segnali pronti</span><span class="hlg">8</span></div>
            <div class="row"><span>Prossima fase</span><span class="hl">briefing operatore</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- STEP 5 — ANTE/BRIEFING: L'operatore si prepara -->
  <div class="step" data-step="5">
    <div class="step-header">
      <div class="step-icon">&#x1f305;</div>
      <div class="step-meta">
        <div class="step-label">Step 5 — BRIEFING</div>
        <div class="step-title">L'operatore si prepara</div>
        <div class="step-subtitle">09:20 ET — 10 minuti all'apertura</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Checklist apertura</div>
        <div class="description">
          Il NARRATORE ha generato il briefing audio con il riepilogo del giorno: regime, top opportunità, posizioni aperte. L'operatore ascolta, verifica i sistemi, e apre la WAR ROOM pronto all'apertura dei mercati.
        </div>
        <ul class="check-list">
          <li class="pass">
            <span class="check-icon">&#x2705;</span>
            <span class="check-name">Sessione scheduler</span>
            <span class="check-val">ACTIVE &#x2014; avviata 09:28</span>
          </li>
          <li class="pass">
            <span class="check-icon">&#x2705;</span>
            <span class="check-name">Connessione IBKR</span>
            <span class="check-val">LIVE</span>
          </li>
          <li class="pass">
            <span class="check-icon">&#x2705;</span>
            <span class="check-name">Observer Telegram</span>
            <span class="check-val">ON</span>
          </li>
          <li class="pass">
            <span class="check-icon">&#x2705;</span>
            <span class="check-name">Briefing ascoltato</span>
            <span class="check-val">09:20 &#x2014; 2 min 14 sec</span>
          </li>
          <li class="pass">
            <span class="check-icon">&#x2705;</span>
            <span class="check-name">Regime del giorno: NORMAL</span>
            <span class="check-val">sizing 100%</span>
          </li>
        </ul>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">WAR ROOM &#x2014; Apertura sessione</div>
        </div>
        <div class="screen-body">
<span class="dim">[09:20:00]</span> <span class="hlg">INFO</span>  session status: <span class="hlg">ACTIVE</span><br>
<span class="dim">[09:20:00]</span> <span class="hlg">INFO</span>  IBKR connection: <span class="hlg">LIVE</span> &#x2713;<br>
<span class="dim">[09:20:01]</span> <span class="hlg">INFO</span>  Observer Telegram: <span class="hlg">ON</span> &#x2713;<br>
          <div class="section">
            <div class="row"><span>Regime</span><span class="badge normal">&#x25cf; NORMAL</span></div>
            <div class="row"><span>Segnali pronti</span><span class="hlg">8</span></div>
            <div class="row"><span>Top segnale</span><span class="hl">SPY 490/485P</span></div>
          </div>
<span class="dim">[09:20:14]</span> <span class="hl">NARRATORE</span>  briefing generato &#x2713;<br>
<span class="dim hlt">&nbsp;&nbsp;&#x25b6;  "Regime stabile. 8 opportunit&#xe0;.</span><br>
<span class="dim hlt">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Top: SPY put spread 490/485,</span><br>
<span class="dim hlt">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;score 7.82. IVR=42, DTE=35."</span><br>
          <div class="section">
            <div class="row"><span>Posizioni aperte</span><span class="hlt">3</span></div>
            <div class="row"><span>P&amp;L aperto</span><span class="hlg">+$312</span></div>
            <div class="row"><span>Capitale disponibile</span><span class="hlb">$2.087</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

'''

# Replace the opening of the stage (remove "active" from step 6 which was step 1)
content = content.replace(
    '<div class="step active" data-step="6">',
    '<div class="step" data-step="6">'
)
# Insert ANTE steps right after <div class="stage">
content = content.replace('<div class="stage">\n\n  <!-- STEP 1 -->', '<div class="stage">\n\n' + ante_html + '  <!-- STEP 6 —', 1)
# Fix the comment that was "<!-- STEP 1 -->" and is now split
# Actually the replace above is wrong, let me fix:
# The original has: <div class="stage">\n\n  <!-- STEP 1 -->\n  <div class="step active" data-step="6">
# After our earlier replacement the active was removed, and now data-step is 6
# Let's check what we have and fix
if '<!-- STEP 6 —' not in content:
    # The comment was <!-- STEP 1 --> originally, now data-step is 6 but comment unchanged
    content = content.replace(
        '<div class="stage">\n\n  <!-- STEP 1 -->\n  <div class="step" data-step="6">',
        '<div class="stage">\n\n' + ante_html + '  <!-- STEP 6 — Ricezione dati -->\n  <div class="step" data-step="6">'
    )

# ═══════════════════════════════════════════════════════
# 3. INSERT step 22 (Posizioni & P&L) after step 21 (Tier Roadmap)
# ═══════════════════════════════════════════════════════
step22_html = '''
  <!-- STEP 22 — OP/METRICHE: Posizioni & P&L -->
  <div class="step" data-step="22">
    <div class="step-header">
      <div class="step-icon">&#x1f4c8;</div>
      <div class="step-meta">
        <div class="step-label">Step 22 &#x2014; METRICHE</div>
        <div class="step-title">Il portafoglio in un colpo d'occhio</div>
        <div class="step-subtitle">Snapshot in tempo reale &#x2014; aperto, chiuso, disponibile</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Stato portafoglio</div>
        <div class="description">
          La WAR ROOM aggrega in un pannello dedicato tutte le metriche operative: posizioni aperte con P&amp;L mark-to-market, capitale impegnato, capitale disponibile per nuove operazioni, e il contatore verso il gate Kelly N&#x2265;50.
        </div>
        <div class="data-grid">
          <div class="data-item">
            <div class="data-label">Posizioni aperte</div>
            <div class="data-value teal">3</div>
            <div class="data-sub">spread + wheel IWM</div>
          </div>
          <div class="data-item">
            <div class="data-label">P&amp;L aperto</div>
            <div class="data-value ok">+$312</div>
            <div class="data-sub">mark-to-market</div>
          </div>
          <div class="data-item">
            <div class="data-label">P&amp;L cumulato</div>
            <div class="data-value ok">+$1.240</div>
            <div class="data-sub">da inizio paper</div>
          </div>
          <div class="data-item">
            <div class="data-label">Capitale impegnato</div>
            <div class="data-value warn">$2.413</div>
            <div class="data-sub">53% del totale</div>
          </div>
          <div class="data-item">
            <div class="data-label">Capitale libero</div>
            <div class="data-value ok">$2.087</div>
            <div class="data-sub">disponibile subito</div>
          </div>
          <div class="data-item">
            <div class="data-label">Trade verso Kelly</div>
            <div class="data-value warn">47 / 50</div>
            <div class="data-sub">3 trade al gate</div>
          </div>
        </div>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">WAR ROOM &#x2014; Pannello Portafoglio</div>
        </div>
        <div class="screen-body">
          <div class="section">
            <div class="row"><span class="hl">SPY 490/485P</span><span class="badge pass">APERTA</span></div>
            <div class="row"><span class="dim">P&amp;L aperto</span><span class="hlg">+$89</span></div>
            <div class="row"><span class="dim">DTE rimasti</span><span>35</span></div>
          </div>
          <div class="section">
            <div class="row"><span class="hl">IWM Wheel</span><span class="badge blue">OPEN_CSP</span></div>
            <div class="row"><span class="dim">P&amp;L aperto</span><span class="hlg">+$72</span></div>
            <div class="row"><span class="dim">Ciclo #</span><span>4</span></div>
          </div>
          <div class="section">
            <div class="row"><span>Capitale libero</span><span class="hlg">$2.087 (47%)</span></div>
            <div class="row"><span>Kelly gate</span><span class="hly">47/50 &#x2014; 3 mancanti</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

'''

# Insert before </div><!-- /stage -->
content = content.replace('</div><!-- /stage -->', step22_html + '</div><!-- /stage -->')

# ═══════════════════════════════════════════════════════
# 4. INSERT steps 23-24 (POST) before </div><!-- /stage -->
# ═══════════════════════════════════════════════════════
post_html = '''  <!-- STEP 23 — POST/CHIUSURA: La sessione si chiude -->
  <div class="step" data-step="23">
    <div class="step-header">
      <div class="step-icon">&#x1f306;</div>
      <div class="step-meta">
        <div class="step-label">Step 23 &#x2014; CHIUSURA</div>
        <div class="step-title">La sessione si chiude</div>
        <div class="step-subtitle">16:00 ET &#x2014; mercati chiusi</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Chiusura automatica</div>
        <div class="description">
          Alle 16:00 lo scheduler avvia la chiusura automatica della sessione. I log vengono consolidati, l'observer invia la notifica su Telegram. Le posizioni aperte rimangono monitorate e attive per i giorni successivi — non vengono chiuse automaticamente.
        </div>
        <div class="data-grid">
          <div class="data-item">
            <div class="data-label">Sessione</div>
            <div class="data-value ok">CLOSED</div>
            <div class="data-sub">chiusura automatica 16:00</div>
          </div>
          <div class="data-item">
            <div class="data-label">Trade eseguiti oggi</div>
            <div class="data-value blue">2</div>
            <div class="data-sub">aperti in sessione</div>
          </div>
          <div class="data-item">
            <div class="data-label">P&amp;L sessione</div>
            <div class="data-value ok">+$147</div>
            <div class="data-sub">compresi trade aperti</div>
          </div>
          <div class="data-item">
            <div class="data-label">Posizioni aperte</div>
            <div class="data-value teal">3</div>
            <div class="data-sub">monitorate anche domani</div>
          </div>
        </div>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">session_logs &#x2014; EOD</div>
        </div>
        <div class="screen-body">
<span class="dim">[16:00:00.012]</span> <span class="hlg">INFO</span>  market close detected<br>
<span class="dim">[16:00:00.015]</span> <span class="hlg">INFO</span>  session ending &#x2014; scheduler<br>
<span class="dim">[16:00:00.018]</span> <span class="hlt">META</span>  trade eseguiti: 2<br>
<span class="dim">[16:00:00.019]</span> <span class="hlt">META</span>  session P&amp;L = <span class="hlg">+$147.00</span><br>
<span class="dim">[16:00:00.024]</span> <span class="hlg">INFO</span>  session status &#x2192; <span class="hl">CLOSED</span><br>
<span class="dim">[16:00:00.031]</span> <span class="hlg">INFO</span>  observer: notifica Telegram inviata<br>
          <div class="section">
            <div class="row"><span>Durata sessione</span><span class="hlt">6h 31m</span></div>
            <div class="row"><span>Prossima sessione</span><span class="hl">domani 09:28</span></div>
            <div class="row"><span>Kill switch</span><span class="hlg">OFF &#x2713;</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- STEP 24 — POST/REPORT: Il report di fine giornata -->
  <div class="step" data-step="24">
    <div class="step-header">
      <div class="step-icon">&#x1f4ca;</div>
      <div class="step-meta">
        <div class="step-label">Step 24 &#x2014; REPORT</div>
        <div class="step-title">Il giorno in numeri</div>
        <div class="step-subtitle">16:05 ET &#x2014; consolidamento completato</div>
      </div>
    </div>
    <div class="step-body">
      <div class="panel">
        <div class="panel-title">Journal e statistiche aggiornati</div>
        <div class="description">
          Il journal registra tutti gli eventi della sessione. Le posizioni Wheel rimangono attive e monitorate. La History Readiness avanza verso il gate Kelly. Domani il ciclo ricomincia: scheduler alle 09:28, ingest, analisi, briefing.
        </div>
        <div class="data-grid">
          <div class="data-item">
            <div class="data-label">Trade chiusi oggi</div>
            <div class="data-value ok">1</div>
            <div class="data-sub">SPY 490/485P &#x2192; +$64</div>
          </div>
          <div class="data-item">
            <div class="data-label">Trade chiusi totali</div>
            <div class="data-value blue">48</div>
            <div class="data-sub">su 50 richiesti per Kelly</div>
          </div>
          <div class="data-item">
            <div class="data-label">P&amp;L cumulato</div>
            <div class="data-value ok">+$1.304</div>
            <div class="data-sub">da inizio paper</div>
          </div>
          <div class="data-item">
            <div class="data-label">History Readiness</div>
            <div class="data-value warn">69%</div>
            <div class="data-sub">34/50 giorni &#x2014; Kelly ancora bloccato</div>
          </div>
          <div class="data-item full">
            <div class="data-label">Domani</div>
            <div class="data-value orange">Scheduler 09:28</div>
            <div class="data-sub">il ciclo ricomincia &#x2014; ingest &#x2192; analisi &#x2192; segnali &#x2192; briefing</div>
          </div>
        </div>
      </div>
      <div class="screen">
        <div class="screen-bar">
          <div class="screen-dot r"></div><div class="screen-dot y"></div><div class="screen-dot g"></div>
          <div class="screen-title">report_eod &#x2014; 15 aprile</div>
        </div>
        <div class="screen-body">
<span class="dim">[16:05:00]</span> <span class="hlg">INFO</span>  EOD report generating...<br>
          <div class="section">
            <div class="dim" style="font-size:10px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px">Sessione del 15 aprile</div>
            <div class="row"><span class="dim">trade_aperti</span><span>2</span></div>
            <div class="row"><span class="dim">trade_chiusi</span><span>1</span></div>
            <div class="row"><span class="dim">pnl_sessione</span><span class="hlg">+$147.00</span></div>
            <div class="row"><span class="dim">pnl_cumulato</span><span class="hlg">+$1.304</span></div>
          </div>
          <div class="section">
            <div class="row"><span class="dim">history_readiness</span><span class="hly">69% (34/50g)</span></div>
            <div class="row"><span class="dim">kelly_gate</span><span class="hlr">DISABILITATO</span></div>
            <div class="row"><span class="dim">trade_storici</span><span class="hly">48/50</span></div>
          </div>
<span class="dim">[16:05:01]</span> <span class="hlg">INFO</span>  journal updated &#x2713;<br>
<span class="dim">[16:05:01]</span> <span class="hlg">INFO</span>  domani: scheduler 09:28 &#x2192;<br>
<span class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ingest &#x2192; analisi &#x2192; segnali &#x2192; briefing</span><br>
        </div>
      </div>
    </div>
  </div>

'''
content = content.replace(step22_html + '</div><!-- /stage -->', step22_html + post_html + '</div><!-- /stage -->')

# ═══════════════════════════════════════════════════════
# 5. UPDATE header stot
# ═══════════════════════════════════════════════════════
content = content.replace('<span id="stot">16</span>', '<span id="stot">24</span>')

# ═══════════════════════════════════════════════════════
# 6. REPLACE footer with 2-level design
# ═══════════════════════════════════════════════════════
# Remove old dots div and footer, build new
old_footer_start = '\n<footer>'
old_footer_end = '</footer>'
footer_idx_start = content.rfind('\n<footer>')
footer_idx_end = content.find('</footer>', footer_idx_start) + len('</footer>')
old_footer_block = content[footer_idx_start:footer_idx_end]

new_footer = '''
<footer>
  <button class="nav-btn" id="btnPrev" onclick="navigate(-1)" disabled>&#x2190; Indietro</button>
  <div class="phase-container">
    <div class="parent-phases">
      <div class="parent-phase parent-active" data-parent="ante" style="flex:5">
        <span class="parent-lbl">ANTE</span><div class="parent-brk"></div>
      </div>
      <div class="parent-phase" data-parent="op" style="flex:17">
        <span class="parent-lbl">OP</span><div class="parent-brk"></div>
      </div>
      <div class="parent-phase" data-parent="post" style="flex:2">
        <span class="parent-lbl">POST</span><div class="parent-brk"></div>
      </div>
    </div>
    <div class="sub-phases">
      <div class="phase-group phase-active" data-phase="dati">
        <div class="phase-head"><span class="phase-lbl">DATI</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-dati"></div>
      </div>
      <div class="phase-group" data-phase="analisi">
        <div class="phase-head"><span class="phase-lbl">ANALISI</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-analisi"></div>
      </div>
      <div class="phase-group" data-phase="briefing">
        <div class="phase-head"><span class="phase-lbl">BRIEFING</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-briefing"></div>
      </div>
      <div class="phase-group" data-phase="trading">
        <div class="phase-head"><span class="phase-lbl">TRADING</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-trading"></div>
      </div>
      <div class="phase-group" data-phase="wheel">
        <div class="phase-head"><span class="phase-lbl">WHEEL</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-wheel"></div>
      </div>
      <div class="phase-group" data-phase="metriche">
        <div class="phase-head"><span class="phase-lbl">METRICHE</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-metriche"></div>
      </div>
      <div class="phase-group" data-phase="chiusura">
        <div class="phase-head"><span class="phase-lbl">CHIUSURA</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-chiusura"></div>
      </div>
      <div class="phase-group" data-phase="report">
        <div class="phase-head"><span class="phase-lbl">REPORT</span><div class="phase-brk"></div></div>
        <div class="phase-dots" id="dots-report"></div>
      </div>
    </div>
  </div>
  <button class="nav-btn primary" id="btnNext" onclick="navigate(1)">Avanti &#x2192;</button>
</footer>'''

content = content[:footer_idx_start] + new_footer + content[footer_idx_end:]

# ═══════════════════════════════════════════════════════
# 7. REPLACE TOC
# ═══════════════════════════════════════════════════════
toc_start = content.find('<!-- ── TOC panel ── -->')
toc_end = content.find('</nav>', toc_start) + len('</nav>')

new_toc = '''<!-- ── TOC panel ── -->
<nav class="toc-panel" id="tocPanel">
  <div class="toc-header">I Passi del Trade</div>
  <div class="toc-item active" data-step="1" onclick="goTo(1)">
    <span class="toc-num">1</span><span class="toc-icon">&#x1f319;</span>
    <span class="toc-name">Ingest pipeline</span>
  </div>
  <div class="toc-item" data-step="2" onclick="goTo(2)">
    <span class="toc-num">2</span><span class="toc-icon">&#x1f4da;</span>
    <span class="toc-name">Consolidamento</span>
  </div>
  <div class="toc-item" data-step="3" onclick="goTo(3)">
    <span class="toc-num">3</span><span class="toc-icon">&#x1f52c;</span>
    <span class="toc-name">Regime calcolato</span>
  </div>
  <div class="toc-item" data-step="4" onclick="goTo(4)">
    <span class="toc-num">4</span><span class="toc-icon">&#x26a1;</span>
    <span class="toc-name">Segnali pronti</span>
  </div>
  <div class="toc-item" data-step="5" onclick="goTo(5)">
    <span class="toc-num">5</span><span class="toc-icon">&#x1f305;</span>
    <span class="toc-name">Briefing &amp; apertura</span>
  </div>
  <div class="toc-item" data-step="6" onclick="goTo(6)">
    <span class="toc-num">6</span><span class="toc-icon">&#x1f4e1;</span>
    <span class="toc-name">Dato in arrivo</span>
  </div>
  <div class="toc-item" data-step="7" onclick="goTo(7)">
    <span class="toc-num">7</span><span class="toc-icon">&#x1f50d;</span>
    <span class="toc-name">I numeri</span>
  </div>
  <div class="toc-item" data-step="8" onclick="goTo(8)">
    <span class="toc-num">8</span><span class="toc-icon">&#x1f6a6;</span>
    <span class="toc-name">Filtri duri</span>
  </div>
  <div class="toc-item" data-step="9" onclick="goTo(9)">
    <span class="toc-num">9</span><span class="toc-icon">&#x2b50;</span>
    <span class="toc-name">Scoring</span>
  </div>
  <div class="toc-item" data-step="10" onclick="goTo(10)">
    <span class="toc-num">10</span><span class="toc-icon">&#x1f321;&#xfe0f;</span>
    <span class="toc-name">Regime</span>
  </div>
  <div class="toc-item" data-step="11" onclick="goTo(11)">
    <span class="toc-num">11</span><span class="toc-icon">&#x1f4cb;</span>
    <span class="toc-name">WAR ROOM</span>
  </div>
  <div class="toc-item" data-step="12" onclick="goTo(12)">
    <span class="toc-num">12</span><span class="toc-icon">&#x2705;</span>
    <span class="toc-name">Conferma</span>
  </div>
  <div class="toc-item" data-step="13" onclick="goTo(13)">
    <span class="toc-num">13</span><span class="toc-icon">&#x1f4c8;</span>
    <span class="toc-name">Trade aperto</span>
  </div>
  <div class="toc-item" data-step="14" onclick="goTo(14)">
    <span class="toc-num">14</span><span class="toc-icon">&#x1f3af;</span>
    <span class="toc-name">Exit candidate</span>
  </div>
  <div class="toc-item" data-step="15" onclick="goTo(15)">
    <span class="toc-num">15</span><span class="toc-icon">&#x1f3c1;</span>
    <span class="toc-name">Trade chiuso</span>
  </div>
  <div class="toc-item" data-step="16" onclick="goTo(16)">
    <span class="toc-num">16</span><span class="toc-icon">&#x1f504;</span>
    <span class="toc-name">Wheel &#x2014; ciclo</span>
  </div>
  <div class="toc-item" data-step="17" onclick="goTo(17)">
    <span class="toc-num">17</span><span class="toc-icon">&#x1f4b0;</span>
    <span class="toc-name">CSP &#x2014; vendita put</span>
  </div>
  <div class="toc-item" data-step="18" onclick="goTo(18)">
    <span class="toc-num">18</span><span class="toc-icon">&#x1f4e6;</span>
    <span class="toc-name">Assegnazione</span>
  </div>
  <div class="toc-item" data-step="19" onclick="goTo(19)">
    <span class="toc-num">19</span><span class="toc-icon">&#x1f4de;</span>
    <span class="toc-name">CC &#x2014; covered call</span>
  </div>
  <div class="toc-item" data-step="20" onclick="goTo(20)">
    <span class="toc-num">20</span><span class="toc-icon">&#x2705;</span>
    <span class="toc-name">Ciclo chiuso</span>
  </div>
  <div class="toc-item" data-step="21" onclick="goTo(21)">
    <span class="toc-num">21</span><span class="toc-icon">&#x1f5fa;&#xfe0f;</span>
    <span class="toc-name">Tier Roadmap</span>
  </div>
  <div class="toc-item" data-step="22" onclick="goTo(22)">
    <span class="toc-num">22</span><span class="toc-icon">&#x1f4c8;</span>
    <span class="toc-name">Posizioni &amp; P&amp;L</span>
  </div>
  <div class="toc-item" data-step="23" onclick="goTo(23)">
    <span class="toc-num">23</span><span class="toc-icon">&#x1f306;</span>
    <span class="toc-name">Sessione chiusa</span>
  </div>
  <div class="toc-item" data-step="24" onclick="goTo(24)">
    <span class="toc-num">24</span><span class="toc-icon">&#x1f4ca;</span>
    <span class="toc-name">Report di fine giornata</span>
  </div>
</nav>'''

content = content[:toc_start] + new_toc + content[toc_end:]

# ═══════════════════════════════════════════════════════
# 8. ADD CSS for 2-level phase bar + fix padding
# ═══════════════════════════════════════════════════════
phase_css_addition = '''
  /* ── 2-level phase bar ── */
  .phase-container { flex:1; display:flex; flex-direction:column; gap:1px; min-width:0; }
  .parent-phases { display:flex; gap:10px; align-items:flex-end; margin-bottom:1px; }
  .parent-phase { display:flex; flex-direction:column; align-items:center; min-width:0; }
  .parent-lbl { font-size:8px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:#333350; margin-bottom:2px; transition:color .25s; }
  .parent-brk { width:100%; height:4px; border-top:1px solid #282840; border-left:1px solid #282840; border-right:1px solid #282840; border-radius:2px 2px 0 0; transition:border-color .25s; }
  .parent-phase.parent-active .parent-lbl { color:rgba(255,109,0,.6); }
  .parent-phase.parent-active .parent-brk { border-color:rgba(255,109,0,.4); }
  .sub-phases { display:flex; gap:4px; }
'''
content = content.replace('</style>', phase_css_addition + '</style>', 1)
content = content.replace('padding-bottom: 80px;', 'padding-bottom: 110px;')

# ═══════════════════════════════════════════════════════
# 9. UPDATE JavaScript
# ═══════════════════════════════════════════════════════
old_js = '  const TOTAL = 16;\n  let current = 1;'
new_js = '  const TOTAL = 24;\n  let current = 1;'
content = content.replace(old_js, new_js)

# Replace dots builder and phase updater
old_build_dots = '''  // Build dots
  const dotsEl = document.getElementById("dots");
  for (let i = 1; i <= TOTAL; i++) {
    const d = document.createElement("div");
    d.className = "dot" + (i === 1 ? " active" : "");
    d.title = "Step " + i;
    d.onclick = () => goTo(i);
    dotsEl.appendChild(d);
  }'''

new_build_dots = '''  // Sub-phase → step mapping
  const SUB_PHASES = {
    dati:     [1,2], analisi: [3,4], briefing: [5],
    trading:  [6,7,8,9,10,11,12,13,14,15],
    wheel:    [16,17,18,19,20], metriche: [21,22],
    chiusura: [23], report: [24]
  };
  const PARENT_PHASES = {
    ante: [1,2,3,4,5],
    op:   [6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22],
    post: [23,24]
  };

  function updatePhase() {
    Object.entries(SUB_PHASES).forEach(([ph, steps]) => {
      const g = document.querySelector(`.phase-group[data-phase="${ph}"]`);
      if (g) g.classList.toggle('phase-active', steps.includes(current));
    });
    Object.entries(PARENT_PHASES).forEach(([p, steps]) => {
      const e = document.querySelector(`.parent-phase[data-parent="${p}"]`);
      if (e) e.classList.toggle('parent-active', steps.includes(current));
    });
  }

  // Build dots in sub-phase groups
  Object.entries(SUB_PHASES).forEach(([phase, steps]) => {
    const container = document.getElementById(`dots-${phase}`);
    if (!container) return;
    steps.forEach(step => {
      const d = document.createElement("div");
      d.className = "dot" + (step === 1 ? " active" : "");
      d.dataset.step = step;
      d.title = "Step " + step;
      d.onclick = () => goTo(step);
      container.appendChild(d);
    });
  });'''

content = content.replace(old_build_dots, new_build_dots)

# Update goTo dots section (old version used index i+1)
old_dots_update = '''    // dots
    document.querySelectorAll(".dot").forEach((d, i) => {
      d.classList.remove("active","done");
      if (i + 1 === current) d.classList.add("active");
      else if (i + 1 < current) d.classList.add("done");
    });'''
new_dots_update = '''    // dots
    document.querySelectorAll(".dot").forEach(d => {
      const s = parseInt(d.dataset.step);
      d.classList.remove("active","done");
      if (s === current) d.classList.add("active");
      else if (s < current) d.classList.add("done");
    });
    updatePhase();'''
content = content.replace(old_dots_update, new_dots_update)

# ═══════════════════════════════════════════════════════
# WRITE OUTPUT
# ═══════════════════════════════════════════════════════
with open(SRC, 'w', encoding='utf-8') as f:
    f.write(content)

# VERIFY
import re
stage_steps = sorted(set(int(s) for s in re.findall(r'<div class="step[^"]*" data-step="(\d+)"', content)))
toc_steps   = sorted(set(int(s) for s in re.findall(r'class="toc-item[^"]*" data-step="(\d+)"', content)))
total       = re.search(r'const TOTAL = (\d+)', content)
stot        = re.search(r'id="stot">(\d+)', content)
print(f"Stage steps ({len(stage_steps)}): {stage_steps}")
print(f"TOC steps   ({len(toc_steps)}):   {toc_steps}")
print(f"JS TOTAL: {total.group(1) if total else 'MISSING'}")
print(f"Header stot: {stot.group(1) if stot else 'MISSING'}")
missing = set(range(1,25)) - set(stage_steps)
print(f"Missing from stage: {sorted(missing) or 'NONE'}")
