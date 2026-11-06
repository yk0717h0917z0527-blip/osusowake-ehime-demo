import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding='utf-8').read()

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f'NG ({n}): {old[:70]}')
    s = s.replace(old, new)

# 単体ファイルとして開けるよう、文書の骨組みを付ける（元ファイルの文字コード指定は骨組み側に移す）
CHARSET = '<meta charset="utf-8">\n'
if s.startswith(CHARSET):
    s = s[len(CHARSET):]
s = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#13A35A">
""" + s
rep('<div class="stage">', '</head>\n<body>\n<div class="stage">')
s = s.rstrip() + '\n</body>\n</html>\n'

# スマホ表示：枠なしの全画面、案内は右下ボタンから重ねて開く
rep('</style>', r"""html,body{margin:0}
img{max-width:100%}
button{-webkit-tap-highlight-color:transparent}
.guide-toggle,.guide-close{display:none}
@media (max-width:600px){
  html,body{height:100%;overflow:hidden}
  .stage{display:block;padding:0;min-height:0;height:100vh;height:100dvh}
  .phone{width:100%;max-width:none;height:100%;padding:0;border-radius:0;background:none;box-shadow:none}
  .screen{border-radius:0;border:0}
  .sbar{display:none}
  .view{background:var(--card);padding-top:env(safe-area-inset-top,0px)}
  .scroll{background:var(--bg)}
  .tabbar{padding-bottom:max(10px,env(safe-area-inset-bottom,0px))}
  .cta,.composer{padding-bottom:max(14px,env(safe-area-inset-bottom,0px))}
  input,select,textarea,.composer input,textarea.ta,input.in,select.in{font-size:16px}
  .toast{bottom:calc(96px + env(safe-area-inset-bottom,0px))}
  .guide{position:fixed;inset:0;z-index:60;width:auto;max-width:none;background:var(--stage);overflow-y:auto;
    padding:calc(16px + env(safe-area-inset-top,0px)) max(16px,env(safe-area-inset-right,0px)) calc(24px + env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px))}
  .guide:not(.open){display:none}
  /* 画面の右端に細いタブとして置き、カードや一覧の文字に重ならないようにする */
  .guide-toggle{display:flex;flex-direction:column;align-items:center;gap:4px;position:fixed;right:0;top:46%;transform:translateY(-50%);z-index:40;
    width:16px;padding:14px 0 16px;border-radius:8px 0 0 8px;background:var(--ink);color:var(--card);font-size:10px;font-weight:700;letter-spacing:.06em;line-height:1;
    box-shadow:-2px 2px 10px rgba(0,0,0,.2);opacity:.88}
  .guide-toggle span{writing-mode:vertical-rl;text-orientation:upright}
  .guide-toggle .ic{flex:none;width:12px;height:12px}
  .guide-toggle:active{opacity:1}  .guide-close{display:flex;align-self:flex-end;align-items:center;gap:4px;border:1.5px solid var(--line);background:var(--card);border-radius:999px;padding:6px 14px;font-size:13px;font-weight:700}
  .guide-close .ic{width:16px;height:16px}
}
</style>""")
rep('<div class="phone"><div class="screen" id="app"></div></div>',
    '<div class="phone"><div class="screen" id="app"></div></div>\n  <button class="guide-toggle" id="gtoggle" aria-label="デモの案内を開く"></button>')
rep("guide.innerHTML=`<div class=\"brand\">", "guide.innerHTML=`<button class=\"guide-close\" data-gclose>${ic('x')}閉じる</button><div class=\"brand\">")
rep("render();\n</script>", r"""document.getElementById('gtoggle').innerHTML=`${ic('list')}<span>デモ案内</span>`;
/* 案内の開閉（画面を選んだら閉じる）。描画で案内が作り直される前に判定するため capture で受ける */
document.addEventListener('click',e=>{
  if(e.target.closest('#gtoggle')){guide.classList.add('open');guide.scrollTop=0;return}
  if(e.target.closest('[data-gclose]')||e.target.closest('.guide [data-jump]')||e.target.closest('.guide [data-act^="mode:"]'))guide.classList.remove('open');
},true);
render();
</script>""")

open(dst, 'w', encoding='utf-8').write(s)
print('ok')
