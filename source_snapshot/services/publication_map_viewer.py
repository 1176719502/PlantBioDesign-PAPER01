"""Bounded, identity-preserving interaction shell for Publication Map SVGs."""
from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping

_VIEWER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")


def build_publication_map_viewer_html(
    svg_text: str,
    *,
    viewer_id: str,
    viewer_height: int = 520,
    labels: Mapping[str, str] | None = None,
) -> str:
    """Wrap the exact rendered SVG with zoom, pan, fit, reset and full-size controls.

    The SVG is embedded byte-for-byte. View state only changes the display
    transform and is never used to build an export artifact.
    """
    if not isinstance(svg_text, str) or "<svg" not in svg_text:
        raise ValueError("viewer requires SVG text")
    if not _VIEWER_ID.fullmatch(str(viewer_id or "")):
        raise ValueError("viewer_id must be a bounded HTML identifier")
    if isinstance(viewer_height, bool) or not isinstance(viewer_height, int) or not 360 <= viewer_height <= 760:
        raise ValueError("viewer_height must be between 360 and 760")
    copy = {
        "zoom_in": "Zoom in", "zoom_out": "Zoom out", "pan": "Pan", "fit": "Fit",
        "reset": "Reset", "fullscreen": "Full size",
        "zoom_in_aria": "Zoom in on map", "zoom_out_aria": "Zoom out on map",
        "pan_aria": "Pan map",
        "fit_aria": "Fit map to window", "reset_aria": "Reset map scale and position",
        "fullscreen_aria": "Open full-size map view", "viewer_aria": "Interactive publication map",
        "toolbar_aria": "Map view tools", "viewport_aria": "Zoomable and pannable map",
    }
    if labels:
        copy.update({str(k): str(v) for k, v in labels.items()})
    root_id = f"publication-map-viewer-{viewer_id}"
    root_js = json.dumps(root_id)
    button = lambda action, key: (
        f'<button type="button" data-action="{action}" '
        f'aria-label="{html.escape(copy[key + "_aria"], quote=True)}" '
        f'title="{html.escape(copy[key], quote=True)}">{html.escape(copy[key])}</button>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{{margin:0;background:#fff;color:#1d2920;font-family:Arial,sans-serif}}
.map-viewer{{height:{viewer_height}px;display:grid;grid-template-rows:auto minmax(0,1fr);border:1px solid #dce4dc;background:#fff}}
.map-viewer:fullscreen{{width:100vw;height:100vh;border:0}}
.map-viewer-toolbar{{display:flex;align-items:center;gap:5px;padding:6px 8px;border-bottom:1px solid #dce4dc;background:#f7f9f7}}
.map-viewer-toolbar button{{min-width:38px;height:32px;padding:0 9px;border:1px solid #c7d2c8;border-radius:4px;background:#fff;color:#1d2920;font-size:13px;font-weight:600;cursor:pointer}}
.map-viewer-toolbar button.active{{background:#e8f3eb;border-color:#237a4b;color:#1d663f}}
.map-viewer-toolbar button:focus-visible{{outline:2px solid #237a4b;outline-offset:1px}}
.map-viewer-scale{{margin-left:auto;color:#566579;font-size:13px;font-variant-numeric:tabular-nums}}
.map-viewer-viewport{{position:relative;overflow:hidden;min-height:0;touch-action:none;cursor:grab;background:#fff}}
.map-viewer-viewport.dragging{{cursor:grabbing}}
.map-viewer-stage{{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform}}
.map-viewer-stage svg{{display:block;max-width:none!important;height:auto!important;overflow:visible;user-select:none}}
</style></head><body>
<section id="{root_id}" class="map-viewer" aria-label="{html.escape(copy['viewer_aria'], quote=True)}">
<div class="map-viewer-toolbar" role="toolbar" aria-label="{html.escape(copy['toolbar_aria'], quote=True)}">
{button('zoom-out','zoom_out')}{button('zoom-in','zoom_in')}{button('pan','pan')}{button('fit','fit')}{button('reset','reset')}{button('fullscreen','fullscreen')}<output class="map-viewer-scale" aria-live="polite">100%</output>
</div><div class="map-viewer-viewport" tabindex="0" aria-label="{html.escape(copy['viewport_aria'], quote=True)}"><div class="map-viewer-stage">{svg_text}</div></div></section>
<script>(()=>{{
const root=document.getElementById({root_js}), viewport=root.querySelector('.map-viewer-viewport'), stage=root.querySelector('.map-viewer-stage'), svg=stage.querySelector('svg'), output=root.querySelector('.map-viewer-scale');
const MIN=.2, MAX=8, STEP=1.25; let scale=1, x=0, y=0, fitScale=1, drag=null, panEnabled=false;
const size=()=>{{const b=svg.viewBox?.baseVal;return{{w:b?.width||Number(svg.getAttribute('width'))||1,h:b?.height||Number(svg.getAttribute('height'))||1}}}};
const bounds=()=>{{const s=size();let b=null;const add=(x0,y0,w,h)=>{{if(![x0,y0,w,h].every(Number.isFinite)||w<=0||h<=0)return;const r=x0+w,d=y0+h;b=b?{{x:Math.min(b.x,x0),y:Math.min(b.y,y0),r:Math.max(b.r,r),d:Math.max(b.d,d)}}:{{x:x0,y:y0,r,d}}}};svg.querySelectorAll('[data-layout-bounds],[data-bounds]').forEach(n=>{{const a=String(n.getAttribute('data-layout-bounds')||n.getAttribute('data-bounds')).split(',').map(Number);if(a.length===4)add(a[0],a[1],a[2]-a[0],a[3]-a[1])}});svg.querySelectorAll('text,path,line,polygon,circle,rect').forEach(n=>{{try{{const q=n.getBBox();add(q.x,q.y,q.width,q.height)}}catch(_e){{}}}});return b?{{x:b.x,y:b.y,w:Math.max(1,b.r-b.x),h:Math.max(1,b.d-b.y)}}:{{x:0,y:0,w:s.w,h:s.h}}}};
const render=()=>{{stage.style.transform=`translate(${{x}}px,${{y}}px) scale(${{scale}})`;output.value=`${{Math.round(scale*100)}}%`;root.dataset.scale=scale.toFixed(4);root.dataset.offsetX=x.toFixed(2);root.dataset.offsetY=y.toFixed(2)}};
const setScale=(next,ax=viewport.clientWidth/2,ay=viewport.clientHeight/2)=>{{const bounded=Math.min(MAX,Math.max(MIN,next)),cx=(ax-x)/scale,cy=(ay-y)/scale;x=ax-cx*bounded;y=ay-cy*bounded;scale=bounded;root.dataset.mode='custom';render()}};
const fit=(readable)=>{{const b=bounds(), sx=viewport.clientWidth/(b.w*1.12), sy=viewport.clientHeight/(b.h*1.12), geometry=Math.min(sx,sy)*.96;scale=Math.min(MAX,Math.max(MIN,readable?Math.max(geometry,.65):geometry));fitScale=Math.min(MAX,Math.max(MIN,geometry));x=(viewport.clientWidth-b.w*scale)/2-b.x*scale;y=(viewport.clientHeight-b.h*scale)/2-b.y*scale;root.dataset.mode=readable?'readable':'fit';render()}};
root.querySelector('[data-action=zoom-in]').onclick=()=>setScale(scale*STEP);root.querySelector('[data-action=zoom-out]').onclick=()=>setScale(scale/STEP);root.querySelector('[data-action=pan]').onclick=()=>{{panEnabled=!panEnabled;root.querySelector('[data-action=pan]').classList.toggle('active',panEnabled);root.dataset.pan=panEnabled?'enabled':'disabled';}};root.querySelector('[data-action=fit]').onclick=()=>fit(false);root.querySelector('[data-action=reset]').onclick=()=>fit(true);root.querySelector('[data-action=fullscreen]').onclick=()=>document.fullscreenElement===root?document.exitFullscreen():root.requestFullscreen?.();
viewport.addEventListener('wheel',e=>{{if(!(e.ctrlKey||e.metaKey))return;e.preventDefault();const r=viewport.getBoundingClientRect();setScale(scale*(e.deltaY<0?STEP:1/STEP),e.clientX-r.left,e.clientY-r.top)}},{{passive:false}});
viewport.addEventListener('pointerdown',e=>{{if(!panEnabled||scale<=fitScale+.0001)return;drag={{id:e.pointerId,x:e.clientX,y:e.clientY,ox:x,oy:y}};viewport.setPointerCapture(e.pointerId);viewport.classList.add('dragging')}});viewport.addEventListener('pointermove',e=>{{if(!drag||drag.id!==e.pointerId)return;x=drag.ox+e.clientX-drag.x;y=drag.oy+e.clientY-drag.y;root.dataset.mode='custom';render()}});['pointerup','pointercancel'].forEach(t=>viewport.addEventListener(t,()=>{{drag=null;viewport.classList.remove('dragging')}}));window.addEventListener('resize',()=>fit(root.dataset.mode!=='fit'));requestAnimationFrame(()=>fit(true));
}})();</script></body></html>"""
