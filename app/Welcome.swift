import Foundation

// The welcome screen shown every time the app opens. Logo, wordmark, a time-of-day greeting.
func welcomeHTML(name: String) -> String {
    return """
    <html><head><meta charset="utf-8"><link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400&display=swap" rel="stylesheet">
    <style>
    html,body{margin:0;height:100%;background:#05060f;overflow:hidden}
    body{display:grid;place-items:center;color:#a8afcc;font:300 15px 'IBM Plex Mono',ui-monospace,Menlo,monospace;transition:opacity 1.4s ease}
    body.out .logo,body.out .word,body.out .hi,body.out .st{opacity:.0;transition:opacity 1.4s ease}
    .pool{position:absolute;inset:0;background:radial-gradient(ellipse 50% 40% at 50% 46%,rgba(46,230,255,.10),transparent 70%);animation:breathe 4s ease-in-out infinite}
    .c{position:relative;text-align:center}
    .logo{width:300px;filter:drop-shadow(0 10px 26px rgba(0,0,0,.55));animation:rise 1.6s ease both,float 6s ease-in-out 1.6s infinite}
    .word{margin-top:34px;font-weight:300;font-size:30px;letter-spacing:.55em;margin-right:-.55em;color:#eceef8;animation:fade 1.6s ease .9s both}
    .word i{font-style:normal;color:#fbbf24;letter-spacing:0}
    .hi{margin-top:26px;font-size:15px;color:#dfe5ff;animation:fade 2s ease 3.3s both}
    .st{margin-top:10px;font-size:12.5px;color:#2ee6ff;opacity:.8;animation:fade 2s ease 4.1s both}
    @keyframes rise{from{opacity:0;transform:translateY(14px) scale(.94)}to{opacity:1;transform:none}}
    @keyframes fade{from{opacity:0}to{opacity:1}}
    @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
    @keyframes breathe{0%,100%{opacity:.6}50%{opacity:1}}
    @media (prefers-reduced-motion:reduce){.logo,.pool{animation:none}.word,.hi,.st{animation:fade .4s ease both}}
    </style></head><body>
    <div class="pool"></div>
    <div class="c">
    <svg class="logo" viewBox="10 55 180 90">\(glyphBody)</svg>
    <div class="word">THALAMUS<i>.</i></div>
    <div class="hi" id="hi"></div>
    <div class="st" id="st">// waking the brain…</div>
    </div>
    <script>
    var h=new Date().getHours(),g=h<5?"Still up":h<12?"Good morning":h<18?"Good afternoon":"Good evening";
    document.getElementById('hi').textContent=g+", \(name).";
    </script></body></html>
    """
}
