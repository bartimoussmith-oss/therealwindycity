/* DOM interaction tests. Install jsdom separately; see README. Not a visual/browser permission test. */
const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const root = __dirname;
const tick = () => new Promise(resolve => setImmediate(resolve));

async function setup() {
  const dom = new JSDOM(fs.readFileSync(path.join(root, 'index.html'), 'utf8').replace(/<script[^>]*src[^>]*><\/script>/g, ''), {url:'https://atlas.example/',runScripts:'dangerously'});
  const w = dom.window;
  Object.defineProperty(w, 'isSecureContext', {value:true});
  w.requestAnimationFrame = () => 0;
  w.HTMLCanvasElement.prototype.getContext = () => ({fillRect(){},fillText(){},drawImage(){}});
  w.HTMLMediaElement.prototype.pause = function() {};
  w.HTMLMediaElement.prototype.load = function() {};
  w.HTMLMediaElement.prototype.play = function() { return Promise.resolve(); };
  w.fetch = async url => ({ok:true,json:async()=> url.includes('catalog') ? {count:1,meetings:[],agendas:[],topics:['Water'],videos:['test.mp4']} : []});
  w.URL.createObjectURL = () => 'blob:test';
  w.URL.revokeObjectURL = () => {};
  for (const f of ['app.js','lens.js']) {
    const script = w.document.createElement('script'); script.textContent = fs.readFileSync(path.join(root,f),'utf8'); w.document.body.append(script);
  }
  await tick();
  return {dom,w,$:s=>w.document.querySelector(s)};
}
function streamFixture() {
  let stopped = 0;
  let ended;
  const track = {stop(){stopped++}, addEventListener(name,fn){if(name==='ended')ended=fn}};
  const stream = {getTracks:()=>[track],getVideoTracks:()=>[track]};
  return {stream,get stopped(){return stopped},end(){ended()}};
}

test('global toggle docks the existing tiles without creating independent video players', async () => {
  const {dom,$} = await setup();
  $('#lens-toggle').click();
  assert.equal($('#floating-lens').hidden,false);
  assert.equal($('#tiles').parentElement.id,'floating-tiles');
  assert.equal(dom.window.document.querySelectorAll('video').length,1);
  assert.equal($('#tiles').querySelectorAll('canvas').length,4);
  $('#float-settings').click();
  assert.equal($('#tiles').classList.contains('compact-tiles'),false);
  $('#float-close').click();
  assert.equal($('#tiles').parentElement.id,'tiles-home');
  assert.equal($('#lens-toggle').getAttribute('aria-pressed'),'false');
  dom.window.close();
});

test('shared source starts, remains active when lens closes, and releases on stop', async () => {
  const {dom,w,$} = await setup(); const fixture=streamFixture();
  w.navigator.mediaDevices = {getDisplayMedia:async()=>fixture.stream};
  $('#share-video').click(); await tick();
  assert.equal($('#video').srcObject,fixture.stream);
  assert.equal($('#video').muted,true);
  assert.equal($('#stop-share').hidden,false);
  assert.equal($('#floating-lens').hidden,false);
  $('#float-close').click(); assert.equal(fixture.stopped,0);
  $('#stop-share').click();
  assert.equal(fixture.stopped,1);
  assert.equal($('#video').srcObject,null);
  assert.equal($('#video').controls,true);
  assert.equal($('#stop-share').hidden,true);
  dom.window.close();
});

test('ending capture clears stale pixels and shows sharing-ended status', async () => {
  const {dom,w,$} = await setup(); const fixture=streamFixture();
  w.navigator.mediaDevices = {getDisplayMedia:async()=>fixture.stream};
  $('#share-video').click(); await tick(); fixture.end();
  assert.match($('#capture-status').textContent,/Sharing ended/);
  assert.equal($('#video').srcObject,null);
  dom.window.close();
});

test('changing to archive video stops screen capture', async () => {
  const {dom,w,$} = await setup();const fixture=streamFixture();
  w.navigator.mediaDevices = {getDisplayMedia:async()=>fixture.stream};
  $('#share-video').click(); await tick();
  $('#video-select').value='test.mp4';$('#video-select').dispatchEvent(new w.Event('change'));
  assert.equal(fixture.stopped,1);
  assert.equal($('#video').srcObject,null);
  assert.match($('#video').src,/\/media\/test.mp4$/);
  assert.match($('#capture-status').textContent,/Archive/);
  dom.window.close();
});

test('cancelled source picker keeps existing capture and re-enables share control', async () => {
  const {dom,w,$} = await setup();const fixture=streamFixture();
  w.navigator.mediaDevices={getDisplayMedia:async()=>fixture.stream};$('#share-video').click();await tick();
  w.navigator.mediaDevices.getDisplayMedia=async()=>{const e=new Error('cancel');e.name='NotAllowedError';throw e};
  $('#share-video').click();await tick();
  assert.equal($('#video').srcObject,fixture.stream);assert.equal(fixture.stopped,0);
  assert.equal($('#share-video').disabled,false);assert.match($('#toast').textContent,/cancelled or blocked/);
  $('#stop-share').click();dom.window.close();
});

test('pop-out uses the same tiles, and closing restores them', async () => {
  const {dom,w,$} = await setup();let pop;
  w.open=()=>{pop=new JSDOM('<html><head></head><body></body></html>',{url:'https://atlas.example/'}).window;pop.focus=()=>{};return pop};
  $('#pop-lens').click();
  assert.equal(w.lensWindowOpen,true);
  assert.equal(pop.document.querySelectorAll('canvas').length,4);
  assert.equal($('#tiles'),null);
  pop.dispatchEvent(new pop.Event('pagehide'));
  assert.equal($('#tiles').parentElement.id,'floating-tiles');
  assert.equal(w.lensWindowOpen,false);
  pop.close();dom.window.close();
});

test('blocked pop-up falls back to floating lens', async () => {
  const {dom,w,$} = await setup();w.open=()=>null;
  $('#pop-lens').click();assert.equal($('#floating-lens').hidden,false);
  assert.match($('#toast').textContent,/Pop-up blocked/);dom.window.close();
});

test('unsupported capture has actionable fallback', async () => {
  const {dom,$} = await setup();$('#share-video').click();
  assert.match($('#toast').textContent,/supported desktop browser over HTTPS/);dom.window.close();
});
