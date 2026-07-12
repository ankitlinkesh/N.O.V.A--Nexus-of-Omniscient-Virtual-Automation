const timeline = document.querySelector("#timeline");
const composer = document.querySelector("#composer");
const messageInput = document.querySelector("#messageInput");
const statusPill = document.querySelector("#statusPill");
const modelName = document.querySelector("#modelName");
const voiceStatus = document.querySelector("#voiceStatus");
const screenButton = document.querySelector("#screenButton");
const screenImage = document.querySelector("#screenImage");
const screenFrame = document.querySelector(".screen-frame");
const uplinkStatus = document.querySelector("#uplinkStatus");
const localTime = document.querySelector("#localTime");
const quickChips = document.querySelectorAll(".quick-chip");
const startupGreeting = document.querySelector("#startupGreeting");
const visionStatus = document.querySelector("#visionStatus");
const lastScan = document.querySelector("#lastScan");
const voiceToggle = document.querySelector("#voiceToggle");
const ttsProviderSelect = document.querySelector("#ttsProviderSelect");
const voiceSelect = document.querySelector("#voiceSelect");
const voiceMode = document.querySelector("#voiceMode");
const testVoiceButton = document.querySelector("#testVoiceButton");
const stopVoiceButton = document.querySelector("#stopVoiceButton");
const refreshVoicesButton = document.querySelector("#refreshVoicesButton");
const voiceRate = document.querySelector("#voiceRate");
const voicePitch = document.querySelector("#voicePitch");
const voiceVolume = document.querySelector("#voiceVolume");
const micButton = document.querySelector("#micButton");
const micLabel = document.querySelector("#micLabel");
const voiceTranscript = document.querySelector("#voiceTranscript");
const brainSelect = document.querySelector("#brainSelect");
const evaCoreVideo = document.querySelector("#evaCoreVideo");
const nimChip = document.querySelector("#nimChip");
const chatStateLabel = document.querySelector("#chatStateLabel");
const activeProvider = document.querySelector("#activeProvider");
const activeModel = document.querySelector("#activeModel");
const activeMode = document.querySelector("#activeMode");
const researchDbStatus = document.querySelector("#researchDbStatus");

let sessionId = localStorage.getItem("eva-session-id") || null;
const HIDE_AGENT_TRACE_BY_DEFAULT = true;
const VOICE_PROFILE_VERSION = "soft-stable-v2-browser-default";
const DEFAULT_VOICE_RATE = 1.08;
const DEFAULT_VOICE_PITCH = 1.02;
const DEFAULT_VOICE_VOLUME = 0.82;
const MIN_VOICE_RATE = 0.85;
const MAX_VOICE_RATE = 1.25;
const MIN_VOICE_PITCH = 0.9;
const MAX_VOICE_PITCH = 1.15;
const MIN_VOICE_VOLUME = 0.4;
const MAX_VOICE_VOLUME = 1.0;
const MAX_SPOKEN_CHARS = 450;
const DIAGNOSTIC_TABLE_HEADER = "provider | configured | model | status";
const WINDOWS_PATH_SPEECH_LABEL = "C:\\... paths -> local Windows path";
const storedVoiceProfileVersion = localStorage.getItem("eva-voice-profile-version");
if (storedVoiceProfileVersion !== VOICE_PROFILE_VERSION) {
  localStorage.removeItem("eva-voice-name");
  localStorage.removeItem("eva-voice-rate");
  localStorage.removeItem("eva-voice-pitch");
  localStorage.removeItem("eva.selectedVoiceName");
  localStorage.removeItem("eva.selectedVoiceLang");
  localStorage.removeItem("eva.voiceRate");
  localStorage.removeItem("eva.voicePitch");
  localStorage.removeItem("eva.voiceVolume");
  localStorage.removeItem("eva-tts-provider");
  localStorage.setItem("eva-voice-profile-version", VOICE_PROFILE_VERSION);
}
let voiceSettings = {
  enabled: true,
  rate: DEFAULT_VOICE_RATE,
  pitch: DEFAULT_VOICE_PITCH,
  volume: DEFAULT_VOICE_VOLUME,
  preferredVoices: [
    "Microsoft Aria Online",
    "Microsoft Jenny Online",
    "Microsoft Zira",
    "Google US English",
    "Samantha",
  ],
};
let availableVoices = [];
let selectedVoiceName = localStorage.getItem("eva.selectedVoiceName") || localStorage.getItem("eva-voice-name") || "";
let selectedVoiceLang = localStorage.getItem("eva.selectedVoiceLang") || "";
let ttsProvider = localStorage.getItem("eva-tts-provider") || "browser";
let speechQueue = [];
let activeUtterance = null;
let activePiperAudio = null;
let activePiperUrl = null;
let speechDebounceTimer = null;
let speechStallTimer = null;
let speechKeepAliveTimer = null;
let speechSequence = 0;
const VOICE_INTERRUPT_ON_NEW_COMMAND = true;
const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;
let recognition = null;
let isListening = false;
let pendingVoiceTranscript = "";
let voiceTranscriptSent = false;
let suppressBrainSelectEvent = false;

function brainCommand(mode) {
  if (mode === "nvidia_nim") return "use nvidia nim";
  if (mode === "gemini") return "use gemini";
  if (mode === "openrouter") return "use openrouter";
  if (mode === "groq") return "use groq";
  if (mode === "clod") return "use clod";
  if (mode === "qwen") return "use qwen";
  if (mode === "llama") return "use llama";
  if (mode === "local") return "use local brain";
  return "use auto brain";
}

function setBrainSelectValue(mode) {
  if (!brainSelect) return;
  const clean = ["auto", "nvidia_nim", "gemini", "openrouter", "groq", "clod", "qwen", "llama", "local"].includes(mode) ? mode : "auto";
  suppressBrainSelectEvent = true;
  brainSelect.value = clean;
  suppressBrainSelectEvent = false;
  localStorage.setItem("eva-brain-mode", clean);
}

function setEvaState(state) {
  document.body.dataset.evaState = state;
  if (state === "idle") statusPill.textContent = "Online";
  if (state === "listening") statusPill.textContent = "Listening";
  if (state === "thinking") statusPill.textContent = "Thinking";
  if (state === "acting") statusPill.textContent = "Acting";
  if (state === "speaking") statusPill.textContent = "Speaking";
  if (chatStateLabel) chatStateLabel.textContent = statusPill.textContent;
}

function setActivityLabel(label) {
  const text = String(label || "").trim();
  if (!text) return;
  uplinkStatus.textContent = text.replace(/\.+$/, "");
}

function scrollMessagesToBottom() {
  requestAnimationFrame(() => {
    timeline.scrollTop = timeline.scrollHeight;
  });
}

function addMessage(role, content = "") {
  const node = document.createElement("article");
  node.className = `message ${role}`;
  node.innerHTML = `<span>${role === "user" ? "You" : "EVA"}</span><p></p>`;
  node.querySelector("p").textContent = content;
  timeline.appendChild(node);
  scrollMessagesToBottom();
  return node;
}

function setMessage(node, content) {
  node.querySelector("p").textContent = content;
  scrollMessagesToBottom();
}

function updateClock() {
  if (!localTime) return;
  localTime.textContent = new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function boolFromStorage(name, fallback) {
  const value = localStorage.getItem(name);
  if (value === null) return fallback;
  return value === "true";
}

function clampNumber(value, fallback, min = 0, max = 10) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    const fallbackNumber = Number(fallback);
    if (!Number.isFinite(fallbackNumber)) return min;
    return Math.min(max, Math.max(min, fallbackNumber));
  }
  return Math.min(max, Math.max(min, parsed));
}

function normalizeTechnicalSpeech(text) {
  return String(text || "")
    .replace(/\b[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\s\r\n]*/g, "local Windows path")
    .replace(/\bOS\b/g, "Operating system")
    .replace(/\.exe\b/gi, " executable")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanSpeechText(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return "";
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    return "";
  }
  let speech = trimmed
    .replace(/```[\s\S]*?```/g, "")
    .replace(/https?:\/\/\S+/gi, "link available in chat")
    .replace(/\b(Planning|Tool|Step \d+|Searching sources|Research saved|Tavily returned|Observing desktop|Checking active window|Listing open windows|Verifying action|Focusing window|Desktop action complete|Checking browser|Opening URL|Reading page|Extracting links|Summarizing page|Saving page to research|Browser action complete|Indexing code|Searching code|Finding symbol|Building project map|Debugging error|Planning code change|Code intelligence complete)\b.*$/gim, "")
    .replace(/[`*_#>]/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/\s+[|]\s+/g, ", ")
    .replace(/\bDone\s+[—-]\s+/i, "Done, ")
    .replace(/\s+/g, " ")
    .trim();
  speech = normalizeTechnicalSpeech(speech);
  if (/\b(frontend\/|backend\/eva\/|project files|system map|agentic v2|desktop agent core|browser agent core|code intelligence|research sqlite)\b/i.test(speech)) {
    return "I put the full architecture in chat.";
  }
  if (new RegExp(`\\b(${DIAGNOSTIC_TABLE_HEADER.replace(/[|]/g, "\\|")}|Eva system health|Working:|Degraded:|Unavailable:|Suggested fixes:|LLM status:)\\b`, "i").test(speech)) {
    return "System health is in chat. I kept the technical details there.";
  }
  if (speech.length > MAX_SPOKEN_CHARS) {
    const firstSentence = speech.split(/(?<=[.!?])\s+/).slice(0, 2).join(" ");
    speech = `${firstSentence || "I found it."} I put the full details in chat.`;
  }
  if (/api[_ -]?key|authorization|bearer\s+[a-z0-9]/i.test(speech)) {
    return "";
  }
  return speech;
}

function shouldSpeakMessage(message) {
  const text = String(message || "").trim();
  if (!text) return false;
  if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) return false;
  if (/^\s*(Planning|Tool:|Step\s+\d+|Searching|Retrieving|Summarizing|Research saved|Workspace skill|Tavily returned|Observing desktop|Checking active window|Listing open windows|Verifying action|Focusing window|Desktop action complete|Checking browser|Opening URL|Reading page|Extracting links|Summarizing page|Saving page to research|Browser action complete|Indexing code|Searching code|Finding symbol|Building project map|Debugging error|Planning code change|Code intelligence complete)/i.test(text)) return false;
  if (/"(active_mode|provider_order|configured_keys|topic_count|database|soft_rpm|requests_today)"/.test(text)) return false;
  if (/\b(api[_ -]?key|authorization|bearer\s+[a-z0-9]|traceback|exception|stack trace)\b/i.test(text)) return false;
  if (text.length > 1200 && /[{[\]":]/.test(text)) return false;
  return true;
}

function voiceQualityScore(voice) {
  const haystack = `${voice.name} ${voice.voiceURI}`.toLowerCase();
  const lang = String(voice.lang || "").toLowerCase();
  let score = 0;
  if (lang.startsWith("en")) score += 20;
  if (haystack.includes("natural")) score += 80;
  if (haystack.includes("neural")) score += 70;
  if (haystack.includes("online")) score += 55;
  if (haystack.includes("microsoft aria online")) score += 140;
  if (haystack.includes("microsoft jenny online")) score += 135;
  if (haystack.includes("microsoft zira")) score += 110;
  if (haystack.includes("google us english")) score += 95;
  if (haystack.includes("jenny")) score += 70;
  if (haystack.includes("aria")) score += 68;
  if (haystack.includes("ava")) score += 62;
  if (haystack.includes("sonia")) score += 58;
  if (haystack.includes("samantha")) score += 52;
  if (haystack.includes("google") && haystack.includes("female")) score += 48;
  if (haystack.includes("zira")) score += 18;
  if (haystack.includes("desktop")) score -= 30;
  if (haystack.includes("david") || haystack.includes("mark") || haystack.includes("male")) score -= 45;
  if (voice.localService && !/natural|neural|online|google|samantha/i.test(haystack)) score -= 12;
  return score;
}

function voiceLooksPreferred(voice) {
  const haystack = `${voice.name} ${voice.voiceURI}`.toLowerCase();
  return voiceSettings.preferredVoices.some((name) => haystack.includes(name.toLowerCase()));
}

function voiceLooksFemaleEnglish(voice) {
  const name = `${voice.name} ${voice.voiceURI}`.toLowerCase();
  return /^en/i.test(voice.lang || "") && /(jenny|aria|zira|samantha|female|natural|neural|susan|hazel)/i.test(name);
}

function selectDefaultVoice() {
  if (!availableVoices.length) return null;
  const stored = availableVoices.find((voice) => voice.name === selectedVoiceName && (!selectedVoiceLang || voice.lang === selectedVoiceLang));
  if (stored) return stored;
  return [...availableVoices].sort((a, b) => {
    const preferredDelta = Number(voiceLooksPreferred(b)) - Number(voiceLooksPreferred(a));
    if (preferredDelta) return preferredDelta;
    const femaleDelta = Number(voiceLooksFemaleEnglish(b)) - Number(voiceLooksFemaleEnglish(a));
    if (femaleDelta) return femaleDelta;
    return voiceQualityScore(b) - voiceQualityScore(a);
  })[0];
}

function saveLockedVoice(voice) {
  if (!voice) return;
  selectedVoiceName = voice.name;
  selectedVoiceLang = voice.lang || "";
  localStorage.setItem("eva.selectedVoiceName", selectedVoiceName);
  localStorage.setItem("eva.selectedVoiceLang", selectedVoiceLang);
  localStorage.setItem("eva-voice-name", selectedVoiceName);
  if (voiceMode) voiceMode.textContent = selectedVoiceName;
}

function lockedVoice() {
  if (!availableVoices.length) return null;
  const saved = availableVoices.find((voice) => voice.name === selectedVoiceName && (!selectedVoiceLang || voice.lang === selectedVoiceLang));
  if (saved) return saved;
  const selected = selectDefaultVoice();
  if (selected) saveLockedVoice(selected);
  return selected;
}

function populateVoices() {
  if (!("speechSynthesis" in window) || !voiceSelect) {
    if (voiceMode) voiceMode.textContent = "Unsupported";
    if (voiceStatus) voiceStatus.textContent = "Unsupported";
    return;
  }
  availableVoices = window.speechSynthesis.getVoices();
  voiceSelect.innerHTML = "";
  for (const voice of availableVoices) {
    const option = document.createElement("option");
    option.value = `${voice.name}|||${voice.lang || ""}`;
    option.textContent = `${voice.name}${voice.lang ? ` (${voice.lang})` : ""}`;
    voiceSelect.appendChild(option);
  }
  const selected = lockedVoice();
  if (selected) {
    saveLockedVoice(selected);
    voiceSelect.value = `${selected.name}|||${selected.lang || ""}`;
    if (voiceMode) voiceMode.textContent = selected.name;
    if (voiceStatus) voiceStatus.textContent = voiceSettings.enabled ? "On" : "Off";
  } else {
    if (voiceMode) voiceMode.textContent = "No voices found";
  }
}

function setTtsProvider(provider, piperConfig = null) {
  const clean = provider === "piper" ? "piper" : "browser";
  ttsProvider = clean;
  localStorage.setItem("eva-tts-provider", clean);
  if (ttsProviderSelect) {
    ttsProviderSelect.value = clean;
    const piperOption = ttsProviderSelect.querySelector('option[value="piper"]');
    if (piperOption && piperConfig) {
      const available = Boolean(piperConfig.enabled && piperConfig.exe_exists && piperConfig.model_exists && piperConfig.runtime_ready);
      piperOption.disabled = !available;
      piperOption.textContent = available ? "Piper offline" : "Piper offline (missing files)";
      if (!available && clean === "piper") {
        ttsProvider = "browser";
        ttsProviderSelect.value = "browser";
        localStorage.setItem("eva-tts-provider", "browser");
      }
    }
  }
}

function applyVoiceSettings(config = {}) {
  const storedEnabled = localStorage.getItem("eva.voiceEnabled") ?? localStorage.getItem("eva-voice-enabled");
  const storedRate = localStorage.getItem("eva.voiceRate") ?? localStorage.getItem("eva-voice-rate");
  const storedPitch = localStorage.getItem("eva.voicePitch") ?? localStorage.getItem("eva-voice-pitch");
  const storedVolume = localStorage.getItem("eva.voiceVolume");
  voiceSettings = {
    enabled: storedEnabled === null ? Boolean(config.enabled ?? true) : storedEnabled === "true",
    rate: clampNumber(storedRate, config.rate ?? DEFAULT_VOICE_RATE, MIN_VOICE_RATE, MAX_VOICE_RATE),
    pitch: clampNumber(storedPitch, config.pitch ?? DEFAULT_VOICE_PITCH, MIN_VOICE_PITCH, MAX_VOICE_PITCH),
    volume: clampNumber(storedVolume, config.volume ?? DEFAULT_VOICE_VOLUME, MIN_VOICE_VOLUME, MAX_VOICE_VOLUME),
    preferredVoices: Array.isArray(config.preferred_voices) && config.preferred_voices.length
      ? config.preferred_voices
      : voiceSettings.preferredVoices,
  };
  if (voiceToggle) voiceToggle.checked = voiceSettings.enabled;
  if (voiceRate) voiceRate.value = voiceSettings.rate;
  if (voicePitch) voicePitch.value = voiceSettings.pitch;
  if (voiceVolume) voiceVolume.value = voiceSettings.volume;
  if (voiceStatus) voiceStatus.textContent = voiceSettings.enabled ? "On" : "Off";
  // Browser speech starts fastest and uses the locked soft female voice; Piper stays opt-in.
  setTtsProvider(localStorage.getItem("eva-tts-provider") || "browser", config.piper || null);
  populateVoices();
}

function speakEva(text, {force = false} = {}) {
  if (!force && !voiceSettings.enabled) return;
  if (!force && !shouldSpeakMessage(text)) {
    console.debug("[EvaVoice] speech_skip_activity");
    return;
  }
  const speech = cleanSpeechText(text);
  if (!speech) return;
  speechQueue = [{text: speech, force, id: ++speechSequence}];
  cancelActiveSpeech("new_final_response", false);
  window.clearTimeout(speechDebounceTimer);
  speechDebounceTimer = window.setTimeout(processSpeechQueue, 70);
}

function processSpeechQueue() {
  if (!speechQueue.length || activeUtterance || activePiperAudio) return;
  const item = speechQueue.shift();
  if (!item || !item.text) return;
  if (ttsProvider === "piper") {
    speakWithPiper(item.text, item.id).catch((error) => {
      console.warn("[EvaVoice] Piper failed, falling back to browser voice.", error);
      speakWithBrowser(item.text, item.id, 0);
    });
    return;
  }
  speakWithBrowser(item.text, item.id, 0);
}

function speakWithBrowser(speech, speechId = speechSequence, retryCount = 0) {
  if (!("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance(speech);
  const selected = lockedVoice();
  let started = false;
  if (selected) utterance.voice = selected;
  utterance.rate = clampNumber(voiceSettings.rate, DEFAULT_VOICE_RATE, MIN_VOICE_RATE, MAX_VOICE_RATE);
  utterance.pitch = clampNumber(voiceSettings.pitch, DEFAULT_VOICE_PITCH, MIN_VOICE_PITCH, MAX_VOICE_PITCH);
  utterance.volume = clampNumber(voiceSettings.volume, DEFAULT_VOICE_VOLUME, MIN_VOICE_VOLUME, MAX_VOICE_VOLUME);
  utterance.onstart = () => {
    if (activeUtterance !== utterance) return;
    started = true;
    window.clearTimeout(speechStallTimer);
    window.clearInterval(speechKeepAliveTimer);
    speechKeepAliveTimer = window.setInterval(() => {
      if (activeUtterance !== utterance) {
        window.clearInterval(speechKeepAliveTimer);
        return;
      }
      if (window.speechSynthesis.paused) {
        window.speechSynthesis.resume();
      }
    }, 5000);
    console.debug("[EvaVoice] speech_start");
    setEvaState("speaking");
  };
  utterance.onend = () => {
    if (activeUtterance !== utterance) return;
    window.clearTimeout(speechStallTimer);
    window.clearInterval(speechKeepAliveTimer);
    activeUtterance = null;
    console.debug("[EvaVoice] speech_end");
    setEvaState("idle");
    processSpeechQueue();
  };
  utterance.onerror = (event) => {
    if (activeUtterance !== utterance) return;
    window.clearTimeout(speechStallTimer);
    window.clearInterval(speechKeepAliveTimer);
    activeUtterance = null;
    const error = String(event?.error || "");
    if (!started && retryCount < 1 && !/canceled|interrupted/i.test(error)) {
      console.debug("[EvaVoice] speech_stall_retry");
      window.setTimeout(() => speakWithBrowser(speech, speechId, retryCount + 1), 120);
      return;
    }
    setEvaState("idle");
    processSpeechQueue();
  };
  activeUtterance = utterance;
  window.evaVoiceDebug = {
    selectedVoice: selected ? selected.name : "default",
    selectedVoiceLang: selected ? selected.lang : "",
    rate: utterance.rate,
    pitch: utterance.pitch,
    volume: utterance.volume,
    chars: speech.length,
    speechId,
    retryCount,
  };
  console.info("[EvaVoice]", window.evaVoiceDebug);
  speechStallTimer = window.setTimeout(() => {
    if (activeUtterance !== utterance || started) return;
    activeUtterance = null;
    window.speechSynthesis.cancel();
    if (retryCount < 1) {
      console.debug("[EvaVoice] speech_stall_retry");
      speakWithBrowser(speech, speechId, retryCount + 1);
    } else {
      setEvaState("idle");
      processSpeechQueue();
    }
  }, 1400);
  window.speechSynthesis.speak(utterance);
}

async function speakWithPiper(speech, speechId = speechSequence) {
  const response = await fetch("/api/tts/piper", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Eva-Client": "1"},
    body: JSON.stringify({text: speech}),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Piper TTS failed.");
  }
  const blob = await response.blob();
  activePiperUrl = URL.createObjectURL(blob);
  activePiperAudio = new Audio(activePiperUrl);
  activePiperAudio.volume = clampNumber(voiceSettings.volume, DEFAULT_VOICE_VOLUME, MIN_VOICE_VOLUME, MAX_VOICE_VOLUME);
  activePiperAudio.onplay = () => {
    console.debug("[EvaVoice] speech_start");
    setEvaState("speaking");
  };
  activePiperAudio.onended = () => {
    cleanupPiperAudio();
    console.debug("[EvaVoice] speech_end");
    setEvaState("idle");
    processSpeechQueue();
  };
  activePiperAudio.onerror = () => {
    cleanupPiperAudio();
    setEvaState("idle");
    processSpeechQueue();
  };
  window.evaVoiceDebug = {
    provider: "piper",
    chars: speech.length,
    volume: activePiperAudio.volume,
    speechId,
  };
  console.info("[EvaVoice]", window.evaVoiceDebug);
  await activePiperAudio.play();
}

function cleanupPiperAudio() {
  if (activePiperAudio) {
    activePiperAudio.pause();
    activePiperAudio.currentTime = 0;
    activePiperAudio = null;
  }
  if (activePiperUrl) {
    URL.revokeObjectURL(activePiperUrl);
    activePiperUrl = null;
  }
}

function cancelActiveSpeech(reason = "program", resetState = true) {
  window.clearTimeout(speechDebounceTimer);
  window.clearTimeout(speechStallTimer);
  window.clearInterval(speechKeepAliveTimer);
  activeUtterance = null;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  cleanupPiperAudio();
  if (reason === "user") console.debug("[EvaVoice] speech_cancel_user");
  if (resetState) {
    setEvaState("idle");
  }
}

function stopAllSpeech(resetState = true) {
  speechQueue = [];
  cancelActiveSpeech("user", resetState);
}

function updateMicUi() {
  if (!micButton) return;
  micButton.classList.toggle("listening", isListening);
  micButton.disabled = !SpeechRecognitionCtor;
  if (micLabel) {
    micLabel.textContent = SpeechRecognitionCtor ? (isListening ? "Listening" : "Mic") : "No mic";
  }
}

function setTranscriptPreview(text, tone = "muted") {
  if (!voiceTranscript) return;
  voiceTranscript.dataset.tone = tone;
  voiceTranscript.textContent = text || "";
}

function sendVoiceTranscript(text) {
  const command = String(text || "").trim();
  if (!command || voiceTranscriptSent) return;
  voiceTranscriptSent = true;
  if (messageInput) messageInput.value = "";
  setTranscriptPreview(`Heard: ${command}`, "active");
  submitCommand(command);
}

function stopListening() {
  if (!recognition || !isListening) return;
  try {
    recognition.stop();
  } catch {
    isListening = false;
    updateMicUi();
  }
}

function startListening() {
  if (!SpeechRecognitionCtor || !micButton) {
    setTranscriptPreview("Speech recognition is not available in this browser.", "error");
    return;
  }
  if (!recognition) initSpeechRecognition();
  if (!recognition || isListening) return;
  pendingVoiceTranscript = "";
  voiceTranscriptSent = false;
  cancelActiveSpeech("mic_start", false);
  setTranscriptPreview("Listening... say the command.", "active");
  try {
    recognition.start();
  } catch {
    setTranscriptPreview("Mic is already warming up. Try again in a second.", "error");
  }
}

function initSpeechRecognition() {
  if (!SpeechRecognitionCtor) {
    updateMicUi();
    setTranscriptPreview("Voice commands need a browser with SpeechRecognition support.", "muted");
    return;
  }
  recognition = new SpeechRecognitionCtor();
  recognition.lang = "en-US";
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    isListening = true;
    setEvaState("listening");
    updateMicUi();
  };
  recognition.onresult = (event) => {
    let interim = "";
    let finalText = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0]?.transcript || "";
      if (event.results[index].isFinal) finalText += transcript;
      else interim += transcript;
    }
    const heard = (finalText || interim || pendingVoiceTranscript).trim();
    if (heard) {
      pendingVoiceTranscript = heard;
      if (messageInput) messageInput.value = heard;
      setTranscriptPreview(`Heard: ${heard}`, event.results[event.results.length - 1]?.isFinal ? "active" : "muted");
    }
    if (finalText.trim()) {
      sendVoiceTranscript(finalText.trim());
    }
  };
  recognition.onerror = (event) => {
    const label = event.error === "not-allowed" ? "Mic permission is blocked." : `Mic issue: ${event.error || "unknown"}.`;
    setTranscriptPreview(label, "error");
  };
  recognition.onend = () => {
    isListening = false;
    updateMicUi();
    if (!voiceTranscriptSent && pendingVoiceTranscript.trim()) {
      sendVoiceTranscript(pendingVoiceTranscript);
      return;
    }
    if (!voiceTranscriptSent && statusPill.textContent === "Listening") {
      setEvaState("idle");
      setTranscriptPreview("No speech caught. Tap mic and try again.", "muted");
    }
  };
  updateMicUi();
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    statusPill.textContent = data.ok ? "Online" : "Degraded";
    uplinkStatus.textContent = data.ok ? "Live" : "Degraded";
    modelName.textContent = data.fast_model && data.deep_model
      ? `${data.fast_model} / ${data.deep_model}`
      : data.model || "Unknown";
    setBrainSelectValue(localStorage.getItem("eva-brain-mode") || "auto");
    updateBrainReadout(localStorage.getItem("eva-brain-mode") || "auto");
    voiceStatus.textContent = data.voice_enabled ? "Enabled" : "Modular";
    if (startupGreeting && data.startup_greeting) {
      startupGreeting.textContent = data.startup_greeting;
    }
    applyVoiceSettings(data.voice || {});
    if (visionStatus) {
      const vision = data.vision || {};
      const usage = vision.usage || {};
      if (!vision.vision_enabled) {
        visionStatus.textContent = "Disabled";
      } else if (usage.blocked_until && Number(usage.blocked_until) > Math.floor(Date.now() / 1000)) {
        visionStatus.textContent = "Rate-limited";
      } else {
        visionStatus.textContent = "Ready";
      }
    }
  } catch {
    statusPill.textContent = "Offline";
    uplinkStatus.textContent = "Offline";
    modelName.textContent = "Unavailable";
    if (startupGreeting) {
      startupGreeting.textContent = "Yo Ankit, backend looks offline right now. Some controls won't work till it's back.";
    }
    if (visionStatus) visionStatus.textContent = "Disabled";
    if (nimChip) nimChip.textContent = "Fallback Ready";
  }
}

function updateBrainReadout(mode) {
  const labels = {
    auto: ["Auto", "NIM first"],
    nvidia_nim: ["NVIDIA NIM", "Nemotron / DeepSeek"],
    gemini: ["Gemini", "API brain"],
    openrouter: ["OpenRouter", "Cloud fallback"],
    groq: ["Groq", "Cloud fallback"],
    clod: ["CLōD", "Cloud fallback"],
    qwen: ["Ollama Qwen", "Local planner"],
    llama: ["Ollama Llama", "Local model"],
    local: ["Local Only", "Ollama/local fallback"],
  };
  const [provider, model] = labels[mode] || labels.auto;
  if (activeProvider) activeProvider.textContent = provider;
  if (activeModel) activeModel.textContent = model;
  if (activeMode) activeMode.textContent = mode === "local" ? "Local safe fallback" : "Safe Demo + Catalog";
  if (nimChip) nimChip.textContent = mode === "nvidia_nim" || mode === "auto" ? "Provider Ready" : "Fallback Ready";
}

async function sendStreamingChat(message) {
  const evaNode = addMessage("eva", "");
  evaNode.classList.add("streaming");
  let reply = "";

  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Eva-Client": "1"},
    body: JSON.stringify({message, session_id: sessionId}),
  });

  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Eva stream failed");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "meta") {
        if (event.session_id) {
          sessionId = event.session_id;
          localStorage.setItem("eva-session-id", sessionId);
        }
        if (event.source === "fast-command" || event.source === "fast-casual") {
          statusPill.textContent = "Online";
          document.body.dataset.evaState = "idle";
        } else {
          setEvaState("thinking");
        }
        uplinkStatus.textContent = "Linked";
      }
      if (event.type === "planning") {
        setEvaState("thinking");
        setActivityLabel(event.message || "Planning...");
      }
      if (event.type === "agent_task") {
        setEvaState("acting");
        if (!HIDE_AGENT_TRACE_BY_DEFAULT) addMessage("eva", event.message || "Agent task started");
        else setActivityLabel(event.message || "Agent task started");
      }
      if (event.type === "agent_plan") {
        setEvaState("thinking");
        const plan = Array.isArray(event.plan) ? event.plan.slice(0, 5).map((item, index) => `${index + 1}. ${item}`).join("\n") : "";
        if (!HIDE_AGENT_TRACE_BY_DEFAULT) addMessage("eva", plan ? `Plan ready:\n${plan}` : "Plan ready.");
        else setActivityLabel("Plan ready");
      }
      if (event.type === "agent_step") {
        setEvaState("acting");
        if (!HIDE_AGENT_TRACE_BY_DEFAULT) addMessage("eva", event.message || `Step ${event.step}: working`);
        else setActivityLabel(event.message || "Agent step running");
      }
      if (event.type === "agent_observation") {
        if (!HIDE_AGENT_TRACE_BY_DEFAULT) addMessage("eva", event.message || `Step ${event.step}: observed result`);
        else setActivityLabel("Observation recorded");
      }
      if (event.type === "agent_reflection") {
        if (!HIDE_AGENT_TRACE_BY_DEFAULT) addMessage("eva", event.message || `Step ${event.step}: reflected on progress`);
        else setActivityLabel("Reflection complete");
      }
      if (event.type === "tool") {
        setEvaState("acting");
        let label = `Tool: ${event.tool}`;
        if (event.tool === "web_search") label = "Searching web with Tavily...";
        if (event.tool === "capture_screen") label = "Capturing screen...";
        if (event.tool === "analyze_screen") label = "Analyzing screen with Gemini Vision...";
        if (event.tool === "workspace_list_files" || event.tool === "workspace_status") label = "Scanning workspace...";
        if (event.tool === "workspace_read_file") label = "Reading file...";
        if (event.tool === "workspace_search") label = "Searching project...";
        if (event.tool === "workspace_project_summary" || event.tool === "workspace_summarize_file") label = "Summarizing project...";
        if (event.tool === "research_start_topic") label = "Starting research topic...";
        if (event.tool === "research_web") label = "Searching sources...";
        if (event.tool === "research_save_note") label = "Saving research knowledge...";
        if (event.tool === "research_recall") label = "Retrieving local knowledge...";
        if (event.tool === "research_summary") label = "Summarizing research...";
        if (event.tool === "desktop_observe") label = "Observing desktop...";
        if (event.tool === "window_active") label = "Checking active window...";
        if (event.tool === "window_list") label = "Listing open windows...";
        if (event.tool === "verify_last_action") label = "Verifying action...";
        if (event.tool === "window_focus") label = "Focusing window...";
        if (event.tool === "window_minimize" || event.tool === "window_maximize" || event.tool === "window_close_safe") label = "Desktop action complete";
        if (event.tool === "browser_status" || event.tool === "browser_current_page" || event.tool === "browser_observe") label = "Checking browser...";
        if (event.tool === "browser_open_url" || event.tool === "browser_search") label = "Opening URL...";
        if (event.tool === "chrome_open_web_app") label = "Opening web app...";
        if (event.tool === "chrome_search_site") label = "Searching site...";
        if (event.tool === "chrome_copy_current_url") label = "Verifying page...";
        if (event.tool === "browser_open_result_and_verify") label = "Verifying page...";
        if (event.tool === "chrome_new_tab" || event.tool === "chrome_close_tab" || event.tool === "chrome_reload" || event.tool === "chrome_back" || event.tool === "chrome_forward" || event.tool === "chrome_focus_address_bar") label = "Browser action complete";
        if (event.tool === "browser_summarize_page") label = "Reading page...";
        if (event.tool === "browser_extract_links") label = "Extracting links...";
        if (event.tool === "browser_save_page_to_research") label = "Saving page to research...";
        if (event.tool === "code_reindex") label = "Indexing code...";
        if (event.tool === "code_search") label = "Searching code...";
        if (event.tool === "code_find_symbol") label = "Finding symbol...";
        if (event.tool === "code_project_map" || event.tool === "code_status") label = "Building project map...";
        if (event.tool === "code_debug_traceback") label = "Debugging error...";
        if (event.tool === "code_plan_change") label = "Planning code change...";
        if (event.tool === "code_explain_feature") label = "Searching code...";
        setActivityLabel(label);
      }
      if (event.type === "tool_result") {
        if (event.tool === "web_search" && event.result && typeof event.result === "object") {
          const count = Array.isArray(event.result.results) ? event.result.results.length : 0;
          if (event.result.ok && event.result.provider === "tavily") {
            setActivityLabel(`Tavily returned ${count} result${count === 1 ? "" : "s"}.`);
          } else if (event.result.fallback === "browser") {
            setActivityLabel("Tavily failed, opening browser search instead.");
          } else {
            setActivityLabel(event.ok ? "Tool complete." : "Tool failed safely.");
          }
        } else if (event.tool === "analyze_screen") {
          const result = event.result && typeof event.result === "object" ? event.result : {};
          if (visionStatus) {
            visionStatus.textContent = result.rate_limited ? "Rate-limited" : (event.ok ? "Ready" : "Disabled");
          }
          if (lastScan) {
            lastScan.textContent = new Intl.DateTimeFormat([], {hour: "2-digit", minute: "2-digit"}).format(new Date());
          }
          setActivityLabel(event.ok ? "Screen analysis complete" : "Screen analysis temporarily unavailable.");
        } else if (event.tool === "capture_screen") {
          setActivityLabel(event.ok ? "Screen captured." : "Screen capture failed.");
        } else if (event.tool && event.tool.startsWith("workspace_")) {
          setActivityLabel(event.ok ? "Workspace skill complete." : "Workspace skill refused safely.");
        } else if (event.tool && event.tool.startsWith("research_")) {
          setActivityLabel(event.ok ? "Research saved." : "Research skill failed safely.");
        } else if (event.tool === "desktop_observe" || event.tool === "verify_last_action" || (event.tool && event.tool.startsWith("window_"))) {
          setActivityLabel(event.ok ? "Desktop action complete." : "Desktop action failed safely.");
        } else if (event.tool && event.tool.startsWith("browser_")) {
          setActivityLabel(event.ok ? "Browser action complete." : "Browser action failed safely.");
        } else if (event.tool && event.tool.startsWith("code_")) {
          setActivityLabel(event.ok ? "Code intelligence complete." : "Code intelligence refused safely.");
        } else {
          setActivityLabel(event.ok ? "Tool complete." : "Tool failed safely.");
        }
      }
      if (event.type === "confirmation_required") {
        statusPill.textContent = "Confirm";
        uplinkStatus.textContent = "Waiting";
      }
      if (event.type === "token") {
        reply += event.text;
        setMessage(evaNode, reply);
      }
      if (event.type === "error") {
        reply = event.message;
        setMessage(evaNode, reply);
        statusPill.textContent = "Thinking";
        uplinkStatus.textContent = "Issue";
      }
      if (event.type === "done") {
        const finalDisplayedReply = event.reply || reply;
        reply = finalDisplayedReply;
        setMessage(evaNode, finalDisplayedReply);
        speakEva(finalDisplayedReply);
      }
    }
  }

  evaNode.classList.remove("streaming");
  if (statusPill.textContent !== "Speaking") statusPill.textContent = "Done";
  uplinkStatus.textContent = "Live";
  setTimeout(() => {
    if (statusPill.textContent === "Done") {
      statusPill.textContent = "Online";
    }
  }, 900);
}

async function submitCommand(message) {
  if (!message) return;
  if (VOICE_INTERRUPT_ON_NEW_COMMAND) {
    speechQueue = [];
    cancelActiveSpeech("new_command", true);
  }
  addMessage("user", message);
  setEvaState("thinking");
  uplinkStatus.textContent = "Routing";

  try {
    await sendStreamingChat(message);
  } catch (error) {
    addMessage("eva", `I hit a local error: ${error.message}`);
    statusPill.textContent = "Error";
    uplinkStatus.textContent = "Issue";
  }
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  messageInput.value = "";
  messageInput.focus();
  await submitCommand(message);
});

brainSelect?.addEventListener("change", async () => {
  if (suppressBrainSelectEvent) return;
  const mode = brainSelect.value || "auto";
  setBrainSelectValue(mode);
  updateBrainReadout(mode);
  await submitCommand(brainCommand(mode));
});

quickChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const prompt = chip.dataset.prompt || chip.textContent.trim();
    submitCommand(prompt);
  });
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  if (button.classList.contains("quick-chip")) return;
  button.addEventListener("click", () => {
    const prompt = button.dataset.prompt || button.textContent.trim();
    submitCommand(prompt);
  });
});

if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = populateVoices;
  populateVoices();
} else {
  applyVoiceSettings({enabled: false});
}

voiceToggle?.addEventListener("change", () => {
  voiceSettings.enabled = voiceToggle.checked;
  localStorage.setItem("eva.voiceEnabled", String(voiceSettings.enabled));
  localStorage.setItem("eva-voice-enabled", String(voiceSettings.enabled));
  if (voiceStatus) voiceStatus.textContent = voiceSettings.enabled ? "On" : "Off";
  if (!voiceSettings.enabled) stopAllSpeech();
});

ttsProviderSelect?.addEventListener("change", () => {
  setTtsProvider(ttsProviderSelect.value);
});

voiceSelect?.addEventListener("change", () => {
  const [name, lang = ""] = voiceSelect.value.split("|||");
  const chosen = availableVoices.find((voice) => voice.name === name && (!lang || voice.lang === lang));
  if (chosen) saveLockedVoice(chosen);
  else {
    selectedVoiceName = name;
    selectedVoiceLang = lang;
    localStorage.setItem("eva.selectedVoiceName", selectedVoiceName);
    localStorage.setItem("eva.selectedVoiceLang", selectedVoiceLang);
    localStorage.setItem("eva-voice-name", selectedVoiceName);
  }
  if (voiceMode) voiceMode.textContent = selectedVoiceName || "Auto";
});

voiceRate?.addEventListener("input", () => {
  voiceSettings.rate = clampNumber(voiceRate.value, DEFAULT_VOICE_RATE, MIN_VOICE_RATE, MAX_VOICE_RATE);
  localStorage.setItem("eva.voiceRate", String(voiceSettings.rate));
  localStorage.setItem("eva-voice-rate", String(voiceSettings.rate));
});

voicePitch?.addEventListener("input", () => {
  voiceSettings.pitch = clampNumber(voicePitch.value, DEFAULT_VOICE_PITCH, MIN_VOICE_PITCH, MAX_VOICE_PITCH);
  localStorage.setItem("eva.voicePitch", String(voiceSettings.pitch));
  localStorage.setItem("eva-voice-pitch", String(voiceSettings.pitch));
});

voiceVolume?.addEventListener("input", () => {
  voiceSettings.volume = clampNumber(voiceVolume.value, DEFAULT_VOICE_VOLUME, MIN_VOICE_VOLUME, MAX_VOICE_VOLUME);
  localStorage.setItem("eva.voiceVolume", String(voiceSettings.volume));
});

refreshVoicesButton?.addEventListener("click", () => {
  populateVoices();
  const voice = lockedVoice();
  const label = voice ? `${voice.name}${voice.lang ? ` (${voice.lang})` : ""}` : "No voices found";
  if (voiceMode) voiceMode.textContent = label;
});

testVoiceButton?.addEventListener("click", () => {
  speakEva("Hey Ankit, this is Eva. I’ll keep it soft and quick.", {force: true});
});

stopVoiceButton?.addEventListener("click", () => {
  stopAllSpeech();
});

micButton?.addEventListener("click", () => {
  if (isListening) {
    stopListening();
  } else {
    startListening();
  }
});

screenButton.addEventListener("click", async () => {
  screenButton.disabled = true;
  screenButton.textContent = "Analyzing...";
  try {
    await submitCommand("look at my screen and tell me what is open");
    if (lastScan) {
      lastScan.textContent = new Intl.DateTimeFormat([], {hour: "2-digit", minute: "2-digit"}).format(new Date());
    }
  } catch (error) {
    addMessage("eva", `Screen analysis failed: ${error.message}`);
  } finally {
    screenButton.disabled = false;
    screenButton.textContent = "Analyze Screen";
  }
});

if (evaCoreVideo) {
  evaCoreVideo.addEventListener("error", () => {
    document.body.classList.add("video-fallback");
  });
  const syncVideoMotion = () => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (document.hidden || reduceMotion) {
      evaCoreVideo.pause();
    } else {
      evaCoreVideo.play().catch(() => document.body.classList.add("video-fallback"));
    }
  };
  document.addEventListener("visibilitychange", syncVideoMotion);
  window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", syncVideoMotion);
  syncVideoMotion();
}

updateClock();
setInterval(updateClock, 1000);
initSpeechRecognition();
loadHealth();
messageInput.focus();

