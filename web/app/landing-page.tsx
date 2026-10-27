"use client";

import { useState } from "react";
import { AuthPanel } from "./auth-panel";

type AuthMode = "login" | "register";
type User = { id: string; full_name: string | null; email: string; created_at: string };

const features = [
  {
    number: "01",
    icon: "notebook",
    title: "A journal with context",
    description:
      "Bring the setup, execution, emotions, and outcome together in one searchable trade history.",
  },
  {
    number: "02",
    icon: "target",
    title: "Plan before the fill",
    description:
      "Write down your thesis and risk before entering, then compare your decisions with the original plan.",
  },
  {
    number: "03",
    icon: "chart",
    title: "See the process clearly",
    description:
      "Review realized P&L, win rate, and performance over time without losing sight of the decisions behind them.",
  },
  {
    number: "04",
    icon: "layers",
    title: "Keep records connected",
    description:
      "Manage accounts, import journal records, and use available MT5 and TradingView integrations when configured.",
  },
  {
    number: "05",
    icon: "spark",
    title: "Your edge, measured in R",
    description:
      "Expectancy, profit factor, drawdown and recovery, computed only from your own closed trades.",
  },
  {
    number: "06",
    icon: "layers",
    title: "Strategy & setup ranking",
    description:
      "See which strategies show an observed edge and which leak, with honest sample-size warnings.",
  },
  {
    number: "07",
    icon: "target",
    title: "Behavior & time insight",
    description:
      "Find patterns after losses, rule breaks, emotions, and the hours and days you trade best.",
  },
  {
    number: "08",
    icon: "check",
    title: "A personal roadmap",
    description:
      "Get 2–3 focus areas for the next 30 days and track your progress against them.",
  },
];

const resources = [
  {
    icon: "spark",
    title: "Getting started",
    description: "Set up your workspace and capture your first trade plan.",
    link: "#about",
    label: "See how it works",
  },
  {
    icon: "book",
    title: "The journal workflow",
    description: "Explore planning, journaling, and review in one connected loop.",
    link: "#features",
    label: "Explore features",
  },
  {
    icon: "help",
    title: "Frequently asked",
    description: "Learn how your account, trade records, and integrations work.",
    link: "#faq",
    label: "Read the answers",
  },
];

function Mark({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 1 4 17.5z" /><path d="M4 16.5A2.5 2.5 0 0 1 6.5 14H20M8 7h7" /></>,
    chart: <><path d="M4 19V5m0 14h17" /><path d="m7 15 4-4 3 2 5-6" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.6 9a2.5 2.5 0 1 1 4.2 1.8c-1.1.9-1.8 1.3-1.8 2.7M12 17h.01" /></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 1 1 8 0v3" /></>,
    notebook: <><path d="M6 3h12a2 2 0 0 1 2 2v16H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M8 8h8M8 12h8M8 16h5M4 7h2m-2 4h2m-2 4h2" /></>,
    spark: <><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z" /><path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" /></>,
    target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></>,
  };

  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.6"
      viewBox="0 0 24 24"
      width="20"
    >
      {paths[name] ?? paths.spark}
    </svg>
  );
}

function Brand() {
  return (
    <a aria-label="TradeIQ home" className="landing-brand" href="#">
      <span className="landing-brand-mark"><Mark name="chart" /></span>
      <span>Trade<span className="brand-accent">IQ</span></span>
    </a>
  );
}

function WorkspacePreview() {
  return (
    <div aria-label="Illustrative TradeIQ journal workspace preview" className="preview-frame">
      <div className="preview-window-bar">
        <div className="preview-dots"><i /><i /><i /></div>
        <span>TRADEIQ / OVERVIEW</span>
        <span className="preview-live"><i /> SYNCED</span>
      </div>
      <div className="preview-workspace">
        <aside className="preview-sidebar">
          <div className="preview-mini-brand"><span>IQ</span> TradeIQ</div>
          <div className="preview-side-label">WORKSPACE</div>
          <div className="preview-nav-item selected"><span>◫</span> Overview</div>
          <div className="preview-nav-item"><span>▤</span> Trade journal</div>
          <div className="preview-nav-item"><span>◎</span> Trade plans</div>
          <div className="preview-nav-item"><span>⌁</span> Analytics</div>
          <div className="preview-profile"><span>JD</span><div><b>My workspace</b><small>Personal</small></div></div>
        </aside>
        <div className="preview-main">
          <div className="preview-heading"><div><small>MONDAY, OCTOBER 23</small><b>Your trading overview</b></div><span>Last 30 days⌄</span></div>
          <div className="preview-stat-row">
            <div className="preview-stat"><small>NET P&amp;L</small><b>+$2,840.50</b><span>Illustrative data</span></div>
            <div className="preview-stat"><small>WIN RATE</small><b>64.8%</b><span>Illustrative data</span></div>
            <div className="preview-stat"><small>TRADES REVIEWED</small><b>28</b><span>Illustrative data</span></div>
          </div>
          <div className="preview-chart-card">
            <div className="preview-chart-heading"><div><b>Performance</b><small>Realized P&amp;L over time</small></div><span>30D&nbsp; ⌄</span></div>
            <div className="preview-chart">
              <div className="chart-y-labels"><span>$3k</span><span>$2k</span><span>$1k</span><span>$0</span></div>
              <svg aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 460 145">
                <defs><linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#56e0ae" stopOpacity=".22" /><stop offset="100%" stopColor="#56e0ae" stopOpacity="0" /></linearGradient></defs>
                <path d="M0 124 C25 120 30 96 55 104 S88 117 107 88 S140 92 159 81 S190 100 214 66 S245 76 267 59 S301 67 321 42 S350 62 368 35 S399 51 418 24 S440 36 460 13 V145 H0Z" fill="url(#chart-fill)" />
                <path d="M0 124 C25 120 30 96 55 104 S88 117 107 88 S140 92 159 81 S190 100 214 66 S245 76 267 59 S301 67 321 42 S350 62 368 35 S399 51 418 24 S440 36 460 13" fill="none" stroke="#56e0ae" strokeWidth="2.5" />
              </svg>
            </div>
            <div className="preview-chart-months"><span>OCT 01</span><span>OCT 08</span><span>OCT 15</span><span>OCT 23</span></div>
          </div>
          <div className="preview-trade-card">
            <div className="preview-trade-heading"><b>Recent trades</b><span>View journal <Mark name="arrow" /></span></div>
            <div className="preview-trade-row"><span className="trade-symbol">XAU</span><b>Gold · Long</b><small>Plan followed</small><strong>+$248.00</strong></div>
            <div className="preview-trade-row"><span className="trade-symbol alt">EUR</span><b>EUR/USD · Short</b><small>Needs review</small><strong className="trade-loss">−$72.50</strong></div>
          </div>
        </div>
      </div>
      <div className="preview-float-note"><span><Mark name="check" /></span><div><b>Your process, in focus</b><small>Plan · Execute · Review</small></div></div>
    </div>
  );
}

export function LandingPage({
  apiError,
  onAuthenticated,
  onRetry,
}: {
  apiError: string;
  onAuthenticated: (user: User) => void;
  onRetry: () => void;
}) {
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);

  function openAuth(mode: AuthMode) {
    setAuthMode(mode);
  }

  return (
    <main className="landing-page">
      <header className="landing-header">
        <div className="landing-header-inner">
          <Brand />
          <nav aria-label="Main navigation" className="landing-nav">
            <a href="#features">Features</a>
            <a href="#about">About</a>
            <a href="#resources">Resources</a>
          </nav>
          <div className="landing-header-actions">
            <button className="landing-signin" onClick={() => openAuth("login")}>
              Sign in
            </button>
            <button className="landing-button landing-button-primary header-cta" onClick={() => openAuth("register")}>
              Sign up <Mark name="arrow" />
            </button>
          </div>
        </div>
      </header>

      {apiError && (
        <div className="landing-api-warning" role="alert">
          <span>{apiError}</span>
          <button onClick={onRetry}>Retry connection</button>
        </div>
      )}

      <section className="landing-hero">
        <div className="landing-hero-glow" />
        <div className="landing-hero-copy">
          <span className="landing-kicker"><i /> A CLEARER WAY TO TRADE</span>
          <h1>Turn every trade into <span>your next edge.</span></h1>
          <p className="landing-hero-description">
            A trading journal built for the decisions behind the numbers. Plan with intention,
            capture what happened, and learn from every outcome.
          </p>
          <div className="landing-hero-actions">
            <button className="landing-button landing-button-primary" onClick={() => openAuth("register")}>
              Start your journal <Mark name="arrow" />
            </button>
            <a className="landing-button landing-button-quiet" href="#features">Explore the platform <span>↓</span></a>
          </div>
          <div className="landing-hero-points">
            <span><Mark name="lock" /> Private by design</span>
            <span><Mark name="check" /> Your process, your pace</span>
          </div>
        </div>
        <div className="landing-hero-visual">
          <div className="visual-orbit orbit-one" />
          <div className="visual-orbit orbit-two" />
          <WorkspacePreview />
        </div>
      </section>

      <div className="landing-proof-strip">
        <span>ONE CONNECTED WORKFLOW</span>
        <div><Mark name="target" /> Plan with intention</div><i />
        <div><Mark name="notebook" /> Journal the details</div><i />
        <div><Mark name="chart" /> Review with clarity</div>
      </div>

      <section className="landing-section features-section" id="features">
        <div className="landing-section-heading">
          <span className="landing-kicker">BUILT AROUND YOUR PROCESS</span>
          <h2>More than numbers.<br /><span>A better way to improve.</span></h2>
          <p>Every feature connects the choices you make to the results you see—so your review becomes part of the next plan.</p>
        </div>
        <div className="feature-grid">
          {features.map((feature) => (
            <article className="feature-card" key={feature.number}>
              <div className="feature-card-top"><span className="feature-icon"><Mark name={feature.icon} /></span><span>{feature.number}</span></div>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
              <span className="feature-card-line" />
            </article>
          ))}
        </div>
        <div className="feature-spotlight">
          <div className="spotlight-copy">
            <span className="landing-kicker">FROM INTENT TO INSIGHT</span>
            <h3>One master journal.<br /><span>One step forward.</span></h3>
            <p>Give each trade its full story—from the plan you made before entry to the lesson you take into your next session.</p>
            <button className="landing-text-link" onClick={() => openAuth("register")}>Create your account <Mark name="arrow" /></button>
          </div>
          <div className="spotlight-flow">
            <div><span>01</span><b>Plan</b><small>Define the setup</small><i /></div>
            <div><span>02</span><b>Record</b><small>Capture the trade</small><i /></div>
            <div><span>03</span><b>Review</b><small>Find the lesson</small><i /></div>
          </div>
        </div>
      </section>

      <section className="landing-section agent-section" id="agent">
        <div className="landing-section-heading">
          <span className="landing-kicker">EDGE INTELLIGENCE</span>
          <h2>Four questions. <span>Answered by your own data.</span></h2>
          <p>A calm workspace, not a wall of charts. Every number is scoped to your account and your trades.</p>
        </div>
        <div className="agent-grid">
          <article><span className="agent-q">01</span><h3>What is happening?</h3><p>Live account status, open positions and recent trade activity from MT5.</p></article>
          <article><span className="agent-q">02</span><h3>What does my data reveal?</h3><p>Expectancy, profit factor, strategy ranking, time and behavior analysis, MAE/MFE.</p></article>
          <article><span className="agent-q">03</span><h3>What should I work on?</h3><p>A personalized roadmap with the highest-impact focus areas.</p></article>
          <article><span className="agent-q">04</span><h3>Am I improving?</h3><p>Saved roadmaps, personal goals and rule experiments with honest evidence, plus a process score for reviews and rule adherence.</p></article>
        </div>
        <div className="agent-points"><span>Private per-user analysis</span><span>No outside AI sees your trades</span><span>Samples flagged until 30 trades</span><span>Associations, not advice</span></div>
      </section>

      <section className="landing-section about-section" id="about">
        <div className="about-visual">
          <div className="about-orbit"><div className="about-core"><span>IQ</span><small>YOUR PROCESS</small></div><i className="orbit-node node-one" /><i className="orbit-node node-two" /><i className="orbit-node node-three" /></div>
          <div className="about-caption"><Mark name="spark" /><span>Make every review count.</span></div>
        </div>
        <div className="about-copy">
          <span className="landing-kicker">WHY TRADEIQ</span>
          <h2>Better trading starts with <span>better questions.</span></h2>
          <p>Performance is more than a winning streak. TradeIQ gives you a thoughtful place to record your decisions, revisit your plan, and understand the habits behind your results.</p>
          <p>Version 2 adds Edge Intelligence on top of the journal: the same private workspace now shows where your edge is and where it leaks.</p>
          <p>It is designed to keep your trading story in one private workspace—clear enough to review, structured enough to learn from.</p>
          <div className="about-values">
            <div><Mark name="lock" /><span><b>Your data stays yours</b><small>Private workspace, secured account.</small></span></div>
            <div><Mark name="chart" /><span><b>Process over noise</b><small>See the context behind each outcome.</small></span></div>
          </div>
        </div>
      </section>

      <section className="landing-section resources-section" id="resources">
        <div className="landing-section-heading resources-heading">
          <span className="landing-kicker">RESOURCES</span>
          <h2>A good place to <span>begin.</span></h2>
          <p>Explore the workflow and get answers to common questions before your first review.</p>
        </div>
        <div className="resource-grid">
          {resources.map((resource) => (
            <a className="resource-card" href={resource.link} key={resource.title}>
              <span className="resource-icon"><Mark name={resource.icon} /></span>
              <span className="resource-card-copy"><b>{resource.title}</b><small>{resource.description}</small><span>{resource.label} <Mark name="arrow" /></span></span>
            </a>
          ))}
        </div>
        <div className="faq-block" id="faq">
          <div><span className="landing-kicker">QUICK ANSWERS</span><h3>Things traders ask.</h3></div>
          <div className="faq-list">
            <details><summary>What happens when I sign in?<span>+</span></summary><p>Your credentials are checked by the TradeIQ API. Once your session is confirmed, your private journal workspace opens.</p></details>
            <details><summary>What is Edge Intelligence?<span>+</span></summary><p>A per-user analytics layer that turns your closed trades, tags and reviews into expectancy, strategy ranking, behavior patterns and a roadmap. It uses only your data and does not give trading signals.</p></details>
            <details><summary>Why do some metrics show a dash?<span>+</span></summary><p>Metrics need recorded R-multiples. Nothing is estimated, and profit factor is hidden when accounts mix currencies.</p></details>
            <details><summary>Do I need to connect a broker?<span>+</span></summary><p>No. You can start with a manual journal. Account connections and integrations are optional and depend on your setup.</p></details>
            <details><summary>Is TradeIQ a trading or investment service?<span>+</span></summary><p>No. TradeIQ is a journaling and decision-review workspace, not financial advice or a broker.</p></details>
          </div>
        </div>
      </section>

      <section className="landing-final-cta">
        <span className="landing-kicker">YOUR NEXT SESSION STARTS HERE</span>
        <h2>Make room to <span>think clearly.</span></h2>
        <p>Start with a plan. Keep the full story. Learn as you go.</p>
        <button className="landing-button landing-button-primary" onClick={() => openAuth("register")}>Create your account <Mark name="arrow" /></button>
      </section>

      <footer className="landing-footer">
        <Brand />
        <span>Make every trade a chance to learn.</span>
        <div><a href="#features">Features</a><a href="#about">About</a><a href="#resources">Resources</a></div>
        <small>© 2026 TradeIQ. All rights reserved.</small>
      </footer>

      {authMode && (
        <AuthPanel
          apiError={apiError}
          initialMode={authMode}
          onAuthenticated={onAuthenticated}
          onClose={() => setAuthMode(null)}
          onRetry={onRetry}
        />
      )}
    </main>
  );
}
