\<!DOCTYPE html>

\<html lang="en">

\<head>

\<meta charset="UTF-8">

\<meta name="viewport" content="width=device-width, initial-scale=1.0">

\<title>TrimAURA — Minimal Templates + Ranked Results\</title>

\<link href="https\://fonts.googleapis.com/css2?family=Inter:wght\@400;500;600;700;800;900\&family=IBM+Plex+Mono:wght\@400;500\&display=swap" rel="stylesheet">

\<style>

  :root{

    --bg:#EDE9E3; --card:#FBF9F6; --hairline:#DDD5C8;

    --ink:#1C1917; --ink-dim:#8A8378;

    --gold:#C9A056; --gold-deep:#9C7530;

    --green:#3A9D5E;

  }

  \*{ box-sizing:border-box; -webkit-tap-highlight-color: transparent; }

  html,body{ margin:0; background:#DCD3C4; }

  body{ font-family:'Inter', sans-serif; color:var(--ink); display:flex; justify-content:center; align-items:center; padding:50px 20px; }

  svg.icon{ display:block; stroke:currentColor; fill:none; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; }



  .frame{ width:390px; height:844px; background:var(--bg); border-radius:40px; overflow:hidden; position:relative; border:9px solid #fff; box-shadow:0 40px 80px rgba(0,0,0,0.25); }

  .scroll{ height:100%; overflow-y:auto; padding: 26px 22px 40px; }

  .scroll::-webkit-scrollbar{ display:none; }



  .profile{ text-align:center; margin-bottom:22px; }

  .avatar{ width:56px; height:56px; border-radius:50%; margin:0 auto 12px; background:#1C1917; display:flex; align-items:center; justify-content:center; }

  .avatar-mark{ width:17px; height:17px; background:var(--gold); clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%); }

  .p-name{ font-size:22px; font-weight:800; }

  .p-sub{ font-size:12px; color:var(--ink-dim); margin-top:4px; }



  .stats-row{ display:flex; justify-content:center; gap:36px; margin:20px 0 26px; }

  .stat{ text-align:center; }

  .stat-num{ font-size:22px; font-weight:800; }

  .stat-label{ font-size:9.5px; color:var(--ink-dim); font-weight:600; letter-spacing:0.3px; margin-top:2px; }

  .stat-sep{ width:1px; background:var(--hairline); }



  .section-label{ font-size:11px; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; color:var(--ink-dim); margin:22px 2px 12px; display:flex; justify-content:space-between; }

  .section-label span.hint{ color: var(--gold-deep); font-weight:600; }



  .url-field{ background:var(--card); border:1px solid var(--hairline); border-radius:30px; padding:15px 18px; font-size:13px; color:var(--ink-dim); }

  .divider-or{ display:flex; align-items:center; gap:10px; margin:16px 0; font-size:10px; color:var(--ink-dim); font-weight:600; letter-spacing:1px; }

  .divider-or::before, .divider-or::after{ content:''; flex:1; height:1px; background:var(--hairline); }



  .upload-card{ background:var(--card); border:1.5px solid var(--green); border-radius:22px; padding:22px 18px; text-align:center; }

  .upload-icon{ width:40px; height:40px; border-radius:50%; margin:0 auto 10px; background:#F2EEE6; display:flex; align-items:center; justify-content:center; color:var(--ink); }

  .upload-filename{ font-family:'IBM Plex Mono', monospace; font-size:12.5px; font-weight:600; }

  .upload-check{ display:flex; align-items:center; justify-content:center; gap:6px; font-size:11px; color:var(--green); font-weight:700; margin-top:6px; }



  /\* ============ MINIMAL: single-row circular style picker ============ \*/

  .style-row{ display:flex; gap: 16px; padding: 2px 2px 4px; overflow-x:auto; }

  .style-row::-webkit-scrollbar{ display:none; }

  .style-chip{ display:flex; flex-direction:column; align-items:center; gap:6px; flex-shrink:0; }

  .style-swatch{

    width: 52px; height:52px; border-radius:50%; background-size:cover; background-position:center;

    position:relative;

  }

  .style-chip.active .style-swatch{ box-shadow: 0 0 0 2.5px #fff, 0 0 0 4.5px var(--gold); }

  .style-name{ font-size: 9.5px; font-weight:600; color: var(--ink-dim); }

  .style-chip.active .style-name{ color: var(--ink); font-weight:700; }



  .cta-row{ display:flex; gap:10px; margin-top:22px; }

  .cta{ flex:1; padding:16px; border-radius:30px; border:none; font-size:14px; font-weight:700; background: var(--ink); color:#fff; }

  .icon-btn{ width:52px; border-radius:30px; background:var(--card); border:1px solid var(--hairline); display:flex; align-items:center; justify-content:center; color:var(--ink); }



  /\* ============ RESULTS: Opus-style ranked vertical list ============ \*/

  .result-row{

    display:flex; align-items:center; gap: 14px; background: var(--card);

    border-radius: 18px; padding: 12px; margin-bottom: 10px; border: 1px solid var(--hairline);

  }

  .result-row\.top{ border-color: var(--gold); background: linear-gradient(155deg, #FBF9F6, #F7EFDC); }

  .result-score{

    display:flex; flex-direction:column; align-items:center; justify-content:center;

    width: 46px; flex-shrink:0;

  }

  .result-score-num{ font-size: 20px; font-weight:900; letter-spacing:-0.5px; color: var(--ink); }

  .result-row\.top .result-score-num{ color: var(--gold-deep); }

  .result-score-label{ font-size: 7.5px; color: var(--ink-dim); font-weight:700; letter-spacing:0.3px; text-transform:uppercase; margin-top:1px; }

  .result-thumb{

    width: 46px; height:62px; border-radius: 10px; background-size:cover; background-position:center; flex-shrink:0;

    position:relative;

  }

  .result-thumb::after{ content:''; position:absolute; inset:0; border-radius:10px; box-shadow: inset 0 0 0 1px rgba(0,0,0,0.06); }

  .result-play{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:#fff; opacity:0.85; }

  .result-body{ flex:1; min-width:0; }

  .result-title{ font-size: 12px; font-weight:700; line-height:1.3; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }

  .result-meta{ display:flex; gap:8px; margin-top:6px; }

  .result-meta span{ font-family:'IBM Plex Mono', monospace; font-size:9px; color: var(--ink-dim); }

  .result-action{

    width: 34px; height:34px; border-radius:50%; background: var(--ink); color:#fff;

    display:flex; align-items:center; justify-content:center; flex-shrink:0;

  }

  .result-row\.top .result-action{ background: var(--gold-deep); }

  .top-badge{

    position:absolute; top:-8px; left:12px; font-family:'IBM Plex Mono', monospace; font-size:8px; font-weight:700;

    color:#fff; background: var(--gold-deep); padding:3px 8px; border-radius:10px; letter-spacing:0.5px;

  }

  .result-row\.top{ position:relative; margin-top:14px; }



  .vault-item{ display:flex; align-items:center; gap:12px; padding:13px 0; border-bottom:1px solid var(--hairline); }

  .vault-thumb{ width:42px; height:42px; border-radius:12px; background-size:cover; flex-shrink:0; }

  .vault-name{ font-size:12.5px; font-weight:700; }

  .vault-meta{ font-family:'IBM Plex Mono', monospace; font-size:9.5px; color:var(--ink-dim); margin-top:3px; }

  .vault-status{ margin-left:auto; font-family:'IBM Plex Mono', monospace; font-size:9px; color:var(--ink-dim); background:#F2EEE6; padding:5px 10px; border-radius:20px; }

\</style>

\</head>

\<body>



\<div class="frame">

  \<div class="scroll">



    \<div class="profile">

      \<div class="avatar">\<div class="avatar-mark">\</div>\</div>

      \<div class="p-name">TrimAURA\</div>

      \<div class="p-sub">Upload once. Create endlessly.\</div>

    \</div>



    \<div class="stats-row">

      \<div class="stat">\<div class="stat-num">1,204\</div>\<div class="stat-label">CLIPS MADE\</div>\</div>

      \<div class="stat-sep">\</div>

      \<div class="stat">\<div class="stat-num">68%\</div>\<div class="stat-label">WATCH-THROUGH\</div>\</div>

      \<div class="stat-sep">\</div>

      \<div class="stat">\<div class="stat-num">10K\</div>\<div class="stat-label">REACHED\</div>\</div>

    \</div>



    \<div class="section-label">New short\</div>

    \<div class="url-field">Google Drive URL\</div>

    \<div class="divider-or">OR\</div>

    \<div class="upload-card">

      \<div class="upload-icon">\<svg class="icon" width="16" height="16" viewBox="0 0 24 24">\<path d="M12 16V6 M8 10l4-4 4 4"/>\<path d="M5 18h14"/>\</svg>\</div>

      \<div class="upload-filename">1000272478.mp4\</div>

      \<div class="upload-check">\<svg class="icon" width="10" height="10" viewBox="0 0 24 24">\<path d="M4 12l5 5L20 6"/>\</svg>READY TO PROCESS\</div>

    \</div>



    \<!-- ============ MINIMAL STYLE PICKER — 4 core templates only ============ -->

    \<div class="section-label" style="margin-top:24px;">Style \<span class="hint">Blur Pad\</span>\</div>

    \<div class="style-row">

      \<div class="style-chip active">

        \<div class="style-swatch" style="background-image:url('https\://picsum.photos/seed/blurpad/120/120')">\</div>

        \<div class="style-name">Blur Pad\</div>

      \</div>

      \<div class="style-chip">

        \<div class="style-swatch" style="background-image:url('https\://picsum.photos/seed/brandbold/120/120')">\</div>

        \<div class="style-name">Brand\</div>

      \</div>

      \<div class="style-chip">

        \<div class="style-swatch" style="background-image:url('https\://picsum.photos/seed/gamingneon/120/120')">\</div>

        \<div class="style-name">Gaming\</div>

      \</div>

      \<div class="style-chip">

        \<div class="style-swatch" style="background-image:url('https\://picsum.photos/seed/mrbeast/120/120')">\</div>

        \<div class="style-name">MrBeast\</div>

      \</div>

    \</div>



    \<div class="cta-row">

      \<button class="cta">Generate shorts\</button>

      \<div class="icon-btn">\<svg class="icon" width="16" height="16" viewBox="0 0 24 24">\<path d="M12 16V6 M8 10l4-4 4 4"/>\<path d="M5 18h14"/>\</svg>\</div>

      \<div class="icon-btn">\<svg class="icon" width="16" height="16" viewBox="0 0 24 24">\<circle cx="12" cy="12" r="4"/>\<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>\</svg>\</div>

    \</div>



    \<!-- ============ RESULTS: Opus-style ranked list ============ -->

    \<div class="section-label" style="margin-top:28px;">Results \<span class="hint">5 clips\</span>\</div>



    \<div class="result-row top">

      \<div class="top-badge">TOP PICK\</div>

      \<div class="result-score">

        \<div class="result-score-num">92\</div>

        \<div class="result-score-label">Score\</div>

      \</div>

      \<div class="result-thumb" style="background-image:url('https\://picsum.photos/seed/clip1/200/280')">

        \<svg class="icon result-play" width="14" height="14" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M8 5l11 7-11 7Z"/>\</svg>

      \</div>

      \<div class="result-body">

        \<div class="result-title">Why 100 Kids Got Their Biggest Wish…\</div>

        \<div class="result-meta">\<span>0:24\</span>\<span>Strong hook · 0–2s\</span>\</div>

      \</div>

      \<div class="result-action">\<svg class="icon" width="14" height="14" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M12 16V6 M8 10l4-4 4 4" transform="rotate(180 12 12)"/>\<path d="M5 18h14"/>\</svg>\</div>

    \</div>



    \<div class="result-row">

      \<div class="result-score">

        \<div class="result-score-num">88\</div>

        \<div class="result-score-label">Score\</div>

      \</div>

      \<div class="result-thumb" style="background-image:url('https\://picsum.photos/seed/clip2/200/280')">

        \<svg class="icon result-play" width="13" height="13" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M8 5l11 7-11 7Z"/>\</svg>

      \</div>

      \<div class="result-body">

        \<div class="result-title">The Moment LeBron Walked In\</div>

        \<div class="result-meta">\<span>0:31\</span>\<span>High retention\</span>\</div>

      \</div>

      \<div class="result-action">\<svg class="icon" width="14" height="14" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M12 16V6 M8 10l4-4 4 4" transform="rotate(180 12 12)"/>\<path d="M5 18h14"/>\</svg>\</div>

    \</div>



    \<div class="result-row">

      \<div class="result-score">

        \<div class="result-score-num">81\</div>

        \<div class="result-score-label">Score\</div>

      \</div>

      \<div class="result-thumb" style="background-image:url('https\://picsum.photos/seed/clip3/200/280')">

        \<svg class="icon result-play" width="13" height="13" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M8 5l11 7-11 7Z"/>\</svg>

      \</div>

      \<div class="result-body">

        \<div class="result-title">Kid's Reaction Says It All\</div>

        \<div class="result-meta">\<span>0:19\</span>\<span>Emotional peak\</span>\</div>

      \</div>

      \<div class="result-action">\<svg class="icon" width="14" height="14" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M12 16V6 M8 10l4-4 4 4" transform="rotate(180 12 12)"/>\<path d="M5 18h14"/>\</svg>\</div>

    \</div>



    \<div class="result-row">

      \<div class="result-score">

        \<div class="result-score-num">76\</div>

        \<div class="result-score-label">Score\</div>

      \</div>

      \<div class="result-thumb" style="background-image:url('https\://picsum.photos/seed/clip4/200/280')">

        \<svg class="icon result-play" width="13" height="13" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M8 5l11 7-11 7Z"/>\</svg>

      \</div>

      \<div class="result-body">

        \<div class="result-title">Closing Line — Call to Action\</div>

        \<div class="result-meta">\<span>0:27\</span>\<span>Good closer\</span>\</div>

      \</div>

      \<div class="result-action">\<svg class="icon" width="14" height="14" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M12 16V6 M8 10l4-4 4 4" transform="rotate(180 12 12)"/>\<path d="M5 18h14"/>\</svg>\</div>

    \</div>



    \<div class="result-row">

      \<div class="result-score">

        \<div class="result-score-num">70\</div>

        \<div class="result-score-label">Score\</div>

      \</div>

      \<div class="result-thumb" style="background-image:url('https\://picsum.photos/seed/clip5/200/280')">

        \<svg class="icon result-play" width="13" height="13" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M8 5l11 7-11 7Z"/>\</svg>

      \</div>

      \<div class="result-body">

        \<div class="result-title">Behind‑the‑Scenes Prep Moment\</div>

        \<div class="result-meta">\<span>0:22\</span>\<span>Context setup\</span>\</div>

      \</div>

      \<div class="result-action">\<svg class="icon" width="14" height="14" viewBox="0 0 24 24" style="stroke:#fff">\<path d="M12 16V6 M8 10l4-4 4 4" transform="rotate(180 12 12)"/>\<path d="M5 18h14"/>\</svg>\</div>

    \</div>



    \<div class="section-label" style="margin-top:24px;">Clip vault \<span class="hint">0 pending\</span>\</div>

    \<div class="vault-item">

      \<div class="vault-thumb" style="background-image:url('https\://picsum.photos/seed/vault1/100/100')">\</div>

      \<div>

        \<div class="vault-name">Short · Jul 30, 3:42 AM\</div>

        \<div class="vault-meta">5 CLIPS · 2H AGO\</div>

      \</div>

      \<div class="vault-status">READY\</div>

    \</div>



  \</div>

\</div>



\</body>

\</html>

