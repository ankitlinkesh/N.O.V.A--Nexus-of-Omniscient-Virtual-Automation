// N.O.V.A living orb — a DOTTED particle sphere (THREE.Points). Thousands of
// glowing dots on a sphere, displaced gently by simplex noise so the orb
// breathes rather than thrashes. Greyish-white at rest; it only takes on colour
// when listening / thinking / acting / speaking. A faint additive core gives it
// body. Same controller API as before (setMode / setAudioLevel) so the rest of
// the app is untouched. Fully offline: three is vendored + importmap-resolved.
import * as THREE from "three";

// Per-state look. Motion values are deliberately small (calm, not violent).
// idle is neutral grey-white; colour appears only in the active states.
const STATES = {
  idle:      { amp: 0.040, freq: 1.4, speed: 0.14, spin: 0.020, glow: 0.85, size: 8.5,  color: [0.82, 0.86, 0.92] },
  listening: { amp: 0.070, freq: 2.0, speed: 0.45, spin: 0.055, glow: 1.20, size: 9.5,  color: [0.22, 0.95, 0.86] },
  thinking:  { amp: 0.085, freq: 1.8, speed: 0.40, spin: 0.110, glow: 1.10, size: 9.0,  color: [0.62, 0.44, 1.00] },
  acting:    { amp: 0.100, freq: 2.2, speed: 0.55, spin: 0.085, glow: 1.30, size: 10.0, color: [1.00, 0.64, 0.22] },
  speaking:  { amp: 0.070, freq: 1.6, speed: 0.48, spin: 0.055, glow: 1.25, size: 9.5,  color: [0.56, 0.76, 1.00] },
};

const SNOISE = /* glsl */ `
  vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
  vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
  vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
  vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
  float snoise(vec3 v){
    const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
    vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
    vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
    vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
    i=mod289(i);
    vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
    float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
    vec4 j=p-49.0*floor(p*ns.z*ns.z);
    vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
    vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
    vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
    vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
    vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
    vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
    vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
    p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
    vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
    return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
  }
`;

const POINTS_VERT = /* glsl */ `
  uniform float uTime, uAmp, uFreq, uSpeed, uAudio, uSize, uPixelRatio;
  varying float vGlow;
  ${SNOISE}
  void main(){
    vec3 dir = normalize(position);
    float t = uTime * uSpeed;
    float n = snoise(dir * uFreq + vec3(0.0, 0.0, t));
    n += 0.5 * snoise(dir * (uFreq * 2.0) + vec3(t * 0.5, 0.0, 0.0));
    float disp = n * uAmp + uAudio * 0.14;
    vec3 displaced = dir * (1.0 + disp);
    vGlow = 0.55 + 0.45 * n + uAudio * 0.6;
    vec4 mv = modelViewMatrix * vec4(displaced, 1.0);
    gl_PointSize = (uSize + uAudio * 5.0) * uPixelRatio / -mv.z;
    gl_Position = projectionMatrix * mv;
  }
`;

const POINTS_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3 uColor;
  uniform float uGlow;
  varying float vGlow;
  void main(){
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    if (d > 0.5) discard;
    float alpha = smoothstep(0.5, 0.05, d);   // soft round dot
    gl_FragColor = vec4(uColor * vGlow * uGlow, alpha);
  }
`;

const CORE_VERT = /* glsl */ `
  varying vec3 vN, vV;
  void main(){
    vN = normalize(normalMatrix * normal);
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vV = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;
const CORE_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3 uColor; uniform float uGlow;
  varying vec3 vN, vV;
  void main(){
    float f = clamp(dot(normalize(vN), normalize(vV)), 0.0, 1.0); // 1 center -> soft filled glow
    gl_FragColor = vec4(uColor * uGlow, f * f * 0.16);
  }
`;

function lerp(a, b, t) { return a + (b - a) * t; }

// Evenly-spaced points on a sphere (Fibonacci lattice) — clean, no clustering.
function fibonacciSphere(n) {
  const pos = new Float32Array(n * 3);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = golden * i;
    pos[i * 3] = Math.cos(th) * r;
    pos[i * 3 + 1] = y;
    pos[i * 3 + 2] = Math.sin(th) * r;
  }
  return pos;
}

export function initOrb(canvas) {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "high-performance" });
  } catch (err) {
    console.warn("[Orb] WebGL unavailable, using CSS fallback.", err);
    document.body.classList.add("orb-no-webgl");
    return { setMode() {}, setAudioLevel() {}, dispose() {} };
  }
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(pixelRatio);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 3.4);

  const group = new THREE.Group();
  scene.add(group);

  const s0 = STATES.idle;

  // Dotted shell
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(fibonacciSphere(11000), 3));
  const pUniforms = {
    uTime: { value: 0 }, uAmp: { value: s0.amp }, uFreq: { value: s0.freq },
    uSpeed: { value: s0.speed }, uAudio: { value: 0 }, uSize: { value: s0.size },
    uPixelRatio: { value: pixelRatio }, uGlow: { value: s0.glow },
    uColor: { value: new THREE.Color().fromArray(s0.color) },
  };
  const points = new THREE.Points(geo, new THREE.ShaderMaterial({
    uniforms: pUniforms, vertexShader: POINTS_VERT, fragmentShader: POINTS_FRAG,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  group.add(points);

  // Faint glowing core for body
  const cUniforms = { uColor: { value: new THREE.Color().fromArray(s0.color) }, uGlow: { value: s0.glow } };
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.86, 48, 48), new THREE.ShaderMaterial({
    uniforms: cUniforms, vertexShader: CORE_VERT, fragmentShader: CORE_FRAG,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  group.add(core);

  const cur = { ...s0 };
  const tgt = { ...s0 };
  const curCol = new THREE.Color().fromArray(s0.color);
  const tgtCol = new THREE.Color().fromArray(s0.color);
  let curSpin = s0.spin, tgtSpin = s0.spin;
  let audio = 0, audioTarget = 0;

  function resize() {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);
  resize();

  const clock = new THREE.Clock();
  function tick() {
    const dt = Math.min(clock.getDelta(), 0.05);
    const k = reduceMotion ? 1 : 1 - Math.pow(0.0001, dt);
    cur.amp = lerp(cur.amp, tgt.amp, k);
    cur.freq = lerp(cur.freq, tgt.freq, k);
    cur.speed = lerp(cur.speed, tgt.speed, k);
    cur.glow = lerp(cur.glow, tgt.glow, k);
    cur.size = lerp(cur.size, tgt.size, k);
    curSpin = lerp(curSpin, tgtSpin, k);
    curCol.lerp(tgtCol, k);
    audio = lerp(audio, audioTarget, reduceMotion ? 1 : 0.25);

    const motion = reduceMotion ? 0.15 : 1;
    pUniforms.uTime.value += dt * (reduceMotion ? 0.2 : 1);
    pUniforms.uAmp.value = cur.amp * motion;
    pUniforms.uFreq.value = cur.freq;
    pUniforms.uSpeed.value = cur.speed;
    pUniforms.uGlow.value = cur.glow;
    pUniforms.uSize.value = cur.size;
    pUniforms.uAudio.value = audio * motion;
    pUniforms.uColor.value.copy(curCol);
    cUniforms.uColor.value.copy(curCol);
    cUniforms.uGlow.value = cur.glow;

    // gentle overall breathing pulse
    const breathe = 1 + (reduceMotion ? 0 : Math.sin(pUniforms.uTime.value * 0.9) * 0.02 + audio * 0.06);
    group.scale.setScalar(breathe);
    group.rotation.y += dt * curSpin * motion;
    group.rotation.x += dt * curSpin * 0.3 * motion;

    renderer.render(scene, camera);
    raf = requestAnimationFrame(tick);
  }
  let raf = requestAnimationFrame(tick);

  return {
    setMode(state) {
      const s = STATES[state] || STATES.idle;
      tgt.amp = s.amp; tgt.freq = s.freq; tgt.speed = s.speed;
      tgt.glow = s.glow; tgt.size = s.size; tgtSpin = s.spin;
      tgtCol.fromArray(s.color);
      if (state !== "speaking" && state !== "listening") audioTarget = 0;
    },
    setAudioLevel(level) { audioTarget = Math.max(0, Math.min(1, level || 0)); },
    dispose() {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      geo.dispose(); points.material.dispose();
      core.geometry.dispose(); core.material.dispose();
      renderer.dispose();
    },
  };
}
