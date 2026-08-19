\<!DOCTYPE html>

\<html lang="en">

\<head>

\<meta charset="UTF-8">

\<meta name="viewport" content="width=device-width, initial-scale=1.0">

\<title>TrimAURA — Minimal White, Animated\</title>

\<link href="https\://fonts.googleapis.com/css2?family=Inter:wght\@400;500;600;700;800\&family=IBM+Plex+Mono:wght\@400;500\&display=swap" rel="stylesheet">

\<style>

  :root{

    --ink:#1C1C1E; --ink-dim:#8E8E93; --hairline:#EDEDEF;

    --card:#FFFFFF; --bg:#FAFAFA;

    --accent:#C9A056;

  }

  \*{ box-sizing:border-box; }

  html,body{ margin:0; background:#E9E9EA; }

  body{

    font-family:'Inter', sans-serif; color:var(--ink);

    display:flex; justify-content:center; align-items:center;

    padding: 50px 20px; perspective: 1600px;

  }

  svg.icon{ display:block; stroke:currentColor; fill:none; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }



  .stage{ transform: rotateY(-6deg) rotateX(1deg); transform-style: preserve-3d; }

  .frame{

    width: 375px; height: 812px; background: var(--bg);

    border-radius: 42px; overflow:hidden; position:relative;

    border: 9px solid #fff;

    box-shadow: 0 45px 80px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.06);

  }

  .scroll{ height:100%; overflow-y:auto; padding: 22px 22px 40px; }

  .scroll::-webkit-scrollbar{ display:none; }



  /\* ---------- Entrance animation ---------- \*/

  @keyframes fadeUp{

    from{ opacity:0; transform: translateY(14px); }

    to{ opacity:1; transform: translateY(0); }

  }

  .reveal{ opacity:0; animation: fadeUp 0.6s cubic-bezier(.22,.61,.36,1) forwards; }



  .topbar{ display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px; }

  .icon-circle{

    width: 30px; height:30px; border-radius:50%; background:#fff;

    display:flex; align-items:center; justify-content:center; color: var(--ink);

    box-shadow: 0 2px 6px rgba(0,0,0,0.08);

    transition: transform 0.15s ease, box-shadow 0.15s ease;

  }

  .icon-circle:active{ transform: scale(0.9); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }



  .profile{ text-align:center; margin-bottom: 18px; }

  .avatar{

    width: 60px; height:60px; border-radius:50%; margin: 0 auto 10px; position:relative;

    background: linear-gradient(155deg, #2A2723, #111011);

    display:flex; align-items:center; justify-content:center;

    box-shadow: 0 6px 16px rgba(0,0,0,0.15);

  }

  .avatar::before{

    content:''; position:absolute; inset:-6px; border-radius:50%;

    border: 1px solid rgba(201,160,86,0.5);

    animation: breathe 3.2s ease-in-out infinite;

  }

  @keyframes breathe{

    0%,100%{ transform: scale(1); opacity:0.5; }

    50%{ transform: scale(1.12); opacity:0; }

  }

  .avatar-mark{ width:19px; height:19px; background: linear-gradient(155deg,#E8C778,#9C7530); clip-path: polygon(0% 25%, 100% 50%, 0% 75%); }

  .p-name{ font-size: 17px; font-weight:800; letter-spacing:-0.2px; }

  .p-sub{ font-size: 11px; color: var(--ink-dim); margin-top:3px; }



  .stats-row{ display:flex; justify-content:center; gap: 40px; margin: 16px 0 24px; }

  .stat{ text-align:center; }

  .stat-num{ font-size: 18px; font-weight:800; font-variant-numeric: tabular-nums; }

  .stat-label{ font-size: 9.5px; color: var(--ink-dim); margin-top:2px; }

  .stat-sep{ width:1px; background: var(--hairline); }



  .section-label{ font-size: 10.5px; font-weight:700; letter-spacing:0.4px; text-transform:uppercase; color: var(--ink-dim); margin: 22px 4px 12px; display:flex; justify-content:space-between; }

  .section-label span{ font-weight:600; color: var(--ink); }



  .card{

    background: var(--card); border-radius: 18px; border: 1px solid var(--hairline);

    transition: transform 0.15s ease, box-shadow 0.2s ease, border-color 0.2s ease;

  }

  .url-field{ padding: 14px 16px; font-size: 12.5px; color: var(--ink-dim); }

  .url-field:active{ transform: scale(0.99); }

  .divider-or{ display:flex; align-items:center; gap: 10px; margin: 14px 0; font-size: 9.5px; color: var(--ink-dim); font-weight:600; letter-spacing:1px; }

  .divider-or::before, .divider-or::after{ content:''; flex:1; height:1px; background: var(--hairline); }



  .upload-card{ padding: 20px 16px; text-align:center; border-color:#1C1C1E; box-shadow: 0 4px 14px rgba(0,0,0,0.06); }

  .upload-card:active{ transform: scale(0.98); }

  .upload-icon{ width:38px; height:38px; border-radius:50%; margin:0 auto 10px; background:#F2F2F3; display:flex; align-items:center; justify-content:center; color: var(--ink); }

  .upload-filename{ font-family:'IBM Plex Mono', monospace; font-size: 12px; font-weight:600; }

  .upload-check{ display:flex; align-items:center; justify-content:center; gap:5px; font-size: 9.5px; color:#5EA36E; margin-top:6px; font-weight:600; letter-spacing:0.3px; }

  .upload-check svg{ animation: checkPop 0.5s cubic-bezier(.34,1.56,.64,1) 0.7s backwards; }

  @keyframes checkPop{ from{ transform: scale(0); } to{ transform: scale(1); } }



  /\* Template grid \*/

  .grid{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }

  .thumb{

    aspect-ratio: 3/4; border-radius: 12px; position:relative; overflow:hidden;

    transition: transform 0.18s ease, box-shadow 0.18s ease;

  }

  .thumb:active{ transform: scale(0.94); }

  .thumb.active{ box-shadow: 0 0 0 2px var(--ink), 0 6px 16px rgba(0,0,0,0.18); animation: ringPulse 2.4s ease-in-out infinite; }

  @keyframes ringPulse{

    0%,100%{ box-shadow: 0 0 0 2px var(--ink), 0 6px 16px rgba(0,0,0,0.18); }

    50%{ box-shadow: 0 0 0 2px var(--ink), 0 6px 16px rgba(0,0,0,0.18), 0 0 0 6px rgba(28,28,30,0.06); }

  }

  .thumb-label{ position:absolute; bottom:7px; left:7px; right:7px; font-size: 9px; color:#fff; font-weight:700; text-shadow: 0 1px 3px rgba(0,0,0,0.5); }



  /\* CTA \*/

  .cta-row{ display:flex; gap: 10px; margin-top: 22px; }

  .cta{

    flex:1; padding: 15px; border-radius: 16px; border:none; background: var(--ink); color:#fff;

    font-size: 13.5px; font-weight:700; position:relative; overflow:hidden;

    transition: transform 0.12s ease;

  }

  .cta::after{

    content:''; position:absolute; top:0; left:-40%; width:30%; height:100%;

    background: linear-gradient(115deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.18) 50%, rgba(255,255,255,0) 100%);

    animation: shine 3.5s ease-in-out infinite;

  }

  @keyframes shine{ 0%{ left:-40%; } 35%{ left: 130%; } 100%{ left:130%; } }

  .cta:active{ transform: scale(0.97); }

  .settings-btn{ width: 50px; border-radius: 16px; background:#fff; border:1px solid var(--hairline); display:flex; align-items:center; justify-content:center; color: var(--ink); transition: transform 0.12s ease; }

  .settings-btn:active{ transform: scale(0.9) rotate(25deg); }



  .progress-track{ height:4px; background:#EFEFEF; border-radius:10px; margin: 16px 0 6px; overflow:hidden; }

  .progress-fill{

    height:100%; width:4%; border-radius:10px;

    background: linear-gradient(90deg, #1C1C1E, #4A4A4C, #1C1C1E);

    background-size: 200% 100%;

    animation: shimmer 2s ease-in-out infinite;

  }

  @keyframes shimmer{ 0%{background-position:0% 50%;} 50%{background-position:100% 50%;} 100%{background-position:0% 50%;} }

  .progress-row{ display:flex; justify-content:space-between; font-size: 10px; color: var(--ink-dim); font-weight:600; }



  /\* Vault list \*/

  .list-item{

    display:flex; align-items:center; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--hairline);

    transition: transform 0.15s ease, background 0.15s ease;

  }

  .list-item:active{ transform: scale(0.98) translateX(2px); background: #F7F7F8; }

  .list-thumb{ width: 42px; height:42px; border-radius: 12px; flex-shrink:0; background-size:cover; }

  .list-body{ flex:1; }

  .list-name{ font-size: 12.5px; font-weight:700; }

  .list-meta-row{ display:flex; gap: 10px; margin-top:4px; }

  .list-meta{ display:flex; align-items:center; gap:3px; font-size: 9.5px; color: var(--ink-dim); }

  .list-status{

    font-family:'IBM Plex Mono', monospace; font-size: 8.5px; letter-spacing:0.5px; color: var(--ink-dim);

    background:#F2F2F3; padding: 4px 9px; border-radius: 20px;

    position:relative; overflow:hidden;

  }

  .list-status::before{

    content:''; position:absolute; left:5px; top:50%; transform: translateY(-50%);

    width:4px; height:4px; border-radius:50%; background:#C9A056;

    animation: dotPulse 1.6s ease-in-out infinite;

  }

  .list-status{ padding-left: 16px; }

  @keyframes dotPulse{ 0%,100%{ opacity:0.3; } 50%{ opacity:1; } }

\</style>

\</head>

\<body>



\<div class="stage">

\<div class="frame">

  \<div class="scroll">

    \<div class="topbar reveal" style="animation-delay:0.02s;">

      \<div class="icon-circle">\<svg class="icon" width="14" height="14" viewBox="0 0 24 24">\<path d="M4 7h16M4 12h16M4 17h16"/>\</svg>\</div>

      \<div class="icon-circle">\<svg class="icon" width="13" height="13" viewBox="0 0 24 24">\<circle cx="12" cy="12" r="3"/>\<path d="M12 3v2.2 M12 18.8V21 M4.9 4.9l1.6 1.6 M17.5 17.5l1.6 1.6 M3 12h2.2 M18.8 12H21 M4.9 19.1l1.6-1.6 M17.5 6.5l1.6-1.6"/>\</svg>\</div>

    \</div>



    \<div class="profile reveal" style="animation-delay:0.08s;">

      \<div class="avatar">\<div class="avatar-mark">\</div>\</div>

      \<div class="p-name">TrimAURA\</div>

      \<div class="p-sub">Upload once. Create endlessly.\</div>

    \</div>



    \<div class="stats-row reveal" style="animation-delay:0.14s;">

      \<div class="stat">\<div class="stat-num" data-count="1204">0\</div>\<div class="stat-label">Clips made\</div>\</div>

      \<div class="stat-sep">\</div>

      \<div class="stat">\<div class="stat-num" data-count="68" data-suffix="%">0%\</div>\<div class="stat-label">Watch‑through\</div>\</div>

      \<div class="stat-sep">\</div>

      \<div class="stat">\<div class="stat-num" data-count="10" data-suffix="K">0K\</div>\<div class="stat-label">Reached\</div>\</div>

    \</div>



    \<div class="section-label reveal" style="animation-delay:0.18s;">New short\</div>

    \<div class="card url-field reveal" style="animation-delay:0.2s;">Google Drive URL\</div>

    \<div class="divider-or reveal" style="animation-delay:0.22s;">OR\</div>

    \<div class="card upload-card reveal" style="animation-delay:0.24s;">

      \<div class="upload-icon">\<svg class="icon" width="15" height="15" viewBox="0 0 24 24">\<path d="M12 16V6 M8 10l4-4 4 4"/>\<path d="M5 18h14"/>\</svg>\</div>

      \<div class="upload-filename">1000263233.mp4\</div>

      \<div class="upload-check">\<svg class="icon" width="9" height="9" viewBox="0 0 24 24" style="stroke:#5EA36E">\<path d="M4 12l5 5L20 6"/>\</svg>READY TO PROCESS\</div>

    \</div>



    \<div class="section-label reveal" style="animation-delay:0.28s;">Template \<span>01 / 06\</span>\</div>

    \<div class="grid">

      \<div class="thumb active reveal" style="animation-delay:0.3s; background:linear-gradient(155deg,#E7B5A0,#C97B57)">\<div class="thumb-label">Blur Pad\</div>\</div>

      \<div class="thumb reveal" style="animation-delay:0.33s; background:linear-gradient(155deg,#8FA8C9,#4E6E96)">\<div class="thumb-label">Brand Bold\</div>\</div>

      \<div class="thumb reveal" style="animation-delay:0.36s; background:linear-gradient(155deg,#B8C98F,#748C4E)">\<div class="thumb-label">Gaming Neon\</div>\</div>

      \<div class="thumb reveal" style="animation-delay:0.39s; background:linear-gradient(155deg,#D9B7E0,#9C6BA8)">\<div class="thumb-label">Minimal\</div>\</div>

      \<div class="thumb reveal" style="animation-delay:0.42s; background:linear-gradient(155deg,#E8C778,#9C7530)">\<div class="thumb-label">Cinematic\</div>\</div>

      \<div class="thumb reveal" style="animation-delay:0.45s; background:linear-gradient(155deg,#8FC9BE,#4E9688)">\<div class="thumb-label">Podcast\</div>\</div>

    \</div>



    \<div class="cta-row reveal" style="animation-delay:0.5s;">

      \<button class="cta">Generate shorts\</button>

      \<div class="settings-btn">\<svg class="icon" width="16" height="16" viewBox="0 0 24 24">\<circle cx="12" cy="12" r="3"/>\<path d="M12 3v2.2 M12 18.8V21 M4.9 4.9l1.6 1.6 M17.5 17.5l1.6 1.6 M3 12h2.2 M18.8 12H21 M4.9 19.1l1.6-1.6 M17.5 6.5l1.6-1.6"/>\</svg>\</div>

    \</div>

    \<div class="progress-track reveal" style="animation-delay:0.54s;">\<div class="progress-fill">\</div>\</div>

    \<div class="progress-row reveal" style="animation-delay:0.56s;">\<span>PENDING\</span>\<span>0%\</span>\</div>



    \<div class="section-label reveal" style="animation-delay:0.6s; margin-top:26px;">Clip vault \<span>2 pending\</span>\</div>

    \<div class="list-item reveal" style="animation-delay:0.62s;">

      \<div class="list-thumb" style="background:linear-gradient(155deg,#E7B5A0,#C97B57)">\</div>

      \<div class="list-body">

        \<div class="list-name">async-test\</div>

        \<div class="list-meta-row">

          \<div class="list-meta">\<svg class="icon" width="10" height="10" viewBox="0 0 24 24">\<circle cx="12" cy="12" r="9"/>\<path d="M12 7v5l3 2"/>\</svg>0 clips\</div>

          \<div class="list-meta">6h ago\</div>

        \</div>

      \</div>

      \<div class="list-status">PENDING\</div>

    \</div>

    \<div class="list-item reveal" style="animation-delay:0.66s;">

      \<div class="list-thumb" style="background:linear-gradient(155deg,#8FA8C9,#4E6E96)">\</div>

      \<div class="list-body">

        \<div class="list-name">modal-test-2\</div>

        \<div class="list-meta-row">

          \<div class="list-meta">\<svg class="icon" width="10" height="10" viewBox="0 0 24 24">\<circle cx="12" cy="12" r="9"/>\<path d="M12 7v5l3 2"/>\</svg>0 clips\</div>

          \<div class="list-meta">6h ago\</div>

        \</div>

      \</div>

      \<div class="list-status">PENDING\</div>

    \</div>

  \</div>

\</div>

\</div>



\<script>

  document.querySelectorAll('.stat-num\[data-count]').forEach(el => {

    const target = parseInt(el.dataset.count, 10);

    const suffix = el.dataset.suffix || '';

    const duration = 900;

    const startDelay = 300;

    const startTime = performance.now() + startDelay;

    function tick(now){

      const t = Math.min(1, Math.max(0, (now - startTime) / duration));

      const eased = 1 - Math.pow(1 - t, 3);

      const val = Math.round(target \* eased);

      el.textContent = val.toLocaleString() + suffix;

      if(t < 1) requestAnimationFrame(tick);

    }

    requestAnimationFrame(tick);

  });

\</script>



\</body>

\</html>

