with open('static/index.html', encoding='utf-8') as f:
    html = f.read()

# Find the home section boundaries
start_marker = '  <!-- HOME VIEW -->'
end_marker = '  <!-- LOGIN VIEW -->'

start_idx = html.find(start_marker)
end_idx = html.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print('ERROR: markers not found')
    print('start:', start_idx, 'end:', end_idx)
    exit(1)

print(f'Found home section: chars {start_idx}..{end_idx}')

new_home = '''  <!-- HOME VIEW -->
  <section id="view-home" class="view-content active">

    <!-- Hero -->
    <div class="hero">
      <span class="badge badge-purple" style="margin-bottom:1rem; font-size:0.75rem; padding:0.3rem 0.8rem">✦ AI-POWERED ACADEMIC PLATFORM</span>
      <h2>Automate Your Research Pipeline</h2>
      <p>From literature discovery to LaTeX export — powered by Gemini, Perplexity &amp; OpenAI for high-fidelity survey papers.</p>
      <div style="display:flex; gap:0.6rem; justify-content:center; flex-wrap:wrap; margin-bottom:1.75rem">
        <span style="background:rgba(255,255,255,0.12); color:#e0e7ff; font-size:0.75rem; padding:0.25rem 0.75rem; border-radius:9999px; border:1px solid rgba(255,255,255,0.2)">🔍 Paper Discovery</span>
        <span style="background:rgba(255,255,255,0.12); color:#e0e7ff; font-size:0.75rem; padding:0.25rem 0.75rem; border-radius:9999px; border:1px solid rgba(255,255,255,0.2)">🧠 AI Synthesis</span>
        <span style="background:rgba(255,255,255,0.12); color:#e0e7ff; font-size:0.75rem; padding:0.25rem 0.75rem; border-radius:9999px; border:1px solid rgba(255,255,255,0.2)">✍️ Auto Draft</span>
        <span style="background:rgba(255,255,255,0.12); color:#e0e7ff; font-size:0.75rem; padding:0.25rem 0.75rem; border-radius:9999px; border:1px solid rgba(255,255,255,0.2)">📄 LaTeX Export</span>
      </div>
      <div class="hero-btns">
        <button class="btn btn-primary" style="font-size:0.95rem; padding:0.65rem 1.5rem" onclick="token ? switchView('topics') : switchView('login')">🚀 Get Started</button>
        <button class="btn" style="background:rgba(255,255,255,0.15); color:white; border:1.5px solid rgba(255,255,255,0.3); font-size:0.95rem; padding:0.65rem 1.5rem; backdrop-filter:blur(4px)" onclick="document.getElementById('home-news-section').scrollIntoView({behavior:'smooth'})">📰 Latest Updates</button>
      </div>
    </div>

    <!-- Lab info bar -->
    <div id="home-lab-bar" style="display:none; align-items:center; gap:1rem; padding:0.9rem 1.25rem; background:white; border-radius:14px; border:1px solid rgba(99,102,241,0.15); margin-bottom:2rem; flex-wrap:wrap; box-shadow:0 2px 12px rgba(99,102,241,0.08)">
      <div style="width:44px; height:44px; background:linear-gradient(135deg,#6366f1,#8b5cf6); border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:1.4rem; flex:0 0 auto; box-shadow:0 2px 8px rgba(99,102,241,0.3)">🏛️</div>
      <div style="flex:1; min-width:0">
        <div id="home-lab-name" style="font-weight:800; font-size:1rem; color:var(--text-main)"></div>
        <div id="home-lab-desc" style="font-size:0.78rem; color:var(--text-muted); margin-top:0.1rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap"></div>
      </div>
      <div id="home-stats-grid" style="display:flex; gap:0.65rem; flex-wrap:wrap; flex:0 0 auto"></div>
    </div>

    <!-- Latest News (full width) -->
    <div id="home-news-section" style="margin-bottom:2.5rem">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem">
        <h2 style="font-size:1.15rem; font-weight:800; display:flex; align-items:center; gap:0.65rem; color:var(--text-main)">
          <span style="width:34px; height:34px; background:linear-gradient(135deg,#f59e0b,#d97706); border-radius:9px; display:inline-flex; align-items:center; justify-content:center; font-size:1rem; box-shadow:0 2px 6px rgba(245,158,11,0.35); flex:0 0 auto">📰</span>
          Latest News
        </h2>
        <span id="home-news-count" style="font-size:0.75rem; color:var(--text-muted); background:#f5f3ff; padding:0.2rem 0.65rem; border-radius:9999px; border:1px solid #e0e7ff"></span>
      </div>
      <div id="home-news-list" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:1rem"></div>
      <div id="home-news-pagination" style="display:flex; gap:0.5rem; justify-content:center; margin-top:1.25rem; flex-wrap:wrap"></div>
    </div>

    <!-- Lab Members (full width, groups stacked vertically) -->
    <div id="home-members-section">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem">
        <h2 style="font-size:1.15rem; font-weight:800; display:flex; align-items:center; gap:0.65rem; color:var(--text-main)">
          <span style="width:34px; height:34px; background:linear-gradient(135deg,#06b6d4,#0891b2); border-radius:9px; display:inline-flex; align-items:center; justify-content:center; font-size:1rem; box-shadow:0 2px 6px rgba(6,182,212,0.35); flex:0 0 auto">👥</span>
          Lab Members
        </h2>
        <span id="home-members-total" style="font-size:0.75rem; color:var(--text-muted); background:#f5f3ff; padding:0.2rem 0.65rem; border-radius:9999px; border:1px solid #e0e7ff"></span>
      </div>
      <div id="home-members-list"></div>
    </div>

  </section>

'''

html = html[:start_idx] + new_home + html[end_idx:]

with open('static/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Done. New lines:', html.count('\n'))
